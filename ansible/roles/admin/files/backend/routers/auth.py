"""
routers/auth.py — Login and logout endpoints for the CafeBox admin backend.

POST /api/admin/login   — validate credentials and issue a session cookie.
POST /api/admin/logout  — clear the session cookie.
"""

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from auth import verify_password
from session import clear_session_cookie, set_session_cookie

router = APIRouter(prefix="/api/admin")


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(body: LoginRequest, response: Response):
    """Authenticate with the ``cafebox-admin`` system account.

    Returns HTTP 200 and sets a signed ``cafebox_session`` cookie on success.
    Returns HTTP 401 when the credentials are invalid.
    """
    if not verify_password(body.username, body.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    set_session_cookie(response, {"username": body.username})
    return {"status": "ok"}


@router.post("/logout")
async def logout(response: Response):
    """Clear the session cookie, effectively logging the user out."""
    clear_session_cookie(response)
    return {"status": "ok"}
