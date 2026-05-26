"""Aqara Open Cloud API client.

Talks directly to the developer-platform REST API at:

    https://open-usa.aqara.com/v3.0/open/api    (US region, default)
    https://open-cn.aqara.com/v3.0/open/api     (CN)
    https://open-ger.aqara.com/v3.0/open/api    (EU)
    https://open-ru.aqara.com/v3.0/open/api     (RU)
    https://open-kr.aqara.com/v3.0/open/api     (KR)

Authentication requires four credentials, obtained by registering a developer
app at https://developer.aqara.com :

    AQARA_OPEN_APP_ID         — application id
    AQARA_OPEN_APP_KEY        — app key (used to sign requests)
    AQARA_OPEN_KEY_ID         — per-key identifier
    AQARA_OPEN_ACCESS_TOKEN   — OAuth-issued user access token
    AQARA_OPEN_REFRESH_TOKEN  — OAuth refresh token (for renewal)
    AQARA_OPEN_REGION         — usa | cn | eu | ru | kr  (default: usa)

The CLI reads both upper-case and lower-case variants for compatibility with
ad-hoc shell setups.

Signature algorithm (per Aqara's apiIntroduction/signGenerationRules):

    Sign = MD5(lower(
        "Accesstoken={AccessToken}&Appid={AppID}&Keyid={KeyID}&Nonce={Nonce}&Time={Time}"
        + AppKey
    ))

Accesstoken is omitted from the signature base for calls that don't require it
(e.g. the refresh-token call itself).
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets as _secrets
import time
from typing import Any
from urllib.request import Request, urlopen


REGION_DOMAINS = {
    "usa": "open-usa.aqara.com",
    "cn":  "open-cn.aqara.com",
    "eu":  "open-ger.aqara.com",
    "ru":  "open-ru.aqara.com",
    "kr":  "open-kr.aqara.com",
}

# Aqara API error codes that indicate the AccessToken has expired or is
# otherwise invalid. Triggers an auto-refresh attempt.
EXPIRED_TOKEN_CODES = {108, 109, 110, 111}
EXPIRED_TOKEN_MSG_FRAGMENTS = (
    "token expire", "token invalid", "accesstoken expir",
    "accesstoken invalid", "auth fail",
)

ENV_KEYS = (
    "AQARA_OPEN_APP_ID",
    "AQARA_OPEN_APP_KEY",
    "AQARA_OPEN_KEY_ID",
    "AQARA_OPEN_ACCESS_TOKEN",
    "AQARA_OPEN_REFRESH_TOKEN",
    "AQARA_OPEN_REGION",
)


class AqaraError(RuntimeError):
    """Raised for missing config or non-zero API response codes."""


def _load_env() -> dict[str, str]:
    """Read Aqara credentials from the environment.

    Each key is checked in both upper-case and lower-case form (some users
    have legacy lowercase exports from earlier tooling).
    """
    env: dict[str, str] = {}
    for k in ENV_KEYS:
        v = os.environ.get(k) or os.environ.get(k.lower())
        if v:
            env[k] = v
    return env


def _endpoint(region: str) -> str:
    domain = REGION_DOMAINS.get(region.lower())
    if not domain:
        raise AqaraError(
            f"unknown region {region!r}; expected one of {sorted(REGION_DOMAINS)}"
        )
    return f"https://{domain}/v3.0/open/api"


def _sign(
    access_token: str, app_id: str, key_id: str, nonce: str, ts: str, app_key: str,
) -> str:
    parts: list[str] = []
    if access_token:
        parts.append(f"Accesstoken={access_token}")
    parts.extend([
        f"Appid={app_id}",
        f"Keyid={key_id}",
        f"Nonce={nonce}",
        f"Time={ts}",
    ])
    base = "&".join(parts) + app_key
    return hashlib.md5(base.lower().encode("utf-8")).hexdigest()


def _raw_call(
    intent: str,
    data: dict[str, Any] | None,
    env: dict[str, str],
    *,
    verbose: bool,
) -> dict:
    """Single Open API call without retry — used by both call() and refresh()."""
    app_id = env["AQARA_OPEN_APP_ID"]
    key_id = env["AQARA_OPEN_KEY_ID"]
    app_key = env["AQARA_OPEN_APP_KEY"]
    access_token = env.get("AQARA_OPEN_ACCESS_TOKEN", "")
    region = env.get("AQARA_OPEN_REGION", "usa")

    ts = str(int(time.time() * 1000))
    nonce = _secrets.token_hex(8)
    sign = _sign(access_token, app_id, key_id, nonce, ts, app_key)
    headers = {
        "Content-Type": "application/json",
        "Appid": app_id,
        "Keyid": key_id,
        "Time": ts,
        "Nonce": nonce,
        "Sign": sign,
    }
    if access_token:
        headers["Accesstoken"] = access_token

    body = {"intent": intent, "data": data or {}}
    body_bytes = json.dumps(body, separators=(",", ":")).encode("utf-8")

    url = _endpoint(region)
    if verbose:
        print(
            f"POST {url}\n"
            f"  intent={intent}  data={data}\n"
            f"  app_id={app_id}  key_id={key_id}  ts={ts}  "
            f"has_token={bool(access_token)}"
        )

    req = Request(url, data=body_bytes, headers=headers, method="POST")
    with urlopen(req, timeout=15) as resp:
        raw = resp.read()
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {"raw": raw.decode("utf-8", errors="replace")}


def _is_token_expired(resp: dict) -> bool:
    code = resp.get("code")
    if code in EXPIRED_TOKEN_CODES:
        return True
    msg = (
        (resp.get("message") or "").lower()
        + " "
        + (resp.get("msgDetails") or "").lower()
    )
    return any(frag in msg for frag in EXPIRED_TOKEN_MSG_FRAGMENTS)


def refresh_access_token(*, verbose: bool = False) -> dict:
    """Refresh the AccessToken using the stored refresh_token.

    Calls intent ``config.auth.refreshToken`` with ``{refreshToken: <stored>}``.
    On success, updates ``os.environ`` with the new tokens so the next
    ``call()`` invocation uses them. **Does not** persist to disk — the caller
    is responsible for re-exporting if they want the new tokens to outlive the
    current process.
    """
    env = _load_env()
    rt = env.get("AQARA_OPEN_REFRESH_TOKEN", "")
    if not rt:
        raise AqaraError(
            "no AQARA_OPEN_REFRESH_TOKEN in env — re-authorize via "
            "https://developer.aqara.com to obtain a new refresh token"
        )
    env_no_token = dict(env)
    env_no_token["AQARA_OPEN_ACCESS_TOKEN"] = ""
    resp = _raw_call(
        "config.auth.refreshToken", {"refreshToken": rt},
        env_no_token, verbose=verbose,
    )
    if resp.get("code") != 0:
        raise AqaraError(
            f"refresh failed: code={resp.get('code')} "
            f"message={resp.get('message')!r}"
        )
    result = resp.get("result") or {}
    new_at = result.get("accessToken")
    new_rt = result.get("refreshToken")
    if not new_at:
        raise AqaraError(f"refresh returned no accessToken: {result}")
    os.environ["AQARA_OPEN_ACCESS_TOKEN"] = new_at
    if new_rt:
        os.environ["AQARA_OPEN_REFRESH_TOKEN"] = new_rt
    return resp


def call(
    intent: str,
    data: dict[str, Any] | None = None,
    *,
    verbose: bool = False,
    _retry: bool = True,
) -> dict:
    """Make an Aqara Open API call.

    On expired-token responses, auto-refresh once (if a refresh_token is
    available) and retry the same call.
    """
    env = _load_env()
    for required in ("AQARA_OPEN_APP_ID", "AQARA_OPEN_APP_KEY", "AQARA_OPEN_KEY_ID"):
        if not env.get(required):
            raise AqaraError(
                f"missing {required} — register a developer app at "
                "https://developer.aqara.com and export the credentials as env vars"
            )

    resp = _raw_call(intent, data, env, verbose=verbose)

    if _retry and _is_token_expired(resp) and env.get("AQARA_OPEN_REFRESH_TOKEN"):
        if verbose:
            print(f"  token expired (code={resp.get('code')}); refreshing...")
        try:
            refresh_access_token(verbose=verbose)
        except AqaraError as exc:
            if verbose:
                print(f"  refresh failed: {exc}")
            return resp
        return call(intent, data, verbose=verbose, _retry=False)

    return resp


def ensure_ok(resp: dict, action: str = "call") -> dict:
    """Raise AqaraError if ``resp`` has a non-zero code; otherwise return it."""
    code = resp.get("code")
    if code != 0:
        msg = resp.get("msgDetails") or resp.get("message") or "(no message)"
        raise AqaraError(f"{action} failed: code={code} msg={msg!r}")
    return resp


# ---------------------------------------------------------------------------
# Typed wrappers
# ---------------------------------------------------------------------------

def query_homes(*, verbose: bool = False) -> list[dict]:
    """List top-level positions (homes)."""
    resp = ensure_ok(
        call("query.position.info", {"pageNum": 1, "pageSize": 50}, verbose=verbose),
        "query_homes",
    )
    return (resp.get("result") or {}).get("data") or []


def query_rooms(home_position_id: str, *, verbose: bool = False) -> list[dict]:
    """List rooms (sub-positions) under a given home."""
    resp = ensure_ok(
        call(
            "query.position.info",
            {"parentPositionId": home_position_id, "pageNum": 1, "pageSize": 200},
            verbose=verbose,
        ),
        "query_rooms",
    )
    return (resp.get("result") or {}).get("data") or []


def query_devices(*, verbose: bool = False) -> list[dict]:
    """List every device the credentials can see (across all homes)."""
    resp = ensure_ok(call("query.device.info", {}, verbose=verbose), "query_devices")
    return (resp.get("result") or {}).get("data") or []


def query_device_status(did: str, *, verbose: bool = False) -> list[dict]:
    """Query the current status of a device by ``did``."""
    resp = ensure_ok(
        call("query.resource.value", {"resources": [{"subjectId": did}]}, verbose=verbose),
        "query_device_status",
    )
    return (resp.get("result") or []) if isinstance(resp.get("result"), list) else []


def rename_device(did: str, name: str, *, verbose: bool = False) -> dict:
    """Rename an Aqara device (intent: ``config.device.name``)."""
    return ensure_ok(
        call("config.device.name", {"did": did, "name": name}, verbose=verbose),
        "rename_device",
    )


def move_device(did: str, position_id: str, *, verbose: bool = False) -> dict:
    """Move a device to a different position/room.

    The ``config.device.position`` intent expects a ``dids`` ARRAY, not a
    singular ``did``. Calling with ``did`` returns ``code=302, msg='Param
    not valid: dids 不能为空'``.
    """
    return ensure_ok(
        call(
            "config.device.position",
            {"dids": [did], "positionId": position_id},
            verbose=verbose,
        ),
        "move_device",
    )


def rename_position(position_id: str, name: str, *, verbose: bool = False) -> dict:
    """Rename a position (home or room).

    Uses ``config.position.update`` — the seemingly-named
    ``config.position.name`` intent returns 403 in practice.
    """
    return ensure_ok(
        call(
            "config.position.update",
            {"positionId": position_id, "positionName": name},
            verbose=verbose,
        ),
        "rename_position",
    )


def create_position(name: str, parent_position_id: str, *, verbose: bool = False) -> dict:
    """Create a new room under ``parent_position_id`` (typically a home id)."""
    return ensure_ok(
        call(
            "config.position.create",
            {"positionName": name, "parentPositionId": parent_position_id},
            verbose=verbose,
        ),
        "create_position",
    )


def delete_position(position_id: str, *, verbose: bool = False) -> dict:
    """Delete a position. The API typically refuses if devices are still
    associated; move them out first.

    Note: ``config.position.delete`` takes singular ``positionId``. Calling
    with the natural-looking plural ``positionIds: [list]`` returns 302.
    """
    return ensure_ok(
        call("config.position.delete", {"positionId": position_id}, verbose=verbose),
        "delete_position",
    )


def query_scenes(*, verbose: bool = False) -> list[dict]:
    """List scenes."""
    resp = ensure_ok(
        call("query.scene.listByPositionId", {"positionId": ""}, verbose=verbose),
        "query_scenes",
    )
    return (resp.get("result") or {}).get("data") or []


def run_scene(scene_id: str, *, verbose: bool = False) -> dict:
    return ensure_ok(
        call("config.scene.run", {"sceneId": scene_id}, verbose=verbose),
        "run_scene",
    )
