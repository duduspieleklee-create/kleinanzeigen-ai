from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def get_current_user(token: str = Depends(oauth2_scheme)):
    # TODO: Replace with real JWT validation
    # For now, return a dummy user for development
    if token != "fake-jwt-token":
        raise HTTPException(status_code=401, detail="Invalid token")
    
    return {"id": 1, "username": "demo_user"}
