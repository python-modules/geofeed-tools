"""Validation engine for RFC 8805 geofeed content."""

from __future__ import annotations

import collections
import csv
import dataclasses
import ipaddress

import pycountry

from .loader import is_url
from .models import ValidationIssue, ValidationReport
from .parsing import (
    MAX_FIELDS,
    iter_data_lines,
    normalize_fields,
    parse_record,
)

Network = ipaddress.IPv4Network | ipaddress.IPv6Network


class _ValidationState:
    """Mutable validation state carried across parsed data lines."""

    def __init__(self) -> None:
        self.record_count = 0
        self.prev_by_version: dict[int, Network] = {}
        self.records_for_aggregation: list[tuple[Network, tuple[str, str, str, str], int]] = []


def find_aggregations(
    records: list[tuple[Network, tuple[str, str, str, str], int]],
) -> list[ValidationIssue]:
    """Return warnings for prefixes that can be merged safely."""
    issues: list[ValidationIssue] = []
    for net_to_lines in _aggregation_groups(records):
        for issue in _group_aggregation_issues(net_to_lines):
            issues.append(issue)

    issues.sort(
        key=lambda issue: (
            issue.line if issue.line is not None else 0,
            issue.message,
        )
    )
    return issues


def _aggregation_groups(
    records: list[tuple[Network, tuple[str, str, str, str], int]],
) -> list[dict[Network, list[int]]]:
    """Group records by version and geo metadata for aggregation checks."""
    by_key: dict[tuple, list[tuple[Network, int]]] = collections.defaultdict(list)
    for network, metadata, lineno in records:
        by_key[(_network_version(network), metadata)].append((network, lineno))

    groups: list[dict[Network, list[int]]] = []
    for nets in by_key.values():
        net_to_lines: dict[Network, list[int]] = collections.defaultdict(list)
        for network, lineno in nets:
            net_to_lines[network].append(lineno)
        if len(net_to_lines) >= 2:
            groups.append(net_to_lines)
    return groups


def _group_aggregation_issues(
    net_to_lines: dict[Network, list[int]],
) -> list[ValidationIssue]:
    """Build aggregation warnings for one metadata-equivalent group."""
    unique = list(net_to_lines.keys())
    collapsed = _collapse_same_version(unique)
    issues: list[ValidationIssue] = []
    for supernet in collapsed:
        contributors = _contributors_for_supernet(
            net_to_lines,
            unique,
            supernet,
        )
        if len({net for net, _line in contributors}) < 2:
            continue
        contributors.sort(key=lambda item: (item[1], item[0]))
        issues.append(_aggregation_issue(contributors, supernet))
    return issues


def _contributors_for_supernet(
    net_to_lines: dict[Network, list[int]],
    unique: list[Network],
    supernet: Network,
) -> list[tuple[Network, int]]:
    """Return prefixes and source lines contained by a candidate supernet."""
    contributors: list[tuple[Network, int]] = []
    for original in unique:
        if not _network_subnet_of(original, supernet):
            continue
        for line in net_to_lines[original]:
            contributors.append((original, line))
    return contributors


def _aggregation_issue(
    contributors: list[tuple[Network, int]],
    supernet: Network,
) -> ValidationIssue:
    """Build one aggregatable warning from contributors."""
    parts = ", ".join(f"{net} (line {line})" for net, line in contributors)
    return ValidationIssue(
        severity="warning",
        line=contributors[0][1],
        code="aggregatable",
        message=f"{parts} can be aggregated into {supernet}",
    )


def _network_version(network: Network) -> int:
    """Return network IP version as integer."""
    return 4 if isinstance(network, ipaddress.IPv4Network) else 6


def _network_subnet_of(candidate: Network, container: Network) -> bool:
    """Check subnet relation while preserving type safety across families."""
    if isinstance(candidate, ipaddress.IPv4Network) and isinstance(
        container,
        ipaddress.IPv4Network,
    ):
        return candidate.subnet_of(container)
    if isinstance(candidate, ipaddress.IPv6Network) and isinstance(
        container,
        ipaddress.IPv6Network,
    ):
        return candidate.subnet_of(container)
    return False


def _network_lt(left: Network, right: Network) -> bool:
    """Compare two same-family networks for ordering."""
    if isinstance(left, ipaddress.IPv4Network) and isinstance(
        right,
        ipaddress.IPv4Network,
    ):
        return left < right
    if isinstance(left, ipaddress.IPv6Network) and isinstance(
        right,
        ipaddress.IPv6Network,
    ):
        return left < right
    return False


def _collapse_same_version(unique: list[Network]) -> list[Network]:
    """Collapse a same-version network list with stable typing."""
    if not unique:
        return []

    if isinstance(unique[0], ipaddress.IPv4Network):
        ipv4_nets = [net for net in unique if isinstance(net, ipaddress.IPv4Network)]
        return list(ipaddress.collapse_addresses(ipv4_nets))

    ipv6_nets = [net for net in unique if isinstance(net, ipaddress.IPv6Network)]
    return list(ipaddress.collapse_addresses(ipv6_nets))


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
    issues: list[ValidationIssue] = []
    _add_content_type_issue(
        issues,
        source,
        content_type,
        check_content_type,
    )

    text = _decode_for_validation(raw, issues)
    if text is None:
        return _report_from_issues(source, 0, issues)

    state = _ValidationState()
    for lineno, data in iter_data_lines(text):
        _validate_data_line(
            lineno,
            data,
            issues,
            state,
            check_sort,
            check_aggregation,
        )

    if check_aggregation:
        issues.extend(find_aggregations(state.records_for_aggregation))

    if text is not None:
        line_map = dict(enumerate(text.splitlines(), start=1))
        issues = [
            dataclasses.replace(issue, raw_line=line_map.get(issue.line)) if issue.line is not None else issue
            for issue in issues
        ]

    return _report_from_issues(source, state.record_count, issues)


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
    lineno: int,
    data: str,
    issues: list[ValidationIssue],
    state: _ValidationState,
    check_sort: bool,
    check_aggregation: bool,
) -> None:
    """Validate one parsed data line and update shared state."""
    fields = _parse_fields(lineno, data, issues)
    if fields is None:
        return

    network, geo = _validate_prefix_and_geo(lineno, fields, issues)
    if network is None or geo is None:
        return

    state.record_count += 1
    country_norm, region_norm, city, postal = geo

    _apply_sort_check(lineno, network, issues, state, check_sort)

    if check_aggregation:
        state.records_for_aggregation.append((network, (country_norm, region_norm, city, postal), lineno))


