# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-05-26

### Added

- `aqara auth browser-flow` — bootstrap tokens via Aqara's OAuth web flow.
  Starts a local callback listener, opens
  `open-<region>.aqara.com/v3.0/open/authorize` in your browser, captures
  the redirect, exchanges the code at `/v3.0/open/access_token`, and writes
  the resulting tokens to credentials.json.
- Flags: `--port` (override 8765), `--no-browser` (print URL only, useful
  over SSH), `--no-save` (print tokens, skip persistence).

### Changed

- README reordered: browser-flow is now the **primary** documented bootstrap
  path. The email verification-code flow (`request-code` + `get-token`) is
  documented as a fallback because Aqara's email delivery is unreliable
  enough that several users have reported the code never arriving. The
  fallback path stays in the CLI; new users just won't trip over it first.

## [0.2.0] - 2026-05-26

### Added

- `aqara auth` command group, covering the full token bootstrap +
  recurring-refresher lifecycle:
  - `auth set-app` — persist AppId/AppKey/KeyId/region to credentials.json.
  - `auth request-code <account>` — step 1 of OAuth (Aqara emails a code).
  - `auth get-token <account> <code>` — step 2 (exchange for AccessToken +
    RefreshToken; persisted to credentials.json by default).
  - `auth install-refresher` — write + load a launchd plist that runs
    `aqara refresh` every 5 days. Logs to ~/Library/Logs/aqara-cli/.
  - `auth uninstall-refresher` / `auth status` — manage the launchd job.
- `~/.config/aqara-cli/credentials.json` (mode 600) as a secondary credential
  source. Env vars still take precedence; credentials.json fills in any
  missing values and receives the refreshed access/refresh tokens so a
  recurring refresher works without env-var rewriting.
- Comprehensive getting-started in the README walking through developer
  portal signup, app creation, region selection, OAuth bootstrap, and
  launchd install.

## [0.1.0] - 2026-05-26

### Added

- `aqara` CLI talking directly to the Aqara Open Cloud REST API at
  `https://open-{region}.aqara.com/v3.0/open/api`.
- Commands:
  - **Read**: `info`, `homes`, `rooms`, `devices`, `device-status`, `scenes`.
  - **Write**: `rename` (device), `move` (device → room), `room rename`,
    `room create`, `room delete`, `scene-run`.
  - **Auth**: `refresh` (re-issue access token from refresh token).
  - **Escape hatch**: `call <intent> [--data JSON]` for any Aqara intent.
  - **Config**: `home set <name|id>` / `home clear` persist a default home in
    `~/.config/aqara-cli/config.json`.
- Auto-refresh of expired access tokens (code 108/109 → invoke
  `config.auth.refreshToken`, retry the original call once).
- `--dry-run` on every write command. JSON output everywhere for
  programmatic use.
- Verified intent shapes, with quirks documented in the code:
  - `config.device.position` requires `dids` (list), **not** `did`.
  - `config.position.update` is the rename intent (`config.position.name`
    returns 403).
  - `config.position.delete` requires singular `positionId`
    (`positionIds: [list]` returns 302).

[Unreleased]: https://github.com/omarshahine/aqara-cli/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/omarshahine/aqara-cli/releases/tag/v0.3.0
[0.2.0]: https://github.com/omarshahine/aqara-cli/releases/tag/v0.2.0
[0.1.0]: https://github.com/omarshahine/aqara-cli/releases/tag/v0.1.0
