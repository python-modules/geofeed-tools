"""Basic API tests for the geofeed_tools package."""

from __future__ import annotations

from pathlib import Path

from geofeed_tools import GeoFeed


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
    assert info.ipv4_records == 2
    assert info.ipv6_records == 1


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
