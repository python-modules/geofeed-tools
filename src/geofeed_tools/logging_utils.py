"""Logging helpers for core module and optional CLI."""

from __future__ import annotations

import logging
import sys

LOGGER_NAME = "geofeed_tools"
logger = logging.getLogger(LOGGER_NAME)


def configure_logging(verbosity: int = 0) -> None:
    """Configure standard-library logging for core operations."""

    if verbosity <= 0:
        level = logging.WARNING
    elif verbosity == 1:
        level = logging.INFO
    else:
        level = logging.DEBUG

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.WARNING)

    logger.setLevel(level)
