"""
session.py — Signed-cookie session support for the Hearth admin backend.

Uses ``itsdangerous`` to create tamper-proof, time-limited session cookies.
No server-side state is required, which keeps the footprint small on an
embedded device.

Why ``Secure=False``:
    The admin UI is served over plain HTTP on the local hotspot LAN.  There
    is no TLS termination on the device itself.  Using ``Secure=True`` would
    prevent the browser from sending the cookie at all over HTTP.  The LAN
    is a private, isolated network, so the risk of cookie interception is
    acceptable and far lower than breaking the login flow entirely.
"""

import os
from typing import Optional

from fastapi import Cookie, HTTPException, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

_SESSION_COOKIE = "hearth_session"
_SESSION_MAX_AGE = 86_400  # 24 hours


def _serializer() -> URLSafeTimedSerializer:
    secret = os.environ.get("HEARTH_SECRET_KEY")
    if not secret:
        raise RuntimeError(
            "HEARTH_SECRET_KEY environment variable is required but not set. "
            "Set it to a long random string before starting the server."
        )
    return URLSafeTimedSerializer(secret)


def set_session_cookie(response: Response, data: dict) -> None:
    """Write a signed session cookie containing *data* to *response*."""
    token = _serializer().dumps(data)
    response.set_cookie(
        _SESSION_COOKIE,
        token,
        httponly=True,
        samesite="strict",
        secure=False,  # HTTP-only LAN; see module docstring
    )


def clear_session_cookie(response: Response) -> None:
    """Remove the session cookie from *response*."""
    response.delete_cookie(_SESSION_COOKIE, samesite="strict")


async def require_session(
    hearth_session: Optional[str] = Cookie(default=None),
) -> dict:
    """FastAPI dependency — enforce that a valid session cookie is present.

    Returns the deserialized session payload (a dict) on success.
    Raises HTTP 401 if the cookie is absent, expired, or tampered with.
    """
    if not hearth_session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        return _serializer().loads(hearth_session, max_age=_SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        raise HTTPException(status_code=401, detail="Not authenticated")
