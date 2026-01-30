from __future__ import annotations

from dataclasses import dataclass

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
        "message": "condolence",
        "send message": "condolence",

        "4": "location",
        "location": "location",
        "venue": "location",
        "address": "location",
        "where": "location",
        "map": "location",
    }

    return aliases.get(t, t)


def _menu_text(guest_name: str) -> str:
    return (
        f"Thank you, {guest_name}.\n"
        "How can we help you today?\n\n"
        "1. 📄 Download event brochure\n"
        "2. 💝 Give / Donate\n"
        "3. 🕊️ Send condolence / message\n"
        "4. 📍 Location"
    )


def _normalize_event_code(code: str) -> str:
    return (code or "").strip().upper()


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

        # Pre-fetch guest profile if already registered.
        if phone_number:
            guest = backend.check_guest_registration(phone_number)
            if guest.status == "found" and guest.guest:
                session.guest_id = guest.guest.guest_id
                session.guest_name = guest.guest.full_name
                session.backend_token = guest.token
                session.funeral_unique_codes = guest.guest.funeral_unique_codes

        store.upsert(sender_key, session)
        return OutgoingMessage(text=WELCOME_TEXT)

    # Global commands
    if choice == "restart":
        store.clear(sender_key)
        session = Session(state=ConversationState.WAIT_EVENT_CODE.value, phone_number=phone_number or None)

        if phone_number:
            guest = backend.check_guest_registration(phone_number)
            if guest.status == "found" and guest.guest:
                session.guest_id = guest.guest.guest_id
                session.guest_name = guest.guest.full_name
                session.backend_token = guest.token
                session.funeral_unique_codes = guest.guest.funeral_unique_codes

        store.upsert(sender_key, session)
        return OutgoingMessage(text=WELCOME_TEXT)

    if choice == "help":
        help_text = (
            "You can reply with:\n"
            "- *DEMO* (or your event code) to start\n"
            "- *1* for brochure\n"
            "- *2* to donate\n"
            "- *3* to send a message\n"
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
        # If we don't have a token yet, collect the code and ask for the guest name first.
        if not session.backend_token:
            session.event_code = text
            session.state = ConversationState.WAIT_NAME.value
            store.upsert(sender_key, session)
            return OutgoingMessage(text="Thank you. Please enter your *name* to continue.")

        # Optimization: if the guest profile already lists this event code, do not call
        # verify-funeral-details again (backend may be non-idempotent).
        if _guest_has_event_code(session, text):
            code = _normalize_event_code(text)
            session.event_code = code
            session.event_id = code
            session.event_name = _event_display_name(settings, code)
            session.event_location = settings.default_event_location
            session.event_location_url = settings.default_event_location_url

            if session.guest_name:
                session.state = ConversationState.MENU.value
                store.upsert(sender_key, session)
                return OutgoingMessage(
                    text=_menu_text(session.guest_name),
                    interactive_menu=True,
                    guest_name=session.guest_name,
                )

            session.state = ConversationState.WAIT_NAME.value
            store.upsert(sender_key, session)
            return OutgoingMessage(
                text=(
                    "Thank you.\n"
                    f"This is the funeral/event of *{session.event_name}*.\n\n"
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

        # Cache the verified code into the guest's known codes so we can skip re-verification.
        existing = session.funeral_unique_codes or []
        if code and not any(_normalize_event_code(str(x)) == code for x in existing):
            session.funeral_unique_codes = [*existing, code]

        # If we already know the guest name from the backend, go straight to the menu.
        if session.guest_name:
            session.state = ConversationState.MENU.value
            store.upsert(sender_key, session)
            return OutgoingMessage(
                text=_menu_text(session.guest_name),
                interactive_menu=True,
                guest_name=session.guest_name,
            )

        session.state = ConversationState.WAIT_NAME.value
        store.upsert(sender_key, session)

        return OutgoingMessage(
            text=(
                "Thank you.\n"
                f"This is the funeral/event of *{session.event_name}*.\n\n"
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

        # Now that we (likely) have a token, verify the previously collected event code.
        if not session.event_code:
            session.state = ConversationState.WAIT_EVENT_CODE.value
            store.upsert(sender_key, session)
            return OutgoingMessage(text=WELCOME_TEXT)

        # If the guest profile already includes the code, skip verifying (backend may reject repeats).
        if session.backend_token and _guest_has_event_code(session, session.event_code):
            code = _normalize_event_code(session.event_code)
            session.event_id = code
            session.event_name = _event_display_name(settings, code)
            session.event_location = settings.default_event_location
            session.event_location_url = settings.default_event_location_url

            session.state = ConversationState.MENU.value
            store.upsert(sender_key, session)
            return OutgoingMessage(
                text=_menu_text(session.guest_name),
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

            if result.status == "found" and result.event:
                session.event_id = result.event.event_id
                session.event_name = result.event.name
                session.event_location = result.event.location
                session.event_location_url = result.event.location_url

                code = _normalize_event_code(session.event_code)
                existing = session.funeral_unique_codes or []
                if code and not any(_normalize_event_code(str(x)) == code for x in existing):
                    session.funeral_unique_codes = [*existing, code]

                session.state = ConversationState.MENU.value
                store.upsert(sender_key, session)
                return OutgoingMessage(
                    text=_menu_text(session.guest_name),
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

        if choice in {"brochure", "donate", "condolence", "location"}:
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
                    return OutgoingMessage(text=f"Sorry, {error}\n\n" + _menu_text(session.guest_name))

                # Stay in MENU state and show menu again after sending the brochure.
                store.upsert(sender_key, session)
                return OutgoingMessage(
                    text=(
                        "Here is the event brochure.\n"
                        "You may download it to your phone.\n\n"
                        + _menu_text(session.guest_name)
                    ),
                    media_url=brochure.brochure.media_url,
                )

            if choice == "donate":
                if not session.event_id:
                    return OutgoingMessage(text="Missing event context. Please type 'restart'.")

                intent = backend.create_donation_intent(session.event_id, session.guest_name)
                if intent.status == "ready" and intent.intent:
                    return OutgoingMessage(text=intent.intent.instructions + "\n\n" + _menu_text(session.guest_name))

                if intent.status == "unavailable" and intent.intent:
                    return OutgoingMessage(text=intent.intent.instructions + "\n\n" + _menu_text(session.guest_name))

                return OutgoingMessage(
                    text=(
                        "We couldn’t complete the donation right now.\n"
                        "Please try again later.\n\n" + _menu_text(session.guest_name)
                    )
                )

            if choice == "condolence":
                session.state = ConversationState.WAIT_CONDOLENCE.value
                store.upsert(sender_key, session)
                return OutgoingMessage(
                    text=(
                        "Please type the message you would like to send to the family.\n"
                        "(Reply *back* to return to the menu.)"
                    )
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
                    if loc.location.day:
                        lines.append(f"Day: {loc.location.day}")
                    if loc.location.time:
                        lines.append(f"Time: {loc.location.time}")
                    if loc.location.link:
                        lines.append(f"Map: {loc.location.link}")
                else:
                    error = loc.error or "Location details are not available yet."
                    lines = [f"Sorry, {error}"]

                lines.append("")
                lines.append(_menu_text(session.guest_name))
                return OutgoingMessage(text="\n".join(lines))

        return OutgoingMessage(
            text=(
                "Please reply with *1*, *2*, *3*, or *4* (or type *brochure*, *donate*, *message*, *location*).\n\n"
                + _menu_text(session.guest_name)
            )
        )

    if session.state == ConversationState.WAIT_CONDOLENCE.value:
        if not session.guest_name or not session.event_id:
            session.state = ConversationState.MENU.value
            store.upsert(sender_key, session)
            return OutgoingMessage(text="Missing context. Returning to main menu.\n\n" + _menu_text(session.guest_name or ""))

        if not session.guest_id:
            session.state = ConversationState.MENU.value
            store.upsert(sender_key, session)
            return OutgoingMessage(
                text=(
                    "We couldn’t identify your guest profile.\n"
                    "Please type *restart* and try again.\n\n" + _menu_text(session.guest_name)
                )
            )

        if choice == "back" or choice == "menu":
            session.state = ConversationState.MENU.value
            store.upsert(sender_key, session)
            return OutgoingMessage(text=_menu_text(session.guest_name))

        if not text:
            return OutgoingMessage(text="Please type the message you would like to send to the family.")

        result = backend.submit_condolence(
            session.event_id,
            session.guest_id,
            text,
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
                    text,
                    token=session.backend_token,
                )

        session.state = ConversationState.MENU.value
        store.upsert(sender_key, session)

        if result.status == "ok":
            return OutgoingMessage(
                text=(
                    "Thank you.\n"
                    "Your message has been sent to the family.\n\n" + _menu_text(session.guest_name)
                )
            )

        return OutgoingMessage(
            text=(
                "Sorry, we couldn’t send your message right now.\n"
                "Please try again later.\n\n" + _menu_text(session.guest_name)
            )
        )

    # Unknown state: reset politely
    store.clear(sender_key)
    return OutgoingMessage(text=WELCOME_TEXT)
