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


def test_dump_defaults_to_json() -> None:
    """Dump should default to JSON output with validation fields."""
    result = runner.invoke(build_app(), ["dump", fixture_path("valid_geofeed.csv")])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload) == 3
    assert payload[0]["prefix"] == "192.0.2.0/24"
    assert payload[0]["valid"] is True
    assert payload[0]["validation_messages"] == []


def test_dump_csv_format_emits_geofeed_rows() -> None:
    """Dump should emit standard geofeed CSV rows in csv mode."""
    result = runner.invoke(
        build_app(),
        ["dump", fixture_path("valid_geofeed.csv"), "--format", "csv"],
    )

    assert result.exit_code == 0
    assert result.stdout.splitlines() == [
        "192.0.2.0/24,US,US-CA,San Francisco,94104",
        "192.0.2.128/25,US,US-CA,San Francisco,94104",
        "2001:db8::/32,US,US-NY,New York,10001",
    ]


def test_dump_table_format_emits_tabulated_output() -> None:
    """Dump should emit a tabulated view in table mode."""
    result = runner.invoke(
        build_app(),
        ["dump", fixture_path("valid_geofeed.csv"), "--format", "table"],
    )

    assert result.exit_code == 0
    assert "| Prefix" in result.stdout
    assert "| Country" in result.stdout
    assert "| Valid" in result.stdout
    assert "192.0.2.0/24" in result.stdout
    assert "San Francisco" in result.stdout
