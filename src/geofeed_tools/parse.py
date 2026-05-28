"""Geofeed parsing and record-level validation annotation."""

from __future__ import annotations

import collections

from ._net_utils import Network
from .config import TRACE_LEVEL
from .logging import logger
from .models import GeofeedRecord
from .parsing import iter_records
from .validate import validate_bytes


def parse_text_with_networks(
    text: str,
) -> tuple[list[GeofeedRecord], list[Network | None]]:
    """Parse text into records, carrying the parsed network alongside each row."""
    records: list[GeofeedRecord] = []
    networks: list[Network | None] = []
    skipped_csv_errors = 0
    skipped_missing_prefix = 0
    for line in iter_records(text, strict=False):
        if line.csv_error is not None:
            skipped_csv_errors += 1
            logger.log(
                TRACE_LEVEL,
                "Skipping geofeed line during parse due to CSV error: line=%d error=%s",
                line.lineno,
                line.csv_error,
            )
            continue
        if not line.prefix:
            skipped_missing_prefix += 1
            logger.log(
                TRACE_LEVEL,
                "Skipping geofeed line during parse due to missing prefix: line=%d",
                line.lineno,
            )
            continue
        records.append(
            GeofeedRecord(
                prefix=line.prefix,
                country=line.country,
                region=line.region,
                city=line.city,
                postal_code=line.postal,
                line=line.lineno,
            )
        )
        networks.append(line.network)
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
