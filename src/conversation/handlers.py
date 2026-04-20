from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..backend.client import BackendClient
from ..config import Settings
from ..integrations.ai_writer import AIMessageWriter
from ..storage.session_store import Session, SessionStore
from .state import ConversationState, normalize_text


@dataclass(frozen=True)
class OutgoingMessage:
    text: str
    media_url: str | None = None
    interactive_menu: bool = False
    guest_name: str | None = None
    interactive_buttons: list[dict[str, str]] | None = None
    interactive_button_text: str | None = None
    interactive_section_title: str | None = None
    interactive_rows: list[dict[str, str]] | None = None


WELCOME_TEXT = (
    "Hello 👋\n"
    "Welcome to Yala.\n"
    "Please enter the *Event Code* on your card to continue."
)





def _is_greeting(text: str) -> bool:
    t = normalize_text(text).lower()
    return t in {"hi", "hello", "hey", "good morning", "good afternoon", "good evening"}


def _normalize_phone(sender_key: str) -> str:
    raw = (sender_key or "").strip()
    if raw.lower().startswith("whatsapp:"):
        raw = raw.split(":", 1)[1]
    raw = raw.strip()
    if raw.startswith("+"):
        raw = raw[1:]
    digits = "".join(ch for ch in raw if ch.isdigit())
    return digits


def _normalize_choice(text: str) -> str:
    t = normalize_text(text).lower()
    if not t:
        return ""

    aliases: dict[str, str] = {
        "0": "menu",
        "o": "menu",
        "menu": "menu",
        "main menu": "menu",
        "home": "menu",
        "help": "help",
        "?": "help",
        "restart": "restart",
        "reset": "restart",
        "start over": "restart",
        "back": "back",

        "1": "brochure",
        "brochure": "brochure",
        "outline": "brochure",
        "program outline": "brochure",
        "get program outline": "brochure",
        "download": "brochure",
        "pdf": "brochure",
        "program": "brochure",

        "2": "donate",
        "donate": "donate",
        "donation": "donate",
        "give": "donate",
        "donate now": "donate",

        "3": "condolence",
        "condolence": "condolence",
        "condolences": "condolence",
        "send condolence": "condolence",
        "send condolences": "condolence",
        "well wish": "condolence",
        "well wishes": "condolence",
        "well-wishes": "condolence",
        "wellwish": "condolence",
        "message": "condolence",
        "send message": "condolence",
        "send well wishes": "condolence",
        "question": "condolence",
        "feedback": "condolence",
        "send feedback": "condolence",
        "enquiry": "condolence",
        "inquiry": "condolence",
        "interest": "condolence",
        "ai generate": "ai_generate",
        "generate with ai": "ai_generate",
        "ai condolence": "ai_generate",
        "ai well wishes": "ai_generate",
        "ai enhance": "ai_enhance",
        "enhance": "ai_enhance",
        "enhance message": "ai_enhance",

        "4": "location",
        "location": "location",
        "venue": "location",
        "address": "location",
        "where": "location",
        "map": "location",

        "5": "photos",
        "photos": "photos",
        "photo": "photos",
        "upload photos": "upload_photos",
        "upload photo": "upload_photos",
        "download photos": "download_photos",
        "download photo": "download_photos",

        "6": "contact",
        "contact": "contact",
        "contact us": "contact",
        "support": "contact",
        "help desk": "contact",
        "customer care": "contact",
    }

    return aliases.get(t, t)


def _event_type_key(event_type: str | None) -> str:
    t = normalize_text(event_type or "").lower()
    if t in {"farewell", "connect", "celebrate", "exhibit"}:
        return t
    return "default"


def _supports_donations(event_type: str | None) -> bool:
    return _event_type_key(event_type) not in {"connect", "exhibit"}


def _supports_photos(event_type: str | None) -> bool:
    return _event_type_key(event_type) not in {"connect", "exhibit"}


def _brochure_menu_label(event_type: str | None) -> str:
    if _event_type_key(event_type) in {"connect", "exhibit"}:
        return "Get Program Outline"
    return "Download Event Brochure"


def _brochure_ready_text(event_type: str | None) -> str:
    if _event_type_key(event_type) in {"connect", "exhibit"}:
        return "Here is the program outline.\nYou may open it on your phone."
    return "Here is the event brochure.\nYou may download it to your phone."


def _message_menu_label(event_type: str | None) -> str:
    key = _event_type_key(event_type)
    labels = {
        "farewell": "Send Condolence",
        "connect": "Send Question / Feedback",
        "celebrate": "Send Well Wishes",
        "exhibit": "Send Enquiry / Interest",
        "default": "Send Well Wishes / Message",
    }
    return labels[key]


def _message_menu_description(event_type: str | None) -> str:
    key = _event_type_key(event_type)
    descriptions = {
        "farewell": "Share a condolence message",
        "connect": "Ask a question or share feedback",
        "celebrate": "Share joyful wishes",
        "exhibit": "Show product interest or enquiry",
        "default": "Send a message",
    }
    return descriptions[key]


def _supports_ai_generate(event_type: str | None) -> bool:
    return _event_type_key(event_type) in {"farewell", "celebrate"}


def _menu_option_lines(event_type: str | None) -> list[str]:
    lines: list[str] = [f"1. 📄 {_brochure_menu_label(event_type)}"]
    if _supports_donations(event_type):
        lines.append("2. 💝 Give / Donate")
    lines.append(f"3. 🕊️ {_message_menu_label(event_type)}")
    lines.append("4. 📍 Location")
    if _supports_photos(event_type):
        lines.append("5. 📷 Photos")
    lines.append("6. ☎️ Contact Us")
    return lines


def _predefined_messages(event_type: str | None) -> list[str] | None:
    key = _event_type_key(event_type)
    by_type: dict[str, list[str]] = {
        "farewell": [
            "Please accept my deepest condolences. May your loved one rest in peace.",
            "My thoughts and prayers are with you and your family during this difficult time.",
            "Wishing your family comfort, strength, and peace in loving memory.",
        ],
        "celebrate": [
            "Congratulations on your celebration. Wishing you joy and lifelong happiness.",
            "May this special occasion be filled with love, laughter, and beautiful memories.",
            "Sending warm wishes for a wonderful celebration and a blessed future.",
        ],
    }
    return by_type.get(key)


