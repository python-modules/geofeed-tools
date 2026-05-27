"""Geofeed parsing and record-level validation annotation."""

from __future__ import annotations

import collections
import csv
import ipaddress

from .logging import TRACE_LEVEL, logger
from .models import GeofeedRecord
from .parsing import iter_data_lines, normalize_fields, parse_record
from .validate import validate_bytes

Network = ipaddress.IPv4Network | ipaddress.IPv6Network


def parse_text(text: str) -> list[GeofeedRecord]:
    """Parse text into geofeed records, skipping malformed rows."""
    records, _networks = _parse_text_impl(text, include_networks=False)
    return records


def parse_text_with_networks(
    text: str,
) -> tuple[list[GeofeedRecord], list[Network | None]]:
    """Parse text into records and carry parsed network info forward."""
    records, networks = _parse_text_impl(text, include_networks=True)
    assert networks is not None
    return records, networks


def _parse_text_impl(
    text: str,
    *,
    include_networks: bool,
) -> tuple[list[GeofeedRecord], list[Network | None] | None]:
    """Parse text into geofeed records with optional parsed-network metadata."""
    records: list[GeofeedRecord] = []
    networks: list[Network | None] | None = [] if include_networks else None
    skipped_csv_errors = 0
    skipped_missing_prefix = 0
    for lineno, data in iter_data_lines(text):
        try:
            fields = parse_record(data)
        except csv.Error as exc:
            skipped_csv_errors += 1
            logger.log(
                TRACE_LEVEL,
                "Skipping geofeed line during parse due to CSV error: line=%d error=%s",
                lineno,
                exc,
            )
            continue
        prefix, country, region, city, postal = normalize_fields(fields)
        if not prefix:
            skipped_missing_prefix += 1
            logger.log(
                TRACE_LEVEL,
                "Skipping geofeed line during parse due to missing prefix: line=%d",
                lineno,
            )
            continue
        record = GeofeedRecord(
            prefix=prefix,
            country=country,
            region=region,
            city=city,
            postal_code=postal,
            line=lineno,
        )
        records.append(record)
        if networks is not None:
            try:
                networks.append(ipaddress.ip_network(prefix, strict=False))
            except ValueError:
                networks.append(None)
    logger.debug(
        "Parsed raw geofeed text into records: records=%d skipped_csv_errors=%d skipped_missing_prefix=%d",
        len(records),
        skipped_csv_errors,
        skipped_missing_prefix,
    )
    return records, networks


def annotate_validity(
    records: list[GeofeedRecord],
    *,
    source: str,
    raw: bytes,
    content_type: str | None,
) -> list[GeofeedRecord]:
    """Annotate parsed records with error-derived validity flags."""
    logger.debug(
        "Annotating parsed geofeed records with validation results: source=%s records=%d",
        source,
        len(records),
    )
    report = validate_bytes(
        raw,
        source,
        content_type,
        check_sort=False,
        check_content_type=False,
        check_aggregation=False,
    )

    errors_by_line: dict[int, list[str]] = collections.defaultdict(list)
    for issue in report.issues:
        if issue.severity == "error" and issue.line is not None:
            errors_by_line[issue.line].append(issue.message)

    out: list[GeofeedRecord] = []
    for record in records:
        messages = tuple(errors_by_line.get(record.line, []))
        out.append(
            GeofeedRecord(
                prefix=record.prefix,
                country=record.country,
                region=record.region,
                city=record.city,
                postal_code=record.postal_code,
                line=record.line,
                valid=not messages,
                validation_messages=messages,
            )
        )

    invalid_records = sum(1 for record in out if not record.valid)
    logger.debug(
        "Annotated parsed geofeed records with validation results: source=%s records=%d invalid_records=%d",
        source,
        len(out),
        invalid_records,
    )

    return out
