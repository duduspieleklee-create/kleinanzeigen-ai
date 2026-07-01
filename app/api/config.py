from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    environment: str = "dev"
    # Use a sync driver (psycopg2) here — the app uses synchronous SQLAlchemy.
    # Do NOT use postgresql+asyncpg:// — asyncpg is async-only and incompatible
    # with create_engine() and Alembic's engine_from_config().
    database_url: str = "postgresql://user:password@localhost/kleinanzeigen"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "change-me-in-production"
    api_token_expire_minutes: int = 60

    # User ID used for ScrapeTask records created by Celery Beat scheduled runs.
    # Create a dedicated "scheduler" user in your database and set this to their ID.
    # Defaults to 1 (assumes first seeded user). Set via SYSTEM_USER_ID env var.
    system_user_id: int = 1

    # Comma-separated list of Google email addresses allowed to log in.
    # Leave empty to allow any Google account (open registration).
    # Example: "alice@example.com,bob@example.com"
    allowed_emails: str = ""

    # VAPID keys for Web Push notifications.
    # Generate with: python3 -c "from py_vapid import Vapid; v=Vapid(); v.generate_keys(); print(v.private_pem())"
    # Set VAPID_PUBLIC_KEY to the base64url-encoded uncompressed EC public key (87 chars).
    # Leave empty to disable push notifications.
    vapid_private_key: str = ""
    vapid_public_key: str = ""
    vapid_email: str = "mailto:admin@example.com"

    # Login credentials — set APP_USERNAME / APP_PASSWORD env vars to override.
    app_username: str = "admin"
    app_password: str = "KaSearch2026"

    # Build/version metadata — injected at image build time via Docker build
    # args (see app/api/Dockerfile and the CI build job). Defaults apply to
    # local development where the image wasn't built by CI.
    app_version: str = "dev"      # e.g. "1.0.42"
    git_sha: str = "local"        # full commit SHA
    build_number: str = "0"       # CI run number / deployment number
    build_time: str = "unknown"   # ISO-8601 UTC build timestamp

    # Rotating proxy support. When an admin adds a proxy it must pass a live
    # test — fetching this URL through the proxy — before it joins the pool.
    # The kleinanzeigen homepage is the right target: a proxy that can't reach
    # it is useless for scraping.
    proxy_test_url: str = "https://www.kleinanzeigen.de/"
    proxy_test_timeout: int = 15


settings = Settings()
