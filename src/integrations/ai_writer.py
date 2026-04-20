from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any, Protocol

import requests

from ..config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AITextResult:
    status: str  # "ready" | "unavailable" | "error"
    text: str | None = None
    error: str | None = None


class AIMessageWriter(Protocol):
    def generate_message(
        self,
        *,
        event_type: str,
        event_name: str | None = None,
        guest_name: str | None = None,
        prompt: str | None = None,
    ) -> AITextResult: ...

    def enhance_message(self, *, event_type: str, draft: str) -> AITextResult: ...


class OpenAIMessageWriter:
    def __init__(self, settings: Settings) -> None:
        self._api_key = (settings.ai_api_key or "").strip()
        self._base_url = self._normalize_base_url(settings.ai_base_url)
        self._model = (settings.ai_model or "gpt-4o-mini").strip()
        self._timeout_seconds = max(3, min(60, int(settings.ai_timeout_seconds)))
        self._local = threading.local()

    @staticmethod
    def _normalize_base_url(base_url: str | None) -> str:
        # Accept either a base URL (e.g. .../v1) or a full endpoint
        # (e.g. .../chat/completions), and normalize trailing slashes.
        normalized = (base_url or "https://api.openai.com/v1").strip() or "https://api.openai.com/v1"
        return normalized.rstrip("/")

    def _chat_completions_url(self) -> str:
        if self._base_url.endswith("/chat/completions"):
            return self._base_url
        return f"{self._base_url}/chat/completions"

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _session(self) -> requests.Session:
        sess = getattr(self._local, "session", None)
        if sess is None:
            sess = requests.Session()
            self._local.session = sess
        return sess

    def _timeout(self) -> tuple[float, float]:
        connect = min(3.0, float(self._timeout_seconds))
        read = float(self._timeout_seconds)
        return (connect, read)

    def _complete(self, *, system_prompt: str, user_prompt: str, temperature: float = 0.7) -> AITextResult:
        if not self.is_configured():
            return AITextResult(status="unavailable", error="AI is not configured")

        url = self._chat_completions_url()
        payload: dict[str, Any] = {
            "model": self._model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            resp = self._session().post(url, json=payload, headers=headers, timeout=self._timeout())
        except Exception as exc:  # noqa: BLE001
            logger.exception("AI request failed")
            return AITextResult(status="error", error=str(exc))

        if resp.status_code >= 400:
            body = (resp.text or "").strip()
            logger.error("AI completion failed: %s %s", resp.status_code, body)
            return AITextResult(status="error", error=f"AI request failed ({resp.status_code})")

        try:
            data = resp.json()
        except Exception:  # noqa: BLE001
            return AITextResult(status="error", error="Invalid AI response")

        text = ""
        try:
            choices = data.get("choices") if isinstance(data, dict) else None
            first = choices[0] if isinstance(choices, list) and choices else None
            message = first.get("message") if isinstance(first, dict) else None
            text = str((message or {}).get("content") or "").strip()
        except Exception:  # noqa: BLE001
            text = ""

        if not text:
            return AITextResult(status="error", error="AI returned an empty message")
        return AITextResult(status="ready", text=text)

    @staticmethod
    def _event_style(event_type: str) -> str:
        t = (event_type or "").strip().lower()
        if t == "farewell":
            return "a respectful condolence message"
        if t == "celebrate":
            return "a warm celebration well-wish"
        if t == "connect":
            return "a professional conference question or feedback message"
        if t == "exhibit":
            return "a concise product enquiry/interest message"
        return "a warm and respectful message"

    def generate_message(
        self,
        *,
        event_type: str,
        event_name: str | None = None,
        guest_name: str | None = None,
        prompt: str | None = None,
    ) -> AITextResult:
        t = (event_type or "").strip().lower()
        if t not in {"farewell", "celebrate"}:
            return AITextResult(status="unavailable", error="AI generation is only available for this event type")

        style = "condolence" if t == "farewell" else "well-wish"
        event_text = (event_name or "this event").strip()
        sender_text = (guest_name or "a guest").strip()
        guidance = (prompt or "").strip()
        system_prompt = (
            "You write short WhatsApp-ready messages. "
            "Return plain text only, no quotes, no numbering, no markdown."
        )
        if guidance:
            user_prompt = (
                f"Generate one {style} message for {event_text} from {sender_text}. "
                f"User guidance: {guidance}. "
                "Keep it sincere, culturally neutral, and 1-2 sentences."
            )
        else:
            user_prompt = (
                f"Generate one {style} message for {event_text} from {sender_text}. "
                "Keep it sincere, culturally neutral, and 1-2 sentences."
            )
        return self._complete(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.8)

    def enhance_message(self, *, event_type: str, draft: str) -> AITextResult:
        source = (draft or "").strip()
        if not source:
            return AITextResult(status="error", error="Message text is required")

        style = self._event_style(event_type)
        system_prompt = (
            "You improve user-written messages for WhatsApp. "
            "Preserve intent, improve grammar and tone, and keep it concise. "
            "Return plain text only, no quotes, no markdown."
        )
        user_prompt = (
            f"Enhance this message into {style}. Keep it to at most 2 sentences.\n\n"
            f"Original: {source}"
        )
        return self._complete(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.5)
