"""CSV parsing helpers shared across operations."""

from __future__ import annotations

import csv
import ipaddress
from collections.abc import Iterator
from dataclasses import dataclass

from ._net_utils import Network

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
    return next(csv.reader([data_line]))


def iter_data_lines_with_raw(text: str) -> Iterator[tuple[int, str, str]]:
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


@dataclass(frozen=True, slots=True)
class ParsedLine:
    """One parsed RFC 8805 data line with normalized fields and optional network."""

    lineno: int
    raw_line: str
    raw_fields: list[str] | None
    csv_error: csv.Error | None
    prefix: str
    country: str
    region: str
    city: str
    postal: str
    network: Network | None
    network_error: ValueError | None

    @property
    def ok(self) -> bool:
        """True iff CSV parsed, prefix present, and network parsed under requested strictness."""
        return self.csv_error is None and bool(self.prefix) and self.network is not None


def iter_records(text: str, *, strict: bool = True) -> Iterator[ParsedLine]:
    """Yield ParsedLine objects for every non-empty data line.

    Always emits one ParsedLine per data line; callers branch on csv_error,
    missing prefix (``prefix == ""``), or network_error to handle error cases.
    """
    for lineno, raw_line, data in iter_data_lines_with_raw(text):
        try:
            raw_fields = parse_record(data)
        except csv.Error as exc:
            yield ParsedLine(
                lineno=lineno,
                raw_line=raw_line,
                raw_fields=None,
                csv_error=exc,
                prefix="",
                country="",
                region="",
                city="",
                postal="",
                network=None,
                network_error=None,
            )
            continue

        prefix, country, region, city, postal = normalize_fields(raw_fields)
        network: Network | None = None
        network_error: ValueError | None = None
        if prefix:
            try:
                network = ipaddress.ip_network(prefix, strict=strict)
            except ValueError as exc:
                network_error = exc

        yield ParsedLine(
            lineno=lineno,
            raw_line=raw_line,
            raw_fields=raw_fields,
            csv_error=None,
            prefix=prefix,
            country=country,
            region=region,
            city=city,
            postal=postal,
            network=network,
            network_error=network_error,
        )
