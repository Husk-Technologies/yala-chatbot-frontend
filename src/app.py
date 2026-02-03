import logging
import os
import hmac
import hashlib
from typing import Any
import time
import threading
from concurrent.futures import ThreadPoolExecutor
import uuid

from dotenv import load_dotenv, find_dotenv
from flask import Flask, request

load_dotenv(find_dotenv())

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

from .backend.http_client import HttpBackendClient, HttpBackendConfig
from .config import SETTINGS
from .conversation.handlers import handle_incoming_message
from .integrations.meta_cloud import MetaWhatsAppCloud
from .storage.session_store import SessionStore
from .storage.redis_session_store import RedisDedupe, RedisLock, RedisSessionStore, create_redis_client

_REDIS = None
_REDIS_DEDUPE: RedisDedupe | None = None


def _init_redis() -> None:
    global _REDIS, _REDIS_DEDUPE
    if _REDIS is not None or not SETTINGS.redis_url:
        return
    try:
        client = create_redis_client(SETTINGS.redis_url)
        if client is None:
            return
        # Validate connectivity early in production if requested.
        if SETTINGS.redis_required:
            client.ping()
        _REDIS = client
        _REDIS_DEDUPE = RedisDedupe(redis_client=client, key_prefix=SETTINGS.redis_key_prefix)
        logger.info("Redis enabled for sessions/de-dupe")
    except Exception:  # noqa: BLE001
        logger.exception("Failed to initialize Redis")
        if SETTINGS.redis_required:
            raise


_init_redis()


if _REDIS is not None:
    SESSION_STORE = RedisSessionStore(
        redis_client=_REDIS,
        ttl_seconds=SETTINGS.session_ttl_seconds,
        key_prefix=SETTINGS.redis_key_prefix,
    )
else:
    SESSION_STORE = SessionStore(ttl_seconds=SETTINGS.session_ttl_seconds)
BACKEND = HttpBackendClient(
    HttpBackendConfig(
        base_url=SETTINGS.backend_base_url,
        timeout_seconds=SETTINGS.backend_timeout_seconds,
        auth_bearer_token=SETTINGS.backend_auth_bearer_token,
        public_base_url=SETTINGS.public_base_url,
        default_event_name=SETTINGS.default_event_name,
        default_event_location=SETTINGS.default_event_location,
        default_event_location_url=SETTINGS.default_event_location_url,
    )
)
META = MetaWhatsAppCloud(SETTINGS)

# Keep a small ring buffer of recent Meta webhook receipts for debugging.
_META_LAST: list[dict[str, object]] = []
_META_LAST_MAX = 25
_META_LAST_LOCK = threading.Lock()

# Track recently handled Meta message IDs to avoid duplicate processing
# when Meta retries webhook deliveries.
_META_SEEN: dict[str, float] = {}
_META_SEEN_TTL_SECONDS = 24 * 60 * 60
_META_SEEN_LOCK = threading.Lock()


# Background processing:
# - Use a bounded worker pool (instead of spawning unbounded threads per message)
# - Serialize work per sender to avoid racing the session state machine
_WORKER_THREADS = max(2, int(os.getenv("WEBHOOK_WORKER_THREADS", "16")))
_MAX_INFLIGHT = max(_WORKER_THREADS, int(os.getenv("WEBHOOK_MAX_INFLIGHT", str(_WORKER_THREADS * 8))))
_EXECUTOR: ThreadPoolExecutor | None = None
_EXECUTOR_LOCK = threading.Lock()
_INFLIGHT_SEM = threading.BoundedSemaphore(_MAX_INFLIGHT)


def _get_executor() -> ThreadPoolExecutor:
    # Lazily create the executor so pre-fork servers (e.g. gunicorn) don't
    # instantiate a thread pool in the master process.
    global _EXECUTOR
    if _EXECUTOR is not None:
        return _EXECUTOR
    with _EXECUTOR_LOCK:
        if _EXECUTOR is None:
            _EXECUTOR = ThreadPoolExecutor(max_workers=_WORKER_THREADS, thread_name_prefix="webhook")
        return _EXECUTOR

