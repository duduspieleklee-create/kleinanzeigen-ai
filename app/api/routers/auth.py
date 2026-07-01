from datetime import timedelta

import bcrypt
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.config import settings
from app.api.dependencies import ACCESS_TOKEN_EXPIRE_MINUTES, create_access_token
from app.api.version import register_globals
from app.shared.database import get_db
from app.shared.models import User

router = APIRouter()
templates = Jinja2Templates(directory="app/api/templates")
register_globals(templates)


def _pw_bytes(plain: str) -> bytes:
    # bcrypt only uses the first 72 bytes and raises on longer input, so
    # truncate explicitly to stay compatible with all bcrypt versions.
    return plain.encode("utf-8")[:72]


def _verify(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_pw_bytes(plain), hashed.encode("utf-8"))
    except ValueError:
        return False


def _hash(plain: str) -> str:
    return bcrypt.hashpw(_pw_bytes(plain), bcrypt.gensalt()).decode("utf-8")


def _issue_cookie(user_id: int, username: str) -> RedirectResponse:
    token = create_access_token(
        data={"sub": str(user_id), "username": username},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        secure=True,
        samesite="lax",
    )
    return response


@router.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == username).first()

    if user:
        if not _verify(password, user.hashed_password):
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "Invalid username or password"},
                status_code=401,
            )
    elif username == settings.app_username and password == settings.app_password:
        # Settings-based admin — find or create in DB so FK constraints hold
        user = db.query(User).filter(User.username == settings.app_username).first()
        if not user:
            user = User(
                username=settings.app_username,
                email="admin@local",
                hashed_password=_hash(password),
                is_active=1,
                daily_limit=0,  # admin is exempt from the daily search cap
            )
            db.add(user)
            db.commit()
            db.refresh(user)
    else:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid username or password"},
            status_code=401,
        )

    return _issue_cookie(user.id, user.username)


@router.get("/register")
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@router.post("/register")
async def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
):
    if password != confirm_password:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Passwords do not match", "username": username, "email": email},
            status_code=400,
        )
    if len(password) < 8:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Password must be at least 8 characters", "username": username, "email": email},
            status_code=400,
        )
    if db.query(User).filter(User.username == username).first():
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Username already taken", "email": email},
            status_code=400,
        )
    if db.query(User).filter(User.email == email).first():
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Email already registered", "username": username},
            status_code=400,
        )

    user = User(
        username=username,
        email=email,
        hashed_password=_hash(password),
        is_active=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return _issue_cookie(user.id, user.username)


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/")
    response.delete_cookie("access_token")
    return response
