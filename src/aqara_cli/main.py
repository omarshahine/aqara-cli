"""Aqara Open Cloud CLI — Click command group and all subcommands."""

from __future__ import annotations

import json
import os
from pathlib import Path

import click

from . import api, config


def _json(data) -> None:
    """Print data as formatted JSON to stdout."""
    click.echo(json.dumps(data, indent=2, default=str))


def _resolve_home(home: str | None) -> str | None:
    """Resolve the home position id from --home, config, or None.

    Accepts a literal position id (``real1.xxx``) or a home name; in the
    latter case, queries the API to look it up.
    """
    if not home:
        return config.get_default_home()
    if home.startswith("real1.") or home.startswith("real2."):
        return home
    # Look up by name
    for h in api.query_homes():
        if h.get("positionName") == home:
            return h.get("positionId")
    raise click.ClickException(
        f"home {home!r} not found. Run `aqara homes` to see available homes."
    )


@click.group()
@click.option(
    "--home",
    "home",
    default=None,
    help="Home name or position id. Overrides config; falls back to no filter.",
)
@click.pass_context
def cli(ctx, home):
    """Aqara Open Cloud CLI."""
    ctx.ensure_object(dict)
    ctx.obj["home"] = home


# ---------------------------------------------------------------------------
# info — auth state + default home
# ---------------------------------------------------------------------------
@cli.command()
@click.pass_context
def info(ctx):
    """Show auth status, default home, and version info."""
    env = api._load_env()
    have = {k: bool(env.get(k)) for k in api.ENV_KEYS}
    region = env.get("AQARA_OPEN_REGION", "usa")
    default_home = config.get_default_home()
    out = {
        "region": region,
        "endpoint": api._endpoint(region) if have.get("AQARA_OPEN_APP_ID") else None,
        "credentials_present": have,
        "default_home": default_home,
    }
    if all(have[k] for k in ("AQARA_OPEN_APP_ID", "AQARA_OPEN_APP_KEY", "AQARA_OPEN_KEY_ID")):
        # Light auth check
        try:
            homes = api.query_homes()
            out["auth_ok"] = True
            out["homes"] = [{"id": h.get("positionId"), "name": h.get("positionName")} for h in homes]
        except api.AqaraError as exc:
            out["auth_ok"] = False
            out["error"] = str(exc)
    _json(out)


# ---------------------------------------------------------------------------
# homes — list top-level positions
# ---------------------------------------------------------------------------
@cli.command()
def homes():
    """List the homes the credentials can see."""
    _json(api.query_homes())


# ---------------------------------------------------------------------------
# home — group: set/get default home
# ---------------------------------------------------------------------------
@cli.group()
def home():
    """Manage the default home (persisted in ~/.config/aqara-cli/config.json)."""


@home.command("set")
@click.argument("name_or_id")
def home_set(name_or_id):
    """Set the default home by name or position id.

    The default home scopes subsequent ``devices`` / ``rooms`` / ``scenes``
    commands. Use ``aqara homes`` to find names.
    """
    pid = _resolve_home(name_or_id)
    if pid is None:
        raise click.ClickException(f"could not resolve home {name_or_id!r}")
    config.set_default_home(pid)
    _json({"default_home": pid, "set": True})


@home.command("clear")
def home_clear():
    """Clear the default home (subsequent commands will show data across all homes)."""
    config.set_default_home(None)
    _json({"default_home": None, "cleared": True})


# ---------------------------------------------------------------------------
# rooms — list positions under the current home
# ---------------------------------------------------------------------------
@cli.command()
@click.pass_context
def rooms(ctx):
    """List rooms in the default (or --home) home."""
    home_id = _resolve_home(ctx.obj.get("home"))
    if not home_id:
        raise click.ClickException(
            "no home selected — pass --home <name> or run `aqara home set <name>`"
        )
    _json(api.query_rooms(home_id))


