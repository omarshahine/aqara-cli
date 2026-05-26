"""Local config persistence (~/.config/aqara-cli/config.json).

Stores non-secret preferences only — credentials live in env vars (see api.py).
Currently tracks:

- ``default_home``: the position id of the user's preferred home, used as the
  implicit scope for ``aqara devices`` / ``aqara rooms`` / ``aqara scenes``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("AQARA_CONFIG_DIR", Path.home() / ".config" / "aqara-cli"))
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config() -> dict:
    """Return the current config dict; empty if file missing or unreadable."""
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text())
    except Exception:
        return {}


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2) + "\n")


def get_default_home() -> str | None:
    """Return the persisted default home position id, or None."""
    return load_config().get("default_home")


def set_default_home(position_id: str | None) -> None:
    cfg = load_config()
    if position_id is None:
        cfg.pop("default_home", None)
    else:
        cfg["default_home"] = position_id
    save_config(cfg)
