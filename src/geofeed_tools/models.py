"""Dataclasses used by the public geofeed_tools API."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .config import DEFAULT_RDAP_METHOD


@dataclass(frozen=True)
class GeofeedRecord:
    """One parsed geofeed CSV row."""

    prefix: str
    country: str = ""
    region: str = ""
    city: str = ""
    postal_code: str = ""
    line: int = 0
    raw_line: str | None = None
    valid: bool = True
    validation_messages: tuple[str, ...] = ()

    def as_dict(
        self,
        *,
        include_validation: bool = True,
        include_raw_line: bool = False,
    ) -> dict[str, object]:
        """Return a JSON-serializable representation of the record."""
        data: dict[str, object] = {
            "prefix": self.prefix,
            "country": self.country,
            "region": self.region,
            "city": self.city,
            "postal_code": self.postal_code,
        }
        if include_raw_line:
            data["raw_line"] = self.raw_line
        if include_validation:
            data["valid"] = self.valid
            data["validation_messages"] = list(self.validation_messages)
        return data


@dataclass(frozen=True)
class ValidationIssue:
    """Validation issue with severity, location, and machine-readable code."""

    severity: str
    line: int | None
    code: str
    message: str
    raw_line: str | None = None

    def format(self) -> str:
        """Render the issue as a human-readable single-line message."""
        location = f"line {self.line}" if self.line is not None else "file"
        return f"[{self.severity.upper()}] {location}: {self.code}: {self.message}"


@dataclass(frozen=True)
class ValidationReport:
    """Validation summary and issue list for a source geofeed."""

    source: str
    records: int
    errors: int
    warnings: int
    valid: bool
    issues: tuple[ValidationIssue, ...] = ()

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serializable validation report."""
        return {
            "source": self.source,
            "records": self.records,
            "errors": self.errors,
            "warnings": self.warnings,
            "valid": self.valid,
            "issues": [asdict(issue) for issue in self.issues],
        }


@dataclass(frozen=True)
class QueryResult:
    """Query results for an IP or prefix lookup."""

    query: str
    matches: tuple[GeofeedRecord, ...] = ()

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the query result."""
        return {
            "query": self.query,
            "matches": [
                record.as_dict(
                    include_validation=False,
                    include_raw_line=True,
                )
                for record in self.matches
            ],
        }


@dataclass(frozen=True)
class DoctorLookup:
    """Metadata describing how a geofeed was discovered via RDAP."""

    lookup_strategy: str
    rdap_query: str
    bootstrap_url: str
    rdap_method: str = DEFAULT_RDAP_METHOD
    bootstrap_source_url: str | None = None
    resolved_urls: tuple[str, ...] = ()
    referring_handle: str | None = None
    referring_range: str | None = None
    geofeed_url: str | None = None
    geofeed_discovered_via: str | None = None
    geofeed_reference_url: str | None = None

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the lookup metadata."""
        return {
            "lookup_strategy": self.lookup_strategy,
            "rdap_method": self.rdap_method,
            "rdap_query": self.rdap_query,
            "bootstrap_url": self.bootstrap_url,
            "bootstrap_source_url": self.bootstrap_source_url,
            "resolved_urls": list(self.resolved_urls),
            "referring_handle": self.referring_handle,
            "referring_range": self.referring_range,
            "geofeed_url": self.geofeed_url,
            "geofeed_discovered_via": self.geofeed_discovered_via,
            "geofeed_reference_url": self.geofeed_reference_url,
        }