def _has_predefined_messages(event_type: str | None) -> bool:
    return _predefined_messages(event_type) is not None


def _message_prompt_text(event_type: str | None) -> str:
    label = _message_menu_label(event_type)
    if _has_predefined_messages(event_type):
        return (
            f"{label}: choose an option below, or type your own message.\n"
            "(Reply *0* or *back* to return to the menu.)"
        )
    return (
        f"{label}: choose an option below, or type your own message.\n"
        "(Reply *0* or *back* to return to the menu.)"
    )


def _ai_enhance_prompt_text(event_type: str | None) -> str:
    label = _message_menu_label(event_type)
    return (
        f"{label}: type the message you want AI to enhance.\n"
        "(Reply *0* or *back* to return to the menu.)"
    )


def _ai_unavailable_text() -> str:
    return "AI assistant is not available right now. Please type your message directly."


_MESSAGE_TEMPLATE_IDS = {
    "one": "msg_template_1",
    "two": "msg_template_2",
    "three": "msg_template_3",
}

_MESSAGE_AI_GENERATE_ID = "ai_generate_message"
_MESSAGE_AI_ENHANCE_ID = "ai_enhance_message"


def _message_template_buttons(event_type: str | None) -> list[dict[str, str]]:
    if not _has_predefined_messages(event_type):
        return []

    key = _event_type_key(event_type)
    titles: dict[str, list[str]] = {
        "farewell": ["Deep Condolence", "Thoughts & Prayers", "Comfort & Peace"],
        "celebrate": ["Congratulations", "Joy & Happiness", "Warm Wishes"],
    }
    selected = titles[key]
    return [
        {"id": _MESSAGE_TEMPLATE_IDS["one"], "title": selected[0]},
        {"id": _MESSAGE_TEMPLATE_IDS["two"], "title": selected[1]},
        {"id": _MESSAGE_TEMPLATE_IDS["three"], "title": selected[2]},
    ]


