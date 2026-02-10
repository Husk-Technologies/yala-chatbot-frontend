from __future__ import annotations

from enum import Enum


class ConversationState(str, Enum):
    WAIT_EVENT_CODE = "wait_event_code"
    WAIT_NAME = "wait_name"
    MENU = "menu"
    WAIT_CONDOLENCE = "wait_condolence"
    WAIT_DONATION_AMOUNT = "wait_donation_amount"


def normalize_text(text: str) -> str:
    return (text or "").strip()
