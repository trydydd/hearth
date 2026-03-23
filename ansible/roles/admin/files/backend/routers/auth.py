"""
routers/auth.py — Authentication endpoints for the CafeBox admin backend.

POST /api/admin/login                — validate credentials; issue session cookie.
POST /api/admin/logout               — clear session cookie.
POST /api/admin/auth/change-password — change the admin password.
"""

import os
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from auth import verify_password
from csrf import verify_csrf_token
from session import clear_session_cookie, require_session, set_session_cookie

router = APIRouter(prefix="/api/admin")

_FIRST_BOOT_MARKER = Path(
    os.environ.get("CAFEBOX_FIRST_BOOT_MARKER", "/run/cafebox/initial-password")
)
_MIN_PASSWORD_LENGTH = 12


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


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


@router.post(
    "/auth/change-password",
    dependencies=[Depends(require_session), Depends(verify_csrf_token)],
)
async def change_password(
    body: ChangePasswordRequest,
    session: dict = Depends(require_session),
):
    """Change the admin account password.

    * Validates the current password before updating.
    * Enforces a minimum length of 12 characters.
    * Updates the system account via ``chpasswd``.
    * Deletes ``/run/cafebox/initial-password`` on success to clear the
      first-boot banner.
    """
    # Validate minimum length first to give a clear 422 before touching auth
    if len(body.new_password) < _MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"New password must be at least {_MIN_PASSWORD_LENGTH} characters",
        )

    username: str = session.get("username", "admin")

    if not verify_password(username, body.current_password):
        raise HTTPException(status_code=403, detail="Current password is incorrect")

    # Update system account password via chpasswd (no shell — safe)
    try:
        result = subprocess.run(
            ["chpasswd"],
            input=f"{username}:{body.new_password}",
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=500, detail="chpasswd not available in this environment"
        )
    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=result.stderr or "chpasswd failed",
        )

    # Clear the first-boot marker so the password banner disappears
    try:
        _FIRST_BOOT_MARKER.unlink(missing_ok=True)
    except OSError:
        pass  # non-fatal; marker may already be gone or unwritable

    return {"status": "ok"}