@dataclass(frozen=True)
class DoctorResult:
    """Doctor results for discovering and querying a published geofeed."""

    query: str
    lookup: DoctorLookup
    matches: tuple[GeofeedRecord, ...] = ()

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the doctor result."""
        return {
            "query": self.query,
            "lookup": self.lookup.as_dict(),
            "matches": [
                record.as_dict(
                    include_validation=False,
                    include_raw_line=True,
                )
                for record in self.matches
            ],
        }


@dataclass(frozen=True)
class CountryStatistics:
    """Per-country prefix and /24 / /48 coverage within a GeoFeedInfo breakdown.

    Address coverage is reported in /24-equivalents for IPv4 and /48-equivalents
    for IPv6: a /23 contributes 2 /24s, a /24 contributes 1, two /25s sharing a
    /24 contribute 1 between them, and a /25 by itself contributes 0.
    """

    country: str
    prefixes_v4: int = 0
    prefixes_v6: int = 0
    slash_24s: int = 0
    slash_48s: int = 0

    @property
    def prefixes_total(self) -> int:
        """Sum of IPv4 and IPv6 prefix counts."""
        return self.prefixes_v4 + self.prefixes_v6

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "country": self.country,
            "prefixes_total": self.prefixes_total,
            "prefixes_v4": self.prefixes_v4,
            "prefixes_v6": self.prefixes_v6,
            "slash_24s": self.slash_24s,
            "slash_48s": self.slash_48s,
        }


@dataclass(frozen=True)
class NormalizationPreview:
    """Projected counts after a default ``normalize()`` pass.

    Useful for showing how much a feed could shrink: ``invalid_removed`` covers
    rows that fail strict CIDR parsing (and host-bit fixing), while
    ``aggregated`` covers rows folded into supernets or removed as duplicates.
    """

    prefixes_total: int
    prefixes_v4: int
    prefixes_v6: int
    slash_24s: int
    slash_48s: int
    invalid_removed: int
    aggregated: int

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "prefixes_total": self.prefixes_total,
            "prefixes_v4": self.prefixes_v4,
            "prefixes_v6": self.prefixes_v6,
            "slash_24s": self.slash_24s,
            "slash_48s": self.slash_48s,
            "invalid_removed": self.invalid_removed,
            "aggregated": self.aggregated,
        }


@dataclass(frozen=True)
class GeoFeedInfo:
    """Detailed counts and breakdowns for a geofeed source.

    Address coverage is reported in /24-equivalents (``slash_24s``) and
    /48-equivalents (``slash_48s``) so the numbers stay readable even for
    feeds that cover large swathes of IPv6 space.
    """

    source: str
    prefixes_v4: int
    prefixes_v6: int
    unique_prefixes: int
    duplicates: int
    slash_24s: int
    slash_48s: int
    unique_countries: int = 0
    unique_regions: int = 0
    unique_cities: int = 0
    unique_postal_codes: int = 0
    errors: int = 0
    warnings: int = 0
    by_country: tuple[CountryStatistics, ...] = ()
    prefix_length_v4: tuple[tuple[int, int], ...] = ()
    prefix_length_v6: tuple[tuple[int, int], ...] = ()
    top_regions: tuple[tuple[str, int], ...] = ()
    top_cities: tuple[tuple[str, int], ...] = ()
    normalized: NormalizationPreview | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def prefixes_total(self) -> int:
        """Sum of IPv4 and IPv6 prefix counts."""
        return self.prefixes_v4 + self.prefixes_v6

    @property
    def total_records(self) -> int:
        """Alias for ``prefixes_total``."""
        return self.prefixes_total

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "source": self.source,
            "prefixes_total": self.prefixes_total,
            "prefixes_v4": self.prefixes_v4,
            "prefixes_v6": self.prefixes_v6,
            "unique_prefixes": self.unique_prefixes,
            "duplicates": self.duplicates,
            "slash_24s": self.slash_24s,
            "slash_48s": self.slash_48s,
            "unique_countries": self.unique_countries,
            "unique_regions": self.unique_regions,
            "unique_cities": self.unique_cities,
            "unique_postal_codes": self.unique_postal_codes,
            "errors": self.errors,
            "warnings": self.warnings,
            "by_country": [c.as_dict() for c in self.by_country],
            "prefix_length_v4": [
                {"prefixlen": pl, "count": count} for pl, count in self.prefix_length_v4
            ],
            "prefix_length_v6": [
                {"prefixlen": pl, "count": count} for pl, count in self.prefix_length_v6
            ],
            "top_regions": [{"region": region, "count": count} for region, count in self.top_regions],
            "top_cities": [{"city": city, "count": count} for city, count in self.top_cities],
            "normalized": self.normalized.as_dict() if self.normalized is not None else None,
            "metadata": dict(self.metadata),
        }


class GeoFeedDiscoveryError(Exception):
    """Raised when no geofeed URL can be discovered for a given query."""

    def __init__(self, query: str) -> None:
        """Initialize with the query that produced no geofeed discovery."""
        super().__init__(f"no geofeed found for {query!r}")
        self.query = query
