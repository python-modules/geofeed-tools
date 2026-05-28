"""CLI tests for the validate command behavior."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from geofeed_tools.cli.app import build_app
from geofeed_tools.models import ValidationReport

runner = CliRunner()


def fixture_path(name: str) -> str:
    """Return absolute path to a fixture file by name."""
    return str(Path(__file__).parent / "fixtures" / name)


def test_validate_json_runs_single_validation_pass(monkeypatch) -> None:
    """Validate should render JSON from a single object-mode validation call."""
    calls: list[str] = []

    def fake_validate(
        self,
        *,
        check_sort: bool = True,
        check_content_type: bool = True,
        check_aggregation: bool = False,
        output: str = "objects",
    ) -> ValidationReport:
        del check_sort, check_content_type, check_aggregation
        calls.append(output)
        assert output == "objects"
        return ValidationReport(
            source=self.source,
            records=3,
            errors=0,
            warnings=0,
            valid=True,
            issues=(),
        )

    monkeypatch.setattr("geofeed_tools.cli.app.GeoFeed.validate", fake_validate)

    result = runner.invoke(build_app(), ["validate", fixture_path("valid_geofeed.csv"), "--format", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["source"].endswith("valid_geofeed.csv")
    assert payload["records"] == 3
    assert payload["errors"] == 0
    assert payload["warnings"] == 0
    assert calls == ["objects"]


def test_validate_strict_fails_on_warning(monkeypatch) -> None:
    """Validate should return exit code 1 with --strict when warnings are present."""

    def fake_validate(
        self,
        *,
        check_sort: bool = True,
        check_content_type: bool = True,
        check_aggregation: bool = False,
        output: str = "objects",
    ) -> ValidationReport:
        del self, check_sort, check_content_type, check_aggregation
        assert output == "objects"
        return ValidationReport(
            source="fixture",
            records=1,
            errors=0,
            warnings=1,
            valid=True,
            issues=(),
        )

    monkeypatch.setattr("geofeed_tools.cli.app.GeoFeed.validate", fake_validate)

    result = runner.invoke(build_app(), ["validate", fixture_path("valid_geofeed.csv"), "--strict"])

    assert result.exit_code == 1


def test_validate_hook_on_valid_feed_exits_zero() -> None:
    """--hook on a clean feed exits 0 and emits an OK status line on stderr."""
    result = runner.invoke(
        build_app(),
        ["validate", fixture_path("valid_geofeed.csv"), "--hook"],
        env={"COLUMNS": "200"},
    )
    assert result.exit_code == 0
    # rich hook output writes status to stderr; default mix_stderr=True folds them.
    assert "OK" in result.output


def test_validate_hook_grep_emits_issue_lines() -> None:
    """--hook --format grep emits ``path:line:severity:code:message`` rows."""
    result = runner.invoke(
        build_app(),
        ["validate", fixture_path("invalid_geofeed.csv"), "--hook", "--format", "grep"],
    )
    assert result.exit_code == 1
    lines = [line for line in result.stdout.splitlines() if line]
    assert all(line.count(":") >= 4 for line in lines)
    assert any("invalid-prefix" in line for line in lines)


def test_validate_hook_strict_fails_on_warning(monkeypatch) -> None:
    """--hook --strict exits 1 when warnings are present, matching the old hook command."""

    def fake_validate(
        self,
        *,
        check_sort: bool = True,
        check_content_type: bool = True,
        check_aggregation: bool = False,
        output: str = "objects",
    ) -> ValidationReport:
        del self, check_sort, check_content_type, check_aggregation
        assert output == "objects"
        return ValidationReport(
            source="fixture",
            records=1,
            errors=0,
            warnings=1,
            valid=True,
            issues=(),
        )

    monkeypatch.setattr("geofeed_tools.cli.app.GeoFeed.validate", fake_validate)

    result = runner.invoke(
        build_app(),
        ["validate", fixture_path("valid_geofeed.csv"), "--hook", "--strict"],
    )
    assert result.exit_code == 1


def test_legacy_hook_command_removed() -> None:
    """The standalone ``hook`` CLI command is gone — use ``validate --hook`` instead."""
    result = runner.invoke(build_app(), ["hook", fixture_path("valid_geofeed.csv")])
    assert result.exit_code != 0
