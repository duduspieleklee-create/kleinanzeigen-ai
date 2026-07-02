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

    # Google OAuth 2.0 credentials (Google Cloud Console → Credentials).
    # Leave empty to disable the "Sign in with Google" button.
    google_client_id: str = ""
    google_client_secret: str = ""

    # VAPID keys for Web Push notifications. Leave empty to disable push.
    vapid_private_key: str = ""
    vapid_public_key: str = ""
    vapid_email: str = "mailto:admin@example.com"

    # Login credentials — set APP_USERNAME / APP_PASSWORD env vars to override.
    app_username: str = "admin"
    app_password: str = "KaSearch2026"

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

    # Build/version metadata — injected at image build time via Docker build args.
    app_version: str = "dev"
    git_sha: str = "local"
    build_number: str = "0"
    build_time: str = "unknown"

    # Rotating proxy support.
    proxy_test_url: str = "https://www.kleinanzeigen.de/"
    proxy_test_timeout: int = 15

    @model_validator(mode="after")
    def _reject_insecure_defaults_in_prod(self):
        """Fail fast if the app is started outside dev with built-in secrets.

        A known SECRET_KEY lets anyone forge auth tokens; a known APP_PASSWORD
        is an open admin login. Both must be overridden before deploying.
        """
        if self.environment != "dev":
            problems = []
            if self.secret_key == "change-me-in-production":
                problems.append("SECRET_KEY is still the built-in default")
            elif len(self.secret_key) < 32:
                problems.append("SECRET_KEY must be at least 32 characters")
            if self.app_password == "KaSearch2026":
                problems.append("APP_PASSWORD is still the built-in default")
            if problems:
                raise ValueError(
                    f"Insecure configuration for environment='{self.environment}': "
                    + "; ".join(problems)
                    + ". Set these via environment variables before deploying."
                )
        return self


settings = Settings()
