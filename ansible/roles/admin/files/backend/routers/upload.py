"""
routers/upload.py — File upload endpoint for the Hearth admin backend.

POST /api/admin/upload/{service_id}

Streams an uploaded file to the correct storage location defined in
``hearth.yaml`` ``storage.locations``.  Validates the file extension before
writing.

Requires a valid session + CSRF token.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from csrf import verify_csrf_token
from services_map import UPLOAD_EXTENSIONS
from session import require_session

router = APIRouter(
    prefix="/api/admin",
    dependencies=[Depends(require_session), Depends(verify_csrf_token)],
)

_CHUNK_SIZE = 1024 * 256  # 256 KiB streaming chunks
_CONFIG_PATH: Path | None = None


def _storage_path(service_id: str) -> Path:
    """Return the storage directory for *service_id* from hearth.yaml.

    Raises HTTP 404 for unknown service IDs.
    Raises HTTP 500 if the storage location is not configured.
    """
    if service_id not in UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=404, detail=f"Unknown service: {service_id}")

    try:
        from config import load_config as _load_config  # local import avoids module collision
        cfg = _load_config(_CONFIG_PATH)
    except FileNotFoundError:
        cfg = {}

    locations: dict = cfg.get("storage", {}).get("locations", {})
    path_str: str | None = locations.get(service_id)
    if not path_str:
        raise HTTPException(
            status_code=500,
            detail=f"Storage location for '{service_id}' not configured in hearth.yaml",
        )
    return Path(path_str)


def _validate_extension(filename: str, service_id: str) -> None:
    """Raise HTTP 422 if the file extension is not allowed for *service_id*."""
    allowed = UPLOAD_EXTENSIONS.get(service_id, [])
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(
            status_code=422,
            detail=(
                f"File extension '{suffix}' is not allowed for service '{service_id}'. "
                f"Allowed extensions: {', '.join(allowed)}"
            ),
        )


@router.post("/upload/{service_id}", status_code=200)
async def upload_file(service_id: str, file: UploadFile = File(...)):
    """Upload a file to the storage location for *service_id*.

    * Streams the file in chunks to avoid loading it entirely into memory.
    * Validates the file extension before writing any data.
    * Returns 404 for unknown service IDs.
    * Returns 422 for disallowed extensions (e.g. ``.exe``).
    """
    if not file.filename:
        raise HTTPException(status_code=422, detail="No filename provided")

    # Check service_id is known before validating extension
    if service_id not in UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=404, detail=f"Unknown service: {service_id}")

    _validate_extension(file.filename, service_id)
    dest_dir = _storage_path(service_id)

    # Ensure the destination directory exists
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / Path(file.filename).name

    bytes_written = 0
    try:
        with dest_path.open("wb") as out:
            while True:
                chunk = await file.read(_CHUNK_SIZE)
                if not chunk:
                    break
                out.write(chunk)
                bytes_written += len(chunk)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "status": "ok",
        "filename": dest_path.name,
        "bytes_written": bytes_written,
        "destination": str(dest_path),
    }
