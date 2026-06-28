from fastapi import Depends
from sqlalchemy.orm import Session
from app.shared.database import get_db


def get_current_user(db: Session = Depends(get_db)):
    # TODO: Implement real JWT validation + user lookup
    # For now, return a dummy user for development
    return {"id": 1, "username": "demo_user"}