# ---------------------------------------------------------------------------
# devices — list devices (optionally filtered to current home)
# ---------------------------------------------------------------------------
@cli.command()
@click.option(
    "--all-homes",
    is_flag=True,
    help="Include devices from every home the credentials can see.",
)
@click.pass_context
def devices(ctx, all_homes):
    """List devices.

    By default, filters to the current home (--home, or `aqara home set`).
    Pass --all-homes to see everything.
    """
    all_devs = api.query_devices()
    if all_homes:
        _json(all_devs)
        return

    home_id = _resolve_home(ctx.obj.get("home"))
    if not home_id:
        # No default home — fall back to showing all with a hint.
        click.echo(
            "(no default home set — showing all devices. "
            "Run `aqara home set <name>` to scope by home.)",
            err=True,
        )
        _json(all_devs)
        return

    room_ids = {r["positionId"] for r in api.query_rooms(home_id)}
    scoped = [d for d in all_devs if d.get("positionId") in room_ids]
    _json(scoped)


@cli.command("device-status")
@click.argument("did")
def device_status(did):
    """Query the current state of a device by ``did``."""
    _json(api.query_device_status(did))


# ---------------------------------------------------------------------------
# rename — device
# ---------------------------------------------------------------------------
@cli.command()
@click.argument("did")
@click.argument("new_name")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would change without writing.",
)
def rename(did, new_name, dry_run):
    """Rename a device (intent: config.device.name).

    Example:
        aqara rename lumi.158d0008ab2b2d "Front Door Sensor"
    """
    if not new_name or not new_name.strip():
        raise click.BadParameter(
            "new_name must not be empty.", param_hint="'NEW_NAME'"
        )
    if dry_run:
        _json({
            "did": did,
            "new_name": new_name,
            "dry_run": True,
            "would_send": {"intent": "config.device.name", "data": {"did": did, "name": new_name}},
        })
        return
    resp = api.rename_device(did, new_name)
    _json({"did": did, "new_name": new_name, "response": resp})


# ---------------------------------------------------------------------------
# move — device → different position
# ---------------------------------------------------------------------------
@cli.command()
@click.argument("did")
@click.argument("position_id")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would change without writing.",
)
def move(did, position_id, dry_run):
    """Move a device to a different position/room.

    Example:
        aqara move lumi.158d0008ab2b2d real2.1178496813997576192
    """
    if dry_run:
        _json({
            "did": did,
            "position_id": position_id,
            "dry_run": True,
            "would_send": {
                "intent": "config.device.position",
                "data": {"dids": [did], "positionId": position_id},
            },
        })
        return
    resp = api.move_device(did, position_id)
    _json({"did": did, "position_id": position_id, "response": resp})


# ---------------------------------------------------------------------------
# room — group: rename / create / delete positions
# ---------------------------------------------------------------------------
@cli.group()
def room():
    """Manage rooms (positions) in the current home.

    `room rename`, `room create`, `room delete` use the
    `config.position.update` / `.create` / `.delete` intents.
    """


@room.command("rename")
@click.argument("position_id")
@click.argument("new_name")
@click.option("--dry-run", is_flag=True)
def room_rename(position_id, new_name, dry_run):
    """Rename a room.

    Use `config.position.update`; the seemingly-named `config.position.name`
    returns 403 in practice.

    Example:
        aqara room rename real2.1000992461178556416 "Living Room"
    """
    if not new_name or not new_name.strip():
        raise click.BadParameter(
            "new_name must not be empty.", param_hint="'NEW_NAME'"
        )
    if dry_run:
        _json({
            "position_id": position_id,
            "new_name": new_name,
            "dry_run": True,
            "would_send": {
                "intent": "config.position.update",
                "data": {"positionId": position_id, "positionName": new_name},
            },
        })
        return
    resp = api.rename_position(position_id, new_name)
    _json({"position_id": position_id, "new_name": new_name, "response": resp})


@room.command("create")
@click.argument("name")
@click.option(
    "--home",
    "home_id",
    default=None,
    help="Home position id (defaults to current --home / `home set`).",
)
@click.option("--dry-run", is_flag=True)
@click.pass_context
def room_create(ctx, name, home_id, dry_run):
    """Create a new room under the given (or default) home.

    Example:
        aqara room create "Mudroom"
    """
    if not name or not name.strip():
        raise click.BadParameter("name must not be empty.", param_hint="'NAME'")

    parent = home_id or _resolve_home(ctx.obj.get("home"))
    if not parent:
        raise click.ClickException(
            "no home id — pass --home <id> or run `aqara home set <name>`"
        )

    if dry_run:
        _json({
            "name": name,
            "parent_position_id": parent,
            "dry_run": True,
            "would_send": {
                "intent": "config.position.create",
                "data": {"positionName": name, "parentPositionId": parent},
            },
        })
        return
    resp = api.create_position(name, parent)
    _json({
        "name": name,
        "parent_position_id": parent,
        "created_position_id": (resp.get("result") or {}).get("positionId"),
        "response": resp,
    })


