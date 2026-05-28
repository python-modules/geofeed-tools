"""Tests for the geofeed filter Python API and CLI command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from geofeed_tools import GeoFeed
from geofeed_tools.cli.app import build_app
from geofeed_tools.filtering import parse_family

runner = CliRunner()
FIXTURE = str(Path(__file__).parent / "fixtures" / "valid_geofeed.csv")


def _prefixes(records) -> list[str]:
    return [r.prefix for r in records]


def test_filter_with_no_args_returns_every_record() -> None:
    """Calling filter() without any predicate returns every parsed record."""
    geofeed = GeoFeed(FIXTURE)
    records = geofeed.filter()
    assert _prefixes(records) == ["192.0.2.0/24", "192.0.2.128/25", "2001:db8::/32"]


def test_filter_by_country_is_case_insensitive() -> None:
    """Country comparison normalises to uppercase before matching."""
    assert _prefixes(GeoFeed(FIXTURE).filter(country="us")) == [
        "192.0.2.0/24",
        "192.0.2.128/25",
        "2001:db8::/32",
    ]
    assert GeoFeed(FIXTURE).filter(country="ca") == []


def test_filter_by_region_is_case_insensitive() -> None:
    """Region comparison normalises to uppercase before matching."""
    assert _prefixes(GeoFeed(FIXTURE).filter(region="us-ca")) == [
        "192.0.2.0/24",
        "192.0.2.128/25",
    ]


def test_filter_by_city_is_case_insensitive() -> None:
    """City comparison is case-insensitive."""
    assert _prefixes(GeoFeed(FIXTURE).filter(city="san francisco")) == [
        "192.0.2.0/24",
        "192.0.2.128/25",
    ]


def test_filter_by_postal_code() -> None:
    """Postal-code comparison is case-insensitive."""
    assert _prefixes(GeoFeed(FIXTURE).filter(postal_code="10001")) == ["2001:db8::/32"]


def test_filter_by_family_accepts_string_and_int() -> None:
    """Family accepts 4/6, 'v4'/'v6', and 'ipv4'/'ipv6'."""
    geofeed = GeoFeed(FIXTURE)
    assert _prefixes(geofeed.filter(family=4)) == ["192.0.2.0/24", "192.0.2.128/25"]
    assert _prefixes(geofeed.filter(family="v6")) == ["2001:db8::/32"]
    assert _prefixes(geofeed.filter(family="ipv4")) == ["192.0.2.0/24", "192.0.2.128/25"]


def test_filter_by_family_rejects_garbage() -> None:
    """Garbage family values raise a clear ValueError."""
    with pytest.raises(ValueError, match="family"):
        parse_family("nope")
    with pytest.raises(ValueError, match="family"):
        parse_family(7)


def test_filter_by_prefix_length_exact() -> None:
    """Without --longer, prefix_length matches exactly."""
    assert _prefixes(GeoFeed(FIXTURE).filter(prefix_length=24)) == ["192.0.2.0/24"]


def test_filter_by_prefix_length_include_longer() -> None:
    """With include_longer, prefix_length matches length >= the supplied value."""
    assert _prefixes(GeoFeed(FIXTURE).filter(prefix_length=24, include_longer=True)) == [
        "192.0.2.0/24",
        "192.0.2.128/25",
        "2001:db8::/32",
    ]


def test_filter_by_prefix_exact() -> None:
    """Without --longer, prefix matches the exact CIDR."""
    assert _prefixes(GeoFeed(FIXTURE).filter(prefix="192.0.2.0/24")) == ["192.0.2.0/24"]


def test_filter_by_prefix_include_longer() -> None:
    """With include_longer, prefix matches the CIDR and any contained subnets."""
    assert _prefixes(GeoFeed(FIXTURE).filter(prefix="192.0.2.0/24", include_longer=True)) == [
        "192.0.2.0/24",
        "192.0.2.128/25",
    ]


def test_filter_combines_predicates_with_and() -> None:
    """Filters AND together: country + region + prefix narrows the result."""
    assert _prefixes(
        GeoFeed(FIXTURE).filter(country="CA", region="CA-ON", prefix="192.0.2.0/24")
    ) == []
    assert _prefixes(
        GeoFeed(FIXTURE).filter(country="US", region="US-CA", prefix="192.0.2.0/24")
    ) == ["192.0.2.0/24"]


def test_filter_family_plus_prefix_length() -> None:
    """Combining family + prefix_length narrows by both."""
    assert _prefixes(GeoFeed(FIXTURE).filter(family="ipv4", prefix_length=25)) == [
        "192.0.2.128/25",
    ]


def test_filter_output_json_serialises_records() -> None:
    """output='json' returns a JSON array of the matching records."""
    payload = GeoFeed(FIXTURE).filter(country="US", output="json")
    assert isinstance(payload, str)
    rows = json.loads(payload)
    assert len(rows) == 3
    assert rows[0]["prefix"] == "192.0.2.0/24"


def test_cli_filter_country_grep() -> None:
    """CLI --format grep emits CSV rows matching --country."""
    result = runner.invoke(
        build_app(),
        ["filter", FIXTURE, "--country", "US", "--family", "ipv4", "--format", "grep"],
    )
    assert result.exit_code == 0
    assert result.stdout.splitlines() == [
        "192.0.2.0/24,US,US-CA,San Francisco,94104",
        "192.0.2.128/25,US,US-CA,San Francisco,94104",
    ]


def test_cli_filter_prefix_length_with_longer() -> None:
    """CLI --prefix-length 24 --longer keeps /24 and longer prefixes."""
    result = runner.invoke(
        build_app(),
        ["filter", FIXTURE, "--prefix-length", "24", "--longer", "--format", "grep"],
    )
    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    assert "192.0.2.0/24,US,US-CA,San Francisco,94104" in lines
    assert "192.0.2.128/25,US,US-CA,San Francisco,94104" in lines


def test_cli_filter_prefix_exact_vs_longer() -> None:
    """CLI --prefix without --longer is exact-match."""
    exact = runner.invoke(
        build_app(),
        ["filter", FIXTURE, "--prefix", "192.0.2.0/24", "--format", "grep"],
    )
    assert exact.exit_code == 0
    assert exact.stdout.strip() == "192.0.2.0/24,US,US-CA,San Francisco,94104"

    longer = runner.invoke(
        build_app(),
        ["filter", FIXTURE, "--prefix", "192.0.2.0/24", "--longer", "--format", "grep"],
    )
    assert longer.exit_code == 0
    assert longer.stdout.splitlines() == [
        "192.0.2.0/24,US,US-CA,San Francisco,94104",
        "192.0.2.128/25,US,US-CA,San Francisco,94104",
    ]


def test_cli_filter_json_format() -> None:
    """CLI --format json emits a JSON array of records."""
    result = runner.invoke(
        build_app(),
        ["filter", FIXTURE, "--country", "US", "--family", "ipv6", "--format", "json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload) == 1
    assert payload[0]["prefix"] == "2001:db8::/32"


def test_cli_no_args_shows_help() -> None:
    """Running the CLI entrypoint with no command shows help and exits 0."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "geofeed_tools.cli"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"stderr was: {result.stderr}"
    assert "Usage" in result.stdout
    assert "filter" in result.stdout
