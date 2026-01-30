import os


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


class Settings:
    def __init__(self) -> None:
        # Channel selection
        # - meta: WhatsApp Cloud API webhook + Graph API replies
        # - twilio: Twilio WhatsApp webhook + TwiML replies (legacy)
        self.channel = os.getenv("CHANNEL", "meta").strip().lower()
        self.enable_twilio_webhook = _env_bool("ENABLE_TWILIO_WEBHOOK", False)

        self.port = _env_int("PORT", 5000)
        self.public_base_url = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
        self.session_ttl_seconds = _env_int("SESSION_TTL_SECONDS", 25 * 60)

        # Backend (live)
        self.backend_base_url = os.getenv("BACKEND_BASE_URL", "").strip()
        self.backend_timeout_seconds = _env_int("BACKEND_TIMEOUT_SECONDS", 15)
        self.backend_auth_bearer_token = os.getenv("BACKEND_AUTH_BEARER_TOKEN", "").strip()

        # Optional defaults used until event endpoints are available.
        self.default_event_name = os.getenv("DEFAULT_EVENT_NAME", "Yala Event").strip() or "Yala Event"
        self.default_event_location = os.getenv("DEFAULT_EVENT_LOCATION", "").strip() or None
        self.default_event_location_url = os.getenv("DEFAULT_EVENT_LOCATION_URL", "").strip() or None

        # Phase 1 is deterministic; keep agent off by default.
        self.enable_agent = _env_bool("ENABLE_AGENT", False)
        self.verify_twilio_signatures = _env_bool("VERIFY_TWILIO_SIGNATURES", False)

        # Twilio outbound (required only for interactive menu mode)
        self.twilio_account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.twilio_whatsapp_from = os.getenv("TWILIO_WHATSAPP_FROM", "")

        self.twilio_auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.groq_api_key = os.getenv("GROQ_API_KEY", "")

        # Interactive menu via Twilio Content API.
        # Mode: off | content
        self.interactive_menu_mode = os.getenv("INTERACTIVE_MENU_MODE", "off").strip().lower()
        self.twilio_content_sid_menu = os.getenv("TWILIO_CONTENT_SID_MENU", "")

        # Meta WhatsApp Cloud API
        self.meta_api_version = os.getenv("META_API_VERSION", "v20.0").strip()
        self.meta_access_token = os.getenv("META_WA_ACCESS_TOKEN", "")
        self.meta_phone_number_id = os.getenv("META_WA_PHONE_NUMBER_ID", "")
        self.meta_webhook_verify_token = os.getenv("META_WEBHOOK_VERIFY_TOKEN", "")
        self.meta_app_secret = os.getenv("META_APP_SECRET", "")
        self.verify_meta_signatures = _env_bool("VERIFY_META_SIGNATURES", True)

        # Debug helpers (local dev only)
        self.debug_endpoints = _env_bool("DEBUG_ENDPOINTS", False)
        self.debug_token = os.getenv("DEBUG_TOKEN", "")


SETTINGS = Settings()
