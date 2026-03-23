"""
routers/services.py — Service management endpoints stub.

Provides the route skeleton so that Task 1.03 (CSRF protection) can be
exercised in tests.  Full implementation (systemctl integration, service-id
mapping, session requirement) is added in Task 1.07.
"""

from fastapi import APIRouter, Depends

from csrf import verify_csrf_token

router = APIRouter(
    prefix="/api/admin/services",
    dependencies=[Depends(verify_csrf_token)],
)


@router.post("/{service_id}/start")
async def start_service(service_id: str):
    """Start a service (stub — full implementation in Task 1.07)."""
    return {"status": "started", "service_id": service_id}


@router.post("/{service_id}/stop")
async def stop_service(service_id: str):
    """Stop a service (stub — full implementation in Task 1.07)."""
    return {"status": "stopped", "service_id": service_id}


@router.post("/{service_id}/restart")
async def restart_service(service_id: str):
    """Restart a service (stub — full implementation in Task 1.07)."""
    return {"status": "restarted", "service_id": service_id}
