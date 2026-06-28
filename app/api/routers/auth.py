from fastapi import APIRouter, Request
from starlette.responses import RedirectResponse
from app.api.auth.google import oauth
import os

router = APIRouter()

@router.get("/login/google")
async def login_via_google(request: Request):
    redirect_uri = request.url_for("auth_google_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/auth/google/callback", name="auth_google_callback")
async def auth_google_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get("userinfo")

    if not user_info:
        return {"error": "Failed to get user info from Google"}

    # For Milestone 1: Just return user info
    # Later we can create/find user in database
    return {
        "message": "Google login successful",
        "user": {
            "email": user_info.get("email"),
            "name": user_info.get("name"),
            "picture": user_info.get("picture")
        },
        "access_token": token.get("access_token")
    }
