from __future__ import annotations

import logging
from typing import Any
import threading

import requests

from ..config import Settings

logger = logging.getLogger(__name__)


class MetaWhatsAppCloud:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        # One requests.Session per worker thread for connection pooling.
        self._local = threading.local()

    def _session(self) -> requests.Session:
        sess = getattr(self._local, "session", None)
        if sess is None:
            sess = requests.Session()
            self._local.session = sess
        return sess

    @staticmethod
    def _timeout(seconds: float) -> tuple[float, float]:
        connect = min(3.0, float(seconds))
        read = float(seconds)
        return (connect, read)

    def is_configured(self) -> bool:
        return bool(self._settings.meta_access_token and self._settings.meta_phone_number_id)

    def _endpoint(self, path: str) -> str:
        version = self._settings.meta_api_version or "v20.0"
        return f"https://graph.facebook.com/{version}/{path.lstrip('/')}"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._settings.meta_access_token}",
            "Content-Type": "application/json",
        }

    def send_text(self, *, to: str, body: str) -> bool:
        if not self.is_configured():
            logger.warning(
                "Meta Cloud API not configured; cannot send message (missing META_WA_ACCESS_TOKEN or META_WA_PHONE_NUMBER_ID)"
            )
            return False

        url = self._endpoint(f"{self._settings.meta_phone_number_id}/messages")
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body},
        }

        try:
            resp = self._session().post(url, headers=self._headers(), json=payload, timeout=self._timeout(10))
            if resp.status_code >= 400:
                logger.error("Meta send_text failed: %s %s", resp.status_code, resp.text)
                return False
            return True
        except Exception:  # noqa: BLE001
            logger.exception("Meta send_text exception")
            return False

    def send_document(self, *, to: str, link: str, caption: str | None = None, filename: str | None = None) -> bool:
        if not self.is_configured():
            logger.warning(
                "Meta Cloud API not configured; cannot send document (missing META_WA_ACCESS_TOKEN or META_WA_PHONE_NUMBER_ID)"
            )
            return False

        if not (link or "").startswith(("http://", "https://")):
            logger.error("Meta send_document requires a public URL link; got: %r", link)
            return False

        url = self._endpoint(f"{self._settings.meta_phone_number_id}/messages")
        doc: dict[str, Any] = {"link": link}
        if caption:
            doc["caption"] = caption
        if filename:
            doc["filename"] = filename

        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "document",
            "document": doc,
        }

        try:
            resp = self._session().post(url, headers=self._headers(), json=payload, timeout=self._timeout(20))
            if resp.status_code >= 400:
                logger.error("Meta send_document failed: %s %s", resp.status_code, resp.text)
                return False
            return True
        except Exception:  # noqa: BLE001
            logger.exception("Meta send_document exception")
            return False

    def send_list_menu(
        self,
        *,
        to: str,
        body: str,
        button_text: str,
        rows: list[dict[str, str]],
        section_title: str = "Menu",
    ) -> bool:
        """Send a WhatsApp interactive list message.

        `rows` items must include: {"id": "...", "title": "..."}
        Optional: "description".
        """

        if not self.is_configured():
            logger.warning(
                "Meta Cloud API not configured; cannot send interactive list (missing META_WA_ACCESS_TOKEN or META_WA_PHONE_NUMBER_ID)"
            )
            return False

        if not rows:
            logger.error("Meta send_list_menu requires at least one row")
            return False

        url = self._endpoint(f"{self._settings.meta_phone_number_id}/messages")
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": body},
                "action": {
                    "button": button_text,
                    "sections": [
                        {
                            "title": section_title,
                            "rows": rows,
                        }
                    ],
                },
            },
        }

        try:
            resp = self._session().post(url, headers=self._headers(), json=payload, timeout=self._timeout(20))
            if resp.status_code >= 400:
                logger.error("Meta send_list_menu failed: %s %s", resp.status_code, resp.text)
                return False
            return True
        except Exception:  # noqa: BLE001
            logger.exception("Meta send_list_menu exception")
            return False
