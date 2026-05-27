"""Logging helpers for core module and optional CLI."""

from __future__ import annotations

import logging
import sys

LOGGER_NAME = "geofeed_tools"
TRACE_LEVEL = 5
logger = logging.getLogger(LOGGER_NAME)


logging.addLevelName(TRACE_LEVEL, "TRACE")


def _verbosity_to_level(verbosity: int) -> int:
    """Map `-v` counts to stdlib log levels."""
    levels = (logging.WARNING, logging.INFO, logging.DEBUG, TRACE_LEVEL)
    index = min(max(verbosity, 0), 3)
    return levels[index]


def _enable_http_trace_logging() -> None:
    """Enable low-level HTTP diagnostics for trace verbosity."""
    import http.client

    http.client.HTTPConnection.debuglevel = 1
    for name in ("http.client", "urllib3", "requests"):
        logging.getLogger(name).setLevel(logging.DEBUG)


def configure_logging(verbosity: int = 0) -> None:
    """Configure standard-library logging for core operations."""
    level = _verbosity_to_level(verbosity)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.WARNING)

    logger.setLevel(level)


def configure_cli_structlog(verbosity: int = 0) -> None:
    """Configure structlog console logging for the optional CLI."""
    # CLI dependencies are optional; import lazily to keep core module lean.
    import structlog

    level = _verbosity_to_level(verbosity)

    logging.basicConfig(level=level, format="%(message)s", stream=sys.stderr)
    if level <= TRACE_LEVEL:
        _enable_http_trace_logging()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.set_exc_info,
            structlog.dev.ConsoleRenderer(
                colors=True,
                pad_event=30,
                sort_keys=True,
            ),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
