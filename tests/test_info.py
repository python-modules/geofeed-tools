"""Tests for the unified info builder and CLI command."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from geofeed_tools import GeoFeed
from geofeed_tools.cli.app import build_app
from geofeed_tools.models import CountryStatistics, GeoFeedInfo, NormalizationPreview

runner = CliRunner()
FIXTURE = str(Path(__file__).parent / "fixtures" / "valid_geofeed.csv")
INVALID_FIXTURE = str(Path(__file__).parent / "fixtures" / "invalid_geofeed.csv")


def test_info_returns_dataclass() -> None:
    """GeoFeed.info defaults to returning a GeoFeedInfo dataclass."""
    info = GeoFeed(FIXTURE).info()
    assert isinstance(info, GeoFeedInfo)
    assert info.prefixes_v4 == 2
    assert info.prefixes_v6 == 1
    assert info.prefixes_total == 3
    # backwards-compatible alias
    assert info.total_records == 3


def test_info_counts_uniques_and_duplicates() -> None:
    """Unique prefixes and duplicate count are surfaced explicitly."""
    info = GeoFeed(FIXTURE).info()
    assert isinstance(info, GeoFeedInfo)
    assert info.unique_prefixes == 3
    assert info.duplicates == 0


def test_info_slash_24s_uses_floor_division() -> None:
    """A /24 + /25 contributes 384 v4 addresses → 1 full /24 equivalent."""
    info = GeoFeed(FIXTURE).info()
    assert isinstance(info, GeoFeedInfo)
    assert info.slash_24s == 1


def test_info_slash_48s_for_v6() -> None:
    """A single /32 IPv6 prefix yields 2**16 /48 equivalents."""
    info = GeoFeed(FIXTURE).info()
    assert isinstance(info, GeoFeedInfo)
    assert info.slash_48s == 1 << 16  # 65,536


def test_info_geography_uniques() -> None:
    """Geography section reports distinct country/region/city/postal counts."""
    info = GeoFeed(FIXTURE).info()
    assert isinstance(info, GeoFeedInfo)
    assert info.unique_countries == 1
    assert info.unique_regions == 2
    assert info.unique_cities == 2
    assert info.unique_postal_codes == 2


def test_info_by_country_includes_v4_and_v6() -> None:
    """By-country breakdown folds v4 and v6 contributions into one row."""
    info = GeoFeed(FIXTURE).info()
    assert isinstance(info, GeoFeedInfo)
    assert len(info.by_country) == 1
    us = info.by_country[0]
    assert isinstance(us, CountryStatistics)
    assert us.country == "US"
    assert us.prefixes_v4 == 2
    assert us.prefixes_v6 == 1
    assert us.slash_24s == 1
    assert us.slash_48s == 1 << 16


def test_info_prefix_length_histogram_sorted() -> None:
    """Prefix length histograms come back sorted ascending by prefix length."""
    info = GeoFeed(FIXTURE).info()
    assert isinstance(info, GeoFeedInfo)
    assert info.prefix_length_v4 == ((24, 1), (25, 1))
    assert info.prefix_length_v6 == ((32, 1),)


def test_info_top_regions_and_cities_sorted_by_count() -> None:
    """Top regions/cities come back ordered by descending count."""
    info = GeoFeed(FIXTURE).info()
    assert isinstance(info, GeoFeedInfo)
    assert info.top_regions[0] == ("US-CA", 2)
    assert info.top_cities[0] == ("San Francisco", 2)


def test_info_top_n_caps_breakdowns() -> None:
    """`top_n` bounds the size of the top region/city lists."""
    info = GeoFeed(FIXTURE).info(top_n=1)
    assert isinstance(info, GeoFeedInfo)
    assert len(info.top_regions) <= 1
    assert len(info.top_cities) <= 1


def test_info_normalize_preview_clean_feed() -> None:
    """A clean feed should normalize to fewer or equal prefixes with zero invalid."""
    info = GeoFeed(FIXTURE).info()
    assert isinstance(info, GeoFeedInfo)
    assert info.normalized is not None
    assert isinstance(info.normalized, NormalizationPreview)
    assert info.normalized.invalid_removed == 0
    # 192.0.2.0/24 + 192.0.2.128/25 collapse into 192.0.2.0/24 → -1
    assert info.normalized.aggregated >= 1
    assert info.normalized.prefixes_total <= info.prefixes_total


def test_info_normalize_preview_invalid_feed() -> None:
    """The invalid fixture should surface non-zero invalid_removed in the preview."""
    info = GeoFeed(INVALID_FIXTURE).info()
    assert isinstance(info, GeoFeedInfo)
    assert info.normalized is not None
    # All three rows in this fixture are invalid in one way or another
    assert info.normalized.invalid_removed >= 1


def test_info_json_output_matches_dataclass() -> None:
    """output='json' serialises the same data as the dataclass holds."""
    info = GeoFeed(FIXTURE).info()
    assert isinstance(info, GeoFeedInfo)
    payload = GeoFeed(FIXTURE).info(output="json")
    assert isinstance(payload, str)
    parsed = json.loads(payload)
    assert parsed["prefixes_v4"] == info.prefixes_v4
    assert parsed["slash_24s"] == info.slash_24s
    assert parsed["slash_48s"] == info.slash_48s
    assert parsed["unique_prefixes"] == info.unique_prefixes
    assert parsed["unique_countries"] == info.unique_countries
    assert parsed["by_country"][0]["country"] == "US"
    assert parsed["normalized"] is not None
    assert "invalid_removed" in parsed["normalized"]


def test_cli_info_default_rich() -> None:
    """CLI info defaults to rich output and includes the new sections."""
    result = runner.invoke(build_app(), ["info", FIXTURE], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    assert "Geofeed info" in result.stdout
    assert "/24-equivalents" in result.stdout
    assert "/48-equivalents" in result.stdout
    assert "Geography" in result.stdout
    assert "If normalized" in result.stdout


def test_cli_info_grep_format_is_keyvalue() -> None:
    """--format grep emits parseable key=value lines including normalize preview."""
    result = runner.invoke(build_app(), ["info", FIXTURE, "--format", "grep"])
    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    assert "prefixes_v4=2" in lines
    assert "prefixes_v6=1" in lines
    assert "unique_prefixes=3" in lines
    assert "duplicates=0" in lines
    assert "slash_24s=1" in lines
    assert "slash_48s=65536" in lines
    assert "unique_countries=1" in lines
    assert "unique_regions=2" in lines
    assert "country.US.prefixes_v4=2" in lines
    assert any(line.startswith("normalized.prefixes_total=") for line in lines)
    assert any(line.startswith("normalized.invalid_removed=") for line in lines)
    assert any(line.startswith("normalized.aggregated=") for line in lines)
    assert any(line.startswith("top_city.1.name=") for line in lines)


def test_cli_info_json_format() -> None:
    """--format json emits a structured JSON document including normalize preview."""
    result = runner.invoke(build_app(), ["info", FIXTURE, "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["prefixes_total"] == 3
    assert payload["slash_24s"] == 1
    assert payload["slash_48s"] == 1 << 16
    assert payload["unique_countries"] == 1
    assert payload["normalized"]["invalid_removed"] == 0


def test_cli_info_plain_format_has_thousand_separators() -> None:
    """Plain format formats large counts with thousand separators."""
    result = runner.invoke(
        build_app(),
        ["info", FIXTURE, "--format", "plain"],
        env={"COLUMNS": "200"},
    )
    assert result.exit_code == 0
    assert "65,536" in result.stdout
    # Plain mode must not draw rich box characters.
    assert "╭" not in result.stdout


def test_cli_statistics_command_removed() -> None:
    """The `statistics` CLI command no longer exists — it was merged into info."""
    result = runner.invoke(build_app(), ["statistics", FIXTURE])
    assert result.exit_code != 0


def test_cli_info_accepts_ip_source_and_resolves_via_rdap(monkeypatch) -> None:
    """`info <ip>` should run RDAP discovery and report on the resolved geofeed."""
    from geofeed_tools.models import DoctorLookup
    from geofeed_tools.rdap import ResolvedRdapLookup

    geofeed_bytes = Path(FIXTURE).read_bytes()
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

    monkeypatch.setattr(
        "geofeed_tools.core.resolve_geofeed_lookup",
        lambda query, *, rdap_method="rdap.org": resolved,
    )
    monkeypatch.setattr(
        "geofeed_tools.core.load_input",
        lambda source: (geofeed_bytes, "text/csv"),
    )

    result = runner.invoke(build_app(), ["info", "192.0.2.200", "--format", "json"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["prefixes_total"] == 3
    assert payload["source"] == "https://example.com/geofeed.csv"


def test_cli_info_ip_source_no_geofeed_exits_nonzero(monkeypatch) -> None:
    """When RDAP discovery fails the CLI should exit non-zero with a friendly message."""
    from geofeed_tools.models import DoctorLookup
    from geofeed_tools.rdap import ResolvedRdapLookup

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

    result = runner.invoke(build_app(), ["info", "198.51.100.1", "--format", "json"])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["query"] == "198.51.100.1"
    assert "no geofeed" in payload["error"]