@room.command("delete")
@click.argument("position_id")
@click.option("--dry-run", is_flag=True)
def room_delete(position_id, dry_run):
    """Delete a room. The API refuses if devices are still associated;
    move them out (via `aqara move`) first.

    Note: this intent takes singular `positionId`. The seemingly-natural
    `positionIds: [list]` form returns 302.
    """
    if dry_run:
        _json({
            "position_id": position_id,
            "dry_run": True,
            "would_send": {
                "intent": "config.position.delete",
                "data": {"positionId": position_id},
            },
        })
        return
    resp = api.delete_position(position_id)
    _json({"position_id": position_id, "response": resp})


# ---------------------------------------------------------------------------
# scenes
# ---------------------------------------------------------------------------
@cli.command()
def scenes():
    """List scenes the credentials can see."""
    _json(api.query_scenes())


@cli.command("scene-run")
@click.argument("scene_id")
def scene_run(scene_id):
    """Run a scene by id."""
    _json(api.run_scene(scene_id))


# ---------------------------------------------------------------------------
# call — raw escape hatch
# ---------------------------------------------------------------------------
@cli.command()
@click.argument("intent")
@click.option(
    "--data",
    "data_json",
    default="{}",
    help="JSON body for the intent (defaults to empty object).",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Print the outbound request (URL + headers minus secrets, body).",
)
def call(intent, data_json, verbose):
    """Make a raw Aqara Open API call by intent.

    Examples:
        aqara call query.position.info --data '{"pageNum":1,"pageSize":50}'
        aqara call config.auth.refreshToken
    """
    try:
        data = json.loads(data_json)
    except json.JSONDecodeError as exc:
        raise click.BadParameter(f"--data must be valid JSON: {exc}") from exc
    _json(api.call(intent, data, verbose=verbose))


# ---------------------------------------------------------------------------
# auth — bootstrap + recurring-refresher install
# ---------------------------------------------------------------------------
@cli.group()
def auth():
    """One-time bootstrap and recurring-refresher management.

    First-time setup is a two-step OAuth flow:

      1. `aqara auth request-code <your-email>` — Aqara emails a code.
      2. `aqara auth get-token <your-email> <code>` — exchange for tokens.

    After that, install the launchd refresher so the tokens never expire:

      3. `aqara auth install-refresher`
    """


@auth.command("set-app")
@click.option("--app-id", required=True, help="AppId from developer.aqara.com")
@click.option("--app-key", required=True, help="AppKey from developer.aqara.com")
@click.option("--key-id", required=True, help="KeyId from developer.aqara.com")
@click.option(
    "--region",
    type=click.Choice(["usa", "cn", "eu", "ru", "kr"]),
    default="usa",
    show_default=True,
)
def auth_set_app(app_id, app_key, key_id, region):
    """Persist your developer-app credentials to ~/.config/aqara-cli/credentials.json.

    Alternative to setting AQARA_OPEN_APP_ID/_KEY/_ID/_REGION as env vars.
    """
    from . import config as _config

    _config.update_credentials(
        app_id=app_id, app_key=app_key, key_id=key_id, region=region,
    )
    _json({
        "saved_to": str(_config.CREDENTIALS_FILE),
        "fields": ["app_id", "app_key", "key_id", "region"],
    })


@auth.command("request-code")
@click.argument("account")
@click.option(
    "--account-type",
    type=int,
    default=0,
    show_default=True,
    help="0 = email, 1 = phone (China), 2 = phone (international).",
)
@click.option(
    "--validity",
    default="30d",
    show_default=True,
    help="Requested access-token lifetime (e.g. 1h, 7d, 30d). Maximum is "
         "controlled by your app's settings at developer.aqara.com.",
)
def auth_request_code(account, account_type, validity):
    """Step 1 of the OAuth bootstrap. Aqara emails/SMSes a verification code
    to ``account``.

    Example:
        aqara auth request-code you@example.com
    """
    resp = api.request_auth_code(account, account_type=account_type, validity=validity)
    _json({
        "account": account,
        "sent": True,
        "next": "Run `aqara auth get-token {account} <code>` with the code "
                "you receive.".format(account=account),
        "response": resp,
    })


