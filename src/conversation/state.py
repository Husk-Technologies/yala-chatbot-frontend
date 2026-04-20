from __future__ import annotations

from enum import Enum


class ConversationState(str, Enum):
    WAIT_EVENT_CODE = "wait_event_code"
    WAIT_NAME = "wait_name"
    MENU = "menu"
    WAIT_PHOTOS_MENU = "wait_photos_menu"
    WAIT_CONDOLENCE = "wait_condolence"
    WAIT_AI_ENHANCE_INPUT = "wait_ai_enhance_input"
    WAIT_DONATION_REFERENCE = "wait_donation_reference"
    WAIT_DONATION_AMOUNT = "wait_donation_amount"


def normalize_text(text: str) -> str:
    return (text or "").strip()
