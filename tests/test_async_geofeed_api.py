"""Async API tests for the geofeed_tools package."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import geofeed_tools.async_core as async_core_module
from geofeed_tools import AsyncGeoFeed


def fixture_path(name: str) -> str:
    """Return absolute path to a fixture file by name."""
    return str(Path(__file__).parent / "fixtures" / name)


@contextmanager
def serve_fixture(name: str) -> Iterator[str]:
    """Serve a fixture file over local HTTP for async URL-loading tests."""
    body = Path(fixture_path(name)).read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/csv")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        yield f"http://127.0.0.1:{server.server_port}/{name}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_async_parse_and_info() -> None:
    """AsyncGeoFeed should parse valid data and compute basic metrics."""

    async def scenario() -> tuple[int, int, int]:
        geofeed = AsyncGeoFeed(fixture_path("valid_geofeed.csv"))
        records = await geofeed.parse(output="objects")
        info = await geofeed.info(output="objects")
        assert isinstance(records, list)
        assert not isinstance(info, str)
        return len(records), info.ipv4_records, info.ipv6_records

    record_count, ipv4_count, ipv6_count = asyncio.run(scenario())
    assert record_count == 3
    assert ipv4_count == 2
    assert ipv6_count == 1


def test_async_validate_invalid_file() -> None:
    """AsyncGeoFeed should return validation errors for invalid fixtures."""

    async def scenario() -> int:
        geofeed = AsyncGeoFeed(fixture_path("invalid_geofeed.csv"))
        report = await geofeed.validate(output="objects")
        assert not isinstance(report, str)
        return report.errors

    assert asyncio.run(scenario()) >= 2


def test_async_normalize_and_query_outputs() -> None:
    """AsyncGeoFeed should support normalized CSV and query JSON output."""

    async def scenario() -> tuple[str, str]:
        geofeed = AsyncGeoFeed(fixture_path("valid_geofeed.csv"))
        normalized_csv = await geofeed.normalize(output="csv")
        query = await geofeed.query("192.0.2.200", output="json")
        assert isinstance(normalized_csv, str)
        assert isinstance(query, str)
        return normalized_csv, query

    normalized_csv, query = asyncio.run(scenario())
    assert "192.0.2.0/24" in normalized_csv
    assert '"query": "192.0.2.200"' in query


def test_async_factory_eager_loads_source() -> None:
    """Async factory helper should return a loaded instance."""

    async def scenario() -> tuple[bool, bool]:
        geofeed = await AsyncGeoFeed.from_source(fixture_path("valid_geofeed.csv"))
        return geofeed.raw is not None, geofeed.text is not None

    has_raw, has_text = asyncio.run(scenario())
    assert has_raw is True
    assert has_text is True


def test_async_http_parse_returns_records() -> None:
    """AsyncGeoFeed should support URL loading over async HTTP."""

    async def scenario(url: str) -> tuple[int, int, str | None]:
        geofeed = await AsyncGeoFeed.from_source(url)
        records = await geofeed.parse(output="objects")
        report = await geofeed.validate(output="objects")
        assert isinstance(records, list)
        assert not isinstance(report, str)
        return len(records), report.records, geofeed.content_type

    with serve_fixture("valid_geofeed.csv") as url:
        record_count, validated_records, content_type = asyncio.run(scenario(url))

    assert record_count == 3
    assert validated_records == 3
    assert content_type == "text/csv"


def test_async_query_reuses_index_until_reload(monkeypatch) -> None:
    """AsyncGeoFeed query should reuse indexed records until source reload."""
    call_count = 0

    real_loader = async_core_module.load_query_records

    def counting_loader(text: str):
        nonlocal call_count
        call_count += 1
        return real_loader(text)

    monkeypatch.setattr("geofeed_tools.async_core.load_query_records", counting_loader)

    async def scenario() -> int:
        geofeed = AsyncGeoFeed(fixture_path("valid_geofeed.csv"))
        first = await geofeed.query("192.0.2.200", output="objects")
        second = await geofeed.query("2001:db8::1", output="objects")
        assert not isinstance(first, str)
        assert not isinstance(second, str)
        assert call_count == 1

        await geofeed.reload()
        third = await geofeed.query("192.0.2.1", output="objects")
        assert not isinstance(third, str)
        return call_count

    assert asyncio.run(scenario()) == 2


def test_async_query_cache_can_be_disabled(monkeypatch) -> None:
    """AsyncGeoFeed should skip caching when cache_query_index=False."""
    call_count = 0

    real_loader = async_core_module.load_query_records

    def counting_loader(text: str):
        nonlocal call_count
        call_count += 1
        return real_loader(text)

    monkeypatch.setattr("geofeed_tools.async_core.load_query_records", counting_loader)

    async def scenario() -> int:
        geofeed = AsyncGeoFeed(fixture_path("valid_geofeed.csv"), cache_query_index=False)
        first = await geofeed.query("192.0.2.200", output="objects")
        second = await geofeed.query("2001:db8::1", output="objects")
        assert not isinstance(first, str)
        assert not isinstance(second, str)
        return call_count

    assert asyncio.run(scenario()) == 0
