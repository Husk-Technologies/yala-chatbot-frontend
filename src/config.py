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

        # Optional: Redis for shared session storage and cross-worker de-dupe.
        # Example: redis://localhost:6379/0
        self.redis_url = os.getenv("REDIS_URL", "").strip()
        self.redis_key_prefix = os.getenv("REDIS_KEY_PREFIX", "wa_bot").strip() or "wa_bot"
        self.redis_required = _env_bool("REDIS_REQUIRED", False)

        # Error tracking via Sentry.  Set SENTRY_DSN to enable.
        # Example: https://<key>@o<org>.ingest.sentry.io/<project>
        self.sentry_dsn = os.getenv("SENTRY_DSN", "").strip()
        self.sentry_environment = os.getenv("SENTRY_ENVIRONMENT", "production").strip() or "production"
        self.sentry_traces_sample_rate = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1") or "0.1")


SETTINGS = Settings()
