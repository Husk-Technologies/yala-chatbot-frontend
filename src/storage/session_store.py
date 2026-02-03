from __future__ import annotations

from dataclasses import dataclass
import time
import threading


@dataclass
class Session:
    state: str
    phone_number: str | None = None
    event_code: str | None = None
    event_id: str | None = None
    event_name: str | None = None
    event_location: str | None = None
    event_location_url: str | None = None
    guest_name: str | None = None
    guest_id: str | None = None
    backend_token: str | None = None
    funeral_unique_codes: list[str] | None = None

    updated_at: float = 0.0

    def touch(self) -> None:
        self.updated_at = time.time()


class SessionStore:
    def __init__(self, ttl_seconds: int) -> None:
        self._ttl_seconds = max(60, ttl_seconds)
        self._store: dict[str, tuple[Session, float]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Session | None:
        with self._lock:
            item = self._store.get(key)
            if not item:
                return None

            session, expires_at = item
            now = time.time()
            if now >= expires_at:
                self._store.pop(key, None)
                return None

            return session

    def upsert(self, key: str, session: Session) -> None:
        session.touch()
        expires_at = session.updated_at + self._ttl_seconds
        with self._lock:
            self._store[key] = (session, expires_at)

    def clear(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)
