"""CSV parsing helpers shared across operations."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable

MAX_FIELDS = 5


def split_comment(line: str) -> str:
    """Strip RFC 8805 inline comments while honoring quoted fields."""
    in_quote = False
    index = 0
    length = len(line)
    while index < length:
        char = line[index]
        if char == '"':
            if in_quote and index + 1 < length and line[index + 1] == '"':
                index += 2
                continue
            in_quote = not in_quote
        elif char == "#" and not in_quote:
            return line[:index]
        index += 1
    return line


def parse_record(data_line: str) -> list[str]:
    """Parse one CSV data line into fields."""
    return next(csv.reader(io.StringIO(data_line)))


def iter_data_lines(text: str) -> Iterable[tuple[int, str]]:
    """Yield line number and non-empty data content for feed lines."""
    for lineno, _raw_line, data in iter_data_lines_with_raw(text):
        yield lineno, data


def iter_data_lines_with_raw(text: str) -> Iterable[tuple[int, str, str]]:
    """Yield line number, original raw line, and parsed data for feed lines."""
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        data = split_comment(raw_line).strip()
        if data:
            yield lineno, raw_line, data


def normalize_fields(fields: list[str]) -> list[str]:
    """Trim and right-pad parsed fields to RFC 8805 field count."""
    out = [field.strip() for field in fields[:MAX_FIELDS]]
    while len(out) < MAX_FIELDS:
        out.append("")
    return out
