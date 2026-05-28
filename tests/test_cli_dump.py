"""CLI tests for the dump command output formats."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from geofeed_tools.cli.app import build_app

runner = CliRunner()


def fixture_path(name: str) -> str:
    """Return absolute path to a fixture file by name."""
    return str(Path(__file__).parent / "fixtures" / name)


def test_dump_defaults_to_rich() -> None:
    """Dump should default to the rich human-readable format."""
    result = runner.invoke(
        build_app(),
        ["dump", fixture_path("valid_geofeed.csv")],
        env={"COLUMNS": "200"},
    )

    assert result.exit_code == 0
    assert "Prefix" in result.stdout
    assert "192.0.2.0/24" in result.stdout
    # Rich rendering uses box-drawing characters not present in plain CSV/JSON.
    assert "╭" in result.stdout or "│" in result.stdout


def test_dump_json_format() -> None:
    """Dump in json mode should emit a JSON array with validation fields."""
    result = runner.invoke(
        build_app(),
        ["dump", fixture_path("valid_geofeed.csv"), "--format", "json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload) == 3
    assert payload[0]["prefix"] == "192.0.2.0/24"
    assert payload[0]["valid"] is True
    assert payload[0]["validation_messages"] == []


def test_dump_grep_format_emits_geofeed_rows() -> None:
    """Dump in grep mode should emit standard 5-column geofeed CSV rows."""
    result = runner.invoke(
        build_app(),
        ["dump", fixture_path("valid_geofeed.csv"), "--format", "grep"],
    )

    assert result.exit_code == 0
    assert result.stdout.splitlines() == [
        "192.0.2.0/24,US,US-CA,San Francisco,94104",
        "192.0.2.128/25,US,US-CA,San Francisco,94104",
        "2001:db8::/32,US,US-NY,New York,10001",
    ]


def test_dump_plain_format_emits_text_table() -> None:
    """Dump in plain mode should emit an unstyled aligned table."""
    result = runner.invoke(
        build_app(),
        ["dump", fixture_path("valid_geofeed.csv"), "--format", "plain"],
        env={"COLUMNS": "200"},
    )

    assert result.exit_code == 0
    assert "Prefix" in result.stdout
    assert "192.0.2.0/24" in result.stdout
    assert "San Francisco" in result.stdout
    # Plain mode must not draw the rich box characters.
    assert "╭" not in result.stdout
    assert "│" not in result.stdout
