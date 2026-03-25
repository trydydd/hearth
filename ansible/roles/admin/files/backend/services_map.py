"""
services_map.py — CafeBox Service Identity Map.

Single source of truth mapping tile IDs (used in the API) to systemd unit
names, human-readable display names, URL paths, and valid upload extensions.

Tile IDs match the keys used in ``cafe.yaml`` ``services.*``.
"""

from typing import Literal

# Valid file-upload extensions per service.  Keys match tile IDs.
UPLOAD_EXTENSIONS: dict[str, list[str]] = {
    "kiwix": [".zim"],
    "calibre_web": [".epub", ".pdf", ".mobi", ".azw", ".azw3", ".cbz", ".cbr", ".txt"],
    "navidrome": [".mp3", ".flac", ".ogg", ".m4a", ".wav", ".aac"],
}

# Service Identity Map
#   tile_id → {unit, name, url_path}
# tile_id   : key in cafe.yaml ``services`` section and in API responses
# unit      : systemd unit name passed to systemctl
# name      : human-readable label shown in portal/admin UI
# url_path  : nginx location path used to build the full URL
SERVICE_MAP: dict[str, dict[str, str]] = {
    "chat": {
        "unit": "hearth-chat.service",
        "name": "Chat",
        "url_path": "/chat/",
    },
    "calibre_web": {
        "unit": "calibre-web.service",
        "name": "Calibre",
        "url_path": "/calibre_web/",
    },
    "kiwix": {
        "unit": "kiwix.service",
        "name": "Wikipedia",
        "url_path": "/wiki/",
    },
    "navidrome": {
        "unit": "navidrome.service",
        "name": "Music",
        "url_path": "/navidrome/",
    },
}

# Ordered list of valid systemctl actions for validation
ServiceAction = Literal["start", "stop", "restart"]
VALID_ACTIONS: frozenset[str] = frozenset({"start", "stop", "restart"})
