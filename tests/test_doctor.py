"""Tests for RDAP-based geofeed discovery and doctor lookups."""

from __future__ import annotations

import asyncio

import geofeed_tools.doctor as doctor_module
import geofeed_tools.rdap as rdap_module
from geofeed_tools import AsyncGeoFeed, DoctorResult, GeoFeed


def test_doctor_discovers_geofeed_link_and_returns_matches(
    monkeypatch,
) -> None:
    """Doctor should use a direct RDAP geofeed link."""
    geofeed_text = (
        "192.0.2.0/24,US,US-CA,Los Angeles,\n"
        "192.0.2.128/25,US,US-CA,Pasadena,\n"
    )
    rdap_response: dict[str, object] = {
        "handle": "NET-192-0-2-0-1",
        "startAddress": "192.0.2.0",
        "endAddress": "192.0.2.255",
        "links": [
            {
                "rel": "geofeed",
                "href": "https://example.com/geofeed.csv",
                "type": "application/geofeed+csv",
            }
        ],
    }

    def fake_fetch(
        url: str,
        *,
        accept: str = rdap_module.JSON_ACCEPT,
    ) -> tuple[dict[str, object], str]:
        """Return a direct RDAP geofeed link response."""
        del accept
        assert url == "https://rdap.org/ip/192.0.2.200"
        return rdap_response, "https://rdap.example.test/ip/192.0.2.200"

    monkeypatch.setattr(rdap_module, "_fetch_json_urllib", fake_fetch)
    monkeypatch.setattr(
        doctor_module,
        "load_input",
        lambda source: (geofeed_text.encode("utf-8"), "text/csv"),
    )

    result = GeoFeed.doctor("192.0.2.200", output="objects")

    assert isinstance(result, DoctorResult)
    assert result.lookup.lookup_strategy == "ip-address"
    assert result.lookup.rdap_method == "rdap.org"
    assert result.lookup.rdap_query == "192.0.2.200"
    assert result.lookup.resolved_urls == (
        "https://rdap.example.test/ip/192.0.2.200",
    )
    assert result.lookup.referring_handle == "NET-192-0-2-0-1"
    assert result.lookup.referring_range == "192.0.2.0 - 192.0.2.255"
    assert result.lookup.geofeed_url == "https://example.com/geofeed.csv"
    assert result.lookup.geofeed_discovered_via == "rdap link rel=geofeed"
    assert result.matches[0].prefix == "192.0.2.128/25"


def test_doctor_follows_parent_and_filters_records(monkeypatch) -> None:
    """Doctor should follow parent RDAP links."""
    child_response: dict[str, object] = {
        "handle": "NET-192-0-2-0-1-CHILD",
        "startAddress": "192.0.2.0",
        "endAddress": "192.0.2.127",
        "links": [{"rel": "rdap-up", "href": "/ip/parent"}],
    }
    parent_response: dict[str, object] = {
        "handle": "NET-192-0-2-0-1",
        "startAddress": "192.0.2.0",
        "endAddress": "192.0.2.255",
        "remarks": [
            {
                "description": [
                    "Registration Comments",
                    "Geofeed: https://example.com/shared-geofeed.csv",
                ]
            }
        ],
    }
    geofeed_text = (
        "192.0.2.0/24,US,US-CA,Los Angeles,\n"
        "192.0.3.0/24,CA,CA-ON,Toronto,\n"
    )

    def fake_fetch(
        url: str,
        *,
        accept: str = rdap_module.JSON_ACCEPT,
    ) -> tuple[dict[str, object], str]:
        """Return child and parent RDAP objects for traversal tests."""
        del accept
        if url == "https://rdap.org/ip/192.0.2.0":
            return child_response, "https://rdap.example.test/ip/child"
        if url == "https://rdap.example.test/ip/parent":
            return parent_response, url
        raise AssertionError(url)

    monkeypatch.setattr(rdap_module, "_fetch_json_urllib", fake_fetch)
    monkeypatch.setattr(
        doctor_module,
        "load_input",
        lambda source: (geofeed_text.encode("utf-8"), "text/csv"),
    )

    result = GeoFeed.doctor(
        "192.0.2.0/23",
        return_all=True,
        include_longer=True,
        output="objects",
    )

    assert isinstance(result, DoctorResult)
    assert result.lookup.lookup_strategy == "prefix-network-address"
    assert result.lookup.rdap_query == "192.0.2.0"
    assert result.lookup.resolved_urls == (
        "https://rdap.example.test/ip/child",
        "https://rdap.example.test/ip/parent",
    )
    assert (
        result.lookup.geofeed_url
        == "https://example.com/shared-geofeed.csv"
    )
    assert result.lookup.geofeed_discovered_via == "rdap remarks geofeed url"
    assert [record.prefix for record in result.matches] == ["192.0.2.0/24"]


