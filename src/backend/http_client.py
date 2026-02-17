from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin
import threading

import requests

from .client import (
    BackendClient,
    Brochure,
    BrochureResult,
    DonationIntent,
    DonationIntentResult,
    Event,
    EventLookupResult,
    FuneralLocation,
    FuneralLocationResult,
    Guest,
    GuestAuthResult,
    SubmitResult,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HttpBackendConfig:
    base_url: str
    timeout_seconds: int = 15
    auth_bearer_token: str = ""
    public_base_url: str = ""
    default_event_name: str = "Yala Event"
    default_event_location: str | None = None
    default_event_location_url: str | None = None


class HttpBackendClient(BackendClient):
    def __init__(self, config: HttpBackendConfig) -> None:
        # Guard against env var formatting mistakes like:
        #   BACKEND_BASE_URL=https://host.tld\n/api/
        # which otherwise becomes an invalid URL.
        self._base_url = "".join((config.base_url or "").split())
        self._timeout_seconds = max(1, int(config.timeout_seconds))
        self._auth_bearer_token = (config.auth_bearer_token or "").strip()
        self._public_base_url = (config.public_base_url or "").rstrip("/")
        self._default_event_name = config.default_event_name
        self._default_event_location = config.default_event_location
        self._default_event_location_url = config.default_event_location_url

        # Keep one requests.Session per worker thread for connection pooling
        # without sharing a Session across threads.
        self._local = threading.local()

    def _session(self) -> requests.Session:
        sess = getattr(self._local, "session", None)
        if sess is None:
            sess = requests.Session()
            self._local.session = sess
        return sess

    def _timeout(self) -> tuple[float, float]:
        # requests timeout is (connect, read)
        connect = min(3.0, float(self._timeout_seconds))
        read = float(self._timeout_seconds)
        return (connect, read)

    def _url(self, path: str) -> str:
        base = self._base_url.rstrip("/")
        p = path.lstrip("/")
        return f"{base}/{p}"

    def _headers(self, bearer_token: str | None = None) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        token = (bearer_token or "").strip() or self._auth_bearer_token
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _get_json(self, path: str, *, bearer_token: str | None = None) -> tuple[int, dict[str, Any] | None, str | None]:
        if not self._base_url:
            return 0, None, "BACKEND_BASE_URL is not configured"

        url = self._url(path)
        try:
            resp = self._session().get(url, headers=self._headers(bearer_token), timeout=self._timeout())
        except Exception as exc:  # noqa: BLE001
            logger.exception("Backend request failed: %s", url)
            return 0, None, str(exc)

        try:
            data = resp.json() if resp.content else None
        except Exception:  # noqa: BLE001
            data = None

        if 200 <= resp.status_code < 300:
            return resp.status_code, data, None

        error_msg = None
        if isinstance(data, dict):
            error_msg = str(data.get("message") or data.get("error") or "") or None
        if not error_msg:
            error_msg = f"HTTP {resp.status_code}"
        return resp.status_code, data, error_msg

    def _post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        bearer_token: str | None = None,
    ) -> tuple[int, dict[str, Any] | None, str | None]:
        if not self._base_url:
            return 0, None, "BACKEND_BASE_URL is not configured"

        url = self._url(path)
        try:
            resp = self._session().post(
                url,
                headers=self._headers(bearer_token),
                json=payload,
                timeout=self._timeout(),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Backend request failed: %s", url)
            return 0, None, str(exc)

        try:
            data = resp.json() if resp.content else None
        except Exception:  # noqa: BLE001
            data = None

        if 200 <= resp.status_code < 300:
            return resp.status_code, data, None

        error_msg = None
        if isinstance(data, dict):
            error_msg = str(data.get("message") or data.get("error") or "") or None
        if not error_msg:
            error_msg = f"HTTP {resp.status_code}"
        return resp.status_code, data, error_msg

    def _parse_guest_auth(self, data: dict[str, Any] | None, *, status: str) -> GuestAuthResult:
        if not isinstance(data, dict):
            return GuestAuthResult(status="error", error="Invalid backend response")

        guest_raw = data.get("guest")
        token = data.get("token")

        if not isinstance(guest_raw, dict):
            return GuestAuthResult(status="error", error="Missing guest in backend response")

        guest_id = (guest_raw.get("_id") or "").strip()
        full_name = (guest_raw.get("fullName") or "").strip()
        phone_number = (guest_raw.get("phoneNumber") or "").strip()
        funeral_codes_raw = guest_raw.get("funeralUniqueCode")

        funeral_codes: list[str] = []
        if isinstance(funeral_codes_raw, list):
            funeral_codes = [str(x).strip() for x in funeral_codes_raw if str(x).strip()]

        if not guest_id or not phone_number:
            return GuestAuthResult(status="error", error="Invalid guest payload")

        guest = Guest(
            guest_id=guest_id,
            full_name=full_name or phone_number,
            phone_number=phone_number,
            funeral_unique_codes=funeral_codes,
        )
        return GuestAuthResult(status=status, guest=guest, token=str(token) if token else None)

    # --- Phase 1 bot methods (some are placeholders until backend endpoints are available) ---

    def get_event_by_code(self, event_code: str, token: str | None = None) -> EventLookupResult:
        normalized = (event_code or "").strip()
        if not normalized:
            return EventLookupResult(status="not_found")

        status_code, data, error = self._get_json(f"verify-funeral-details/{normalized}", bearer_token=token)

        if status_code in {404}:
            return EventLookupResult(status="not_found")

        if error:
            # Some backends make this endpoint non-idempotent and return an error
            # on subsequent verification attempts (e.g. "event code already verified").
            # For the bot UX, that still means the code is valid.
            msg = ""
            if isinstance(data, dict):
                msg = str(data.get("message") or data.get("error") or "")
            msg_lower = (msg or error or "").lower()

            # Broad match: the backend may phrase the repeat-verification error
            # in many ways ("already verified", "already associated",
            # "previously verified", "code already", etc.).
            _repeat_keywords = ("already", "verified", "associated", "previously", "exists")
            is_repeat = any(kw in msg_lower for kw in _repeat_keywords)

            # Even if not a known repeat keyword, if the error response still
            # contains a uniqueCode or description, the event clearly exists.
            has_event_data = (
                isinstance(data, dict)
                and (data.get("uniqueCode") or data.get("description"))
            )

            if is_repeat or has_event_data:
                unique_code = str(
                    (data.get("uniqueCode") if isinstance(data, dict) else "") or normalized
                ).strip() or normalized
                description = str(data.get("description") or "").strip() if isinstance(data, dict) else ""
                display_name = description or self._default_event_name
                if not description and unique_code and unique_code.lower() not in display_name.lower():
                    display_name = f"{display_name} ({unique_code})"
                logger.info(
                    "verify-funeral-details/%s returned repeat/known error (%s); description=%r",
                    normalized, msg_lower[:80], description,
                )
                return EventLookupResult(
                    status="found",
                    event=Event(
                        event_id=unique_code,
                        name=display_name,
                        location=self._default_event_location,
                        location_url=self._default_event_location_url,
                    ),
                )

            # Some backends may return 200 with success=false.
            if isinstance(data, dict) and data.get("success") is False:
                return EventLookupResult(status="not_found")
            return EventLookupResult(status="error", error=error)

        if not isinstance(data, dict):
            return EventLookupResult(status="not_found")

        # The backend may return 200 with success=false on repeat verification
        # but still include the description field.  Extract it when available.
        if data.get("success") is not True:
            desc = str(data.get("description") or "").strip()
            uc = str(data.get("uniqueCode") or normalized).strip() or normalized
            if desc or data.get("uniqueCode"):
                display = desc or self._default_event_name
                if not desc and uc and uc.lower() not in display.lower():
                    display = f"{display} ({uc})"
                logger.info(
                    "verify-funeral-details/%s returned 200 success=false with description=%r",
                    normalized, desc,
                )
                return EventLookupResult(
                    status="found",
                    event=Event(
                        event_id=uc,
                        name=display,
                        location=self._default_event_location,
                        location_url=self._default_event_location_url,
                    ),
                )
            return EventLookupResult(status="not_found")

        unique_code = str(data.get("uniqueCode") or normalized).strip() or normalized
        description = str(data.get("description") or "").strip()
        display_name = description or self._default_event_name
        if not description and unique_code and unique_code.lower() not in display_name.lower():
            display_name = f"{display_name} ({unique_code})"

        return EventLookupResult(
            status="found",
            event=Event(
                event_id=unique_code,
                name=display_name,
                location=self._default_event_location,
                location_url=self._default_event_location_url,
            ),
        )

    def get_brochure(self, event_id: str, token: str | None = None) -> BrochureResult:
        normalized = (event_id or "").strip()
        if not normalized:
            return BrochureResult(status="missing")

        status_code, data, error = self._get_json(f"funeral-brochure/{normalized}", bearer_token=token)
        if status_code in {404}:
            return BrochureResult(status="missing")

        if error:
            if isinstance(data, dict) and data.get("success") is False:
                return BrochureResult(status="missing")
            return BrochureResult(status="error", error=error)

        if not isinstance(data, dict) or data.get("success") is not True:
            return BrochureResult(status="missing")

        brochure_url = (data.get("brochureUrl") or "").strip()
        if not brochure_url:
            return BrochureResult(status="missing")

        # Allow backends to return relative brochure URLs.
        if brochure_url.startswith("/") or brochure_url.startswith("./"):
            base_for_join = self._base_url
            if base_for_join and not base_for_join.endswith("/"):
                base_for_join = base_for_join + "/"
            brochure_url = urljoin(base_for_join, brochure_url)

        return BrochureResult(status="ready", brochure=Brochure(media_url=brochure_url))

    def get_funeral_location(self, event_id: str, token: str | None = None) -> FuneralLocationResult:
        normalized = (event_id or "").strip()
        if not normalized:
            return FuneralLocationResult(status="missing")

        status_code, data, error = self._get_json(f"funeral-location/{normalized}", bearer_token=token)
        if status_code in {404}:
            return FuneralLocationResult(status="missing")

        if error:
            if isinstance(data, dict) and data.get("success") is False:
                return FuneralLocationResult(status="missing")
            return FuneralLocationResult(status="error", error=error)

        if not isinstance(data, dict) or data.get("success") is not True:
            return FuneralLocationResult(status="missing")

        loc = data.get("location")
        if not isinstance(loc, dict):
            return FuneralLocationResult(status="missing")

        location = FuneralLocation(
            day=(loc.get("day") or None),
            time=(loc.get("time") or None),
            name=(loc.get("name") or None),
            link=(loc.get("link") or None),
        )
        return FuneralLocationResult(status="ready", location=location)

    def submit_condolence(
        self,
        event_id: str,
        guest_id: str,
        message: str,
        token: str | None = None,
    ) -> SubmitResult:
        funeral_code = (event_id or "").strip()
        guest_id_norm = (guest_id or "").strip()
        msg = (message or "").strip()
        if not funeral_code or not guest_id_norm or not msg:
            return SubmitResult(status="error", error="Missing required fields")

        status_code, data, error = self._post_json(
            "condolence-submit",
            {
                "funeralUniqueCode": funeral_code,
                "guestId": guest_id_norm,
                "message": msg,
            },
            bearer_token=token,
        )

        if error:
            return SubmitResult(status="error", error=error)

        if isinstance(data, dict) and data.get("success") is False:
            message = str(data.get("message") or data.get("error") or "").strip()
            return SubmitResult(
                status="unavailable",
                error=message or "Condolence messages are disabled for this funeral.",
            )

        if not isinstance(data, dict):
            return SubmitResult(status="error", error="Invalid backend response")

        # backend returns 201 on success (but any 2xx is handled above)
        condolence_id = None
        condolence = data.get("condolence")
        if isinstance(condolence, dict):
            condolence_id = condolence.get("_id")
        return SubmitResult(status="ok", id=str(condolence_id) if condolence_id else None)

    def create_donation_intent(
        self,
        event_id: str,
        guest_id: str,
        amount: float,
        token: str | None = None,
    ) -> DonationIntentResult:
        payload = {
            "funeralUniqueCode": event_id,
            "guestId": guest_id,
            "donationAmount": amount,
        }
        status_code, data, error = self._post_json("make-donation", payload, bearer_token=token)

        if status_code == 404:
            # Funeral does not accept donations or not found
            # The API doc says: "This event does not accept donations"
            return DonationIntentResult(status="unavailable", error=error)

        if error or not data:
            return DonationIntentResult(status="error", error=error)

        checkout_url = data.get("url")
        reference = data.get("reference")

        if not checkout_url:
            return DonationIntentResult(status="error", error="Missing checkout URL in response")

        return DonationIntentResult(
            status="ready",
            intent=DonationIntent(
                checkout_url=checkout_url,
                reference=reference,
            ),
        )

    # --- Live backend (backend.md) ---

    def check_guest_registration(self, phone_number: str) -> GuestAuthResult:
        status_code, data, error = self._post_json(
            "check-guest-registration",
            {"phoneNumber": (phone_number or "").strip()},
        )

        if status_code in {404}:
            return GuestAuthResult(status="not_found")

        if error:
            # Some backends may return 200 with success=false; treat that as not_found when possible.
            if isinstance(data, dict) and data.get("success") is False:
                return GuestAuthResult(status="not_found")
            return GuestAuthResult(status="error", error=error)

        return self._parse_guest_auth(data, status="found")

    def register_guest(self, full_name: str, phone_number: str) -> GuestAuthResult:
        status_code, data, error = self._post_json(
            "register-guest",
            {"fullName": (full_name or "").strip(), "phoneNumber": (phone_number or "").strip()},
        )

        if error:
            # Common case: already exists. Fall back to lookup.
            if status_code in {409}:
                return self.check_guest_registration(phone_number)
            return GuestAuthResult(status="error", error=error)

        # backend returns 201 on success, but allow any 2xx.
        return self._parse_guest_auth(data, status="created")
