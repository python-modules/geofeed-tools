"""CLI tests for the doctor command behavior."""

from __future__ import annotations

from typer.testing import CliRunner

from geofeed_tools import DoctorLookup, DoctorResult, GeofeedRecord
from geofeed_tools.cli.app import build_app

runner = CliRunner()


def test_cli_doctor_emits_json(monkeypatch) -> None:
    """CLI doctor should serialize structured output when JSON is requested."""

    class FakeGeoFeed:
        """Capture doctor arguments for JSON-mode CLI assertions."""

        last_rdap_method: str | None = None

        @staticmethod
        def doctor(
            query: str,
            *,
            return_all: bool = False,
            include_longer: bool = False,
            rdap_method: str = "rdap.org",
            output: str = "objects",
        ) -> DoctorResult:
            del return_all, include_longer
            FakeGeoFeed.last_rdap_method = rdap_method
            assert output == "objects"
            return DoctorResult(
                query=query,
                lookup=DoctorLookup(
                    lookup_strategy="ip-address",
                    rdap_method=rdap_method,
                    rdap_query=query,
                    bootstrap_url=f"https://rdap.org/ip/{query}",
                    bootstrap_source_url="https://rdap.org/",
                    resolved_urls=(f"https://rdap.example.test/ip/{query}",),
                    referring_handle="NET-203-0-113-0-1",
                    referring_range="203.0.113.0 - 203.0.113.255",
                    geofeed_url="https://example.com/geofeed.csv",
                    geofeed_discovered_via="rdap link rel=geofeed",
                    geofeed_reference_url=(f"https://rdap.example.test/ip/{query}"),
                ),
                matches=(
                    GeofeedRecord(
                        prefix="203.0.113.0/24",
                        country="US",
                        region="US-CA",
                        city="Los Angeles",
                    ),
                ),
            )

    monkeypatch.setattr("geofeed_tools.cli.app.GeoFeed", FakeGeoFeed)

    result = runner.invoke(build_app(), ["doctor", "203.0.113.1", "--json"])

    assert result.exit_code == 0
    assert FakeGeoFeed.last_rdap_method == "rdap.org"
    assert '"query": "203.0.113.1"' in result.stdout
    assert '"geofeed_url": "https://example.com/geofeed.csv"' in result.stdout


def test_cli_doctor_returns_nonzero_when_not_found(monkeypatch) -> None:
    """CLI doctor should fail when discovery finds no published geofeed."""

    class FakeGeoFeed:
        """Return an empty doctor result for CLI failure assertions."""

        @staticmethod
        def doctor(
            query: str,
            *,
            return_all: bool = False,
            include_longer: bool = False,
            rdap_method: str = "rdap.org",
            output: str = "objects",
        ) -> DoctorResult:
            del return_all, include_longer
            assert output == "objects"
            return DoctorResult(
                query=query,
                lookup=DoctorLookup(
                    lookup_strategy="ip-address",
                    rdap_method=rdap_method,
                    rdap_query=query,
                    bootstrap_url=f"https://rdap.org/ip/{query}",
                    bootstrap_source_url="https://rdap.org/",
                    resolved_urls=(f"https://rdap.example.test/ip/{query}",),
                ),
                matches=(),
            )

    monkeypatch.setattr("geofeed_tools.cli.app.GeoFeed", FakeGeoFeed)

    result = runner.invoke(build_app(), ["doctor", "203.0.113.1"])

    assert result.exit_code == 1
    assert "Geofeed URL: not found" in result.stdout


def test_cli_doctor_accepts_iana_bootstrap_override(monkeypatch) -> None:
    """CLI doctor should pass through an explicit RDAP method override."""

    class FakeGeoFeed:
        """Capture the explicit RDAP method passed from the CLI."""

        last_rdap_method: str | None = None

        @staticmethod
        def doctor(
            query: str,
            *,
            return_all: bool = False,
            include_longer: bool = False,
            rdap_method: str = "rdap.org",
            output: str = "objects",
        ) -> DoctorResult:
            del query, return_all, include_longer
            FakeGeoFeed.last_rdap_method = rdap_method
            assert output == "objects"
            return DoctorResult(
                query="31.133.128.1",
                lookup=DoctorLookup(
                    lookup_strategy="ip-address",
                    rdap_method=rdap_method,
                    rdap_query="31.133.128.1",
                    bootstrap_url="https://rdap.db.ripe.net/ip/31.133.128.1",
                    bootstrap_source_url=("https://data.iana.org/rdap/ipv4.json"),
                    resolved_urls=("https://rdap.db.ripe.net/ip/31.133.128.1",),
                    geofeed_url="https://noc.ietf.org/geo/google.csv",
                ),
                matches=(GeofeedRecord(prefix="31.133.128.0/17"),),
            )

    monkeypatch.setattr("geofeed_tools.cli.app.GeoFeed", FakeGeoFeed)

    result = runner.invoke(
        build_app(),
        ["doctor", "31.133.128.1", "--rdap-method", "iana-bootstrap"],
    )

    assert result.exit_code == 0
    assert FakeGeoFeed.last_rdap_method == "iana-bootstrap"
    assert "RDAP method: iana-bootstrap" in result.stdout
