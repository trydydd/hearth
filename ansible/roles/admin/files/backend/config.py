"""
config.py — CafeBox admin backend configuration loader.

Reads cafe.yaml and exposes its contents as a plain dict.

The resolved path priority is (highest to lowest):
  1. Explicit ``path`` argument passed to :func:`load_config`.
  2. ``CAFEBOX_CONFIG`` environment variable.
  3. ``cafe.yaml`` in the current working directory.
"""

import os
from pathlib import Path

import yaml


def load_config(path: Path | None = None) -> dict:
    """Load cafe.yaml and return the parsed contents.

    Args:
        path: Explicit path to cafe.yaml.  When *None*, the function checks
              the ``CAFEBOX_CONFIG`` environment variable and then falls back
              to ``cafe.yaml`` in the current working directory.

    Returns:
        A dict of the parsed YAML config.

    Raises:
        FileNotFoundError: if the resolved file does not exist.
    """
    if path is not None:
        config_path = Path(path)
    elif "CAFEBOX_CONFIG" in os.environ:
        config_path = Path(os.environ["CAFEBOX_CONFIG"])
    else:
        config_path = Path("cafe.yaml")

    with config_path.open() as fh:
        data = yaml.safe_load(fh)
    return data or {}
