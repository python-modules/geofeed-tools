"""Validation engine for RFC 8805 geofeed content."""

from __future__ import annotations

import collections
import ipaddress
from functools import lru_cache
from typing import cast

import pycountry

from ._net_utils import (
    Network,
    collapse_same_version,
    network_lt,
    network_subnet_of,
    network_version,
)
from .config import LRU_COUNTRY_CACHE_SIZE, LRU_SUBDIVISION_CACHE_SIZE, TRACE_LEVEL
from .loader import is_url
from .logging import logger
from .models import ValidationIssue, ValidationReport
from .parsing import MAX_FIELDS, ParsedLine, iter_records

AggregationRecord = tuple[Network, tuple[str, str, str, str], int, str]


class _ValidationState:
    """Mutable validation state carried across parsed data lines."""

    def __init__(self) -> None:
        self.record_count = 0
        self.prev_by_version: dict[int, Network] = {}
        self.records_for_aggregation: list[AggregationRecord] = []

    def observe_for_sort(
        self,
        network: Network,
        lineno: int,
        raw_line: str,
        issues: list[ValidationIssue],
    ) -> None:
        """Append a warning when same-version prefixes appear out of order."""
        version = network_version(network)
        previous = self.prev_by_version.get(version)
        if previous is not None and network_lt(network, previous):
            _append_issue(
                issues,
                severity="warning",
                line=lineno,
                code="unsorted",
                message=f"Prefix {network} appears after {previous}; RFC 8805 says records SHOULD be sorted",
                raw_line=raw_line,
            )
        self.prev_by_version[version] = network


def _append_issue(
    issues: list[ValidationIssue],
    *,
    severity: str,
    line: int | None,
    code: str,
    message: str,
    raw_line: str | None = None,
) -> None:
    """Append one validation issue and emit a TRACE log for it."""
    issue = ValidationIssue(
        severity=severity,
        line=line,
        code=code,
        message=message,
        raw_line=raw_line,
    )
    issues.append(issue)
    if logger.isEnabledFor(TRACE_LEVEL):
        logger.log(
            TRACE_LEVEL,
            "Validation issue detected: severity=%s line=%s code=%s message=%s",
            severity,
            line,
            code,
            message,
        )


def find_aggregations(
    records: list[AggregationRecord],
) -> list[ValidationIssue]:
    """Return warnings for prefixes that can be merged safely."""
    issues: list[ValidationIssue] = []
    for net_to_lines in _aggregation_groups(records):
        issues.extend(_group_aggregation_issues(net_to_lines))

    issues.sort(
        key=lambda issue: (
            issue.line if issue.line is not None else 0,
            issue.message,
        )
    )
    return issues


def _aggregation_groups(
    records: list[AggregationRecord],
) -> list[dict[Network, list[tuple[int, str]]]]:
    """Group records by version and geo metadata for aggregation checks."""
    by_key: dict[tuple, list[tuple[Network, int, str]]] = collections.defaultdict(list)
    for network, metadata, lineno, raw_line in records:
        by_key[(network_version(network), metadata)].append((network, lineno, raw_line))

    groups: list[dict[Network, list[tuple[int, str]]]] = []
    for nets in by_key.values():
        net_to_lines: dict[Network, list[tuple[int, str]]] = collections.defaultdict(list)
        for network, lineno, raw_line in nets:
            net_to_lines[network].append((lineno, raw_line))
        if len(net_to_lines) >= 2:
            groups.append(net_to_lines)
    return groups


def _group_aggregation_issues(
    net_to_lines: dict[Network, list[tuple[int, str]]],
) -> list[ValidationIssue]:
    """Build aggregation warnings for one metadata-equivalent group."""
    unique = list(net_to_lines.keys())
    if not unique:
        return []
    issues: list[ValidationIssue] = []

    if isinstance(unique[0], ipaddress.IPv4Network):
        for supernet_v4 in collapse_same_version([cast(ipaddress.IPv4Network, network) for network in unique]):
            contributors = _contributors_for_supernet(
                net_to_lines,
                unique,
                supernet_v4,
            )
            if len({net for net, _line, _raw in contributors}) < 2:
                continue
            contributors.sort(key=lambda item: (item[1], item[0]))
            issues.append(_aggregation_issue(contributors, supernet_v4))
    else:
        for supernet_v6 in collapse_same_version([cast(ipaddress.IPv6Network, network) for network in unique]):
            contributors = _contributors_for_supernet(
                net_to_lines,
                unique,
                supernet_v6,
            )
            if len({net for net, _line, _raw in contributors}) < 2:
                continue
            contributors.sort(key=lambda item: (item[1], item[0]))
            issues.append(_aggregation_issue(contributors, supernet_v6))
    return issues


