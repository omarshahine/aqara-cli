"""Aqara Open Cloud CLI — Click command group and all subcommands."""

from __future__ import annotations

import json
import os

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
