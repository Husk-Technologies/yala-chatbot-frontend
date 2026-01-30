from __future__ import annotations






















































import json
import logging

from twilio.rest import Client

from ..config import Settings

logger = logging.getLogger(__name__)


def can_send_interactive_menu(settings: Settings) -> bool:
    if settings.interactive_menu_mode != "content":
        return False
    return bool(
        settings.twilio_account_sid
        and settings.twilio_auth_token
        and settings.twilio_whatsapp_from
        and settings.twilio_content_sid_menu
    )


def send_interactive_menu(*, to: str, guest_name: str, settings: Settings) -> bool:
    """Send an interactive menu using Twilio Content API.

    This requires a Content template configured in Twilio that includes buttons.
    """

    if not can_send_interactive_menu(settings):
        return False

    try:
        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        content_variables = json.dumps({"guest_name": guest_name})
        client.messages.create(
            from_=settings.twilio_whatsapp_from,
            to=to,
            content_sid=settings.twilio_content_sid_menu,
            content_variables=content_variables,
        )
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Failed to send interactive menu")
        return False
