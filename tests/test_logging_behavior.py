"""Tests for geofeed_tools logging behavior."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from geofeed_tools import AsyncGeoFeed, GeoFeed
from geofeed_tools.logging import LOGGER_NAME, TRACE_LEVEL, configure_cli_structlog, logger


def fixture_path(name: str) -> str:
    """Return absolute path to a fixture file by name."""
    return str(Path(__file__).parent / "fixtures" / name)


def test_sync_reload_logs_load_lifecycle(caplog) -> None:
    """Sync loading should log source selection and completion details."""
    geofeed = GeoFeed(fixture_path("valid_geofeed.csv"), auto_load=False)

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        geofeed.reload()

    messages = [record.getMessage() for record in caplog.records]
    assert any("Loading geofeed source from file:" in message for message in messages)
    assert any("Reading geofeed bytes from file:" in message for message in messages)
    assert any("Loaded geofeed source from file:" in message for message in messages)


def test_async_reload_logs_async_load_lifecycle(caplog) -> None:
    """Async loading should log async-specific source lifecycle messages."""

    async def scenario() -> None:
        geofeed = AsyncGeoFeed(fixture_path("valid_geofeed.csv"))
        await geofeed.reload()

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        asyncio.run(scenario())

    messages = [record.getMessage() for record in caplog.records]
    assert any("Loading geofeed source asynchronously from file:" in message for message in messages)
    assert any("Reading geofeed bytes from file asynchronously:" in message for message in messages)
    assert any("Loaded geofeed source asynchronously from file:" in message for message in messages)


def test_validation_trace_logs_issue_details(caplog) -> None:
    """Trace logging should include per-issue validation details."""
    geofeed = GeoFeed(fixture_path("invalid_geofeed.csv"), auto_load=False)

    with caplog.at_level(TRACE_LEVEL, logger=LOGGER_NAME):
        report = geofeed.validate(output="objects")

    assert not isinstance(report, str)
    messages = [record.getMessage() for record in caplog.records]
    assert any("Validation issue detected:" in message and "invalid-prefix" in message for message in messages)
    assert any("Validation issue detected:" in message and "missing-prefix" in message for message in messages)


def test_cli_structlog_uses_colored_human_readable_output(capsys) -> None:
    """CLI structlog setup should render stdlib logs with colors and readable formatting."""
    import structlog

    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_root_level = root.level
    original_logger_level = logger.level

    try:
        configure_cli_structlog(1)
        logger.info("Loading geofeed source from file: %s", fixture_path("valid_geofeed.csv"))
        output = capsys.readouterr().err
        assert "Loading geofeed source from file:" in output
        assert "info" in output.lower()
        assert "\x1b[" in output
    finally:
        root.handlers.clear()
        root.handlers.extend(original_handlers)
        root.setLevel(original_root_level)
        logger.setLevel(original_logger_level)
        structlog.reset_defaults()
