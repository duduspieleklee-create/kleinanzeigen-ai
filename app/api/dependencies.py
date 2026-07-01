from app.api.config import settings


def get_current_user(*args, **kwargs) -> dict:
    return {"id": settings.system_user_id, "username": "admin", "email": ""}