def _contributors_for_supernet(
    net_to_lines: dict[Network, list[tuple[int, str]]],
    unique: list[Network],
    supernet: Network,
) -> list[tuple[Network, int, str]]:
    """Return prefixes and source lines contained by a candidate supernet."""
    contributors: list[tuple[Network, int, str]] = []
    for original in unique:
        if not network_subnet_of(original, supernet):
            continue
        for line, raw_line in net_to_lines[original]:
            contributors.append((original, line, raw_line))
    return contributors


def _aggregation_issue(
    contributors: list[tuple[Network, int, str]],
    supernet: Network,
) -> ValidationIssue:
    """Build one aggregatable warning from contributors."""
    parts = ", ".join(f"{net} (line {line})" for net, line, _raw_line in contributors)
    return ValidationIssue(
        severity="warning",
        line=contributors[0][1],
        code="aggregatable",
        message=f"{parts} can be aggregated into {supernet}",
        raw_line=contributors[0][2],
    )


@lru_cache(maxsize=LRU_COUNTRY_CACHE_SIZE)
def _lookup_country(alpha2: str):
    """Return cached ISO 3166-1 country lookup results."""
    return pycountry.countries.get(alpha_2=alpha2)


@lru_cache(maxsize=LRU_SUBDIVISION_CACHE_SIZE)
def _lookup_subdivision(code: str):
    """Return cached ISO 3166-2 subdivision lookup results."""
    return pycountry.subdivisions.get(code=code)


def validate_bytes(
    raw: bytes,
    source: str,
    content_type: str | None = None,
    *,
    check_sort: bool = True,
    check_content_type: bool = True,
    check_aggregation: bool = False,
) -> ValidationReport:
    """Validate geofeed bytes and return a structured report."""
    logger.debug(
        "Running validation engine: source=%s bytes=%d check_sort=%s check_content_type=%s check_aggregation=%s",
        source,
        len(raw),
        check_sort,
        check_content_type,
        check_aggregation,
    )
    issues: list[ValidationIssue] = []
    _add_content_type_issue(issues, source, content_type, check_content_type)

    text = _decode_for_validation(raw, issues)
    if text is None:
        logger.debug("Validation stopped before record scanning due to decode failure: source=%s", source)
        return _report_from_issues(source, 0, issues)

    state = _ValidationState()
    for line in iter_records(text, strict=True):
        _validate_data_line(line, issues, state, check_sort, check_aggregation)

    if check_aggregation:
        aggregation_issues = find_aggregations(state.records_for_aggregation)
        issues.extend(aggregation_issues)
        if logger.isEnabledFor(TRACE_LEVEL):
            for issue in aggregation_issues:
                logger.log(
                    TRACE_LEVEL,
                    "Validation issue detected: severity=%s line=%s code=%s message=%s",
                    issue.severity,
                    issue.line,
                    issue.code,
                    issue.message,
                )

    report = _report_from_issues(source, state.record_count, issues)
    logger.debug(
        "Validation engine completed: source=%s records=%d errors=%d warnings=%d",
        source,
        report.records,
        report.errors,
        report.warnings,
    )
    return report


def _add_content_type_issue(
    issues: list[ValidationIssue],
    source: str,
    content_type: str | None,
    check_content_type: bool,
) -> None:
    """Append content-type warning when URL payload type is non-CSV."""
    if not (check_content_type and content_type and is_url(source)):
        return
    content_type_raw = content_type.split(";", 1)[0].strip().lower()
    if content_type_raw == "text/csv":
        return
    issues.append(
        ValidationIssue(
            severity="warning",
            line=None,
            code="content-type",
            message=(f"Content-Type is {content_type!r}; RFC 8805 recommends text/csv"),
        )
    )


def _decode_for_validation(
    raw: bytes,
    issues: list[ValidationIssue],
) -> str | None:
    """Decode UTF-8 payload and append encoding or BOM issues."""
    if raw.startswith(b"\xef\xbb\xbf"):
        issues.append(
            ValidationIssue(
                severity="error",
                line=1,
                code="bom",
                message="File starts with a UTF-8 BOM; RFC 8805 forbids BOM",
            )
        )
        raw = raw[3:]
    elif raw.startswith((b"\xff\xfe", b"\xfe\xff", b"\x00\x00\xfe\xff", b"\xff\xfe\x00\x00")):
        issues.append(
            ValidationIssue(
                severity="error",
                line=1,
                code="bom",
                message=("File starts with a UTF-16/32 BOM; RFC 8805 requires UTF-8"),
            )
        )
        return None

    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        issues.append(
            ValidationIssue(
                severity="error",
                line=exc.start,
                code="encoding",
                message=(f"File is not valid UTF-8 at byte {exc.start}: {exc.reason}"),
            )
        )
        return None


