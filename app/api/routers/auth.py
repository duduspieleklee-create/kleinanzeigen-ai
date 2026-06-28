from fastapi import APIRouter, Request, Depends
from starlette.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import timedelta
import os

from app.api.auth.google import oauth
from app.shared.database import get_db
from app.shared.models import User
from app.api.dependencies import create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES

router = APIRouter()


@router.get("/login/google")
async def login_via_google(request: Request):
    redirect_uri = request.url_for("auth_google_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/auth/google/callback", name="auth_google_callback")
async def auth_google_callback(request: Request, db: Session = Depends(get_db)):
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get("userinfo")

    if not user_info:
        return {"error": "Failed to retrieve user information from Google"}

    email = user_info.get("email")
    name = user_info.get("name")

    # Check if user already exists
    user = db.query(User).filter(User.email == email).first()

    if not user:
        # Create new user (Google users won't have a password)
        user = User(
            username=name or email.split("@")[0],
            email=email,
            hashed_password="google-oauth"  # Placeholder since it's Google auth
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    # Create JWT token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id), "username": user.username},
        expires_delta=access_token_expires
    )

    # For Milestone 1: Return token + user info
    # In production you would redirect to frontend with token
    return {
        "message": "Google login successful",
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email
        }
    }
