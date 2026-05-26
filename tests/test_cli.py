"""Smoke tests for the Click CLI surface.

These tests don't talk to the Aqara API — they only verify command discovery,
argument parsing, and the dry-run preview output (which is constructed without
any network call).
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from aqara_cli.main import cli


EXPECTED_COMMANDS = {
    "auth",
    "call",
    "device-status",
    "devices",
    "home",
    "homes",
    "info",
    "move",
    "refresh",
    "rename",
    "room",
    "rooms",
    "scene-run",
    "scenes",
}


def test_help_lists_every_command() -> None:
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0, result.output
    for command in EXPECTED_COMMANDS:
        assert command in result.output, f"missing {command!r} in --help output"


@pytest.mark.parametrize(
    "argv",
    [
        ["--help"],
        ["call", "--help"],
        ["device-status", "--help"],
        ["devices", "--help"],
        ["home", "--help"],
        ["home", "set", "--help"],
        ["home", "clear", "--help"],
        ["homes", "--help"],
        ["info", "--help"],
        ["move", "--help"],
        ["refresh", "--help"],
        ["rename", "--help"],
        ["room", "--help"],
        ["room", "rename", "--help"],
        ["room", "create", "--help"],
        ["room", "delete", "--help"],
        ["rooms", "--help"],
        ["scene-run", "--help"],
        ["scenes", "--help"],
        ["auth", "--help"],
        ["auth", "set-app", "--help"],
        ["auth", "request-code", "--help"],
        ["auth", "get-token", "--help"],
        ["auth", "browser-flow", "--help"],
        ["auth", "install-refresher", "--help"],
        ["auth", "uninstall-refresher", "--help"],
        ["auth", "status", "--help"],
    ],
)
def test_help_for_every_command(argv: list[str]) -> None:
    result = CliRunner().invoke(cli, argv)
    assert result.exit_code == 0, result.output
    assert "Usage:" in result.output


def test_rename_rejects_empty_name() -> None:
    result = CliRunner().invoke(cli, ["rename", "lumi.test", ""])
    assert result.exit_code != 0
    assert "must not be empty" in result.output


def test_rename_rejects_whitespace_only_name() -> None:
    result = CliRunner().invoke(cli, ["rename", "lumi.test", "   "])
    assert result.exit_code != 0
    assert "must not be empty" in result.output


def test_room_rename_rejects_empty_name() -> None:
    result = CliRunner().invoke(cli, ["room", "rename", "real2.test", ""])
    assert result.exit_code != 0
    assert "must not be empty" in result.output


def test_room_create_rejects_empty_name() -> None:
    result = CliRunner().invoke(cli, ["room", "create", "", "--home", "real1.foo"])
    assert result.exit_code != 0
    assert "must not be empty" in result.output


def test_rename_dry_run_does_not_touch_network() -> None:
    """Dry-run must construct its preview without calling the API."""
    result = CliRunner().invoke(
        cli, ["rename", "lumi.test", "New Name", "--dry-run"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["dry_run"] is True
    assert payload["did"] == "lumi.test"
    assert payload["new_name"] == "New Name"
    assert payload["would_send"]["intent"] == "config.device.name"


def test_move_dry_run_does_not_touch_network() -> None:
    result = CliRunner().invoke(
        cli, ["move", "lumi.test", "real2.foo", "--dry-run"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["dry_run"] is True
    assert payload["would_send"]["intent"] == "config.device.position"
    # Critical: must be `dids` (list), not `did` — see #1 bug in field history.
    assert payload["would_send"]["data"] == {
        "dids": ["lumi.test"],
        "positionId": "real2.foo",
    }


def test_room_create_dry_run() -> None:
    result = CliRunner().invoke(
        cli,
        ["room", "create", "Mudroom", "--home", "real1.foo", "--dry-run"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["dry_run"] is True
    assert payload["would_send"]["data"] == {
        "positionName": "Mudroom",
        "parentPositionId": "real1.foo",
    }


def test_room_delete_dry_run_uses_singular_positionId() -> None:
    """`positionIds: [list]` returns 302 from the API — we must use singular."""
    result = CliRunner().invoke(
        cli, ["room", "delete", "real2.foo", "--dry-run"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["dry_run"] is True
    assert payload["would_send"]["data"] == {"positionId": "real2.foo"}


def test_call_rejects_malformed_data() -> None:
    result = CliRunner().invoke(cli, ["call", "query.position.info", "--data", "{not json"])
    assert result.exit_code != 0
    assert "valid JSON" in result.output
