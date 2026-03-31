from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..backend.client import BackendClient
from ..config import Settings
from ..storage.session_store import Session, SessionStore
from .state import ConversationState, normalize_text


@dataclass(frozen=True)
class OutgoingMessage:
    text: str
    media_url: str | None = None
    interactive_menu: bool = False
    guest_name: str | None = None
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
        "well wish": "condolence",
        "well wishes": "condolence",
        "message": "condolence",
        "send message": "condolence",
        "send well wishes": "condolence",

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


def _menu_text(guest_name: str) -> str:
    return (
        f"Thank you, {guest_name}.\n"
        "How can we help you today?\n\n"
        "1. 📄 Download Event Brochure\n"
        "2. 💝 Give / Donate\n"
        "3. 🕊️ Send Well Wishes / Message\n"
        "4. 📍 Location\n"
        "5. 📷 Photos\n"
        "6. ☎️ Contact Us"
    )


def _menu_hint() -> str:
    return "\n\nReply *0* (or type *menu*) to see options."


def _event_intro_text(event_name: str | None) -> str:
    name = normalize_text(event_name or "")
    if not name:
        name = "This Event"
    return f"*{name}*"


def _condolence_prompt_text() -> str:
    return (
        "Please type your well wishes message.\n"
        "(Reply *0* or *back* to return to the menu.)"
    )


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
        session.event_location = result.event.location
        session.event_location_url = result.event.location_url
        _cache_event_description(session, code, result.event.name)


