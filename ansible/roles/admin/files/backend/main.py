"""
main.py — CafeBox admin backend entry point.

Start the server:
    uvicorn main:app

The application is a FastAPI service that exposes:
  GET /healthz  → {"status": "ok"}

Additional routers (auth, services, public) are mounted as they are
implemented in subsequent tasks.
"""

from fastapi import FastAPI

app = FastAPI(title="CafeBox Admin API", version="0.1.0")


@app.get("/healthz")
async def healthz() -> dict:
    """Liveness check — returns HTTP 200 with {"status": "ok"}."""
    return {"status": "ok"}
