from typing import Generator
from app.shared.database import SessionLocal


def get_db() -> Generator:
    """FastAPI dependency that provides a SQLAlchemy database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
