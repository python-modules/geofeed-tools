"""Basic API tests for the geofeed_tools package."""

from __future__ import annotations

from pathlib import Path

import geofeed_tools.core as core_module
import geofeed_tools.query as query_module
from geofeed_tools import GeoFeed, GeoFeedDiscoveryError
from geofeed_tools.models import DoctorLookup
from geofeed_tools.rdap import ResolvedRdapLookup


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


def test_geofeed_accepts_ip_source_and_resolves_via_rdap(monkeypatch) -> None:
    """GeoFeed(ip) should run an RDAP discovery and load the resolved URL."""
    geofeed_text = b"192.0.2.0/24,US,US-CA,Los Angeles,90001\n192.0.2.128/25,US,US-CA,Pasadena,91101\n"
    resolved = ResolvedRdapLookup(
        lookup=DoctorLookup(
            lookup_strategy="ip-address",
            rdap_method="rdap.org",
            rdap_query="192.0.2.200",
            bootstrap_url="https://rdap.org/ip/192.0.2.200",
            geofeed_url="https://example.com/geofeed.csv",
            geofeed_discovered_via="rdap link rel=geofeed",
        ),
        range_start=None,
        range_end=None,
    )

    resolve_calls: list[tuple[str, str]] = []
    load_calls: list[str] = []

    def fake_resolve(query: str, *, rdap_method: str = "rdap.org"):
        resolve_calls.append((query, rdap_method))
        return resolved

    def fake_load(source: str):
        load_calls.append(source)
        return geofeed_text, "text/csv"

    monkeypatch.setattr("geofeed_tools.core.resolve_geofeed_lookup", fake_resolve)
    monkeypatch.setattr("geofeed_tools.core.load_input", fake_load)

    geofeed = GeoFeed("192.0.2.200")

    assert resolve_calls == [("192.0.2.200", "rdap.org")]
    assert load_calls == ["https://example.com/geofeed.csv"]
    assert geofeed.original_source == "192.0.2.200"
    assert geofeed.source == "https://example.com/geofeed.csv"
    assert geofeed.discovery is not None
    assert geofeed.discovery.geofeed_url == "https://example.com/geofeed.csv"

    info = geofeed.info(output="objects")
    assert not isinstance(info, str)
    assert info.prefixes_total == 2


def test_geofeed_accepts_prefix_source(monkeypatch) -> None:
    """GeoFeed should accept a CIDR prefix and resolve it via RDAP."""
    resolved = ResolvedRdapLookup(
        lookup=DoctorLookup(
            lookup_strategy="prefix-network-address",
            rdap_method="rdap.org",
            rdap_query="192.0.2.0",
            bootstrap_url="https://rdap.org/ip/192.0.2.0",
            geofeed_url="https://example.com/geofeed.csv",
        ),
        range_start=None,
        range_end=None,
    )

    monkeypatch.setattr(
        "geofeed_tools.core.resolve_geofeed_lookup",
        lambda query, *, rdap_method="rdap.org": resolved,
    )
    monkeypatch.setattr(
        "geofeed_tools.core.load_input",
        lambda source: (b"192.0.2.0/24,US,US-CA,LA,\n", "text/csv"),
    )

    geofeed = GeoFeed("192.0.2.0/24")
    assert geofeed.source == "https://example.com/geofeed.csv"
    assert geofeed.discovery is not None


def test_geofeed_ip_source_raises_when_no_geofeed_found(monkeypatch) -> None:
    """A failed RDAP discovery should raise GeoFeedDiscoveryError at construction."""
    resolved = ResolvedRdapLookup(
        lookup=DoctorLookup(
            lookup_strategy="ip-address",
            rdap_method="rdap.org",
            rdap_query="198.51.100.1",
            bootstrap_url="https://rdap.org/ip/198.51.100.1",
            geofeed_url=None,
        ),
        range_start=None,
        range_end=None,
    )
    monkeypatch.setattr(
        "geofeed_tools.core.resolve_geofeed_lookup",
        lambda query, *, rdap_method="rdap.org": resolved,
    )

    import pytest

    with pytest.raises(GeoFeedDiscoveryError) as exc_info:
        GeoFeed("198.51.100.1")
    assert exc_info.value.query == "198.51.100.1"


def test_geofeed_rdap_resolution_passes_rdap_method(monkeypatch) -> None:
    """The rdap_method constructor arg should be forwarded to the resolver."""
    captured: list[str] = []

    def fake_resolve(query: str, *, rdap_method: str = "rdap.org"):
        captured.append(rdap_method)
        return ResolvedRdapLookup(
            lookup=DoctorLookup(
                lookup_strategy="ip-address",
                rdap_method=rdap_method,
                rdap_query=query,
                bootstrap_url=f"https://rdap.org/ip/{query}",
                geofeed_url="https://example.com/geofeed.csv",
            ),
            range_start=None,
            range_end=None,
        )

    monkeypatch.setattr("geofeed_tools.core.resolve_geofeed_lookup", fake_resolve)
    monkeypatch.setattr(
        "geofeed_tools.core.load_input",
        lambda source: (b"", "text/csv"),
    )

    GeoFeed("192.0.2.200", rdap_method="iana-bootstrap")
    assert captured == ["iana-bootstrap"]


def test_geofeed_ip_source_does_not_reresolve_on_reload(monkeypatch) -> None:
    """Once resolved, reload reuses the discovered URL without another RDAP call."""
    resolved = ResolvedRdapLookup(
        lookup=DoctorLookup(
            lookup_strategy="ip-address",
            rdap_method="rdap.org",
            rdap_query="192.0.2.200",
            bootstrap_url="https://rdap.org/ip/192.0.2.200",
            geofeed_url="https://example.com/geofeed.csv",
        ),
        range_start=None,
        range_end=None,
    )

    resolve_count = 0

    def fake_resolve(query: str, *, rdap_method: str = "rdap.org"):
        nonlocal resolve_count
        resolve_count += 1
        return resolved

    monkeypatch.setattr("geofeed_tools.core.resolve_geofeed_lookup", fake_resolve)
    monkeypatch.setattr(
        "geofeed_tools.core.load_input",
        lambda source: (b"192.0.2.0/24,US,US-CA,LA,\n", "text/csv"),
    )

    geofeed = GeoFeed("192.0.2.200")
    geofeed.reload()
    geofeed.reload()
    assert resolve_count == 1