@auth.command("get-token")
@click.argument("account")
@click.argument("auth_code")
@click.option(
    "--account-type",
    type=int,
    default=0,
    show_default=True,
)
@click.option(
    "--no-save",
    is_flag=True,
    help="Don't write tokens to credentials.json — just print them so you "
         "can export them yourself.",
)
def auth_get_token(account, auth_code, account_type, no_save):
    """Step 2 of the OAuth bootstrap. Exchange the verification code for
    AccessToken + RefreshToken and persist them to credentials.json.

    Example:
        aqara auth get-token you@example.com 123456
    """
    resp = api.exchange_auth_code(account, auth_code, account_type=account_type)
    result = resp.get("result") or {}
    access_token = result.get("accessToken")
    refresh_token = result.get("refreshToken")
    expires_in = result.get("expiresIn")
    open_id = result.get("openId")
    if not access_token:
        raise click.ClickException(
            f"no accessToken in response result: {result}"
        )

    saved = False
    if not no_save:
        from . import config as _config

        _config.update_credentials(
            access_token=access_token,
            refresh_token=refresh_token,
            open_id=open_id,
        )
        os.environ["AQARA_OPEN_ACCESS_TOKEN"] = access_token
        if refresh_token:
            os.environ["AQARA_OPEN_REFRESH_TOKEN"] = refresh_token
        saved = True

    _json({
        "account": account,
        "expires_in": expires_in,
        "open_id": open_id,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "saved_to_credentials_file": saved,
        "next": (
            "Run `aqara auth install-refresher` to keep tokens fresh "
            "automatically." if saved else
            "Export AQARA_OPEN_ACCESS_TOKEN + AQARA_OPEN_REFRESH_TOKEN to "
            "your shell, then run `aqara auth install-refresher`."
        ),
    })