_SENDER_LOCKS: dict[str, tuple[threading.Lock, float]] = {}
_SENDER_LOCKS_LOCK = threading.Lock()
_SENDER_LOCKS_TTL_SECONDS = 60 * 60  # keep inactive sender locks for 1 hour


def _sender_lock(sender_key: str) -> threading.Lock:
    now = time.time()
    key = (sender_key or "").strip() or "unknown"
    with _SENDER_LOCKS_LOCK:
        item = _SENDER_LOCKS.get(key)
        if item is None:
            lock = threading.Lock()
            _SENDER_LOCKS[key] = (lock, now)
        else:
            lock, _ = item
            _SENDER_LOCKS[key] = (lock, now)

        # Opportunistic cleanup to prevent unbounded growth.
        if len(_SENDER_LOCKS) > 500:
            expired_keys = [k for k, (_, ts) in _SENDER_LOCKS.items() if ts <= now - _SENDER_LOCKS_TTL_SECONDS]
            for k in expired_keys:
                _SENDER_LOCKS.pop(k, None)

        return lock


def _meta_seen(msg_id: str) -> bool:
    now = time.time()
    if not msg_id:
        return False

    if _REDIS_DEDUPE is not None:
        try:
            return _REDIS_DEDUPE.seen(msg_id, ttl_seconds=_META_SEEN_TTL_SECONDS)
        except Exception:  # noqa: BLE001
            logger.exception("Redis de-dupe failed; falling back to in-memory")

    with _META_SEEN_LOCK:
        # opportunistic cleanup
        expired = [k for k, exp in _META_SEEN.items() if exp <= now]
        for k in expired:
            _META_SEEN.pop(k, None)

        if msg_id in _META_SEEN:
            return True
        _META_SEEN[msg_id] = now + _META_SEEN_TTL_SECONDS
        return False


def _debug_allowed() -> bool:
    if not SETTINGS.debug_endpoints:
        return False
    token = request.args.get("token", "")
    return bool(SETTINGS.debug_token and token == SETTINGS.debug_token)


