"""Local config + credentials persistence.

Two files under ``~/.config/aqara-cli/`` (overridable via ``AQARA_CONFIG_DIR``):

- ``config.json`` — non-secret preferences (default home).
- ``credentials.json`` — secrets: app_id, app_key, key_id, region, access_token,
  refresh_token, open_id. **Mode 600.** Env vars (``AQARA_OPEN_*``) still take
  precedence if set, so users with their own secret manager (chezmoi, 1Password
  CLI, etc.) can keep using it; ``credentials.json`` is a fallback for users
  who want everything in one place.

Token refresh writes back to ``credentials.json`` if it exists, so a recurring
refresher (see ``auth install-refresher``) survives across processes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

CONFIG_DIR = Path(
    os.environ.get("AQARA_CONFIG_DIR", Path.home() / ".config" / "aqara-cli")
)
CONFIG_FILE = CONFIG_DIR / "config.json"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"


# ---------------------------------------------------------------------------
# config.json (non-secret prefs)
# ---------------------------------------------------------------------------

def load_config() -> dict:
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
    return load_config().get("default_home")


def set_default_home(position_id: str | None) -> None:
    cfg = load_config()
    if position_id is None:
        cfg.pop("default_home", None)
    else:
        cfg["default_home"] = position_id
    save_config(cfg)


# ---------------------------------------------------------------------------
# credentials.json (secret storage, mode 600)
# ---------------------------------------------------------------------------

CREDENTIAL_KEYS = (
    "app_id",
    "app_key",
    "key_id",
    "region",
    "access_token",
    "refresh_token",
    "open_id",
)


def load_credentials() -> dict:
    if not CREDENTIALS_FILE.exists():
        return {}
    try:
        return json.loads(CREDENTIALS_FILE.read_text())
    except Exception:
        return {}


def save_credentials(creds: dict) -> None:
    """Write credentials.json with mode 600. Only persists known keys."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    filtered = {k: v for k, v in creds.items() if k in CREDENTIAL_KEYS and v is not None}
    # Write with restrictive umask so the file lands 600 from the start.
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(CREDENTIALS_FILE, flags, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(filtered, indent=2) + "\n")
    finally:
        # In case of a pre-existing file with different mode, fix it.
        try:
            os.chmod(CREDENTIALS_FILE, 0o600)
        except OSError:
            pass


def update_credentials(**updates) -> None:
    """Merge ``updates`` into credentials.json (only known keys)."""
    creds = load_credentials()
    for k, v in updates.items():
        if k in CREDENTIAL_KEYS and v is not None:
            creds[k] = v
    save_credentials(creds)