def handle_incoming_message(
    *,
    sender_key: str,
    incoming_text: str,
    store: SessionStore,
    backend: BackendClient,
    settings: Settings,
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
        store.clear(sender_key)
        session = Session(state=ConversationState.WAIT_EVENT_CODE.value, phone_number=phone_number or None)
        session.event_descriptions = saved_descriptions

        store.upsert(sender_key, session)
        return OutgoingMessage(text=WELCOME_TEXT)

    if choice == "help":
        help_text = (
            "You can reply with:\n"
            "- *DEMO* (or your event code) to start\n"
            "- *1* for brochure\n"
            "- *2* to donate\n"
            "- *3* to send a message\n"
            "- *4* for location\n"
            "- *5* for photos\n"
            "- *6* for contact us\n"
            "- *0* to show the menu\n"
            "- *restart* to start over"
        )
        # If we already have a name, include the menu for convenience.
        if session.guest_name:
            help_text = help_text + "\n\n" + _menu_text(session.guest_name)
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
                        + _menu_text(session.guest_name)
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
                    + _menu_text(session.guest_name)
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
                    + _menu_text(session.guest_name)
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
                        + _menu_text(session.guest_name)
                    ),
                    interactive_menu=True,
                    guest_name=session.guest_name,
                )

        # Invalid code (or missing token). Ask for the event code again but keep the guest details.
        session.event_code = None
        session.event_id = None
        session.event_name = None
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
                text=_menu_text(session.guest_name),
                interactive_menu=True,
                guest_name=session.guest_name,
            )

        if choice in {"brochure", "donate", "condolence", "location", "contact", "photos"}:
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
                    text=(
                        "Here is the event brochure.\n"
                        "You may download it to your phone."
                        + _menu_hint()
                    ),
                    media_url=brochure.brochure.media_url,
                )

            if choice == "donate":
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
                return OutgoingMessage(
                    text=_condolence_prompt_text(),
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
                session.state = ConversationState.WAIT_PHOTOS_MENU.value
                store.upsert(sender_key, session)
                return OutgoingMessage(
                    text=_photos_prompt_text(),
                    interactive_menu=True,
                    interactive_button_text="Choose photo option",
                    interactive_section_title="Event Photos",
                    interactive_rows=_photos_rows(),
                )

        # Unrecognized input (including greetings like "hi") — just show the menu.
        return OutgoingMessage(
            text=_menu_text(session.guest_name),
            interactive_menu=True,
            guest_name=session.guest_name,
        )

    if session.state == ConversationState.WAIT_DONATION_AMOUNT.value:
        if not session.guest_name or not session.event_id:
            session.state = ConversationState.MENU.value
            store.upsert(sender_key, session)
            return OutgoingMessage(text="Missing context. Returning to main menu." + _menu_hint())

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
            return OutgoingMessage(text=_menu_text(session.guest_name))

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
            if choice in {"brochure", "donate", "condolence", "location", "contact", "photos"}:
                session.state = ConversationState.MENU.value
                store.upsert(sender_key, session)
                return handle_incoming_message(
                    sender_key=sender_key,
                    incoming_text=choice,
                    store=store,
                    backend=backend,
                    settings=settings,
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

        if choice == "back" or choice == "menu":
            session.state = ConversationState.MENU.value
            session.donation_reference_name = None
            store.upsert(sender_key, session)
            return OutgoingMessage(text=_menu_text(session.guest_name))

        if choice in {"brochure", "donate", "condolence", "location", "contact", "photos"}:
            session.state = ConversationState.MENU.value
            session.donation_reference_name = None
            store.upsert(sender_key, session)
            return handle_incoming_message(
                sender_key=sender_key,
                incoming_text=choice,
                store=store,
                backend=backend,
                settings=settings,
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
                text=_menu_text(session.guest_name),
                interactive_menu=True,
                guest_name=session.guest_name,
            )

        if normalize_text(text).lower() in {"options", "list", "templates"}:
            return OutgoingMessage(
                text=_condolence_prompt_text(),
            )

        message_to_send = normalize_text(text)

        # Allow menu shortcuts in this state.
        if choice in {"brochure", "donate", "condolence", "location", "contact", "photos"}:
            session.state = ConversationState.MENU.value
            store.upsert(sender_key, session)
            return handle_incoming_message(
                sender_key=sender_key,
                incoming_text=choice,
                store=store,
                backend=backend,
                settings=settings,
            )

        if not message_to_send:
            return OutgoingMessage(
                text=_condolence_prompt_text(),
            )

        result = backend.submit_condolence(
            session.event_id,
            session.guest_id,
            message_to_send,
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
                    message_to_send,
                    token=session.backend_token,
                )

        session.state = ConversationState.MENU.value
        store.upsert(sender_key, session)

        if result.status == "ok":
            return OutgoingMessage(
                text=(
                    "Thank you.\n"
                    "Your message has been sent to the family."
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

    if session.state == ConversationState.WAIT_PHOTOS_MENU.value:
        if not session.guest_name or not session.event_id:
            session.state = ConversationState.MENU.value
            store.upsert(sender_key, session)
            return OutgoingMessage(text="Missing context. Returning to main menu." + _menu_hint())

        if choice in {"back", "menu"}:
            session.state = ConversationState.MENU.value
            store.upsert(sender_key, session)
            return OutgoingMessage(
                text=_menu_text(session.guest_name),
                interactive_menu=True,
                guest_name=session.guest_name,
            )

        if choice in {"brochure", "donate", "condolence", "location", "contact", "photos"}:
            session.state = ConversationState.MENU.value
            store.upsert(sender_key, session)
            return handle_incoming_message(
                sender_key=sender_key,
                incoming_text=choice,
                store=store,
                backend=backend,
                settings=settings,
            )

        photo_choice = choice
        if normalize_text(text).lower() in {"1", "upload"}:
            photo_choice = "upload_photos"
        elif normalize_text(text).lower() in {"2", "download"}:
            photo_choice = "download_photos"

        if photo_choice == "upload_photos":
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

            session.state = ConversationState.MENU.value
            store.upsert(sender_key, session)

            if result.status == "ready" and result.photo_link:
                return OutgoingMessage(text=(f"📸 Upload photos here:\n{result.photo_link.url}" + _menu_hint()))

            error = result.error or "Upload photo link is not available right now."
            return OutgoingMessage(text=(f"Sorry, {error}" + _menu_hint()))

        if photo_choice == "download_photos":
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

            session.state = ConversationState.MENU.value
            store.upsert(sender_key, session)

            if result.status == "ready" and result.photo_link:
                return OutgoingMessage(text=(f"🖼️ Download event photos here:\n{result.photo_link.url}" + _menu_hint()))

            error = result.error or "Download photo link is not available right now."
            return OutgoingMessage(text=(f"Sorry, {error}" + _menu_hint()))

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
