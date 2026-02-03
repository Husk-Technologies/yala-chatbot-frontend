from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from typing import Any

try:
    import redis  # type: ignore
except Exception:  # noqa: BLE001
    redis = None  # type: ignore

from .session_store import Session

logger = logging.getLogger(__name__)


def create_redis_client(redis_url: str):
    if not redis_url:
        return None
    if redis is None:
        raise RuntimeError("redis package is not installed")

    client = redis.Redis.from_url(redis_url, decode_responses=True)
    return client


class RedisSessionStore:
    def __init__(
        self,
        *,
        redis_client: Any,
        ttl_seconds: int,
        key_prefix: str = "wa_bot",
    ) -> None:
        self._ttl_seconds = max(60, int(ttl_seconds))
        self._redis = redis_client
        self._prefix = (key_prefix or "wa_bot").strip() or "wa_bot"

    def _key(self, key: str) -> str:
        k = (key or "").strip() or "unknown"
        return f"{self._prefix}:session:{k}"

    def get(self, key: str) -> Session | None:
        raw = self._redis.get(self._key(key))
        if not raw:
            return None

        try:
            data = json.loads(raw)
        except Exception:  # noqa: BLE001
            logger.warning("Invalid session JSON in Redis for key=%s", key)
            return None

        if not isinstance(data, dict):
            return None

        try:
            session = Session(
                state=str(data.get("state") or ""),
                phone_number=data.get("phone_number"),
                event_code=data.get("event_code"),
                event_id=data.get("event_id"),
                event_name=data.get("event_name"),
                event_location=data.get("event_location"),
                event_location_url=data.get("event_location_url"),
                guest_name=data.get("guest_name"),
                guest_id=data.get("guest_id"),
                backend_token=data.get("backend_token"),
                funeral_unique_codes=data.get("funeral_unique_codes"),
                updated_at=float(data.get("updated_at") or 0.0),
            )
        except Exception:  # noqa: BLE001
            logger.warning("Invalid session payload in Redis for key=%s", key)
            return None

        # Preserve original semantics: expiration is handled by Redis TTL.
        return session

    def upsert(self, key: str, session: Session) -> None:
        session.touch()
        payload = asdict(session)
        self._redis.setex(self._key(key), self._ttl_seconds, json.dumps(payload))

    def clear(self, key: str) -> None:
        self._redis.delete(self._key(key))


class RedisDedupe:
    def __init__(
        self,
        *,
        redis_client: Any,
        key_prefix: str = "wa_bot",
    ) -> None:
        self._redis = redis_client
        self._prefix = (key_prefix or "wa_bot").strip() or "wa_bot"

    def _key(self, msg_id: str) -> str:
        return f"{self._prefix}:meta_seen:{msg_id}"

    def seen(self, msg_id: str, *, ttl_seconds: int) -> bool:
        mid = (msg_id or "").strip()
        if not mid:
            return False

        # SET key value NX EX <ttl>
        ok = self._redis.set(self._key(mid), str(int(time.time())), nx=True, ex=int(ttl_seconds))
        return not bool(ok)


class RedisLock:
    """Best-effort distributed lock with a TTL.

    Uses a compare-and-delete Lua script to avoid deleting someone else's lock.
    """

    _RELEASE_SCRIPT = (
        "if redis.call('get', KEYS[1]) == ARGV[1] then "
        "  return redis.call('del', KEYS[1]) "
        "else "
        "  return 0 "
        "end"
    )

    def __init__(self, *, redis_client: Any, key: str, token: str, ttl_ms: int) -> None:
        self._redis = redis_client
        self._key = key
        self._token = token
        self._ttl_ms = max(1000, int(ttl_ms))
        self.acquired = False

    def try_acquire(self) -> bool:
        ok = self._redis.set(self._key, self._token, nx=True, px=self._ttl_ms)
        self.acquired = bool(ok)
        return self.acquired

    def release(self) -> None:
        if not self.acquired:
            return
        try:
            self._redis.eval(self._RELEASE_SCRIPT, 1, self._key, self._token)
        except Exception:  # noqa: BLE001
            # If release fails, TTL will eventually expire.
            logger.exception("Failed to release redis lock")
        finally:
            self.acquired = False