def _parse_fields(
    lineno: int,
    data: str,
    issues: list[ValidationIssue],
) -> list[str] | None:
    """Parse one CSV record into normalized RFC 8805 fields."""
    try:
        fields = parse_record(data)
    except csv.Error as exc:
        issues.append(
            ValidationIssue(
                severity="error",
                line=lineno,
                code="csv",
                message=f"CSV parse error: {exc}",
            )
        )
        return None

    if len(fields) > MAX_FIELDS:
        issues.append(
            ValidationIssue(
                severity="error",
                line=lineno,
                code="too-many-fields",
                message=(f"Expected at most {MAX_FIELDS} fields, got {len(fields)}"),
            )
        )
    return normalize_fields(fields)


def _validate_prefix_and_geo(
    lineno: int,
    fields: list[str],
    issues: list[ValidationIssue],
) -> tuple[
    Network | None,
    tuple[str, str, str, str] | None,
]:
    """Validate prefix and geo fields, returning normalized values."""
    prefix, country, region, city, postal = fields
    network = _parse_network(prefix, lineno, issues)
    if network is None:
        return None, None

    country_norm = _validate_country(
        country,
        region,
        city,
        postal,
        lineno,
        issues,
    )
    region_norm = _validate_region(region, country_norm, lineno, issues)
    return network, (country_norm, region_norm, city, postal)


def _parse_network(
    prefix: str,
    lineno: int,
    issues: list[ValidationIssue],
) -> Network | None:
    """Parse strict CIDR network and append errors on failure."""
    if not prefix:
        issues.append(
            ValidationIssue(
                severity="error",
                line=lineno,
                code="missing-prefix",
                message="IP prefix is empty",
            )
        )
        return None

    try:
        network = ipaddress.ip_network(prefix, strict=True)
        return network
    except ValueError as exc:
        issues.append(
            ValidationIssue(
                severity="error",
                line=lineno,
                code="invalid-prefix",
                message=f"Invalid prefix {prefix!r}: {exc}",
            )
        )
        return None


def _validate_country(
    country: str,
    region: str,
    city: str,
    postal: str,
    lineno: int,
    issues: list[ValidationIssue],
) -> str:
    """Validate and normalize country code with dependent field rules."""
    if not country:
        if region or city or postal:
            issues.append(
                ValidationIssue(
                    severity="error",
                    line=lineno,
                    code="missing-country",
                    message=("Country code is required when region/city/postal-code is present"),
                )
            )
        return ""

    country_norm = country.upper()
    if country != country_norm:
        issues.append(
            ValidationIssue(
                severity="warning",
                line=lineno,
                code="country-case",
                message=(f"Country code {country!r} should be uppercase ({country_norm!r})"),
            )
        )

    if pycountry.countries.get(alpha_2=country_norm):
        return country_norm

    issues.append(
        ValidationIssue(
            severity="error",
            line=lineno,
            code="invalid-country",
            message=(f"Unknown ISO 3166-1 alpha-2 country code {country!r}"),
        )
    )
    return ""


def _validate_region(
    region: str,
    country_norm: str,
    lineno: int,
    issues: list[ValidationIssue],
) -> str:
    """Validate and normalize region code and country affinity."""
    if not region:
        return ""

    region_norm = region.upper()
    if region != region_norm:
        issues.append(
            ValidationIssue(
                severity="warning",
                line=lineno,
                code="region-case",
                message=(f"Region code {region!r} should be uppercase ({region_norm!r})"),
            )
        )

    subdivision = pycountry.subdivisions.get(code=region_norm)
    if subdivision is None:
        issues.append(
            ValidationIssue(
                severity="error",
                line=lineno,
                code="invalid-region",
                message=(f"Unknown ISO 3166-2 subdivision code {region!r}"),
            )
        )
        return region_norm

    if country_norm and subdivision.country_code != country_norm:
        issues.append(
            ValidationIssue(
                severity="error",
                line=lineno,
                code="region-country-mismatch",
                message=(f"Region {region_norm!r} belongs to {subdivision.country_code!r}, not {country_norm!r}"),
            )
        )
    return region_norm


def _apply_sort_check(
    lineno: int,
    network: Network,
    issues: list[ValidationIssue],
    state: _ValidationState,
    check_sort: bool,
) -> None:
    """Append warning when same-version prefixes are out of sort order."""
    if not check_sort:
        return
    version = _network_version(network)
    previous = state.prev_by_version.get(version)
    if previous is not None and _network_lt(network, previous):
        issues.append(
            ValidationIssue(
                severity="warning",
                line=lineno,
                code="unsorted",
                message=(f"Prefix {network} appears after {previous}; RFC 8805 says records SHOULD be sorted"),
            )
        )
    state.prev_by_version[version] = network


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
