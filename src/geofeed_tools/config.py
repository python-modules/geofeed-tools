"""Central configuration constants for geofeed_tools.

All tuneable defaults, limits, and external service endpoints live here so
they are easy to find and adjust without digging through implementation files.
"""

from __future__ import annotations

from importlib.metadata import version

# ── HTTP / network ────────────────────────────────────────────────────────────

USER_AGENT: str = f"Python geofeed-tools/{version('geofeed-tools')}"
"""User-Agent header sent with all outgoing HTTP requests."""

FETCH_TIMEOUT: int = 30
"""Seconds to wait for a remote HTTP response before giving up."""

URL_SCHEMES: tuple[str, ...] = ("http://", "https://")
"""Accepted URL schemes for remote geofeed sources."""

# ── Logging ───────────────────────────────────────────────────────────────────

LOGGER_NAME: str = "geofeed_tools"
"""Root logger name used throughout the package."""

TRACE_LEVEL: int = 5
"""Numeric log level below DEBUG used for verbose HTTP tracing."""

# ── LRU cache sizes ───────────────────────────────────────────────────────────

LRU_COUNTRY_CACHE_SIZE: int = 512
"""Maximum entries in the ISO 3166-1 country code lookup cache."""

LRU_SUBDIVISION_CACHE_SIZE: int = 4096
"""Maximum entries in the ISO 3166-2 subdivision code lookup cache."""

# ── RDAP lookup methods ───────────────────────────────────────────────────────

RDAP_ORG_METHOD: str = "rdap.org"
"""RDAP lookup method that routes all queries through rdap.org."""

IANA_BOOTSTRAP_METHOD: str = "iana-bootstrap"
"""RDAP lookup method that resolves the registry directly via IANA bootstrap."""

RDAP_LOOKUP_METHODS: tuple[str, ...] = (RDAP_ORG_METHOD, IANA_BOOTSTRAP_METHOD)
"""All supported RDAP lookup method identifiers."""

DEFAULT_RDAP_METHOD: str = RDAP_ORG_METHOD
"""Default RDAP lookup method used when no explicit method is specified."""

# ── RDAP service endpoints ────────────────────────────────────────────────────

RDAP_ORG_ROOT_URL: str = "https://rdap.org/"
"""Base URL for the rdap.org proxy service."""

RDAP_ORG_QUERY_TEMPLATE: str = "https://rdap.org/ip/{}"
"""URL template for rdap.org IP queries; {} is replaced with the address."""

IANA_BOOTSTRAP_URLS: dict[int, str] = {
    4: "https://data.iana.org/rdap/ipv4.json",
    6: "https://data.iana.org/rdap/ipv6.json",
}
"""IANA RDAP bootstrap index URLs keyed by IP version."""

MAX_RDAP_DEPTH: int = 8
"""Maximum number of RDAP redirect hops before aborting a lookup."""

# ── HTTP Accept headers ───────────────────────────────────────────────────────

RDAP_ACCEPT: str = "application/rdap+json, application/json, */*"
"""Accept header sent with RDAP queries."""

JSON_ACCEPT: str = "application/json, */*"
"""Accept header sent with plain JSON requests (e.g., IANA bootstrap)."""
