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

    # Celery Beat scheduled search parameters — override via env vars.
    beat_keywords: str = "handwerker"
    beat_location: str = "berlin"
    beat_price_max: int = 200


settings = Settings()
