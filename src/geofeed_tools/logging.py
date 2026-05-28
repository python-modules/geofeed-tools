"""Logging helpers for core module and optional CLI."""

from __future__ import annotations

import logging
import sys

from .config import LOGGER_NAME, TRACE_LEVEL

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
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(TRACE_LEVEL if level <= TRACE_LEVEL else logging.WARNING)

    logger.setLevel(level)
    if level <= TRACE_LEVEL:
        _enable_http_trace_logging()


def configure_cli_structlog(verbosity: int = 0) -> None:
    """Configure structlog console logging for the optional CLI."""
    # CLI dependencies are optional; import lazily to keep core module lean.
    from collections.abc import Callable, Mapping, MutableMapping
    from typing import Any, cast

    import structlog

    Processor = Callable[  # noqa: N806 — local type alias keeps PascalCase
        [Any, str, MutableMapping[str, Any]],
        Mapping[str, Any] | str | bytes | bytearray | tuple[Any, ...],
    ]

    level = _verbosity_to_level(verbosity)

    timestamper = structlog.processors.TimeStamper(fmt="%H:%M:%S")
    shared_processors: list[Processor] = [
        cast(Processor, structlog.contextvars.merge_contextvars),
        cast(Processor, structlog.stdlib.add_log_level),
        cast(Processor, timestamper),
    ]
    renderer = structlog.dev.ConsoleRenderer(
        colors=True,
        pad_event_to=32,
        sort_keys=False,
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(TRACE_LEVEL if level <= TRACE_LEVEL else logging.WARNING)

    logger.setLevel(level)
    if level <= TRACE_LEVEL:
        _enable_http_trace_logging()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
