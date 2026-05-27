"""CLI tests for the lookup command behavior."""

from __future__ import annotations

from typer.testing import CliRunner

from geofeed_tools import GeoFeedDiscoveryError, GeofeedRecord, QueryResult
from geofeed_tools.cli.app import build_app
from geofeed_tools.io_utils import query_to_json, records_to_csv

runner = CliRunner()

_SAMPLE_RECORD = GeofeedRecord(
    prefix="203.0.113.0/24",
    country="US",
    region="US-CA",
    city="Los Angeles",
)


def _make_fake_geofeed(result: QueryResult | GeoFeedDiscoveryError):
    class FakeGeoFeed:
        @staticmethod
        def lookup(
            query: str,
            *,
            return_all: bool = False,
            include_longer: bool = False,
            rdap_method: str = "rdap.org",
            output: str = "objects",
        ) -> str:
            del return_all, include_longer, rdap_method
            if isinstance(result, GeoFeedDiscoveryError):
                raise result
            if output == "json":
                return query_to_json(result)
            assert output == "csv"
            return records_to_csv(result.matches, include_validation=False)

        # keep doctor available so other commands still work
        @staticmethod
        def doctor(*args, **kwargs):  # pragma: no cover
            raise NotImplementedError

    return FakeGeoFeed


def test_cli_lookup_emits_csv_by_default(monkeypatch) -> None:
    """Lookup should print CSV of matches when a geofeed and match are found."""
    qr = QueryResult(query="203.0.113.1", matches=(_SAMPLE_RECORD,))
    monkeypatch.setattr("geofeed_tools.cli.app.GeoFeed", _make_fake_geofeed(qr))

    outcome = runner.invoke(build_app(), ["lookup", "203.0.113.1"])

    assert outcome.exit_code == 0
    assert "203.0.113.0/24" in outcome.stdout
    assert "US" in outcome.stdout


def test_cli_lookup_emits_json(monkeypatch) -> None:
    """Lookup --json should emit a QueryResult-shaped JSON payload."""
    qr = QueryResult(query="203.0.113.1", matches=(_SAMPLE_RECORD,))
    monkeypatch.setattr("geofeed_tools.cli.app.GeoFeed", _make_fake_geofeed(qr))

    outcome = runner.invoke(build_app(), ["lookup", "203.0.113.1", "--json"])

    assert outcome.exit_code == 0
    assert '"query": "203.0.113.1"' in outcome.stdout
    assert '"prefix": "203.0.113.0/24"' in outcome.stdout
    # lookup JSON must NOT include RDAP metadata (unlike doctor)
    assert "geofeed_url" not in outcome.stdout
    assert "lookup_strategy" not in outcome.stdout


def test_cli_lookup_exits_nonzero_when_no_geofeed(monkeypatch) -> None:
    """Lookup should fail with a message when no geofeed URL is discovered."""
    monkeypatch.setattr(
        "geofeed_tools.cli.app.GeoFeed",
        _make_fake_geofeed(GeoFeedDiscoveryError("203.0.113.1")),
    )

    outcome = runner.invoke(build_app(), ["lookup", "203.0.113.1"])

    assert outcome.exit_code == 1
    assert "no geofeed found" in outcome.output


def test_cli_lookup_exits_nonzero_when_no_matches(monkeypatch) -> None:
    """Lookup should fail when the geofeed is found but has no matching records."""
    qr = QueryResult(query="203.0.113.1", matches=())
    monkeypatch.setattr("geofeed_tools.cli.app.GeoFeed", _make_fake_geofeed(qr))

    outcome = runner.invoke(build_app(), ["lookup", "203.0.113.1"])

    assert outcome.exit_code == 1
    assert "no match" in outcome.output


def test_cli_lookup_exits_nonzero_when_no_matches_json(monkeypatch) -> None:
    """Lookup --json should still exit 1 when no matches are found."""
    qr = QueryResult(query="203.0.113.1", matches=())
    monkeypatch.setattr("geofeed_tools.cli.app.GeoFeed", _make_fake_geofeed(qr))

    outcome = runner.invoke(build_app(), ["lookup", "203.0.113.1", "--json"])

    assert outcome.exit_code == 1
    assert '"matches": []' in outcome.stdout


def test_cli_lookup_accepts_rdap_method_override(monkeypatch) -> None:
    """Lookup should forward --rdap-method to GeoFeed.lookup."""
    captured: dict[str, str] = {}

    class CapturingFakeGeoFeed:
        @staticmethod
        def lookup(
            query: str,
            *,
            return_all: bool = False,
            include_longer: bool = False,
            rdap_method: str = "rdap.org",
            output: str = "objects",
        ) -> str:
            del return_all, include_longer
            captured["rdap_method"] = rdap_method
            if output == "json":
                return query_to_json(QueryResult(query=query, matches=(_SAMPLE_RECORD,)))
            return records_to_csv((_SAMPLE_RECORD,), include_validation=False)

    monkeypatch.setattr("geofeed_tools.cli.app.GeoFeed", CapturingFakeGeoFeed)

    outcome = runner.invoke(
        build_app(),
        ["lookup", "203.0.113.1", "--rdap-method", "iana-bootstrap"],
    )

    assert outcome.exit_code == 0
    assert captured["rdap_method"] == "iana-bootstrap"
