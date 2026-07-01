import secrets
from datetime import timedelta

import bcrypt
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.auth.google import oauth
from app.api.config import settings
from app.api.dependencies import ACCESS_TOKEN_EXPIRE_MINUTES, create_access_token
from app.api.security import limiter
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
        # Only require HTTPS for the cookie outside local dev, otherwise the
        # cookie is silently dropped over plain-http and login "does nothing".
        secure=settings.environment != "dev",
        samesite="lax",
    )
    return response


def _allowed_emails() -> set[str]:
    return {e.strip().lower() for e in settings.allowed_emails.split(",") if e.strip()}


def _admin_emails() -> set[str]:
    return {e.strip().lower() for e in settings.admin_emails.split(",") if e.strip()}


@router.post("/login")
@limiter.limit("10/minute")
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
                {"request": request, "error": "Invalid username or password",
                 "google_enabled": bool(settings.google_client_id)},
                status_code=401,
            )
    elif username == settings.app_username and password == settings.app_password:
        # Settings-based bootstrap admin — find or create in DB so FK
        # constraints hold, and make sure the row is flagged as admin.
        user = db.query(User).filter(User.username == settings.app_username).first()
        if not user:
            user = User(
                username=settings.app_username,
                email="admin@local",
                hashed_password=_hash(password),
                is_active=1,
                is_admin=True,
                daily_limit=0,  # admin is exempt from the daily search cap
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        elif not user.is_admin:
            user.is_admin = True
            db.commit()
            db.refresh(user)
    else:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid username or password",
             "google_enabled": bool(settings.google_client_id)},
            status_code=401,
        )

    return _issue_cookie(user.id, user.username)


@router.get("/register")
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@router.post("/register")
@limiter.limit("5/minute")
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


# ── Google OAuth 2.0 (OpenID Connect) ─────────────────────────────────────────

@router.get("/google/login")
async def google_login(request: Request):
    if not settings.google_client_id:
        return RedirectResponse(url="/")
    redirect_uri = request.url_for("google_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback", name="google_callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Google sign-in failed. Please try again.",
             "google_enabled": bool(settings.google_client_id)},
            status_code=401,
        )

    userinfo = token.get("userinfo") or {}
    email = (userinfo.get("email") or "").lower()
    email_verified = userinfo.get("email_verified", True)
    if not email or not email_verified:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Google did not return a verified email.",
             "google_enabled": bool(settings.google_client_id)},
            status_code=401,
        )

    # Enforce the email allow-list when one is configured.
    allow = _allowed_emails()
    if allow and email not in allow:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "This Google account is not authorised.",
             "google_enabled": bool(settings.google_client_id)},
            status_code=403,
        )

    user = db.query(User).filter(User.email == email).first()
    if not user:
        base = (email.split("@")[0] or "user")[:40]
        username = base
        suffix = 1
        while db.query(User).filter(User.username == username).first():
            suffix += 1
            username = f"{base}{suffix}"[:50]
        user = User(
            username=username,
            email=email,
            # OAuth users never sign in with a password; store an unusable one.
            hashed_password=_hash(secrets.token_urlsafe(32)),
            is_active=1,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    # Promote configured admin emails. Applies to both brand-new and existing
    # accounts, so admin rights can be granted after the account already exists.
    if email in _admin_emails() and not user.is_admin:
        user.is_admin = True
        user.daily_limit = 0  # admins are exempt from the daily search cap
        db.commit()
        db.refresh(user)

    return _issue_cookie(user.id, user.username)


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/")
    response.delete_cookie("access_token")
    return response
