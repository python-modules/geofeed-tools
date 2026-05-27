"""Serialization helpers for records and reports."""

from __future__ import annotations

import csv
import json
from io import StringIO

from .models import GeoFeedInfo, GeofeedRecord, QueryResult, ValidationReport


def records_to_csv(
    records: list[GeofeedRecord],
    *,
    include_validation: bool = False,
) -> str:
    """Serialize records to CSV text."""
    output = StringIO()
    writer = csv.writer(output, lineterminator="\n")
    for record in records:
        row = [
            record.prefix,
            record.country,
            record.region,
            record.city,
            record.postal_code,
        ]
        if include_validation:
            row.extend(
                [
                    "true" if record.valid else "false",
                    "; ".join(record.validation_messages),
                ]
            )
        writer.writerow(row)
    return output.getvalue()


def records_to_json(
    records: list[GeofeedRecord],
    *,
    include_validation: bool = True,
) -> str:
    """Serialize records to JSON text."""
    data = [record.as_dict(include_validation=include_validation) for record in records]
    return json.dumps(data, indent=2)


def report_to_json(report: ValidationReport) -> str:
    """Serialize validation report to JSON text."""
    return json.dumps(report.as_dict(), indent=2)


def info_to_json(info: GeoFeedInfo) -> str:
    """Serialize info report to JSON text."""
    return json.dumps(info.as_dict(), indent=2)


def query_to_json(result: QueryResult) -> str:
    """Serialize query result to JSON text."""
    return json.dumps(result.as_dict(), indent=2)
