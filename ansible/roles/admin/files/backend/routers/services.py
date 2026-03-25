"""
routers/services.py — Service management endpoints for the Hearth admin backend.

POST /api/admin/services/{service_id}/start
POST /api/admin/services/{service_id}/stop
POST /api/admin/services/{service_id}/restart

All endpoints require:
  - A valid ``hearth_session`` cookie  (require_session dependency)
  - A matching ``X-CSRF-Token`` header  (verify_csrf_token dependency)

Service IDs are the tile IDs from hearth.yaml / Service Identity Map.
They are mapped to systemd unit names via ``services_map.SERVICE_MAP``.
``sudo systemctl`` is used because the backend runs as the unprivileged
``hearth-admin`` user and the sudoers rule (Task 1.05) grants only the
exact ``systemctl start/stop/restart <unit>`` commands.
"""

import subprocess

from fastapi import APIRouter, Depends, HTTPException

from csrf import verify_csrf_token
from services_map import SERVICE_MAP
from session import require_session


def _service_active(unit: str) -> bool:
    """Return ``True`` if the systemd unit is currently active."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "--quiet", unit],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

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


@router.get("/status")
async def services_status():
    """Return enabled and live running state for all known services.

    ``enabled`` reflects ``hearth.yaml``; ``running`` reflects the current
    systemd unit state.

    Response shape::

        {
          "services": [
            {"id": "kiwix", "name": "Kiwix", "enabled": true, "running": true},
            ...
          ]
        }
    """
    try:
        from config import load_config as _load_config  # local import avoids module collision
        cfg = _load_config(None)
    except FileNotFoundError:
        cfg = {}

    services_cfg: dict = cfg.get("services", {})

    return {
        "services": [
            {
                "id": service_id,
                "name": info["name"],
                "enabled": services_cfg.get(service_id, {}).get("enabled", False),
                "running": _service_active(info["unit"]),
            }
            for service_id, info in SERVICE_MAP.items()
        ]
    }


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