def _message_option_rows(event_type: str | None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    template_buttons = _message_template_buttons(event_type)
    for item in template_buttons:
        rows.append(
            {
                "id": item["id"],
                "title": item["title"],
                "description": "Use predefined message",
            }
        )

    if _supports_ai_generate(event_type):
        rows.append(
            {
                "id": _MESSAGE_AI_GENERATE_ID,
                "title": "Generate With AI",
                "description": "Create a ready-to-send message",
            }
        )

    rows.append(
        {
            "id": _MESSAGE_AI_ENHANCE_ID,
            "title": "Enhance My Message",
            "description": "Improve a message you type",
        }
    )
    return rows


def _message_success_text(event_type: str | None) -> str:
    key = _event_type_key(event_type)
    by_type = {
        "farewell": "Your condolence message has been sent.",
        "connect": "Your question/feedback has been sent.",
        "celebrate": "Your well wishes have been sent.",
        "exhibit": "Your enquiry/interest has been sent.",
        "default": "Your message has been sent.",
    }
    return by_type[key]


def _resolve_message_input(text: str, event_type: str | None) -> tuple[str, str]:
    value = normalize_text(text)
    templates = _predefined_messages(event_type)
    if not templates:
        return value, "defined"

    key = value.lower()
    mapping = {
        _MESSAGE_TEMPLATE_IDS["one"]: templates[0],
        _MESSAGE_TEMPLATE_IDS["two"]: templates[1],
        _MESSAGE_TEMPLATE_IDS["three"]: templates[2],
        "1": templates[0],
        "option 1": templates[0],
        "template 1": templates[0],
        "2": templates[1],
        "option 2": templates[1],
        "template 2": templates[1],
        "3": templates[2],
        "option 3": templates[2],
        "template 3": templates[2],
    }
    resolved = mapping.get(key)
    if resolved:
        return resolved, "predefined"
    return value, "defined"


def _menu_text(guest_name: str, event_type: str | None = None) -> str:
    lines = "\n".join(_menu_option_lines(event_type))
    return (
        f"Thank you, {guest_name}.\n"
        "How can we help you today?\n\n"
        f"{lines}"
    )


def _menu_hint() -> str:
    return "\n\nReply *0* (or type *menu*) to see options."


def _event_intro_text(event_name: str | None) -> str:
    name = normalize_text(event_name or "")
    if not name:
        name = "This Event"
    return f"*{name}*"


def _photos_prompt_text() -> str:
    return (
        "What would you like to do with event photos?\n"
        "Please choose an option below."
    )


def _photos_rows() -> list[dict[str, str]]:
    return [
        {"id": "upload_photos", "title": "Upload Photos", "description": "Share Photos to Event Folder"},
        {"id": "download_photos", "title": "Download Photos", "description": "View Event Photo Gallery"},
    ]





def _normalize_event_code(code: str) -> str:
    return (code or "").strip().upper()





def _format_location_time(raw_time: str | None) -> str | None:
    value = (raw_time or "").strip()
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value

    return dt.strftime("%I:%M %p").lstrip("0")


def _format_location_date(raw_date: str | None) -> str | None:
    value = (raw_date or "").strip()
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value

    return dt.strftime("%a, %d %b %Y")


def _event_display_name(settings: Settings, unique_code: str) -> str:
    display_name = settings.default_event_name
    code = _normalize_event_code(unique_code)
    if code and code.lower() not in display_name.lower():
        return f"{display_name} ({code})"
    return display_name


def _guest_has_event_code(session: Session, unique_code: str) -> bool:
    code = _normalize_event_code(unique_code)
    if not code:
        return False

    codes = session.funeral_unique_codes or []
    for c in codes:
        if _normalize_event_code(str(c)) == code:
            return True
    return False


def _looks_like_auth_error(error: str | None) -> bool:
    if not error:
        return False
    e = str(error).lower()
    return (
        "http 401" in e
        or "401" in e
        or "unauthorized" in e
        or "forbidden" in e
        or "jwt" in e
        or "token" in e and "expire" in e
    )


def _refresh_guest_auth_if_possible(
    *,
    backend: BackendClient,
    sender_key: str,
    session: Session,
    phone_number: str,
    store: SessionStore,
) -> bool:
    phone = session.phone_number or phone_number
    if not phone:
        return False

    guest = backend.check_guest_registration(phone)
    if guest.status != "found" or not guest.guest:
        return False

    session.guest_id = guest.guest.guest_id
    session.guest_name = guest.guest.full_name
    session.backend_token = guest.token
    session.funeral_unique_codes = guest.guest.funeral_unique_codes
    store.upsert(sender_key, session)
    return True


def _cache_event_description(session: Session, code: str, name: str) -> None:
    """Store event description keyed by normalized code so it survives repeat lookups."""
    norm = _normalize_event_code(code)
    if not norm or not name:
        return
    if session.event_descriptions is None:
        session.event_descriptions = {}
    session.event_descriptions[norm] = name


def _cached_event_description(session: Session, code: str) -> str | None:
    norm = _normalize_event_code(code)
    if not norm or not session.event_descriptions:
        return None
    return session.event_descriptions.get(norm)


def _populate_event_details_for_code(
    *,
    code_input: str,
    session: Session,
    settings: Settings,
    backend: BackendClient,
    sender_key: str,
    phone_number: str,
    store: SessionStore,
) -> None:
    code = _normalize_event_code(code_input)
    session.event_code = code
    session.event_id = code
    session.event_type = None

    # Start with the best name we already have (cached > default).
    cached = _cached_event_description(session, code)
    session.event_name = cached or _event_display_name(settings, code)
    session.event_location = settings.default_event_location
    session.event_location_url = settings.default_event_location_url

    if not session.backend_token:
        return

    result = backend.get_event_by_code(code, token=session.backend_token)
    if result.status == "error" and _looks_like_auth_error(result.error):
        if _refresh_guest_auth_if_possible(
            backend=backend,
            sender_key=sender_key,
            session=session,
            phone_number=phone_number,
            store=store,
        ):
            result = backend.get_event_by_code(code, token=session.backend_token)

    if result.status == "found" and result.event:
        session.event_id = result.event.event_id
        session.event_name = result.event.name
        session.event_type = result.event.event_type
        session.event_location = result.event.location
        session.event_location_url = result.event.location_url
        _cache_event_description(session, code, result.event.name)


def _handle_photo_action(
    *,
    action: str,
    session: Session,
    backend: BackendClient,
    sender_key: str,
    phone_number: str,
    store: SessionStore,
) -> OutgoingMessage:
    if action == "upload_photos":
        result = backend.get_upload_photo_link(session.event_id, token=session.backend_token)
        if result.status == "error" and _looks_like_auth_error(result.error):
            if _refresh_guest_auth_if_possible(
                backend=backend,
                sender_key=sender_key,
                session=session,
                phone_number=phone_number,
                store=store,
            ):
                result = backend.get_upload_photo_link(session.event_id, token=session.backend_token)

        store.upsert(sender_key, session)

        if result.status == "ready" and result.photo_link:
            return OutgoingMessage(text=(f"📸 Upload photos here:\n{result.photo_link.url}" + _menu_hint()))

        error = result.error or "Upload photo link is not available right now."
        return OutgoingMessage(text=(f"Sorry, {error}" + _menu_hint()))

    if action == "download_photos":
        result = backend.get_download_photo_link(session.event_id, token=session.backend_token)
        if result.status == "error" and _looks_like_auth_error(result.error):
            if _refresh_guest_auth_if_possible(
                backend=backend,
                sender_key=sender_key,
                session=session,
                phone_number=phone_number,
                store=store,
            ):
                result = backend.get_download_photo_link(session.event_id, token=session.backend_token)

        store.upsert(sender_key, session)

        if result.status == "ready" and result.photo_link:
            return OutgoingMessage(text=(f"🖼️ Download event photos here:\n{result.photo_link.url}" + _menu_hint()))

        error = result.error or "Download photo link is not available right now."
        return OutgoingMessage(text=(f"Sorry, {error}" + _menu_hint()))

    raise ValueError(f"Unknown photo action: {action}")


def _submit_event_message(
    *,
    backend: BackendClient,
    session: Session,
    sender_key: str,
    phone_number: str,
    store: SessionStore,
    message_text: str,
    message_type: str,
):
    result = backend.submit_condolence(
        session.event_id,
        session.guest_id,
        message_text,
        message_type=message_type,
        token=session.backend_token,
    )

    if result.status == "error" and _looks_like_auth_error(result.error):
        if _refresh_guest_auth_if_possible(
            backend=backend,
            sender_key=sender_key,
            session=session,
            phone_number=phone_number,
            store=store,
        ):
            result = backend.submit_condolence(
                session.event_id,
                session.guest_id,
                message_text,
                message_type=message_type,
                token=session.backend_token,
            )

    return result


def handle_incoming_message(
    *,
    sender_key: str,
    incoming_text: str,
    store: SessionStore,
    backend: BackendClient,
    settings: Settings,
    ai_writer: AIMessageWriter | None = None,
) -> OutgoingMessage:
    text = normalize_text(incoming_text)
    choice = _normalize_choice(text)
    phone_number = _normalize_phone(sender_key)

    session = store.get(sender_key)
    if session is None:
        session = Session(state=ConversationState.WAIT_EVENT_CODE.value, phone_number=phone_number or None)

        store.upsert(sender_key, session)
        return OutgoingMessage(text=WELCOME_TEXT)

    # Global commands
    if choice == "restart":
        # Preserve the event description cache so we don't lose it.
        saved_descriptions = session.event_descriptions
        saved_event_type = session.event_type
        store.clear(sender_key)
        session = Session(state=ConversationState.WAIT_EVENT_CODE.value, phone_number=phone_number or None)
        session.event_descriptions = saved_descriptions
        session.event_type = saved_event_type

        store.upsert(sender_key, session)
        return OutgoingMessage(text=WELCOME_TEXT)

    if choice == "help":
        option_three_label = _message_menu_label(session.event_type)
        option_one_text = _brochure_menu_label(session.event_type).lower()
        help_lines = [
            "You can reply with:",
            "- *DEMO* (or your event code) to start",
            f"- *1* for {option_one_text}",
        ]
        if _supports_donations(session.event_type):
            help_lines.append("- *2* to donate")
        help_lines.extend(
            [
                f"- *3* to {option_three_label.lower()}",
                "- *4* for location",
            ]
        )
        if _supports_photos(session.event_type):
            help_lines.append("- *5* for photos")
        help_lines.extend(
            [
                "- *6* for contact us",
                "- *0* to show the menu",
                "- *restart* to start over",
            ]
        )
        help_text = "\n".join(help_lines)
        # If we already have a name, include the menu for convenience.
        if session.guest_name:
            help_text = help_text + "\n\n" + _menu_text(session.guest_name, session.event_type)
        return OutgoingMessage(text=help_text)

    if session.state == ConversationState.WAIT_EVENT_CODE.value:
        if not text:
            return OutgoingMessage(text=WELCOME_TEXT)

        if _is_greeting(text):
            return OutgoingMessage(text=WELCOME_TEXT)

        # Backend requires a guest token to verify event codes.
        # Try recovering guest auth first for already-registered users.
        if not session.backend_token and phone_number:
            guest = backend.check_guest_registration(phone_number)
            if guest.status == "found" and guest.guest:
                session.guest_id = guest.guest.guest_id
                session.guest_name = session.guest_name or guest.guest.full_name
                session.backend_token = guest.token
                session.funeral_unique_codes = guest.guest.funeral_unique_codes

        # If we still don't have a token, collect the code and ask for the guest name.
        if not session.backend_token:
            session.event_code = _normalize_event_code(text)
            session.state = ConversationState.WAIT_NAME.value
            store.upsert(sender_key, session)
            return OutgoingMessage(text="Thank you. Please enter your *name* to continue.")

        # Optimization: if the guest profile already lists this event code, do not call
        # verify-funeral-details again (backend may be non-idempotent).
        if _guest_has_event_code(session, text):
            _populate_event_details_for_code(
                code_input=text,
                session=session,
                settings=settings,
                backend=backend,
                sender_key=sender_key,
                phone_number=phone_number,
                store=store,
            )

            if session.guest_name:
                session.state = ConversationState.MENU.value
                store.upsert(sender_key, session)
                return OutgoingMessage(
                    text=(
                        _event_intro_text(session.event_name)
                        + "\n\n"
                        + _menu_text(session.guest_name, session.event_type)
                    ),
                    interactive_menu=True,
                    guest_name=session.guest_name,
                )

            session.state = ConversationState.WAIT_NAME.value
            store.upsert(sender_key, session)
            return OutgoingMessage(
                text=(
                    "Thank you.\n"
                    f"{_event_intro_text(session.event_name)}\n\n"
                    "Please enter your *name* to continue."
                )
            )

        result = backend.get_event_by_code(text, token=session.backend_token)
        if result.status == "error" and _looks_like_auth_error(result.error):
            if _refresh_guest_auth_if_possible(
                backend=backend,
                sender_key=sender_key,
                session=session,
                phone_number=phone_number,
                store=store,
            ):
                result = backend.get_event_by_code(text, token=session.backend_token)

        if result.status == "closed":
            return OutgoingMessage(
                text=(
                    "Sorry, this event is closed and is no longer accepting guests.\n"
                    "Please contact the event organiser for more information."
                )
            )

        if result.status != "found" or not result.event:
            return OutgoingMessage(
                text=(
                    "Sorry, that event code was not found.\n"
                    "Please check the card and try again."
                )
            )

        code = _normalize_event_code(text)
        session.event_code = code
        session.event_id = result.event.event_id
        session.event_name = result.event.name
        session.event_type = result.event.event_type
        session.event_location = result.event.location
        session.event_location_url = result.event.location_url
        _cache_event_description(session, code, result.event.name)

        # Cache the verified code into the guest's known codes so we can skip re-verification.
        existing = session.funeral_unique_codes or []
        if code and not any(_normalize_event_code(str(x)) == code for x in existing):
            session.funeral_unique_codes = [*existing, code]

        # If we already know the guest name from the backend, go straight to the menu.
        if session.guest_name:
            session.state = ConversationState.MENU.value
            store.upsert(sender_key, session)
            return OutgoingMessage(
                text=(
                    _event_intro_text(session.event_name)
                    + "\n\n"
                    + _menu_text(session.guest_name, session.event_type)
                ),
                interactive_menu=True,
                guest_name=session.guest_name,
            )

        session.state = ConversationState.WAIT_NAME.value
        store.upsert(sender_key, session)

        return OutgoingMessage(
            text=(
                "Thank you.\n"
                f"{_event_intro_text(session.event_name)}\n\n"
                "Please enter your *name* to continue."
            )
        )

    if session.state == ConversationState.WAIT_NAME.value:
        if not text:
            return OutgoingMessage(text="Please enter your name to continue (e.g., Ama / Kofi).")

        session.guest_name = text

        # Register the guest (best-effort). If it fails, we still proceed with the flow.
        phone = session.phone_number or phone_number
        if phone:
            reg = backend.register_guest(full_name=session.guest_name, phone_number=phone)
            if reg.status in {"created", "found"} and reg.guest:
                session.guest_id = reg.guest.guest_id
                session.backend_token = reg.token
                session.funeral_unique_codes = reg.guest.funeral_unique_codes

            # Some backends don't return 409/"found" consistently for existing users.
            # Recover profile/token explicitly so event verification can proceed.
            if not session.backend_token:
                guest = backend.check_guest_registration(phone)
                if guest.status == "found" and guest.guest:
                    session.guest_id = guest.guest.guest_id
                    session.backend_token = guest.token
                    session.funeral_unique_codes = guest.guest.funeral_unique_codes

        # Now that we (likely) have a token, verify the previously collected event code.
        if not session.event_code:
            session.state = ConversationState.WAIT_EVENT_CODE.value
            store.upsert(sender_key, session)
            return OutgoingMessage(text=WELCOME_TEXT)

        # If the guest profile already includes the code, skip verifying (backend may reject repeats).
        if session.backend_token and _guest_has_event_code(session, session.event_code):
            _populate_event_details_for_code(
                code_input=session.event_code,
                session=session,
                settings=settings,
                backend=backend,
                sender_key=sender_key,
                phone_number=phone_number,
                store=store,
            )

            session.state = ConversationState.MENU.value
            store.upsert(sender_key, session)
            return OutgoingMessage(
                text=(
                    _event_intro_text(session.event_name)
                    + "\n\n"
                    + _menu_text(session.guest_name, session.event_type)
                ),
                interactive_menu=True,
                guest_name=session.guest_name,
            )

        if session.backend_token:
            result = backend.get_event_by_code(session.event_code, token=session.backend_token)
            if result.status == "error" and _looks_like_auth_error(result.error):
                if _refresh_guest_auth_if_possible(
                    backend=backend,
                    sender_key=sender_key,
                    session=session,
                    phone_number=phone_number,
                    store=store,
                ):
                    result = backend.get_event_by_code(session.event_code, token=session.backend_token)

            if result.status == "closed":
                session.event_code = None
                session.event_id = None
                session.event_name = None
                session.event_type = None
                session.event_location = None
                session.event_location_url = None
                session.state = ConversationState.WAIT_EVENT_CODE.value
                store.upsert(sender_key, session)
                return OutgoingMessage(
                    text=(
                        "Sorry, this event is closed and is no longer accepting guests.\n"
                        "Please contact the event organiser for more information."
                    )
                )

            if result.status == "found" and result.event:
                session.event_id = result.event.event_id
                session.event_name = result.event.name
                session.event_type = result.event.event_type
                session.event_location = result.event.location
                session.event_location_url = result.event.location_url
                _cache_event_description(session, session.event_code, result.event.name)

                code = _normalize_event_code(session.event_code)
                existing = session.funeral_unique_codes or []
                if code and not any(_normalize_event_code(str(x)) == code for x in existing):
                    session.funeral_unique_codes = [*existing, code]

                session.state = ConversationState.MENU.value
                store.upsert(sender_key, session)
                return OutgoingMessage(
                    text=(
                        _event_intro_text(session.event_name)
                        + "\n\n"
                        + _menu_text(session.guest_name, session.event_type)
                    ),
                    interactive_menu=True,
                    guest_name=session.guest_name,
                )

        # Invalid code (or missing token). Ask for the event code again but keep the guest details.
        session.event_code = None
        session.event_id = None
        session.event_name = None
        session.event_type = None
        session.event_location = None
        session.event_location_url = None
        session.state = ConversationState.WAIT_EVENT_CODE.value
        store.upsert(sender_key, session)
        return OutgoingMessage(
            text=(
                "Sorry, that event code was not found.\n"
                "Please enter the *Event Code* on your card to continue."
            )
        )

    if session.state == ConversationState.MENU.value:
        if not session.guest_name:
            session.state = ConversationState.WAIT_NAME.value
            store.upsert(sender_key, session)
            return OutgoingMessage(text="Please enter your name to continue.")

        if choice in {"menu", ""}:
            return OutgoingMessage(
                text=_menu_text(session.guest_name, session.event_type),
                interactive_menu=True,
                guest_name=session.guest_name,
            )

        if choice in {"brochure", "donate", "condolence", "location", "contact", "photos", "upload_photos", "download_photos"}:
            if choice == "brochure":
                if not session.event_id:
                    return OutgoingMessage(text="Missing event context. Please type 'restart'.")

                brochure = backend.get_brochure(session.event_id, token=session.backend_token)
                if brochure.status == "error" and _looks_like_auth_error(brochure.error):
                    if _refresh_guest_auth_if_possible(
                        backend=backend,
                        sender_key=sender_key,
                        session=session,
                        phone_number=phone_number,
                        store=store,
                    ):
                        brochure = backend.get_brochure(session.event_id, token=session.backend_token)

                if brochure.status != "ready" or not brochure.brochure:
                    error = brochure.error or "Brochure is not available right now."
                    return OutgoingMessage(text=f"Sorry, {error}." + _menu_hint())

                # Stay in MENU state and show menu again after sending the brochure.
                store.upsert(sender_key, session)
                return OutgoingMessage(
                    text=(_brochure_ready_text(session.event_type) + _menu_hint()),
                    media_url=brochure.brochure.media_url,
                )

            if choice == "donate":
                if not _supports_donations(session.event_type):
                    return OutgoingMessage(text="Donations are not available for this event." + _menu_hint())

                if not session.event_id:
                    return OutgoingMessage(text="Missing event context. Please type 'restart'.")

                session.donation_reference_name = None
                session.state = ConversationState.WAIT_DONATION_REFERENCE.value
                store.upsert(sender_key, session)
                return OutgoingMessage(
                    text=(
                        "Who would you like to make this donation to?\n"
                        "For example: *Family A*, *Family B*, or a person\'s name.\n"
                        "(Reply *back* to return to the menu.)"
                    )
                )

            if choice == "condolence":
                session.state = ConversationState.WAIT_CONDOLENCE.value
                store.upsert(sender_key, session)
                rows = _message_option_rows(session.event_type)
                return OutgoingMessage(
                    text=_message_prompt_text(session.event_type),
                    interactive_menu=bool(rows),
                    interactive_button_text="Choose message option",
                    interactive_section_title=_message_menu_label(session.event_type),
                    interactive_rows=rows or None,
                )

            if choice == "location":
                if not session.event_id:
                    return OutgoingMessage(text="Missing event context. Please type 'restart'.")

                loc = backend.get_funeral_location(session.event_id, token=session.backend_token)
                if loc.status == "error" and _looks_like_auth_error(loc.error):
                    if _refresh_guest_auth_if_possible(
                        backend=backend,
                        sender_key=sender_key,
                        session=session,
                        phone_number=phone_number,
                        store=store,
                    ):
                        loc = backend.get_funeral_location(session.event_id, token=session.backend_token)

                if loc.status == "ready" and loc.location:
                    session.event_location = loc.location.name or session.event_location
                    session.event_location_url = loc.location.link or session.event_location_url
                    store.upsert(sender_key, session)

                    lines: list[str] = []
                    if loc.location.name:
                        lines.append(f"📍 {loc.location.name}")

                    formatted_date = _format_location_date(loc.location.date)
                    if formatted_date:
                        lines.append(f"🗓️ Date: {formatted_date}")
                    elif loc.location.day:
                        lines.append(f"🗓️ Date: {loc.location.day}")

                    formatted_time = _format_location_time(loc.location.time)
                    if formatted_time:
                        lines.append(f"🕒 Time: {formatted_time}")

                    if loc.location.link:
                        lines.append(f"🗺️ Directions: {loc.location.link}")
                else:
                    error = loc.error or "Location details are not available yet."
                    lines = [f"Sorry, {error}"]

                return OutgoingMessage(text="\n".join(lines) + _menu_hint())

            if choice == "contact":
                return OutgoingMessage(
                    text=(
                        "☎️ Contact Us\n"
                        "Call/WhatsApp: +233 24 991 0999\n"
                        "Website: https://yalasolution.com/"
                        + _menu_hint()
                    )
                )

            if choice == "photos":
                if not _supports_photos(session.event_type):
                    return OutgoingMessage(text="Photos are not available for this event." + _menu_hint())

                session.state = ConversationState.WAIT_PHOTOS_MENU.value
                store.upsert(sender_key, session)
                return OutgoingMessage(
                    text=_photos_prompt_text(),
                    interactive_menu=True,
                    interactive_button_text="Choose photo option",
                    interactive_section_title="Event Photos",
                    interactive_rows=_photos_rows(),
                )

            if choice in {"upload_photos", "download_photos"}:
                if not _supports_photos(session.event_type):
                    return OutgoingMessage(text="Photos are not available for this event." + _menu_hint())

                session.state = ConversationState.MENU.value
                return _handle_photo_action(
                    action=choice,
                    session=session,
                    backend=backend,
                    sender_key=sender_key,
                    phone_number=phone_number,
                    store=store,
                )

        # Unrecognized input (including greetings like "hi") — just show the menu.
        return OutgoingMessage(
            text=_menu_text(session.guest_name, session.event_type),
            interactive_menu=True,
            guest_name=session.guest_name,
        )

    if session.state == ConversationState.WAIT_DONATION_AMOUNT.value:
        if not session.guest_name or not session.event_id:
            session.state = ConversationState.MENU.value
            store.upsert(sender_key, session)
            return OutgoingMessage(text="Missing context. Returning to main menu." + _menu_hint())

        if not _supports_donations(session.event_type):
            session.state = ConversationState.MENU.value
            session.donation_reference_name = None
            store.upsert(sender_key, session)
            return OutgoingMessage(text="Donations are not available for this event." + _menu_hint())

        if not session.donation_reference_name:
            session.state = ConversationState.WAIT_DONATION_REFERENCE.value
            store.upsert(sender_key, session)
            return OutgoingMessage(
                text=(
                    "Who would you like to make this donation to?\n"
                    "For example: *Family A*, *Family B*, or a person's name.\n"
                    "(Reply *back* to return to the menu.)"
                )
            )

        if not session.guest_id:
            session.state = ConversationState.MENU.value
            store.upsert(sender_key, session)
            return OutgoingMessage(
                text=(
                    "We couldn’t identify your guest profile.\n"
                    "Please type *restart* and try again."
                    + _menu_hint()
                )
            )

        if choice == "back" or choice == "menu":
            session.state = ConversationState.MENU.value
            store.upsert(sender_key, session)
            return OutgoingMessage(text=_menu_text(session.guest_name, session.event_type))

        # Parse amount *before* checking menu shortcuts so that numeric inputs
        # like "2" are treated as donation amounts, not menu option numbers.
        try:
            normalized_amount = text.lower().replace("ghc", "").replace("ghs", "").replace("cedis", "").replace("$", "").replace(",", "").replace("gh¢", "").strip()
            amount = float(normalized_amount)
        except ValueError:
            amount = None

        if amount is not None and amount <= 0:
            return OutgoingMessage(text="Please enter a valid amount greater than zero.")

        # If the input isn't a valid number, allow menu shortcuts to work.
        if amount is None:
            if choice in {"brochure", "donate", "condolence", "location", "contact", "photos", "upload_photos", "download_photos"}:
                session.state = ConversationState.MENU.value
                store.upsert(sender_key, session)
                return handle_incoming_message(
                    sender_key=sender_key,
                    incoming_text=choice,
                    store=store,
                    backend=backend,
                    settings=settings,
                    ai_writer=ai_writer,
                )
            return OutgoingMessage(text="Please enter a valid number for the amount (e.g., 50).")

        if amount <= 0:
            return OutgoingMessage(text="Please enter a valid amount greater than zero.")

        intent = backend.create_donation_intent(
            session.event_id,
            session.guest_id,
            session.donation_reference_name,
            amount,
            token=session.backend_token,
        )

        if intent.status == "error" and _looks_like_auth_error(intent.error):
            if _refresh_guest_auth_if_possible(
                backend=backend,
                sender_key=sender_key,
                session=session,
                phone_number=phone_number,
                store=store,
            ):
                intent = backend.create_donation_intent(
                    session.event_id,
                    session.guest_id,
                    session.donation_reference_name,
                    amount,
                    token=session.backend_token,
                )

        if intent.status == "unavailable":
            session.state = ConversationState.MENU.value
            session.donation_reference_name = None
            store.upsert(sender_key, session)
            return OutgoingMessage(text="This event does not accept donations." + _menu_hint())

        if intent.status == "ready" and intent.intent:
            session.state = ConversationState.MENU.value
            session.donation_reference_name = None
            store.upsert(sender_key, session)
            formatted_amount = f"GH¢{amount:g}"
            return OutgoingMessage(
                text=(
                    f"Thank you. Please use this link to complete your donation of {formatted_amount}:\n"
                    f"{intent.intent.checkout_url}"
                    + _menu_hint()
                )
            )

        error_msg = intent.error or "Unknown error"
        return OutgoingMessage(
            text=(
                f"Sorry, we couldn’t process your donation request.\n"
                f"({error_msg})\n"
                "Please try again or reply *back*."
            )
        )

    if session.state == ConversationState.WAIT_DONATION_REFERENCE.value:
        if not session.guest_name or not session.event_id:
            session.state = ConversationState.MENU.value
            store.upsert(sender_key, session)
            return OutgoingMessage(text="Missing context. Returning to main menu." + _menu_hint())

        if not _supports_donations(session.event_type):
            session.state = ConversationState.MENU.value
            session.donation_reference_name = None
            store.upsert(sender_key, session)
            return OutgoingMessage(text="Donations are not available for this event." + _menu_hint())

        if choice == "back" or choice == "menu":
            session.state = ConversationState.MENU.value
            session.donation_reference_name = None
            store.upsert(sender_key, session)
            return OutgoingMessage(text=_menu_text(session.guest_name, session.event_type))

        if choice in {"brochure", "donate", "condolence", "location", "contact", "photos", "upload_photos", "download_photos"}:
            session.state = ConversationState.MENU.value
            session.donation_reference_name = None
            store.upsert(sender_key, session)
            return handle_incoming_message(
                sender_key=sender_key,
                incoming_text=choice,
                store=store,
                backend=backend,
                settings=settings,
                ai_writer=ai_writer,
            )

        reference_name = normalize_text(text)
        if not reference_name:
            return OutgoingMessage(
                text=(
                    "Please enter who the donation is for.\n"
                    "For example: *Family A*, *Family B*, or a person\'s name."
                )
            )

        session.donation_reference_name = reference_name
        session.state = ConversationState.WAIT_DONATION_AMOUNT.value
        store.upsert(sender_key, session)
        return OutgoingMessage(
            text=(
                f"Donation target: *{reference_name}*\n\n"
                "Please enter the amount you would like to donate (e.g., 50).\n"
                "(Reply *back* to return to the menu.)"
            )
        )

    if session.state == ConversationState.WAIT_CONDOLENCE.value:
        if not session.guest_name or not session.event_id:
            session.state = ConversationState.MENU.value
            store.upsert(sender_key, session)
            return OutgoingMessage(text="Missing context. Returning to main menu." + _menu_hint())

        if not session.guest_id:
            session.state = ConversationState.MENU.value
            store.upsert(sender_key, session)
            return OutgoingMessage(
                text=(
                    "We couldn’t identify your guest profile.\n"
                    "Please type *restart* and try again."
                    + _menu_hint()
                )
            )

        if choice in {"back", "menu"}:
            session.state = ConversationState.MENU.value
            store.upsert(sender_key, session)
            return OutgoingMessage(
                text=_menu_text(session.guest_name, session.event_type),
                interactive_menu=True,
                guest_name=session.guest_name,
            )

        # Allow menu shortcuts in this state.
        if choice in {"brochure", "donate", "condolence", "location", "contact", "photos", "upload_photos", "download_photos"}:
            session.state = ConversationState.MENU.value
            store.upsert(sender_key, session)
            return handle_incoming_message(
                sender_key=sender_key,
                incoming_text=choice,
                store=store,
                backend=backend,
                settings=settings,
                ai_writer=ai_writer,
            )

        if normalize_text(text).lower() in {"options", "list", "templates"}:
            rows = _message_option_rows(session.event_type)
            return OutgoingMessage(
                text=_message_prompt_text(session.event_type),
                interactive_menu=bool(rows),
                interactive_button_text="Choose message option",
                interactive_section_title=_message_menu_label(session.event_type),
                interactive_rows=rows or None,
            )

        if choice in {"ai_generate", _MESSAGE_AI_GENERATE_ID}:
            if not _supports_ai_generate(session.event_type):
                return OutgoingMessage(
                    text=(
                        "AI generation is available for Yala Farewell and Yala Celebrate only."
                        + _menu_hint()
                    )
                )

            if ai_writer is None:
                rows = _message_option_rows(session.event_type)
                return OutgoingMessage(
                    text=(_ai_unavailable_text() + "\n\n" + _message_prompt_text(session.event_type)),
                    interactive_menu=bool(rows),
                    interactive_button_text="Choose message option",
                    interactive_section_title=_message_menu_label(session.event_type),
                    interactive_rows=rows or None,
                )

            ai_result = ai_writer.generate_message(
                event_type=_event_type_key(session.event_type),
                event_name=session.event_name,
                guest_name=session.guest_name,
            )
            if ai_result.status != "ready" or not ai_result.text:
                rows = _message_option_rows(session.event_type)
                err = ai_result.error or "We could not generate a message right now"
                return OutgoingMessage(
                    text=(f"Sorry, {err}.\n\n" + _message_prompt_text(session.event_type)),
                    interactive_menu=bool(rows),
                    interactive_button_text="Choose message option",
                    interactive_section_title=_message_menu_label(session.event_type),
                    interactive_rows=rows or None,
                )

            message_to_send = normalize_text(ai_result.text)
            result = _submit_event_message(
                backend=backend,
                session=session,
                sender_key=sender_key,
                phone_number=phone_number,
                store=store,
                message_text=message_to_send,
                message_type="ai_generated",
            )

            session.state = ConversationState.MENU.value
            store.upsert(sender_key, session)

            if result.status == "ok":
                return OutgoingMessage(
                    text=(
                        "Thank you.\n"
                        "Your AI-generated message has been sent.\n\n"
                        f"Message sent:\n{message_to_send}"
                        + _menu_hint()
                    )
                )

            if result.status == "unavailable":
                return OutgoingMessage(text=(result.error or "Well wishes messages are disabled for this funeral.") + _menu_hint())

            return OutgoingMessage(
                text=(
                    "Sorry, we couldn’t send your AI-generated message right now.\n"
                    "Please try again later."
                    + _menu_hint()
                )
            )

        if choice in {"ai_enhance", _MESSAGE_AI_ENHANCE_ID}:
            session.state = ConversationState.WAIT_AI_ENHANCE_INPUT.value
            store.upsert(sender_key, session)
            return OutgoingMessage(text=_ai_enhance_prompt_text(session.event_type))

        message_to_send, message_type = _resolve_message_input(text, session.event_type)

        if not message_to_send:
            rows = _message_option_rows(session.event_type)
            return OutgoingMessage(
                text=_message_prompt_text(session.event_type),
                interactive_menu=bool(rows),
                interactive_button_text="Choose message option",
                interactive_section_title=_message_menu_label(session.event_type),
                interactive_rows=rows or None,
            )

        result = _submit_event_message(
            backend=backend,
            session=session,
            sender_key=sender_key,
            phone_number=phone_number,
            store=store,
            message_text=message_to_send,
            message_type=message_type,
        )

        session.state = ConversationState.MENU.value
        store.upsert(sender_key, session)

        if result.status == "ok":
            return OutgoingMessage(
                text=(
                    "Thank you.\n"
                    + _message_success_text(session.event_type)
                    + _menu_hint()
                )
            )

        if result.status == "unavailable":
            return OutgoingMessage(text=(result.error or "Well wishes messages are disabled for this funeral.") + _menu_hint())

        return OutgoingMessage(
            text=(
                "Sorry, we couldn’t send your message right now.\n"
                "Please try again later."
                + _menu_hint()
            )
        )

    if session.state == ConversationState.WAIT_AI_ENHANCE_INPUT.value:
        if not session.guest_name or not session.event_id:
            session.state = ConversationState.MENU.value
            store.upsert(sender_key, session)
            return OutgoingMessage(text="Missing context. Returning to main menu." + _menu_hint())

        if not session.guest_id:
            session.state = ConversationState.MENU.value
            store.upsert(sender_key, session)
            return OutgoingMessage(
                text=(
                    "We couldn’t identify your guest profile.\n"
                    "Please type *restart* and try again."
                    + _menu_hint()
                )
            )

        if choice in {"back", "menu"}:
            session.state = ConversationState.MENU.value
            store.upsert(sender_key, session)
            return OutgoingMessage(
                text=_menu_text(session.guest_name, session.event_type),
                interactive_menu=True,
                guest_name=session.guest_name,
            )

        if choice in {"brochure", "donate", "condolence", "location", "contact", "photos", "upload_photos", "download_photos"}:
            session.state = ConversationState.MENU.value
            store.upsert(sender_key, session)
            return handle_incoming_message(
                sender_key=sender_key,
                incoming_text=choice,
                store=store,
                backend=backend,
                settings=settings,
                ai_writer=ai_writer,
            )

        if normalize_text(text).lower() in {"options", "list", "templates"}:
            return OutgoingMessage(text=_ai_enhance_prompt_text(session.event_type))

        if choice in {"ai_generate", _MESSAGE_AI_GENERATE_ID}:
            session.state = ConversationState.WAIT_CONDOLENCE.value
            store.upsert(sender_key, session)
            return handle_incoming_message(
                sender_key=sender_key,
                incoming_text=choice,
                store=store,
                backend=backend,
                settings=settings,
                ai_writer=ai_writer,
            )

        if choice in {"ai_enhance", _MESSAGE_AI_ENHANCE_ID}:
            return OutgoingMessage(text=_ai_enhance_prompt_text(session.event_type))

        if not text:
            return OutgoingMessage(text=_ai_enhance_prompt_text(session.event_type))

        if ai_writer is None:
            session.state = ConversationState.WAIT_CONDOLENCE.value
            store.upsert(sender_key, session)
            rows = _message_option_rows(session.event_type)
            return OutgoingMessage(
                text=(_ai_unavailable_text() + "\n\n" + _message_prompt_text(session.event_type)),
                interactive_menu=bool(rows),
                interactive_button_text="Choose message option",
                interactive_section_title=_message_menu_label(session.event_type),
                interactive_rows=rows or None,
            )

        draft = normalize_text(text)
        ai_result = ai_writer.enhance_message(event_type=_event_type_key(session.event_type), draft=draft)
        if ai_result.status != "ready" or not ai_result.text:
            err = ai_result.error or "We could not enhance your message right now"
            return OutgoingMessage(text=f"Sorry, {err}.\n\n" + _ai_enhance_prompt_text(session.event_type))

        enhanced_message = normalize_text(ai_result.text)
        result = _submit_event_message(
            backend=backend,
            session=session,
            sender_key=sender_key,
            phone_number=phone_number,
            store=store,
            message_text=enhanced_message,
            message_type="ai_enhanced",
        )

        session.state = ConversationState.MENU.value
        store.upsert(sender_key, session)

        if result.status == "ok":
            return OutgoingMessage(
                text=(
                    "Thank you.\n"
                    "Your AI-enhanced message has been sent.\n\n"
                    f"Message sent:\n{enhanced_message}"
                    + _menu_hint()
                )
            )

        if result.status == "unavailable":
            return OutgoingMessage(text=(result.error or "Well wishes messages are disabled for this funeral.") + _menu_hint())

        return OutgoingMessage(
            text=(
                "Sorry, we couldn’t send your AI-enhanced message right now.\n"
                "Please try again later."
                + _menu_hint()
            )
        )

    if session.state == ConversationState.WAIT_PHOTOS_MENU.value:
        if not _supports_photos(session.event_type):
            session.state = ConversationState.MENU.value
            store.upsert(sender_key, session)
            return OutgoingMessage(text="Photos are not available for this event." + _menu_hint())

        if not session.guest_name or not session.event_id:
            session.state = ConversationState.MENU.value
            store.upsert(sender_key, session)
            return OutgoingMessage(text="Missing context. Returning to main menu." + _menu_hint())

        if choice in {"back", "menu"}:
            session.state = ConversationState.MENU.value
            store.upsert(sender_key, session)
            return OutgoingMessage(
                text=_menu_text(session.guest_name, session.event_type),
                interactive_menu=True,
                guest_name=session.guest_name,
            )

        if choice in {"brochure", "donate", "condolence", "location", "contact", "photos", "upload_photos", "download_photos"}:
            session.state = ConversationState.MENU.value
            store.upsert(sender_key, session)
            return handle_incoming_message(
                sender_key=sender_key,
                incoming_text=choice,
                store=store,
                backend=backend,
                settings=settings,
                ai_writer=ai_writer,
            )

        photo_choice = choice
        if normalize_text(text).lower() in {"1", "upload"}:
            photo_choice = "upload_photos"
        elif normalize_text(text).lower() in {"2", "download"}:
            photo_choice = "download_photos"

        if photo_choice in {"upload_photos", "download_photos"}:
            session.state = ConversationState.MENU.value
            return _handle_photo_action(
                action=photo_choice,
                session=session,
                backend=backend,
                sender_key=sender_key,
                phone_number=phone_number,
                store=store,
            )

        return OutgoingMessage(
            text=_photos_prompt_text(),
            interactive_menu=True,
            interactive_button_text="Choose photo option",
            interactive_section_title="Event Photos",
            interactive_rows=_photos_rows(),
        )

    # Unknown state: reset politely
    store.clear(sender_key)
    return OutgoingMessage(text=WELCOME_TEXT)
