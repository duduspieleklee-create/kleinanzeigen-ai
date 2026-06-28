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


settings = Settings()
