"""
routers/public.py — Unauthenticated public API for the CafeBox portal.

GET /api/public/services/status

Returns the current state of all configured services plus a ``first_boot``
flag so the portal can show or hide the initial-password banner.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from fastapi import APIRouter

from services_map import SERVICE_MAP

router = APIRouter(prefix="/api/public")

# Path written by the first-boot script; deleted when the operator changes
# their password.  Its presence signals that the default password is still
# active.
_FIRST_BOOT_MARKER = Path(
    os.environ.get("CAFEBOX_FIRST_BOOT_MARKER", "/run/cafebox/initial-password")
)

# Path to the cafe.yaml config; can be overridden via CAFEBOX_CONFIG env var.
_CONFIG_PATH: Path | None = None


def _is_first_boot() -> bool:
    return _FIRST_BOOT_MARKER.exists()


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
        # systemctl not available (e.g. test environment)
        return False


@router.get("/services/status")
async def services_status():
    """Return the status of all CafeBox services.

    Does **not** require authentication.

    Response shape::

        {
          "first_boot": true,
          "initial_password": "Ab3Xy7Pq1Rz4",
          "services": [
            {"id": "calibre_web", "name": "Calibre", "enabled": true, "url": "http://cafe.box/calibre_web/"},
            ...
          ]
        }

    ``first_boot`` is ``true`` while ``/run/cafebox/initial-password`` exists.
    When ``first_boot`` is ``true`` the ``initial_password`` field is also
    present (the plaintext password read from the marker file).
    ``enabled`` reflects ``cafe.yaml``; it does **not** indicate whether the
    service is currently running.
    """
    try:
        from config import load_config as _load_config  # local import avoids module collision
        cfg = _load_config(_CONFIG_PATH)
    except FileNotFoundError:
        cfg = {}

    services_cfg: dict = cfg.get("services", {})
    box_domain: str = cfg.get("box", {}).get("domain", "cafe.box")

    service_list = []
    for tile_id, info in SERVICE_MAP.items():
        enabled = services_cfg.get(tile_id, {}).get("enabled", False)
        url = f"http://{box_domain}{info['url_path']}" if enabled else None
        service_list.append(
            {
                "id": tile_id,
                "name": info["name"],
                "enabled": enabled,
                "url": url,
            }
        )

    first_boot = _is_first_boot()
    response: dict = {
        "first_boot": first_boot,
        "services": service_list,
    }

    if first_boot:
        try:
            response["initial_password"] = _FIRST_BOOT_MARKER.read_text().strip()
        except OSError:
            pass  # marker disappeared between the exists() check and read

    return response
