# aqara-cli

Command-line client for the [Aqara Open Cloud API](https://developer.aqara.com).
Lists homes, devices, rooms, and scenes — renames and moves devices, manages
rooms, refreshes tokens — straight from the terminal.

Unlike the [Aqara MCP server](https://www.npmjs.com/package/@aqara/mcp), which
only exposes a fixed set of read tools, this CLI talks to the full developer
API and can mutate names + room assignments.

## Install

```bash
pipx install git+https://github.com/omarshahine/aqara-cli.git
```

## Set up credentials

Register a developer app at <https://developer.aqara.com> and export the
following env vars (in your shell rc, `.env`, secret manager — wherever):

| Variable | Purpose |
|---|---|
| `AQARA_OPEN_APP_ID` | App id from the developer portal |
| `AQARA_OPEN_APP_KEY` | App key (used to sign requests) |
| `AQARA_OPEN_KEY_ID` | Per-key identifier |
| `AQARA_OPEN_ACCESS_TOKEN` | OAuth-issued access token for the end user |
| `AQARA_OPEN_REFRESH_TOKEN` | OAuth refresh token (lets the CLI auto-renew) |
| `AQARA_OPEN_REGION` | One of: `usa` (default), `cn`, `eu`, `ru`, `kr` |

Lower-case variants of these names are also accepted.

Quick sanity check:

```bash
aqara info
```

## Set a default home

```bash
aqara homes                    # see what's available
aqara home set "Home"          # persist to ~/.config/aqara-cli/config.json
```

After this, `aqara devices`, `aqara rooms`, and `aqara scenes` are scoped to
that home. Use `--home <name|id>` per-call to override, or `--all-homes` on
`devices` to see everything.

## Common commands

```bash
# Read
aqara homes
aqara rooms
aqara devices
aqara device-status lumi.158d0008ab2b2d
aqara scenes

# Rename a device
aqara rename lumi.158d0008ab2b2d "Front Door Sensor"

# Move a device to a different room
aqara move lumi.158d0008ab2b2d real2.1178496813997576192

# Manage rooms
aqara room rename real2.1000992461178556416 "Living Room"
aqara room create "Mudroom"        # under the default home
aqara room delete real2.foo        # API refuses if devices still present

# Run a scene
aqara scenes
aqara scene-run <scene-id>
```

Every write supports `--dry-run`, which prints the exact intent + payload
without touching the network.

## Escape hatch

For any intent not yet wrapped:

```bash
aqara call query.position.info --data '{"pageNum":1,"pageSize":50}'
aqara call config.auth.refreshToken
aqara call -v query.device.subInfo --data '{"did":"lumi.158d0008ab2b2d"}'
```

Pass `-v` to print the outbound request (URL + headers minus secrets).

## Token refresh

Expired access tokens are detected (codes 108/109, or any "token expired"
message) and refreshed automatically once per call — your stored refresh
token must still be valid. To force a refresh:

```bash
aqara refresh
```

The new tokens are written to `os.environ` for the current process; the CLI
does **not** persist them to disk. Wire your own secret manager (chezmoi,
1Password CLI, …) if you want them to survive across shells. The
`config.auth.refreshToken` response is shown so you can copy the new values.

## Verified intent quirks

Found while building this; documented in code so the next person doesn't
re-discover them:

- `config.device.position` requires `dids` (an array of device ids), **not**
  the natural-looking singular `did`. Calling with `did` returns
  `code=302, msg="Param not valid: dids 不能为空"`.
- The position-rename intent is `config.position.update`, not
  `config.position.name` (that returns 403).
- `config.position.delete` requires singular `positionId`. The plural
  `positionIds: [list]` returns 302.

## License

MIT — see [LICENSE](LICENSE).
