from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Event:
    event_id: str
    name: str
    location: str | None = None
    location_url: str | None = None


@dataclass(frozen=True)
class EventLookupResult:
    status: str  # "found" | "not_found" | "closed" | "error"
    event: Event | None = None
    error: str | None = None


@dataclass(frozen=True)
class Brochure:
    media_url: str


@dataclass(frozen=True)
class BrochureResult:
    status: str  # "ready" | "missing" | "error"
    brochure: Brochure | None = None
    error: str | None = None


@dataclass(frozen=True)
class DonationIntent:
    checkout_url: str
    reference: str | None = None


@dataclass(frozen=True)
class DonationIntentResult:
    status: str  # "ready" | "unavailable" | "error"
    intent: DonationIntent | None = None
    error: str | None = None


@dataclass(frozen=True)
class SubmitResult:
    status: str  # "ok" | "unavailable" | "error"
    id: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class FuneralLocation:
    day: str | None = None
    time: str | None = None
    name: str | None = None
    link: str | None = None


@dataclass(frozen=True)
class FuneralLocationResult:
    status: str  # "ready" | "missing" | "error"
    location: FuneralLocation | None = None
    error: str | None = None


@dataclass(frozen=True)
class Guest:
    guest_id: str
    full_name: str
    phone_number: str
    funeral_unique_codes: list[str]


@dataclass(frozen=True)
class GuestAuthResult:
    status: str  # "found" | "created" | "not_found" | "error"
    guest: Guest | None = None
    token: str | None = None
    error: str | None = None


class BackendClient(Protocol):
    def get_event_by_code(self, event_code: str, token: str | None = None) -> EventLookupResult: ...

    def get_brochure(self, event_id: str, token: str | None = None) -> BrochureResult: ...

    def get_funeral_location(self, event_id: str, token: str | None = None) -> FuneralLocationResult: ...

    def submit_condolence(
        self,
        event_id: str,
        guest_id: str,
        message: str,
        token: str | None = None,
    ) -> SubmitResult: ...

    def create_donation_intent(
        self,
        event_id: str,
        guest_id: str,
        amount: float,
        token: str | None = None,
    ) -> DonationIntentResult: ...

    def check_guest_registration(self, phone_number: str) -> GuestAuthResult: ...

    def register_guest(self, full_name: str, phone_number: str) -> GuestAuthResult: ...