def _verify_meta_signature(raw_body: bytes) -> bool:
    if not SETTINGS.verify_meta_signatures:
        return True
    if not SETTINGS.meta_app_secret:
        logger.warning("VERIFY_META_SIGNATURES=1 but META_APP_SECRET is missing")
        return False

    signature = request.headers.get("X-Hub-Signature-256", "")
    if not signature.startswith("sha256="):
        return False

    provided = signature.split("=", 1)[1]
    expected = hmac.new(
        SETTINGS.meta_app_secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(provided, expected)


def _extract_meta_messages(payload: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Return list of (from_wa_id, message_text, message_id) tuples."""

    out: list[tuple[str, str, str]] = []
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            for msg in value.get("messages", []) or []:
                from_wa = (msg.get("from") or "").strip()
                msg_id = (msg.get("id") or "").strip()
                if not from_wa:
                    continue

                # Text message
                if "text" in msg and isinstance(msg["text"], dict):
                    body = (msg["text"].get("body") or "").strip()
                    out.append((from_wa, body, msg_id))
                    continue

                # Interactive replies (buttons/list)
                if "interactive" in msg and isinstance(msg["interactive"], dict):
                    inter = msg["interactive"]
                    # list_reply: {id, title}
                    list_reply = inter.get("list_reply")
                    if isinstance(list_reply, dict):
                        choice = (list_reply.get("id") or list_reply.get("title") or "").strip()
                        out.append((from_wa, choice, msg_id))
                        continue
                    # button_reply: {id, title}
                    button_reply = inter.get("button_reply")
                    if isinstance(button_reply, dict):
                        choice = (button_reply.get("id") or button_reply.get("title") or "").strip()
                        out.append((from_wa, choice, msg_id))
                        continue

                # Fallback: ignore unsupported types for now

    return out


def _menu_footer_text(guest_name: str) -> str:
    # Must match the text version used by the conversation handler.
    return (
        f"Thank you, {guest_name}.\n"
        "How can we help you today?\n\n"
        "1. 📄 Download event brochure\n"
        "2. 💝 Give / Donate\n"
        "3. 🕊️ Send condolence / message\n"
        "4. 📍 Location"
    )


_MENU_MARKER = (
    "\n1. 📄 Download event brochure\n"
    "2. 💝 Give / Donate\n"
    "3. 🕊️ Send condolence / message\n"
    "4. 📍 Location"
)


def _strip_menu_footer(text: str, guest_name: str | None) -> tuple[str, bool]:
    """Remove the trailing text menu from handler output.

    Returns (stripped_text, had_menu_footer).
    """

    t = text or ""

    # Preferred path: exact footer match when we know the guest name.
    if guest_name:
        footer = _menu_footer_text(guest_name)
        if t.endswith("\n\n" + footer):
            return t[: -len("\n\n" + footer)].rstrip(), True
        if t.endswith(footer):
            return t[: -len(footer)].rstrip(), True

    # Robust fallback: strip from the start of the menu marker.
    idx = t.rfind(_MENU_MARKER)
    if idx != -1:
        return t[:idx].rstrip(), True

    return t, False


def _handle_one_meta_message(from_wa: str, incoming_text: str) -> None:
    # Ensure a single in-flight handler per sender to avoid session races.
    # - Local lock covers single-process setups
    # - Optional Redis lock reduces cross-worker races when running multiple instances
    local_lock = _sender_lock(from_wa)

    redis_lock: RedisLock | None = None
    if _REDIS is not None:
        try:
            lock_key = f"{SETTINGS.redis_key_prefix}:lock:sender:{(from_wa or '').strip() or 'unknown'}"
            redis_lock = RedisLock(
                redis_client=_REDIS,
                key=lock_key,
                token=str(uuid.uuid4()),
                ttl_ms=30_000,
            )
        except Exception:  # noqa: BLE001
            redis_lock = None

    acquired_redis = False
    if redis_lock is not None:
        # best-effort wait a little to preserve ordering
        deadline = time.time() + 3.0
        while time.time() < deadline:
            try:
                if redis_lock.try_acquire():
                    acquired_redis = True
                    break
            except Exception:  # noqa: BLE001
                logger.exception("Redis sender lock error")
                break
            time.sleep(0.05)

    if redis_lock is not None and not acquired_redis:
        logger.warning("Could not acquire redis sender lock quickly; proceeding")

    try:
        with local_lock:
            outgoing = handle_incoming_message(
                sender_key=from_wa,
                incoming_text=incoming_text,
                store=SESSION_STORE,
                backend=BACKEND,
                settings=SETTINGS,
            )

            # Pull the latest session so we can keep menu behavior consistent even when
            # `OutgoingMessage.guest_name` isn't set for non-menu replies.
            session = SESSION_STORE.get(from_wa)
            guest_name = (session.guest_name if session and session.guest_name else outgoing.guest_name)

            # If we're on Meta and this is the main menu screen, prefer sending an interactive list.
            # The row IDs are designed to flow through the existing `_normalize_choice` logic.
            if outgoing.interactive_menu and not outgoing.media_url:
                menu_body = (
                    f"Thank you, {guest_name}.\nHow can we help you today?"
                    if guest_name
                    else "How can we help you today?"
                )
                ok = META.send_list_menu(
                    to=from_wa,
                    body=menu_body,
                    button_text="Choose an option",
                    section_title="Yala Menu",
                    rows=[
                        {"id": "brochure", "title": "Download brochure", "description": "Get the event PDF"},
                        {"id": "donate", "title": "Give / Donate", "description": "Support the family"},
                        {"id": "condolence", "title": "Send condolence", "description": "Send a message"},
                        {"id": "location", "title": "Location", "description": "View venue details"},
                    ],
                )
                if ok:
                    return
                # If interactive send fails, fall back to plain text.

            # Strip any accidental trailing menu text from handler output.
            main_text, _ = _strip_menu_footer(outgoing.text, guest_name)

            # Send brochure as document when a media URL is present; otherwise send text.
            if outgoing.media_url:
                logger.info("Sending document to %s via link: %s", from_wa, outgoing.media_url)
                META.send_document(
                    to=from_wa,
                    link=outgoing.media_url,
                    caption=main_text,
                    filename="brochure.pdf",
                )
            else:
                META.send_text(to=from_wa, body=main_text)
    finally:
        if redis_lock is not None:
            try:
                redis_lock.release()
            except Exception:  # noqa: BLE001
                logger.exception("Failed to release redis sender lock")


def _process_meta_message_task(from_wa: str, incoming_text: str) -> None:
    try:
        _handle_one_meta_message(from_wa, incoming_text)
    except Exception:  # noqa: BLE001
        logger.exception("Unhandled exception while processing meta message")
    finally:
        try:
            _INFLIGHT_SEM.release()
        except ValueError:
            # Semaphore already at max; should not happen, but don't crash worker.
            pass


@app.get("/health")
def health() -> tuple[str, int]:
    return "ok", 200


@app.get("/debug/meta")
@app.get("/debug/meta/")
def debug_meta() -> tuple[dict[str, object], int]:
    return (
        {
            "meta": {
                "configured": META.is_configured(),
                "api_version": SETTINGS.meta_api_version,
                "phone_number_id_set": bool(SETTINGS.meta_phone_number_id),
                "access_token_set": bool(SETTINGS.meta_access_token),
                "verify_token_set": bool(SETTINGS.meta_webhook_verify_token),
                "app_secret_set": bool(SETTINGS.meta_app_secret),
                "verify_signatures": SETTINGS.verify_meta_signatures,
            },
        },
        200,
    )


@app.get("/debug/meta/last")
@app.get("/debug/meta/last/")
def debug_meta_last() -> tuple[dict[str, object], int]:
    if not _debug_allowed():
        return {"error": "forbidden"}, 403
    with _META_LAST_LOCK:
        return {"count": len(_META_LAST), "items": list(_META_LAST)}, 200


@app.post("/debug/meta/send")
@app.post("/debug/meta/send/")
def debug_meta_send() -> tuple[dict[str, object], int]:
    if not _debug_allowed():
        return {"error": "forbidden"}, 403
    if not META.is_configured():
        return {"error": "meta not configured"}, 400

    data = request.get_json(force=True, silent=True) or {}
    to = (data.get("to") or "").strip()
    body = (data.get("body") or "").strip() or "Test message from debug endpoint"
    if not to:
        return {"error": "missing 'to'"}, 400

    ok = META.send_text(to=to, body=body)
    return {"ok": ok}, 200 if ok else 502


@app.get("/webhook/meta")
@app.get("/webhook/meta/")
def meta_verify() -> tuple[str, int]:
    mode = request.args.get("hub.mode", "")
    token = request.args.get("hub.verify_token", "")
    challenge = request.args.get("hub.challenge", "")

    if mode == "subscribe" and token and token == SETTINGS.meta_webhook_verify_token:
        return challenge, 200
    return "forbidden", 403


@app.post("/webhook/meta")
@app.post("/webhook/meta/")
def meta_webhook() -> tuple[str, int]:
    # Cache the raw body so we can both verify signature and parse JSON.
    raw = request.get_data(cache=True) or b""
    if not _verify_meta_signature(raw):
        return "invalid signature", 403

    try:
        payload = request.get_json(force=True, silent=False) or {}
    except Exception:
        logger.exception("Invalid JSON from Meta webhook")
        return "bad request", 400

    extracted = _extract_meta_messages(payload)

    with _META_LAST_LOCK:
        _META_LAST.append(
            {
                "ts": int(time.time()),
                "messages": len(extracted),
                "has_entry": bool(payload.get("entry")),
            }
        )
        if len(_META_LAST) > _META_LAST_MAX:
            del _META_LAST[: len(_META_LAST) - _META_LAST_MAX]

    # Respond quickly to avoid webhook retries; do processing in background.
    for from_wa, incoming_text, msg_id in extracted:
        if msg_id and _meta_seen(msg_id):
            continue
        logger.info("Meta incoming from %s: %s", from_wa, (incoming_text or "").strip())
        if not _INFLIGHT_SEM.acquire(blocking=False):
            logger.warning(
                "Dropping/deferring meta message due to saturation (max_inflight=%s)",
                _MAX_INFLIGHT,
            )
            continue

        _get_executor().submit(_process_meta_message_task, from_wa, incoming_text)

    return "ok", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
