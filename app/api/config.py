from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    environment: str = "dev"
    # Use a sync driver (psycopg2) here — the app uses synchronous SQLAlchemy.
    # Do NOT use postgresql+asyncpg:// — asyncpg is async-only and incompatible
    # with create_engine() and Alembic's engine_from_config().
    database_url: str = "postgresql://user:password@localhost/kleinanzeigen"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "change-me-in-production"
    api_token_expire_minutes: int = 60

    # User ID used for ScrapeTask records created by Celery Beat scheduled runs.
    system_user_id: int = 1

    # Comma-separated list of Google email addresses allowed to log in.
    # Leave empty to allow any Google account (open registration).
    allowed_emails: str = ""

    # Comma-separated list of Google email addresses granted admin rights on
    # login. Admins manage background searches / proxies and can send test
    # push notifications. Leave empty to auto-promote no one.
    admin_emails: str = ""

    # Google OAuth 2.0 credentials (Google Cloud Console → Credentials).
    # Leave empty to disable the "Sign in with Google" button.
    google_client_id: str = ""
    google_client_secret: str = ""

    # VAPID keys for Web Push notifications. Leave empty to disable push.
    vapid_private_key: str = ""
    vapid_public_key: str = ""
    vapid_email: str = "mailto:admin@example.com"

    # Settings-based bootstrap admin login — a fallback so the very first
    # admin account can be created before any Google-OAuth admin exists
    # (via ADMIN_EMAILS). It's a single shared credential with no per-person
    # audit trail, so once real admin accounts exist, set
    # BOOTSTRAP_ADMIN_ENABLED=false to close this path off.
    #
    # IMPORTANT: there is NO built-in default password. APP_USERNAME / APP_PASSWORD
    # MUST be supplied via env (.env). Leaving APP_PASSWORD empty keeps the
    # bootstrap path disabled even when BOOTSTRAP_ADMIN_ENABLED=true, so the app
    # never ships with a known credential.
    bootstrap_admin_enabled: bool = True
    app_username: str = "admin"
    app_password: str = ""

    # ── Stripe billing (leave empty to disable paid plans) ────────────────────
    # Secret API key from https://dashboard.stripe.com/apikeys
    stripe_secret_key: str = ""
    # Webhook signing secret for the /billing/webhook endpoint
    stripe_webhook_secret: str = ""
    # Recurring Price IDs (price_...) for the Core and Pro plans
    stripe_price_core: str = ""
    stripe_price_pro: str = ""
    # Public origin used for Stripe redirect URLs, e.g. https://app.example.com.
    # Falls back to the request base URL when empty.
    public_base_url: str = ""

    # ── Email sending via Resend (verification emails) ────────────────────────
    # API key from https://resend.com/api-keys. Leave empty to disable email
    # sending — in dev, password signups are then auto-verified for convenience;
    # outside dev they stay unverified (and cannot search) until a key is set.
    resend_api_key: str = ""
    # From address. The Resend sandbox sender works without domain verification
    # but can only deliver to the Resend account owner's own inbox — verify a
    # domain in Resend and change this before opening registration to others.
    email_from: str = "onboarding@resend.dev"

    # Build/version metadata — injected at image build time via Docker build args.
    app_version: str = "dev"
    git_sha: str = "local"
    build_number: str = "0"
    build_time: str = "unknown"

    # Rotating proxy support.
    proxy_test_url: str = "https://www.kleinanzeigen.de/"
    proxy_test_timeout: int = 15

    # ── Cloudflare Turnstile (bot / abuse protection on public forms) ─────────
    # Site key is public and rendered into the login/register widget; the
    # secret key is used server-side to validate the token via the siteverify
    # API. Leave both empty to disable Turnstile (dev/local convenience) — the
    # forms then submit without a challenge. Get keys from
    # https://dash.cloudflare.com/ → Turnstile → Add site.
    turnstile_site_key: str = ""
    turnstile_secret_key: str = ""

    # ── Error tracking (Sentry) ────────────────────────────────────────────────
    # DSN from https://sentry.io/ (Settings → Projects → <project> → Client Keys).
    # Leave empty to disable — no-op in dev by default even if set, unless
    # SENTRY_ENABLE_IN_DEV is also set, to avoid noisy local-dev events.
    sentry_dsn: str = ""
    sentry_enable_in_dev: bool = False
    # Fraction of requests/tasks traced for performance monitoring (0 = errors only).
    sentry_traces_sample_rate: float = 0.0
    # Fraction of traced transactions profiled (0 = off). Only meaningful when
    # traces_sample_rate > 0.
    sentry_profiles_sample_rate: float = 0.0

    # ── Custom model endpoint (OpenAI-compatible) ─────────────────────────────
    # Lets Smart Search Suggestions query any OpenAI-compatible Chat Completions
    # API for higher-quality, context-aware suggestions.
    #
    # EITHER set CUSTOM_MODEL_ENDPOINT + CUSTOM_MODEL_NAME directly (full control),
    # OR set CUSTOM_MODEL_PROVIDER to a preset that fills endpoint/auth defaults:
    #   ollama   → http://localhost:11434/v1   (no key)
    #   openai   → https://api.openai.com/v1   (needs CUSTOM_MODEL_API_KEY)
    #   together → https://api.together.xyz/v1 (needs CUSTOM_MODEL_API_KEY)
    # Explicit CUSTOM_MODEL_ENDPOINT / *_API_KEY always win over the preset.
    custom_model_provider: str = ""
    custom_model_endpoint: str = ""
    custom_model_api_key: str = ""
    custom_model_name: str = ""
    # Optional temperature / max tokens for the suggestion call.
    custom_model_temperature: float = 0.3
    custom_model_max_tokens: int = 256

    # Preset → default (endpoint, needs_api_key). Explicit config overrides these.
    _PROVIDER_PRESETS = {
        "ollama": ("http://localhost:11434/v1", False),
        "openai": ("https://api.openai.com/v1", True),
        "together": ("https://api.together.xyz/v1", True),
    }

    @property
    def custom_model_endpoint_resolved(self) -> str:
        """Effective endpoint: explicit setting wins, else provider preset default."""
        if self.custom_model_endpoint:
            return self.custom_model_endpoint
        preset = self._PROVIDER_PRESETS.get(self.custom_model_provider.lower())
        return preset[0] if preset else ""

    @property
    def custom_model_api_key_resolved(self) -> str:
        """Effective API key: explicit setting wins, else provider preset (none)."""
        if self.custom_model_api_key:
            return self.custom_model_api_key
        return ""  # presets either need no key (ollama) or require an explicit one

    @property
    def custom_model_enabled(self) -> bool:
        """True when a usable endpoint+model are resolvable (provider or explicit)."""
        return bool(self.custom_model_endpoint_resolved and self.custom_model_name)

    @property
    def turnstile_enabled(self) -> bool:
        """True only when both Turnstile keys are configured.

        Both are required: without the site key the widget can't render, and
        without the secret key the token can't be validated server-side.
        """
        return bool(self.turnstile_site_key and self.turnstile_secret_key)

    @model_validator(mode="after")
    def _reject_insecure_defaults_in_prod(self):
        """Fail fast if the app is started outside dev with built-in secrets.

        A known SECRET_KEY lets anyone forge auth tokens; a known or weak
        APP_PASSWORD is an open admin login. Both must be overridden before
        deploying — unless the bootstrap admin path is deliberately disabled.
        """
        # test mirrors dev: no production secrets required (CI sets a short
        # SECRET_KEY and no APP_PASSWORD). Every other env-branch in the app
        # already treats test like dev (see auth.py secure/auto_verify,
        # main.py allow_origins/https_only), so enforce secrets only outside
        # dev and test.
        if self.environment not in ("dev", "test"):
            problems = []
            if self.secret_key == "change-me-in-production":
                problems.append("SECRET_KEY is still the built-in default")
            elif len(self.secret_key) < 32:
                problems.append("SECRET_KEY must be at least 32 characters")
            if self.bootstrap_admin_enabled:
                # Reject the previously-hardcoded credential if it somehow
                # survives in an env file — it is public in git history.
                if self.app_password == "KaSearch2026":
                    problems.append(
                        "APP_PASSWORD is the old hardcoded default; it is public "
                        "in git history and must be rotated to a fresh secret"
                    )
                elif not self.app_password:
                    problems.append(
                        "APP_PASSWORD is empty; set a strong password (>=12 chars) "
                        "via env, or set BOOTSTRAP_ADMIN_ENABLED=false"
                    )
                elif len(self.app_password) < 12:
                    problems.append("APP_PASSWORD must be at least 12 characters")
            if problems:
                raise ValueError(
                    f"Insecure configuration for environment='{self.environment}': "
                    + "; ".join(problems)
                    + ". Set these via environment variables before deploying, "
                    + "or set BOOTSTRAP_ADMIN_ENABLED=false if it's no longer needed."
                )
        return self


settings = Settings()
