"""Tests for downloaded real-world geofeed fixtures (local file mode)."""

from __future__ import annotations

from pathlib import Path

import pytest

from geofeed_tools import GeoFeed


def fixture_path(name: str) -> str:
    """Return absolute path to a fixture file by name."""

    return str(Path(__file__).parent / "fixtures" / name)


LOCAL_SOURCES = [
    pytest.param(fixture_path("cloudflare_geofeed.csv"), id="cloudflare"),
    pytest.param(fixture_path("nttgin_geofeed.csv"), id="nttgin"),
    pytest.param(fixture_path("tmobile_geofeed.csv"), id="tmobile"),
]


@pytest.mark.parametrize("source", LOCAL_SOURCES)
def test_local_fixture_parse_returns_records(source: str) -> None:
    """Downloaded fixtures should parse into non-empty record lists."""

    geofeed = GeoFeed(source)
    records = geofeed.parse(output="objects")
    assert isinstance(records, list)
    assert len(records) > 0, f"No records parsed from {source}"


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(fixture_path("cloudflare_geofeed.csv"), id="cloudflare"),
        pytest.param(
            fixture_path("nttgin_geofeed.csv"),
            id="nttgin",
            marks=pytest.mark.xfail(
                strict=True,
                reason=(
                    "nttgin fixture contains invalid prefix "
                    "'165.254.252.023' which currently raises ValueError "
                    "inside info()"
                ),
            ),
        ),
        pytest.param(fixture_path("tmobile_geofeed.csv"), id="tmobile"),
    ],
)
def test_local_fixture_info_totals(source: str) -> None:
    """Info totals should be internally consistent for local fixtures."""

    geofeed = GeoFeed(source)
    info = geofeed.info(output="objects")
    assert not isinstance(info, str)
    assert info.total_records > 0, f"No records reported in info for {source}"
    assert info.ipv4_records + info.ipv6_records == info.total_records


@pytest.mark.parametrize("source", LOCAL_SOURCES)
def test_local_fixture_validate_returns_report(source: str) -> None:
    """Validation should complete and return a structured report."""

    geofeed = GeoFeed(source)
    report = geofeed.validate(output="objects")
    assert not isinstance(report, str)
    assert report.records > 0, (
        f"No records found in validation report for {source}"
    )
