# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/omarshahine/aqara-cli/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/omarshahine/aqara-cli/releases/tag/v0.1.0
