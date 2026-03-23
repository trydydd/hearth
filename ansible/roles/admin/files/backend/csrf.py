"""
csrf.py — CSRF token protection for the CafeBox admin backend.

Uses the double-submit cookie pattern:

1. On the first GET (or any safe) request, a random ``csrf_token`` cookie is
   issued if one is not already present.
2. State-changing requests (POST, PUT, DELETE, PATCH) must echo the token
   value back in an ``X-CSRF-Token`` request header.
3. The server compares the header value against the cookie using a
   constant-time comparison to prevent timing attacks.

The ``csrf_token`` cookie is intentionally **not** ``HttpOnly`` so that the
JavaScript front-end can read it and include it in the request header.
"""

import secrets

from fastapi import HTTPException, Request, Response

_STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})
_CSRF_COOKIE = "csrf_token"
_CSRF_HEADER = "X-CSRF-Token"


def verify_csrf_token(request: Request, response: Response) -> None:
    """FastAPI dependency — enforce CSRF protection on state-changing requests.

    * GET / HEAD / OPTIONS / TRACE: issue a ``csrf_token`` cookie if one is
      not already present in the request.
    * POST / PUT / DELETE / PATCH: require an ``X-CSRF-Token`` header whose
      value matches the ``csrf_token`` cookie; raise HTTP 403 on mismatch or
      when either value is absent.
    """
    cookie_token: str | None = request.cookies.get(_CSRF_COOKIE)

    if request.method in _STATE_CHANGING_METHODS:
        header_token: str | None = request.headers.get(_CSRF_HEADER)
        if (
            not cookie_token
            or not header_token
            or not secrets.compare_digest(cookie_token, header_token)
        ):
            raise HTTPException(status_code=403, detail="CSRF validation failed")
    else:
        if not cookie_token:
            token = secrets.token_hex(32)
            response.set_cookie(
                _CSRF_COOKIE,
                token,
                httponly=False,  # must be readable by JavaScript
                samesite="strict",
                secure=False,  # HTTP-only LAN
            )
