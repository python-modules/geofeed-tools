"""Integration tests that load real geofeed sources over HTTP."""

from __future__ import annotations

import pytest

from geofeed_tools import GeoFeed

# ---------------------------------------------------------------------------
# Parameterized fixtures
# ---------------------------------------------------------------------------

HTTP_SOURCES = [
    pytest.param(
        "https://api.cloudflare.com/local-ip-ranges.csv",
        id="cloudflare",
    ),
    pytest.param(
        "https://raw.githubusercontent.com/nttgin/geofeeds/master/geofeeds.csv",
        id="nttgin",
    ),
    pytest.param(
        "https://raw.githubusercontent.com/tmobile/tmus-geofeed/main/tmus-geo-ip.txt",
        id="tmobile",
    ),
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize("url", HTTP_SOURCES)
def test_http_parse_returns_records(url: str) -> None:
    """Each public geofeed URL should parse into a non-empty record list."""
    geofeed = GeoFeed(url)
    records = geofeed.parse(output="objects")
    assert isinstance(records, list)
    assert len(records) > 0, f"No records parsed from {url}"


@pytest.mark.integration
@pytest.mark.parametrize(
    "url",
    [
        pytest.param(
            "https://api.cloudflare.com/local-ip-ranges.csv",
            id="cloudflare",
        ),
        pytest.param(
            "https://raw.githubusercontent.com/nttgin/geofeeds/master/geofeeds.csv",
            id="nttgin",
            # The feed contains an invalid octet-notation prefix
            # ("165.254.252.023") that triggers a crash in info(); mark xfail
            # so the test documents the known defect and will flip to XPASS if
            # the library is made more tolerant.
            marks=pytest.mark.xfail(
                strict=True,
                reason=(
                    "nttgin feed contains invalid prefix '165.254.252.023' "
                    "which currently raises ValueError inside info()"
                ),
            ),
        ),
        pytest.param(
            "https://raw.githubusercontent.com/tmobile/tmus-geofeed/main/tmus-geo-ip.txt",
            id="tmobile",
        ),
    ],
)
def test_http_info_totals(url: str) -> None:
    """Info totals should be consistent with parsed record counts."""
    geofeed = GeoFeed(url)
    info = geofeed.info(output="objects")
    assert not isinstance(info, str)
    assert info.total_records > 0, f"No records reported in info for {url}"
    assert info.prefixes_v4 + info.prefixes_v6 == info.total_records


@pytest.mark.integration
@pytest.mark.parametrize("url", HTTP_SOURCES)
def test_http_validate_returns_report(url: str) -> None:
    """Validation should complete and return a structured report.

    We do not assert errors == 0 because public third-party feeds may contain
    real RFC 8805 violations that are outside our control.
    """
    geofeed = GeoFeed(url)
    report = geofeed.validate(output="objects")
    assert not isinstance(report, str)
    assert report.records > 0, f"No records found in validation report for {url}"