@auth.command("browser-flow")
@click.option(
    "--port",
    type=int,
    default=8765,
    show_default=True,
    help="Local port for the OAuth callback listener.",
)
@click.option(
    "--no-save",
    is_flag=True,
    help="Don't write tokens to credentials.json — just print them.",
)
@click.option(
    "--no-browser",
    is_flag=True,
    help="Don't auto-open the browser — print the URL and wait for you to "
         "visit it manually (useful over SSH).",
)
def auth_browser_flow(port, no_save, no_browser):
    """Bootstrap tokens via Aqara's OAuth web flow.

    **This is the path most users need** — Aqara's email-code flow
    (`request-code` / `get-token`) is unreliable. The browser flow is
    documented at developer.aqara.com under "Interface Authorization" and
    works consistently.

    Walks you through:

      1. Starts a local HTTPS callback listener on http://localhost:<port>/callback.
      2. Opens https://open-<region>.aqara.com/v3.0/open/authorize in your browser.
      3. You sign in (if needed) and click Authorize.
      4. Aqara redirects back to the local listener with `?code=...`.
      5. The code is exchanged for AccessToken + RefreshToken via the
         /v3.0/open/access_token endpoint.
      6. Tokens are written to credentials.json (or printed with --no-save).

    **Prerequisite:** in your developer.aqara.com app settings, add
    `http://localhost:<port>/callback` as an authorized Redirect URI. Without
    that, Aqara rejects the authorize request with an unhelpful generic error.
    """
    import http.server
    import secrets as _secrets
    import urllib.parse
    import webbrowser
    from urllib.request import Request, urlopen

    env = api._load_env()
    app_id = env.get("AQARA_OPEN_APP_ID")
    app_key = env.get("AQARA_OPEN_APP_KEY")
    region = env.get("AQARA_OPEN_REGION", "usa")
    if not app_id or not app_key:
        raise click.ClickException(
            "missing AQARA_OPEN_APP_ID / AQARA_OPEN_APP_KEY — run "
            "`aqara auth set-app ...` first."
        )
    domain = api.REGION_DOMAINS.get(region.lower())
    if not domain:
        raise click.ClickException(f"unknown region {region!r}")

    redirect_uri = f"http://localhost:{port}/callback"

    captured: dict[str, str] = {}

    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            url = urllib.parse.urlparse(self.path)
            if url.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            params = urllib.parse.parse_qs(url.query)
            captured["code"] = (params.get("code") or [""])[0]
            captured["state"] = (params.get("state") or [""])[0]
            captured["error"] = (params.get("error") or [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = (
                "Authorization received. You can close this tab."
                if captured.get("code") else
                f"Authorization failed: {captured}"
            )
            self.wfile.write(f"<html><body><h2>{msg}</h2></body></html>".encode())

        def log_message(self, fmt, *args):  # silence
            return

    try:
        srv = http.server.HTTPServer(("127.0.0.1", port), CallbackHandler)
    except OSError as exc:
        raise click.ClickException(
            f"can't bind to port {port} ({exc}). Pass --port <other> or stop "
            "whatever's using it."
        ) from exc

    state = _secrets.token_hex(8)
    auth_url = (
        f"https://{domain}/v3.0/open/authorize?"
        + urllib.parse.urlencode({
            "client_id": app_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "state": state,
        })
    )

    click.echo(f"Authorize URL:\n  {auth_url}\n", err=True)
    click.echo(
        f"After you click Authorize, your browser will redirect to {redirect_uri}\n"
        "which this command is listening on. Waiting...\n",
        err=True,
    )
    click.echo(
        "IMPORTANT: make sure your dev app at developer.aqara.com has\n"
        f"  {redirect_uri}\n"
        "registered as an authorized Redirect URI. Without that the\n"
        "authorize page will show a generic error.\n",
        err=True,
    )

    if not no_browser:
        webbrowser.open(auth_url)

    srv.handle_request()
    srv.server_close()

    if captured.get("state") != state:
        raise click.ClickException(
            f"state mismatch — expected {state!r}, got {captured.get('state')!r}"
        )
    if captured.get("error"):
        raise click.ClickException(f"authorize error: {captured['error']}")
    code = captured.get("code")
    if not code:
        raise click.ClickException("no code captured from the callback")

    click.echo(f"Got authorization code (first 8: {code[:8]}…)", err=True)
    click.echo("Exchanging for access token...", err=True)

    token_url = f"https://{domain}/v3.0/open/access_token"
    form = urllib.parse.urlencode({
        "client_id": app_id,
        "client_secret": app_key,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code": code,
    }).encode("utf-8")
    req = Request(
        token_url,
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=15) as resp:
            raw = resp.read()
    except Exception as exc:
        raise click.ClickException(f"token exchange failed: {exc}") from exc

    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise click.ClickException(
            f"non-JSON token response: {raw.decode('utf-8', errors='replace')[:400]}"
        ) from exc

    # Response shape varies: sometimes flat, sometimes {result: {...}}.
    result = data.get("result") if isinstance(data.get("result"), dict) else data
    access_token = result.get("accessToken") or result.get("access_token")
    refresh_token = result.get("refreshToken") or result.get("refresh_token")
    open_id = result.get("openId") or result.get("open_id") or result.get("openid")
    expires_in = result.get("expiresIn") or result.get("expires_in")

    if not access_token:
        raise click.ClickException(f"no access_token in token response: {data}")

    saved = False
    if not no_save:
        from . import config as _config

        _config.update_credentials(
            access_token=access_token,
            refresh_token=refresh_token,
            open_id=open_id,
        )
        os.environ["AQARA_OPEN_ACCESS_TOKEN"] = access_token
        if refresh_token:
            os.environ["AQARA_OPEN_REFRESH_TOKEN"] = refresh_token
        saved = True

    _json({
        "expires_in": expires_in,
        "open_id": open_id,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "saved_to_credentials_file": saved,
        "next": (
            "Run `aqara info` to verify, then `aqara auth install-refresher` "
            "to keep tokens fresh automatically."
        ),
    })


@auth.command("install-refresher")
@click.option(
    "--interval-days",
    type=float,
    default=5.0,
    show_default=True,
    help="How often to refresh. Aqara tokens are 7d (access) / 30d (refresh) "
         "by default; 5 days keeps both well inside their windows.",
)
@click.option(
    "--label",
    default="com.shahine.aqara-cli.refresh",
    show_default=True,
    help="launchd job label.",
)
def auth_install_refresher(interval_days, label):
    """Install a macOS launchd agent that runs ``aqara refresh`` periodically.

    Writes ``~/Library/LaunchAgents/<label>.plist`` and loads it. The agent
    runs as your user and uses the same credentials.json the CLI does, so
    refreshed tokens persist there for the next shell.

    Logs land at ``~/Library/Logs/aqara-cli/refresh.log``.

    Only supported on macOS.
    """
    import shutil
    import subprocess
    import sys as _sys

    if _sys.platform != "darwin":
        raise click.ClickException(
            "install-refresher is macOS-only (uses launchd). On Linux, set up "
            "a systemd timer; on other systems, use cron. Both should call "
            "`aqara refresh`."
        )

    aqara_path = shutil.which("aqara")
    if not aqara_path:
        raise click.ClickException(
            "could not locate the `aqara` executable on PATH — install with "
            "`pipx install aqara-cli` first."
        )

    log_dir = Path.home() / "Library" / "Logs" / "aqara-cli"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "refresh.log"

    plist_dir = Path.home() / "Library" / "LaunchAgents"
    plist_dir.mkdir(parents=True, exist_ok=True)
    plist_path = plist_dir / f"{label}.plist"

    interval_seconds = int(interval_days * 86400)
    plist_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>

    <key>ProgramArguments</key>
    <array>
        <string>{aqara_path}</string>
        <string>refresh</string>
    </array>

    <!-- Refresh every {interval_days} day(s). Default Aqara token lifetimes
         are 7d (access) / 30d (refresh, rotated on each refresh), so 5d
         keeps both well inside their windows. -->
    <key>StartInterval</key>
    <integer>{interval_seconds}</integer>

    <key>RunAtLoad</key>
    <false/>

    <key>ProcessType</key>
    <string>Background</string>

    <key>StandardOutPath</key>
    <string>{log_file}</string>
    <key>StandardErrorPath</key>
    <string>{log_file}</string>
</dict>
</plist>
"""
    plist_path.write_text(plist_xml)

    # Unload first in case it's already loaded under the same label.
    subprocess.run(
        ["launchctl", "unload", str(plist_path)],
        check=False, capture_output=True,
    )
    result = subprocess.run(
        ["launchctl", "load", str(plist_path)],
        check=False, capture_output=True, text=True,
    )
    loaded = result.returncode == 0
    _json({
        "installed": loaded,
        "plist_path": str(plist_path),
        "label": label,
        "interval_seconds": interval_seconds,
        "interval_days": interval_days,
        "log_file": str(log_file),
        "launchctl_output": (result.stdout + result.stderr).strip() or None,
    })


@auth.command("uninstall-refresher")
@click.option(
    "--label",
    default="com.shahine.aqara-cli.refresh",
    show_default=True,
)
def auth_uninstall_refresher(label):
    """Unload and remove the launchd refresher installed via install-refresher."""
    import subprocess

    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
    if not plist_path.exists():
        _json({"removed": False, "reason": "plist not found", "path": str(plist_path)})
        return
    subprocess.run(
        ["launchctl", "unload", str(plist_path)],
        check=False, capture_output=True,
    )
    plist_path.unlink()
    _json({"removed": True, "path": str(plist_path), "label": label})


@auth.command("status")
def auth_status():
    """Show whether the launchd refresher is loaded + the last log lines."""
    import subprocess

    label = "com.shahine.aqara-cli.refresh"
    log_file = Path.home() / "Library" / "Logs" / "aqara-cli" / "refresh.log"
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"

    listed = subprocess.run(
        ["launchctl", "list", label],
        check=False, capture_output=True, text=True,
    )
    last_log = ""
    if log_file.exists():
        try:
            tail = log_file.read_text().splitlines()[-20:]
            last_log = "\n".join(tail)
        except Exception:
            pass

    _json({
        "label": label,
        "plist_exists": plist_path.exists(),
        "plist_path": str(plist_path),
        "log_file": str(log_file),
        "loaded": listed.returncode == 0,
        "launchctl_output": listed.stdout.strip() or None,
        "log_tail": last_log,
    })


# ---------------------------------------------------------------------------
# refresh — manually refresh the access token
# ---------------------------------------------------------------------------
@cli.command()
@click.option("-v", "--verbose", is_flag=True)
def refresh(verbose):
    """Refresh the access token using the stored refresh token.

    Updates os.environ for the current process. To persist across shells,
    re-export the new token from the response, or wire your own secret store.
    """
    resp = api.refresh_access_token(verbose=verbose)
    out = {
        "refreshed": True,
        "access_token_set": bool(os.environ.get("AQARA_OPEN_ACCESS_TOKEN")),
        "response": resp,
    }
    _json(out)


if __name__ == "__main__":
    cli()
