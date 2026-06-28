from fastapi import APIRouter

router = APIRouter()


@router.post("/token")
async def get_token():
    """Issue an API token (placeholder)."""
    # TODO: implement real authentication
    return {"access_token": "placeholder", "token_type": "bearer"}
