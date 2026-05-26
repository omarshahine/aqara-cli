# aqara-cli

Command-line client for the [Aqara Open Cloud API](https://developer.aqara.com).
Lists homes, devices, rooms, and scenes — renames and moves devices, manages
rooms, runs scenes, refreshes tokens — straight from the terminal.

Unlike the [Aqara MCP server](https://www.npmjs.com/package/@aqara/mcp), which
only exposes a fixed set of read tools, this CLI talks to the full developer
API and can mutate names + room assignments. Verified intent quirks (the
"`dids` vs `did`" footgun, the 403 you get from `config.position.name`, the
singular-`positionId` delete) are baked into the wrapper.

## Install

```bash
pipx install git+https://github.com/omarshahine/aqara-cli.git
```

Or for development:

```bash
git clone https://github.com/omarshahine/aqara-cli && cd aqara-cli
pip install -e ".[dev]"
```

---

## Getting started

Setting up Aqara API access is genuinely fiddly — the docs are scattered and
some endpoints expect quirky payloads. The CLI gets you to a working state in
about 10 minutes, and a recurring launchd refresher means you never have to
think about it again.

### Step 1 — Register a developer app at developer.aqara.com

1. Go to <https://developer.aqara.com/> and sign in with the same Aqara
   account you use in the mobile app (same email/phone — this is what gives
   your dev app permission to see *your* homes and devices).
2. **Console → Cloud Development → Project Management → Add Project.**
   - Name: anything you'll recognize later (e.g. `aqara-cli`).
   - Region: pick the one your account lives in. Most US accounts are `USA`.
   - "Whether to access the cloud-cloud open platform service": **yes**.
3. Once the project is created, open its detail page. You'll see:
   - **AppId** — alphanumeric.
   - **KeyId** — alphanumeric.
   - **AppKey** — under "Application key". Reveal it; copy the full string.
4. **Add a Redirect URI.** In your app settings, register
   `http://localhost:8765/callback` as an authorized Redirect URI. The CLI's
   default bootstrap flow (`aqara auth browser-flow`) needs this — the
   alternative email-code flow is unreliable enough that we don't recommend
   it. **Skip this step and the browser flow won't work.**
5. Note the **region**. Each region has its own endpoint:
   - `usa` → `open-usa.aqara.com`  (default)
   - `cn`  → `open-cn.aqara.com`
   - `eu`  → `open-ger.aqara.com`
   - `ru`  → `open-ru.aqara.com`
   - `kr`  → `open-kr.aqara.com`

   Pick the one that matches your Aqara account. If your devices live in the
   US, use `usa` even if you're physically elsewhere.

### Step 2 — Save the app credentials

Two options. **Pick one.**

#### Option A — credentials.json (recommended for new users)

```bash
aqara auth set-app \
  --app-id "<your-AppId>" \
  --app-key "<your-AppKey>" \
  --key-id "<your-KeyId>" \
  --region usa
```

This writes `~/.config/aqara-cli/credentials.json` with mode `0600`. The CLI
will read from this file unless overridden by env vars (see Option B).

#### Option B — env vars (if you use a secret manager like chezmoi, 1Password CLI, etc.)

Export the following in your shell rc / dotenv / secret store:

```bash
export AQARA_OPEN_APP_ID="<your-AppId>"
export AQARA_OPEN_APP_KEY="<your-AppKey>"
export AQARA_OPEN_KEY_ID="<your-KeyId>"
export AQARA_OPEN_REGION="usa"   # one of: usa cn eu ru kr — default: usa
```

Env vars **always win** over `credentials.json`. Lower-case variants
(`aqara_open_app_id`, …) are also accepted for legacy shell setups.

### Step 3 — Bootstrap user tokens (browser OAuth — recommended)

Aqara's API uses per-user OAuth on top of the app credentials. There are two
ways to get the first set of tokens; **the browser flow is the one that
actually works.** Aqara's email-code flow looks simpler in the docs but
their email delivery is unreliable — many users (including this project's
author) never receive the code. Skip the frustration:

**Prerequisite, one-time, easy to miss:** In your developer.aqara.com app
settings, add `http://localhost:8765/callback` as an authorized Redirect URI.
Without it, the authorize page shows a generic error and you'll think the
whole thing is broken.

Then:

```bash
aqara auth browser-flow
```

What happens:

1. The CLI starts a local HTTP listener on `localhost:8765`.
2. Your browser opens `https://open-<region>.aqara.com/v3.0/open/authorize?...`.
3. You sign in with the same Aqara account that owns your homes/devices.
4. You click **Authorize**; Aqara redirects to `localhost:8765/callback?code=...`.
5. The CLI captures the code, exchanges it for an AccessToken + RefreshToken
   at `/v3.0/open/access_token`, and writes both to credentials.json.

Done. `aqara info` should now show `auth_ok: true`.

Flags worth knowing:
- `--port <N>` if 8765 is taken (you'll need to re-register the redirect URI
  with the new port on the developer portal).
- `--no-browser` to print the URL without opening it (useful over SSH —
  forward the port locally, then click the link).
- `--no-save` to print tokens without writing credentials.json (for users
  who keep secrets in their own manager).

Token lifetimes (as of 2026-05):

- **AccessToken**: 7 days (or whatever you passed via `--validity` on the
  email-code path; the browser flow uses Aqara's default).
- **RefreshToken**: 30 days, rotated on every successful refresh.

**Fallback — email verification code** (only if browser flow truly won't
work for you, e.g. no browser available at all):

```bash
aqara auth request-code your-email@example.com        # Aqara emails a code
aqara auth get-token your-email@example.com 123456    # exchange it
```

In practice, the email is slow, lands in spam, or never arrives. If you're
seeing nothing after 5 minutes, switch to `aqara auth browser-flow`.

### Step 4 — Verify

```bash
aqara info
```

You should see `auth_ok: true` and a list of your homes. If `auth_ok: false`,
the error message tells you what's missing.

### Step 5 — Pick a default home

```bash
aqara homes               # see them
aqara home set "Home"     # persist to ~/.config/aqara-cli/config.json
```

After this, `aqara devices`, `aqara rooms`, and `aqara scenes` are scoped to
that home. Pass `--home <name|id>` per-call to override, or `--all-homes`
on `devices` for everything.

### Step 6 — Install the recurring refresher (macOS only)

Refresh tokens expire in 30 days. To make the install long-term unattended:

```bash
aqara auth install-refresher
```

This writes a launchd plist at
`~/Library/LaunchAgents/com.shahine.aqara-cli.refresh.plist` that runs
`aqara refresh` every 5 days (well inside both the 7-day access window and
the 30-day refresh window). Logs land at
`~/Library/Logs/aqara-cli/refresh.log`.

Check on it any time:

```bash
aqara auth status
```

Uninstall:

```bash
aqara auth uninstall-refresher
```

On **Linux**, set up a systemd timer or cron entry that runs `aqara refresh`
every 5 days. The CLI persists the refreshed tokens to `credentials.json`
automatically; nothing else needs to know.

---

## Common commands

```bash
# Read
aqara homes
aqara rooms
aqara devices
aqara device-status lumi.example1234abcd
aqara scenes

# Rename a device
aqara rename lumi.example1234abcd "Front Door Sensor"

# Move a device to a different room
aqara move lumi.example1234abcd real2.exampleRoomId

# Manage rooms
aqara room rename real2.exampleLivingRoom "Living Room"
aqara room create "Mudroom"        # under the default home
aqara room delete real2.foo        # API refuses if devices still present

# Run a scene
aqara scenes
aqara scene-run <scene-id>

# Manual refresh
aqara refresh
```

Every write supports `--dry-run` — prints the exact intent + payload without
touching the network.

## Escape hatch

For any intent the CLI doesn't wrap yet:

```bash
aqara call query.position.info --data '{"pageNum":1,"pageSize":50}'
aqara call config.auth.refreshToken
aqara call -v query.device.subInfo --data '{"did":"lumi.example1234abcd"}'
```

Pass `-v` to print the outbound request (URL + headers minus secrets).

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

## Why the browser flow is the default

Aqara documents both paths as equivalent; in practice the email-code flow
is unreliable enough that I built this CLI's onboarding around the browser
flow. The reasons people get stuck on email-code:

- Aqara's transactional email frequently lands in spam or doesn't arrive
  at all.
- The code is rate-limited and there's no clear per-account dashboard for
  retries — you just sit there hoping.
- It hides errors. The browser flow surfaces "your redirect URI isn't
  registered" or "wrong region" within seconds; the email flow just stays
  silent.

`aqara auth browser-flow` is a verbatim port of the script that successfully
bootstrapped this account when nothing else worked.

## Troubleshooting

- **`auth_ok: false`** on `aqara info`: missing one of AppId/AppKey/KeyId.
  Run `aqara auth set-app` or check your env vars.
- **`code=108`/`109`** on any call: AccessToken expired. The CLI auto-
  refreshes; if you see this persisting, your RefreshToken expired too —
  re-run Step 3.
- **`code=302 msg="Param not valid: dids ..."`** when calling `move` or a
  raw `config.device.position`: you passed singular `did` instead of `dids`
  (an array). The CLI does it right; only happens if you're using the raw
  `aqara call` escape hatch.
- **`code=403`** on a read intent: usually a region mismatch (e.g. account
  is on `usa` but `region=cn`). Re-check Step 1.5.
- **Email never arrives** in Step 3a: Aqara's email delivery is sometimes
  slow or filtered. Wait 5 minutes, check spam, and if still nothing, fall
  back to the browser OAuth path (see above).

## Project layout

```
aqara-cli/
├── src/aqara_cli/
│   ├── api.py        # signed HTTPS client, token refresh, typed wrappers
│   ├── config.py     # ~/.config/aqara-cli/{config,credentials}.json
│   └── main.py       # Click commands
├── tests/test_cli.py # smoke tests (no network)
└── pyproject.toml
```

## License

MIT — see [LICENSE](LICENSE).
