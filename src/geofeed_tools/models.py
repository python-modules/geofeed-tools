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
        """Return a JSON-serializable representation of the validation report."""
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
            "matches": [record.as_dict(include_validation=False, include_raw_line=True) for record in self.matches],
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
        """Return a JSON-serializable representation of the info payload."""
        return asdict(self)
