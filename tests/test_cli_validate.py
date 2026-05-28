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