def _validate_data_line(
    line: ParsedLine,
    issues: list[ValidationIssue],
    state: _ValidationState,
    check_sort: bool,
    check_aggregation: bool,
) -> None:
    """Validate one parsed data line and update shared state."""
    if line.csv_error is not None:
        _append_issue(
            issues,
            severity="error",
            line=line.lineno,
            code="csv",
            message=f"CSV parse error: {line.csv_error}",
            raw_line=line.raw_line,
        )
        return

    assert line.raw_fields is not None
    if len(line.raw_fields) > MAX_FIELDS:
        _append_issue(
            issues,
            severity="error",
            line=line.lineno,
            code="too-many-fields",
            message=f"Expected at most {MAX_FIELDS} fields, got {len(line.raw_fields)}",
            raw_line=line.raw_line,
        )

    if not line.prefix:
        _append_issue(
            issues,
            severity="error",
            line=line.lineno,
            code="missing-prefix",
            message="IP prefix is empty",
            raw_line=line.raw_line,
        )
        return
    if line.network is None:
        _append_issue(
            issues,
            severity="error",
            line=line.lineno,
            code="invalid-prefix",
            message=f"Invalid prefix {line.prefix!r}: {line.network_error}",
            raw_line=line.raw_line,
        )
        return

    country_norm = _validate_country(
        line.country,
        line.region,
        line.city,
        line.postal,
        line.lineno,
        line.raw_line,
        issues,
    )
    region_norm = _validate_region(line.region, country_norm, line.lineno, line.raw_line, issues)

    state.record_count += 1
    if check_sort:
        state.observe_for_sort(line.network, line.lineno, line.raw_line, issues)
    if check_aggregation:
        state.records_for_aggregation.append(
            (line.network, (country_norm, region_norm, line.city, line.postal), line.lineno, line.raw_line)
        )


def _validate_country(
    country: str,
    region: str,
    city: str,
    postal: str,
    lineno: int,
    raw_line: str,
    issues: list[ValidationIssue],
) -> str:
    """Validate and normalize country code with dependent field rules."""
    if not country:
        if region or city or postal:
            _append_issue(
                issues,
                severity="error",
                line=lineno,
                code="missing-country",
                message="Country code is required when region/city/postal-code is present",
                raw_line=raw_line,
            )
        return ""

    country_norm = country.upper()
    if country != country_norm:
        _append_issue(
            issues,
            severity="warning",
            line=lineno,
            code="country-case",
            message=f"Country code {country!r} should be uppercase ({country_norm!r})",
            raw_line=raw_line,
        )

    if _lookup_country(country_norm):
        return country_norm

    _append_issue(
        issues,
        severity="error",
        line=lineno,
        code="invalid-country",
        message=f"Unknown ISO 3166-1 alpha-2 country code {country!r}",
        raw_line=raw_line,
    )
    return ""


def _validate_region(
    region: str,
    country_norm: str,
    lineno: int,
    raw_line: str,
    issues: list[ValidationIssue],
) -> str:
    """Validate and normalize region code and country affinity."""
    if not region:
        return ""

    region_norm = region.upper()
    if region != region_norm:
        _append_issue(
            issues,
            severity="warning",
            line=lineno,
            code="region-case",
            message=f"Region code {region!r} should be uppercase ({region_norm!r})",
            raw_line=raw_line,
        )

    subdivision = _lookup_subdivision(region_norm)
    if subdivision is None:
        _append_issue(
            issues,
            severity="error",
            line=lineno,
            code="invalid-region",
            message=f"Unknown ISO 3166-2 subdivision code {region!r}",
            raw_line=raw_line,
        )
        return region_norm

    if country_norm and subdivision.country_code != country_norm:
        _append_issue(
            issues,
            severity="error",
            line=lineno,
            code="region-country-mismatch",
            message=f"Region {region_norm!r} belongs to {subdivision.country_code!r}, not {country_norm!r}",
            raw_line=raw_line,
        )
    return region_norm


def _report_from_issues(
    source: str,
    record_count: int,
    issues: list[ValidationIssue],
) -> ValidationReport:
    """Build a ValidationReport with computed error and warning counts."""
    errors = sum(1 for issue in issues if issue.severity == "error")
    warnings = sum(1 for issue in issues if issue.severity == "warning")
    return ValidationReport(
        source=source,
        records=record_count,
        errors=errors,
        warnings=warnings,
        valid=errors == 0,
        issues=tuple(issues),
    )


def render_validation_text(report: ValidationReport) -> str:
    """Render a human-readable validation report."""
    lines = [f"source: {report.source}", f"records: {report.records}"]
    if not report.issues:
        lines.append("no issues found")
        return "\n".join(lines)

    lines.append("")
    lines.extend(issue.format() for issue in report.issues)
    lines.append("")
    lines.append(f"summary: {report.errors} error(s), {report.warnings} warning(s)")
    return "\n".join(lines)
