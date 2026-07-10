import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.auth.google import oauth
from app.api.config import settings
from app.api.dependencies import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    get_current_user,
)
from app.api.emailer import email_configured, send_verification_email
from app.api.security import limiter
from app.api.turnstile import (
    FORM_FIELD as TURNSTILE_FIELD,
    client_ip,
    turnstile_configured,
    verify_turnstile,
)
from app.api.version import register_globals
from app.shared.database import get_db
from app.shared.cookies import ascii_cookie
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


VERIFY_TOKEN_TTL_HOURS = 24


def _base_url(request: Request) -> str:
    # Prefer the configured public origin (behind proxies the request base URL
    # can be the internal address); fall back to the request's own base URL.
    return (settings.public_base_url or str(request.base_url)).rstrip("/")


def _start_verification(request: Request, user: User, db: Session) -> tuple[bool, str]:
    """Assign a fresh verification token and email the link. Returns (ok, error)."""
    user.verify_token = secrets.token_urlsafe(32)[:64]
    user.verify_token_expires_at = datetime.now(timezone.utc) + timedelta(
        hours=VERIFY_TOKEN_TTL_HOURS
    )
    db.commit()
    verify_url = f"{_base_url(request)}/auth/verify?token={user.verify_token}"
    return send_verification_email(user.email, user.username, verify_url)


async def _turnstile_ok(request: Request, token: str) -> bool:
    """Validate the Turnstile token, or pass through when Turnstile is off."""
    if not turnstile_configured():
        return True
    return await verify_turnstile(token, client_ip(request))


TURNSTILE_ERROR = (
    "Bitte bestätige mit dem Sicherheitscheck, dass du kein Roboter bist, "
    "und versuche es erneut."
)


def _dashboard_flash(kind: str, message: str) -> RedirectResponse:
    # Flash cookie values must stay ASCII — Starlette encodes Set-Cookie
    # headers as latin-1 and non-ASCII raises at response time.
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(kind, ascii_cookie(message), max_age=10)
    return response


