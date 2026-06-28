import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL environment variable is not set.\n"
        "Set it to your PostgreSQL connection string, e.g.:\n"
        "  export DATABASE_URL=postgresql://user:password@host:5432/kleinanzeigen_ai\n"
        "For local development, add it to a .env file (never commit .env)."
    )

# Normalize async driver variants to their sync equivalents.
# asyncpg is an async-only driver and cannot be used with synchronous
# SQLAlchemy (create_engine). Strip the driver suffix so SQLAlchemy
# falls back to psycopg2, which is the correct sync driver.
_SYNC_URL = (
    DATABASE_URL
    .replace("postgresql+asyncpg://", "postgresql://")
    .replace("postgres+asyncpg://", "postgresql://")
)

engine = create_engine(_SYNC_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
