"""Format dispatchers for CLI output.

Every renderer accepts a ``format`` string (one of ``rich``, ``plain``, ``grep``,
``json``) and routes to a per-format implementation. Rich primitives are
imported lazily so the CLI can still emit a friendly "missing extras" message
when rich is not installed.
"""

from __future__ import annotations

from ._doctor import render_doctor
from ._helpers import (
    ALL_FORMATS,
    FORMAT_GREP,
    FORMAT_JSON,
    FORMAT_PLAIN,
    FORMAT_RICH,
)
from ._info import render_info
from ._records import render_query, render_records
from ._validation import render_hook, render_validation

__all__ = [
    "ALL_FORMATS",
    "FORMAT_GREP",
    "FORMAT_JSON",
    "FORMAT_PLAIN",
    "FORMAT_RICH",
    "render_doctor",
    "render_hook",
    "render_info",
    "render_query",
    "render_records",
    "render_validation",
]