def test_doctor_returns_empty_result_when_no_geofeed_is_published(
    monkeypatch,
) -> None:
    """Doctor should return structured metadata even when no geofeed exists."""
    rdap_response: dict[str, object] = {
        "handle": "NET-198-51-100-0-1",
        "startAddress": "198.51.100.0",
        "endAddress": "198.51.100.255",
        "links": [],
    }

    monkeypatch.setattr(
        rdap_module,
        "_fetch_json_urllib",
        lambda url, accept=rdap_module.JSON_ACCEPT: (
            rdap_response,
            "https://rdap.example.test/ip/198.51.100.1",
        ),
    )

    result = GeoFeed.doctor("198.51.100.1", output="objects")

    assert isinstance(result, DoctorResult)
    assert result.lookup.geofeed_url is None
    assert result.matches == ()


def test_async_doctor_returns_lookup_metadata(monkeypatch) -> None:
    """Async doctor should mirror the sync doctor metadata."""
    geofeed_text = (
        "2001:db8::/32,US,US-NY,New York,\n"
        "2001:db8:abcd::/48,US,US-NY,Brooklyn,\n"
    )
    rdap_response: dict[str, object] = {
        "handle": "NET6-2001-DB8-1",
        "startAddress": "2001:db8::",
        "endAddress": "2001:db8:ffff:ffff:ffff:ffff:ffff:ffff",
        "links": [
            {
                "rel": "geofeed",
                "href": "https://example.com/ipv6-geofeed.csv",
                "type": "application/geofeed+csv",
            }
        ],
    }

    async def fake_fetch(
        url: str,
        *,
        accept: str = rdap_module.JSON_ACCEPT,
    ) -> tuple[dict[str, object], str]:
        """Return an async RDAP response for doctor tests."""
        await asyncio.sleep(0)
        del accept
        assert url == "https://rdap.org/ip/2001:db8:abcd::1"
        return rdap_response, "https://rdap.example.test/ip/2001:db8:abcd::1"

    async def fake_load_input(source: str) -> tuple[bytes, str | None]:
        """Return async geofeed bytes for doctor tests."""
        del source
        await asyncio.sleep(0)
        return geofeed_text.encode("utf-8"), "text/csv"

    monkeypatch.setattr(rdap_module, "_fetch_json_httpx", fake_fetch)
    monkeypatch.setattr(doctor_module, "load_input_async", fake_load_input)

    async def scenario() -> DoctorResult:
        """Execute the async doctor code path."""
        result = await AsyncGeoFeed.doctor(
            "2001:db8:abcd::1",
            output="objects",
        )
        assert isinstance(result, DoctorResult)
        return result

    result = asyncio.run(scenario())

    assert result.lookup.lookup_strategy == "ip-address"
    assert result.lookup.rdap_method == "rdap.org"
    assert result.lookup.geofeed_url == "https://example.com/ipv6-geofeed.csv"
    assert result.matches[0].prefix == "2001:db8:abcd::/48"


def test_doctor_supports_iana_bootstrap_lookup(monkeypatch) -> None:
    """Doctor should optionally resolve the registry URL via IANA bootstrap."""
    geofeed_text = "31.133.128.0/17,SE,SE-AB,Stockholm,\n"
    bootstrap_payload: dict[str, object] = {
        "services": [
            [
                ["31.133.128.0/17"],
                ["https://rdap.db.ripe.net/"],
            ]
        ]
    }
    rdap_response: dict[str, object] = {
        "handle": "IETF-NET",
        "startAddress": "31.133.128.0",
        "endAddress": "31.133.255.255",
        "links": [
            {
                "rel": "geofeed",
                "href": "https://noc.ietf.org/geo/google.csv",
                "type": "application/geofeed+csv",
            }
        ],
    }

    def fake_fetch(
        url: str,
        *,
        accept: str = rdap_module.JSON_ACCEPT,
    ) -> tuple[dict[str, object], str]:
        """Return IANA bootstrap data and a registry RDAP object."""
        del accept
        if url == rdap_module.IANA_BOOTSTRAP_URLS[4]:
            return bootstrap_payload, url
        if url == "https://rdap.db.ripe.net/ip/31.133.128.1":
            return rdap_response, "https://rdap.db.ripe.net/ip/31.133.128.1"
        raise AssertionError(url)

    rdap_module.clear_bootstrap_cache()
    monkeypatch.setattr(rdap_module, "_fetch_json_urllib", fake_fetch)
    monkeypatch.setattr(
        doctor_module,
        "load_input",
        lambda source: (geofeed_text.encode("utf-8"), "text/csv"),
    )

    result = GeoFeed.doctor(
        "31.133.128.1",
        rdap_method="iana-bootstrap",
        output="objects",
    )

    assert isinstance(result, DoctorResult)
    assert result.lookup.rdap_method == "iana-bootstrap"
    assert (
        result.lookup.bootstrap_source_url
        == rdap_module.IANA_BOOTSTRAP_URLS[4]
    )
    assert (
        result.lookup.bootstrap_url
        == "https://rdap.db.ripe.net/ip/31.133.128.1"
    )
    assert result.lookup.geofeed_url == "https://noc.ietf.org/geo/google.csv"
    assert result.matches[0].prefix == "31.133.128.0/17"
