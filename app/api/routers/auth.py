from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from datetime import timedelta
from passlib.context import CryptContext

from app.api.dependencies import create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(request: LoginRequest):
    # TODO: Replace with real user lookup from database
    # For Milestone 1, we use a hardcoded demo user
    if request.username == "demo" and request.password == "demo123":
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": "1", "username": request.username},
            expires_delta=access_token_expires
        )
        return {"access_token": access_token, "token_type": "bearer"}
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect username or password"
    )
