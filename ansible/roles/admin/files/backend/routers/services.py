"""
routers/services.py — Service management endpoints for the CafeBox admin backend.

POST /api/admin/services/{service_id}/start
POST /api/admin/services/{service_id}/stop
POST /api/admin/services/{service_id}/restart

All endpoints require:
  - A valid ``cafebox_session`` cookie  (require_session dependency)
  - A matching ``X-CSRF-Token`` header  (verify_csrf_token dependency)

Service IDs are the tile IDs from cafe.yaml / Service Identity Map.
They are mapped to systemd unit names via ``services_map.SERVICE_MAP``.
``sudo systemctl`` is used because the backend runs as the unprivileged
``cafebox-admin`` user and the sudoers rule (Task 1.05) grants only the
exact ``systemctl start/stop/restart <unit>`` commands.
"""

import subprocess

from fastapi import APIRouter, Depends, HTTPException

from csrf import verify_csrf_token
from services_map import SERVICE_MAP
from session import require_session

router = APIRouter(
    prefix="/api/admin/services",
    dependencies=[Depends(require_session), Depends(verify_csrf_token)],
)


def _run_systemctl(action: str, unit: str) -> None:
    """Run ``sudo systemctl <action> <unit>`` without a shell.

    Uses a list argument to prevent shell injection.
    Raises HTTP 500 with stderr on failure.
    """
    result = subprocess.run(
        ["sudo", "systemctl", action, unit],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=result.stderr or f"systemctl {action} {unit} failed",
        )


def _get_unit(service_id: str) -> str:
    """Resolve a tile ID to a systemd unit name, raising 404 for unknown IDs."""
    info = SERVICE_MAP.get(service_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Unknown service: {service_id}")
    return info["unit"]


@router.post("/{service_id}/start")
async def start_service(service_id: str):
    """Start a service."""
    _run_systemctl("start", _get_unit(service_id))
    return {"status": "started", "service_id": service_id}


@router.post("/{service_id}/stop")
async def stop_service(service_id: str):
    """Stop a service."""
    _run_systemctl("stop", _get_unit(service_id))
    return {"status": "stopped", "service_id": service_id}


@router.post("/{service_id}/restart")
async def restart_service(service_id: str):
    """Restart a service."""
    _run_systemctl("restart", _get_unit(service_id))
    return {"status": "restarted", "service_id": service_id}
