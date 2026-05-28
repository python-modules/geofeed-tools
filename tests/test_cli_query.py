"""CLI tests for the query command behavior."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from geofeed_tools.cli.app import build_app
from geofeed_tools.models import DoctorLookup, QueryResult
from geofeed_tools.rdap import ResolvedRdapLookup

runner = CliRunner()


def fixture_path(name: str) -> str:
    """Return absolute path to a fixture file by name."""
    return str(Path(__file__).parent / "fixtures" / name)


def test_cli_query_disables_query_index_cache(monkeypatch) -> None:
    """CLI query should disable API query cache for one-shot process runs."""

    class FakeGeoFeed:
        last_cache_query_index: bool | None = None

        def __init__(
            self,
            source: str,
            *,
            cache_query_index: bool = True,
            rdap_method: str = "rdap.org",
        ):
            del source, rdap_method
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


def _resolved_with_url(query: str, geofeed_url: str | None) -> ResolvedRdapLookup:
    """Build a ResolvedRdapLookup with the requested geofeed URL (or None)."""
    return ResolvedRdapLookup(
        lookup=DoctorLookup(
            lookup_strategy="ip-address",
            rdap_method="rdap.org",
            rdap_query=query,
            bootstrap_url=f"https://rdap.org/ip/{query}",
            geofeed_url=geofeed_url,
        ),
        range_start=None,
        range_end=None,
    )


def test_cli_query_single_arg_uses_source_as_query(monkeypatch) -> None:
    """`query <ip>` (one arg) discovers via RDAP and queries the same IP."""
    monkeypatch.setattr(
        "geofeed_tools.core.resolve_geofeed_lookup",
        lambda query, *, rdap_method="rdap.org": _resolved_with_url(query, "https://example.com/geofeed.csv"),
    )
    monkeypatch.setattr(
        "geofeed_tools.core.load_input",
        lambda source: (b"203.0.113.0/24,US,US-CA,Los Angeles,\n", "text/csv"),
    )

    result = runner.invoke(build_app(), ["query", "203.0.113.1", "--format", "json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["query"] == "203.0.113.1"
    assert payload["matches"][0]["prefix"] == "203.0.113.0/24"


def test_cli_query_single_arg_requires_ip_or_prefix() -> None:
    """`query <file>` without QUERY should fail with a clear parameter error."""
    result = runner.invoke(build_app(), ["query", fixture_path("valid_geofeed.csv")])
    assert result.exit_code != 0
    assert "IP" in result.output or "IP" in (result.stderr or "")


def test_cli_query_single_arg_no_geofeed_published(monkeypatch) -> None:
    """`query <ip>` exits 1 with a friendly error when no geofeed is published."""
    monkeypatch.setattr(
        "geofeed_tools.core.resolve_geofeed_lookup",
        lambda query, *, rdap_method="rdap.org": _resolved_with_url(query, None),
    )

    result = runner.invoke(build_app(), ["query", "198.51.100.1", "--format", "json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["query"] == "198.51.100.1"
    assert "no geofeed" in payload["error"]


def test_legacy_lookup_command_removed() -> None:
    """The standalone ``lookup`` CLI command is gone — use ``query <ip>`` instead."""
    result = runner.invoke(build_app(), ["lookup", "203.0.113.1"])
    assert result.exit_code != 0