@router.post("/login")
@limiter.limit("10/minute")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    cf_turnstile_response: str = Form("", alias=TURNSTILE_FIELD),
    db: Session = Depends(get_db),
):
    if not await _turnstile_ok(request, cf_turnstile_response):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": TURNSTILE_ERROR,
             "google_enabled": bool(settings.google_client_id)},
            status_code=400,
        )

    user = db.query(User).filter(User.username == username).first()

    if user:
        if not user.is_active:
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "Invalid username or password",
                 "google_enabled": bool(settings.google_client_id)},
                status_code=401,
            )
        if not _verify(password, user.hashed_password):
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "Invalid username or password",
                 "google_enabled": bool(settings.google_client_id)},
                status_code=401,
            )
    elif (
        settings.bootstrap_admin_enabled
        and username == settings.app_username
        and password == settings.app_password
    ):
        # Settings-based bootstrap admin — create only if missing.
        # If the row already exists but is not admin, reject instead of
        # silently escalating it; otherwise this shared credential becomes
        # an unintended privilege-escalation path.
        user = db.query(User).filter(User.username == settings.app_username).first()
        if not user:
            user = User(
                username=settings.app_username,
                email="admin@local",
                hashed_password=_hash(password),
                is_active=1,
                is_admin=True,
                daily_limit=0,  # admin is exempt from the daily search cap
                email_verified=True,  # bootstrap admin has no real inbox
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            return _issue_cookie(user.id, user.username)
        if user.is_admin:
            return _issue_cookie(user.id, user.username)
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
    return templates.TemplateResponse(
        "register.html",
        {"request": request, "google_enabled": bool(settings.google_client_id)},
    )


@router.post("/register")
@limiter.limit("5/minute")
async def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    cf_turnstile_response: str = Form("", alias=TURNSTILE_FIELD),
    db: Session = Depends(get_db),
):
    if not await _turnstile_ok(request, cf_turnstile_response):
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": TURNSTILE_ERROR,
                "username": username,
                "email": email,
                "google_enabled": bool(settings.google_client_id),
            },
            status_code=400,
        )

    if password != confirm_password:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "Passwords do not match",
                "username": username,
                "email": email,
                "google_enabled": bool(settings.google_client_id),
            },
            status_code=400,
        )
    if len(password) < 8:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "Password must be at least 8 characters",
                "username": username,
                "email": email,
                "google_enabled": bool(settings.google_client_id),
            },
            status_code=400,
        )
    email = email.strip().lower()
    if db.query(User).filter(User.username == username).first():
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "Username already taken",
                "email": email,
                "google_enabled": bool(settings.google_client_id),
            },
            status_code=400,
        )
    if db.query(User).filter(User.email == email).first():
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "Email already registered",
                "username": username,
                "google_enabled": bool(settings.google_client_id),
            },
            status_code=400,
        )

    # Without a configured email provider there is no way to deliver the
    # verification link. In dev, auto-verify so local signup keeps working;
    # everywhere else the account stays unverified (it can log in but not
    # search) until a key is configured and the link is resent.
    auto_verify = not email_configured() and settings.environment == "dev"

    user = User(
        username=username,
        email=email,
        hashed_password=_hash(password),
        is_active=1,
        email_verified=auto_verify,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    if not user.email_verified:
        sent, send_error = _start_verification(request, user, db)
        response = _issue_cookie(user.id, user.username)
        if sent:
            response.set_cookie(
                "flash_success",
                ascii_cookie(
                    "Konto erstellt – prüfe dein Postfach und klicke auf den "
                    "Bestätigungslink, um Suchen zu starten."
                ),
                max_age=10,
            )
        else:
            response.set_cookie(
                "flash_error",
                ascii_cookie(
                    f"Konto erstellt, aber die Bestätigungs-E-Mail konnte nicht gesendet werden: "
                    f"{send_error}. Nutze 'Bestätigungs-E-Mail erneut senden', um es erneut zu versuchen."
                ),
                max_age=10,
            )
        return response

    return _issue_cookie(user.id, user.username)


@router.get("/verify")
@limiter.limit("20/minute")
async def verify_email(
    request: Request,
    token: str = "",
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.verify_token == token).first() if token else None

    if not user:
        return _dashboard_flash(
            "flash_error",
            "This verification link is invalid or was already used. "
            "Use 'Resend verification email' to get a fresh one.",
        )

    expires_at = user.verify_token_expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at is None or expires_at < datetime.now(timezone.utc):
        return _dashboard_flash(
            "flash_error",
            "This verification link has expired. "
            "Use 'Resend verification email' to get a fresh one.",
        )

    user.email_verified = True
    user.verify_token = None
    user.verify_token_expires_at = None
    db.commit()

    return _dashboard_flash(
        "flash_success", "E-Mail bestätigt – du kannst jetzt Suchen starten."
    )


@router.post("/resend-verification")
@limiter.limit("3/hour")
async def resend_verification(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user = db.query(User).filter(User.id == current_user["id"]).first()
    if not user or user.email_verified:
        return _dashboard_flash("flash_success", "Your email is already verified.")

    sent, send_error = _start_verification(request, user, db)
    if sent:
        return _dashboard_flash(
            "flash_success",
            f"Verification email sent to {user.email} - the link is valid "
            f"for {VERIFY_TOKEN_TTL_HOURS} hours.",
        )
    return _dashboard_flash(
        "flash_error", f"Could not send the verification email: {send_error}."
    )


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
            # Google already verified this address (email_verified checked above).
            email_verified=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    # A Google login proves ownership of the address, so it also verifies an
    # account that originally signed up by password with the same email.
    if not user.email_verified:
        user.email_verified = True
        user.verify_token = None
        user.verify_token_expires_at = None
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
