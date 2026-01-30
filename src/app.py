import logging
import os
import hmac
import hashlib
from typing import Any
import time
import threading

from dotenv import load_dotenv, find_dotenv
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator

load_dotenv(find_dotenv())

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

from .backend.http_client import HttpBackendClient, HttpBackendConfig
from .config import SETTINGS
from .conversation.handlers import handle_incoming_message
from .integrations.interactive_menu import send_interactive_menu
from .integrations.meta_cloud import MetaWhatsAppCloud
from .storage.session_store import SessionStore


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

# Track recently handled Meta message IDs to avoid duplicate processing
# when Meta retries webhook deliveries.
_META_SEEN: dict[str, float] = {}
_META_SEEN_TTL_SECONDS = 24 * 60 * 60


def _meta_seen(msg_id: str) -> bool:
    now = time.time()
    # opportunistic cleanup
    expired = [k for k, exp in _META_SEEN.items() if exp <= now]
    for k in expired:
        _META_SEEN.pop(k, None)

    if not msg_id:
        return False
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


def _handle_one_meta_message(from_wa: str, incoming_text: str) -> None:
    outgoing = handle_incoming_message(
        sender_key=from_wa,
        incoming_text=incoming_text,
        store=SESSION_STORE,
        backend=BACKEND,
        settings=SETTINGS,
    )

    # Send brochure as document when a media URL is present; otherwise send text.
    if outgoing.media_url:
        logger.info("Sending document to %s via link: %s", from_wa, outgoing.media_url)
        META.send_document(
            to=from_wa,
            link=outgoing.media_url,
            caption=outgoing.text,
            filename="brochure.pdf",
        )
    else:
        META.send_text(to=from_wa, body=outgoing.text)


def _validate_twilio_request() -> bool:
    if not SETTINGS.verify_twilio_signatures:
        return True

    if not SETTINGS.twilio_auth_token:
        logger.warning("VERIFY_TWILIO_SIGNATURES=1 but TWILIO_AUTH_TOKEN is missing")
        return False

    signature = request.headers.get("X-Twilio-Signature", "")
    validator = RequestValidator(SETTINGS.twilio_auth_token)
    # Twilio validation uses the full URL and the POST params.
    return validator.validate(request.url, request.form.to_dict(flat=True), signature)


@app.get("/health")
def health() -> tuple[str, int]:
    return "ok", 200


@app.get("/debug/meta")
@app.get("/debug/meta/")
def debug_meta() -> tuple[dict[str, object], int]:
    return (
        {
            "channel": SETTINGS.channel,
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
        threading.Thread(
            target=_handle_one_meta_message,
            args=(from_wa, incoming_text),
            daemon=True,
        ).start()

    return "ok", 200


@app.post("/")
@app.post("/webhook")
def webhook() -> str:
    if SETTINGS.channel != "twilio" and not SETTINGS.enable_twilio_webhook:
        response = MessagingResponse()
        response.message(
            "This server is configured for WhatsApp Cloud API. "
            "Use /webhook/meta for Meta webhooks."
        )
        return str(response)

    if not _validate_twilio_request():
        response = MessagingResponse()
        response.message("Invalid request signature.")
        return str(response)

    incoming_text = request.form.get("Body", "")
    sender = request.form.get("From", "")
    sender_key = sender.strip() or "unknown"

    logger.info("Incoming message from %s: %s", sender_key, (incoming_text or "").strip())

    outgoing = handle_incoming_message(
        sender_key=sender_key,
        incoming_text=incoming_text,
        store=SESSION_STORE,
        backend=BACKEND,
        settings=SETTINGS,
    )

    # Optional: send an interactive WhatsApp menu via Twilio Content API.
    # This only triggers for the plain menu screen (no media) and falls back to text.
    if outgoing.interactive_menu and not outgoing.media_url:
        guest_name = outgoing.guest_name or ""
        if send_interactive_menu(to=sender_key, guest_name=guest_name, settings=SETTINGS):
            return str(MessagingResponse())

    response = MessagingResponse()
    msg = response.message(outgoing.text)
    if outgoing.media_url:
        msg.media(outgoing.media_url)
    return str(response)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
