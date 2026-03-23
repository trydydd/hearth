"""
main.py — CafeBox admin backend entry point.

Start the server:
    uvicorn main:app

The application is a FastAPI service that exposes:
  GET  /healthz                          → {"status": "ok"}
  POST /api/admin/login                  → issue session cookie
  POST /api/admin/logout                 → clear session cookie
  POST /api/admin/services/{id}/start    → start service (stub)
  POST /api/admin/services/{id}/stop     → stop service (stub)
  POST /api/admin/services/{id}/restart  → restart service (stub)

Additional routers (public, change-password, upload) are mounted as they
are implemented in subsequent tasks.
"""

from fastapi import Depends, FastAPI

from csrf import verify_csrf_token
from routers import auth as auth_router
from routers import services as services_router

app = FastAPI(title="CafeBox Admin API", version="0.1.0")

app.include_router(auth_router.router)
app.include_router(services_router.router)


@app.get("/healthz", dependencies=[Depends(verify_csrf_token)])
async def healthz() -> dict:
    """Liveness check — returns HTTP 200 with {"status": "ok"}.

    The CSRF dependency ensures a ``csrf_token`` cookie is issued on the
    first request so that the front-end can include it in subsequent
    state-changing requests.
    """
    return {"status": "ok"}
