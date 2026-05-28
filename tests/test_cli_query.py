"""CLI tests for the query command behavior."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from geofeed_tools.cli.app import build_app
from geofeed_tools.models import QueryResult

runner = CliRunner()


def fixture_path(name: str) -> str:
    """Return absolute path to a fixture file by name."""
    return str(Path(__file__).parent / "fixtures" / name)


def test_cli_query_disables_query_index_cache(monkeypatch) -> None:
    """CLI query should disable API query cache for one-shot process runs."""

    class FakeGeoFeed:
        last_cache_query_index: bool | None = None

        def __init__(self, source: str, *, cache_query_index: bool = True):
            del source
            FakeGeoFeed.last_cache_query_index = cache_query_index

        def query(
            self,
            query: str,
            *,
            return_all: bool = False,
            include_longer: bool = False,
            output: str = "objects",
        ) -> QueryResult:
            del return_all, include_longer
            assert output == "objects"
            return QueryResult(query=query, matches=())

    monkeypatch.setattr("geofeed_tools.cli.app.GeoFeed", FakeGeoFeed)

    result = runner.invoke(
        build_app(),
        ["query", fixture_path("valid_geofeed.csv"), "192.0.2.1", "--format", "json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["query"] == "192.0.2.1"
    assert payload["matches"] == []
    assert FakeGeoFeed.last_cache_query_index is False
