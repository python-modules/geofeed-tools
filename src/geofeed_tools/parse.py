"""Geofeed parsing and record-level validation annotation."""

from __future__ import annotations

import collections
import csv

from .models import GeofeedRecord
from .parsing import iter_data_lines, normalize_fields, parse_record
from .validate import validate_bytes


def parse_text(text: str) -> list[GeofeedRecord]:
    """Parse text into geofeed records, skipping malformed rows."""

    records: list[GeofeedRecord] = []
    for lineno, data in iter_data_lines(text):
        try:
            fields = parse_record(data)
        except csv.Error:
            continue
        prefix, country, region, city, postal = normalize_fields(fields)
        if not prefix:
            continue
        records.append(
            GeofeedRecord(
                prefix=prefix,
                country=country,
                region=region,
                city=city,
                postal_code=postal,
                line=lineno,
            )
        )
    return records


def annotate_validity(
    records: list[GeofeedRecord],
    *,
    source: str,
    raw: bytes,
    content_type: str | None,
) -> list[GeofeedRecord]:
    """Annotate parsed records with error-derived validity flags."""

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

    return out
