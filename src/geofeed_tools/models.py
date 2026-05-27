"""Dataclasses used by the public geofeed_tools API."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


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


@dataclass(frozen=True)
class ValidationIssue:
    """Validation issue with severity, location, and machine-readable code."""

    severity: str
    line: int | None
    code: str
    message: str
    raw_line: str | None = None

    def format(self) -> str:
        location = f"line {self.line}" if self.line is not None else "file"
        return (
            f"[{self.severity.upper()}] "
            f"{location}: {self.code}: {self.message}"
        )


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
        return {
            "query": self.query,
            "matches": [
                {
                    "prefix": record.prefix,
                    "country": record.country,
                    "region": record.region,
                    "city": record.city,
                    "postal_code": record.postal_code,
                    "raw_line": record.raw_line,
                }
                for record in self.matches
            ],
        }


@dataclass(frozen=True)
class GeoFeedInfo:
    """High-level statistics for a geofeed source."""

    source: str
    total_records: int
    unique_prefixes: int
    ipv4_records: int
    ipv6_records: int
    unique_countries: int
    unique_regions: int
    unique_cities: int
    unique_postal_codes: int
    duplicates: int
    errors: int = 0
    warnings: int = 0
    metadata: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return asdict(self)
