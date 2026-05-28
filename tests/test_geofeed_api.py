"""Basic API tests for the geofeed_tools package."""

from __future__ import annotations

from pathlib import Path

import geofeed_tools.core as core_module
import geofeed_tools.query as query_module
from geofeed_tools import GeoFeed, GeoFeedDiscoveryError
from geofeed_tools.models import DoctorLookup, DoctorResult, QueryResult


def fixture_path(name: str) -> str:
    """Return absolute path to a fixture file by name."""
    return str(Path(__file__).parent / "fixtures" / name)


def test_parse_and_info() -> None:
    """Parse valid data and compute basic summary metrics."""
    geofeed = GeoFeed(fixture_path("valid_geofeed.csv"))
    records = geofeed.parse(output="objects")
    assert isinstance(records, list)
    assert len(records) == 3

    info = geofeed.info(output="objects")
    assert not isinstance(info, str)
    assert info.total_records == 3
    assert info.prefixes_v4 == 2
    assert info.prefixes_v6 == 1


def test_validate_invalid_file() -> None:
    """Ensure invalid fixture returns one or more validation errors."""
    geofeed = GeoFeed(fixture_path("invalid_geofeed.csv"))
    report = geofeed.validate(output="objects")
    assert not isinstance(report, str)
    assert report.errors >= 2


def test_normalize_and_query_outputs() -> None:
    """Validate normalized CSV and query JSON output paths."""
    geofeed = GeoFeed(fixture_path("valid_geofeed.csv"))

    normalized_csv = geofeed.normalize(output="csv")
    assert isinstance(normalized_csv, str)
    assert "192.0.2.0/24" in normalized_csv

    query = geofeed.query("192.0.2.200", output="json")
    assert isinstance(query, str)
    assert '"query": "192.0.2.200"' in query


def test_parse_with_normalize_option() -> None:
    """Parse supports optional normalization before serialization."""
    geofeed = GeoFeed(fixture_path("valid_geofeed.csv"))

    parsed = geofeed.parse(output="objects", include_validation=False)
    normalized = geofeed.parse(
        output="objects",
        include_validation=False,
        normalize=True,
    )

    assert isinstance(parsed, list)
    assert isinstance(normalized, list)
    assert len(parsed) == 3
    assert len(normalized) == 2


def test_query_include_longer_prefers_most_specific_when_not_returning_all() -> None:
    """Single-result query path should return the most specific matching prefix."""
    geofeed = GeoFeed(fixture_path("valid_geofeed.csv"))

    result = geofeed.query(
        "192.0.2.0/24",
        include_longer=True,
        return_all=False,
        output="objects",
    )

    assert not isinstance(result, str)
    assert len(result.matches) == 1
    assert result.matches[0].prefix == "192.0.2.128/25"


def test_validate_includes_raw_line_context() -> None:
    """Validation line-scoped issues should include source raw line context."""
    geofeed = GeoFeed(fixture_path("invalid_geofeed.csv"))
    report = geofeed.validate(output="objects")

    assert not isinstance(report, str)
    assert any(
        issue.code == "invalid-prefix" and issue.raw_line == "badprefix,US,US-CA,City,10000" for issue in report.issues
    )


def test_query_reuses_index_until_reload(monkeypatch) -> None:
    """GeoFeed query should reuse indexed records until source reload."""
    geofeed = GeoFeed(fixture_path("valid_geofeed.csv"))
    call_count = 0

    real_loader = core_module.load_query_records

    def counting_loader(text: str):
        nonlocal call_count
        call_count += 1
        return real_loader(text)

    monkeypatch.setattr("geofeed_tools.core.load_query_records", counting_loader)

    first = geofeed.query("192.0.2.200", output="objects")
    second = geofeed.query("2001:db8::1", output="objects")

    assert not isinstance(first, str)
    assert not isinstance(second, str)
    assert call_count == 1

    geofeed.reload()
    third = geofeed.query("192.0.2.1", output="objects")
    assert not isinstance(third, str)
    assert call_count == 2


def test_query_cache_can_be_disabled(monkeypatch) -> None:
    """GeoFeed should allow skipping query index caching per instance."""
    geofeed = GeoFeed(fixture_path("valid_geofeed.csv"), cache_query_index=False)
    call_count = 0

    real_loader = query_module.load_query_records

    def counting_loader(text: str):
        nonlocal call_count
        call_count += 1
        return real_loader(text)

    monkeypatch.setattr("geofeed_tools.query.load_query_records", counting_loader)

    first = geofeed.query("192.0.2.200", output="objects")
    second = geofeed.query("2001:db8::1", output="objects")

    assert not isinstance(first, str)
    assert not isinstance(second, str)
    assert call_count == 2


def test_lookup_returns_query_result(monkeypatch) -> None:
    """GeoFeed.lookup should return a QueryResult with matches from the discovered geofeed."""
    record_stub = core_module.GeofeedRecord(prefix="203.0.113.0/24", country="US")

    def fake_doctor_query(query, *, return_all=False, include_longer=False, rdap_method="rdap.org"):
        return DoctorResult(
            query=query,
            lookup=DoctorLookup(
                lookup_strategy="ip-address",
                rdap_method=rdap_method,
                rdap_query=query,
                bootstrap_url=f"https://rdap.org/ip/{query}",
                geofeed_url="https://example.com/geofeed.csv",
            ),
            matches=(record_stub,),
        )

    monkeypatch.setattr("geofeed_tools.core.doctor_query", fake_doctor_query)

    result = GeoFeed.lookup("203.0.113.1")

    assert isinstance(result, QueryResult)
    assert result.query == "203.0.113.1"
    assert len(result.matches) == 1
    assert result.matches[0].prefix == "203.0.113.0/24"


def test_lookup_raises_when_no_geofeed(monkeypatch) -> None:
    """GeoFeed.lookup should raise GeoFeedDiscoveryError when no geofeed URL is found."""

    def fake_doctor_query(query, *, return_all=False, include_longer=False, rdap_method="rdap.org"):
        return DoctorResult(
            query=query,
            lookup=DoctorLookup(
                lookup_strategy="ip-address",
                rdap_method=rdap_method,
                rdap_query=query,
                bootstrap_url=f"https://rdap.org/ip/{query}",
            ),
            matches=(),
        )

    monkeypatch.setattr("geofeed_tools.core.doctor_query", fake_doctor_query)

    import pytest

    with pytest.raises(GeoFeedDiscoveryError) as exc_info:
        GeoFeed.lookup("203.0.113.1")
    assert exc_info.value.query == "203.0.113.1"


def test_lookup_json_output(monkeypatch) -> None:
    """GeoFeed.lookup with output='json' should return a JSON string."""
    record_stub = core_module.GeofeedRecord(prefix="203.0.113.0/24", country="US")

    def fake_doctor_query(query, *, return_all=False, include_longer=False, rdap_method="rdap.org"):
        return DoctorResult(
            query=query,
            lookup=DoctorLookup(
                lookup_strategy="ip-address",
                rdap_method=rdap_method,
                rdap_query=query,
                bootstrap_url=f"https://rdap.org/ip/{query}",
                geofeed_url="https://example.com/geofeed.csv",
            ),
            matches=(record_stub,),
        )

    monkeypatch.setattr("geofeed_tools.core.doctor_query", fake_doctor_query)

    payload = GeoFeed.lookup("203.0.113.1", output="json")

    assert isinstance(payload, str)
    assert '"query": "203.0.113.1"' in payload
    assert '"prefix": "203.0.113.0/24"' in payload
