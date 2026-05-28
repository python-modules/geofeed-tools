"""Normalization operations for geofeed records."""

from __future__ import annotations

import collections
import ipaddress
from typing import cast

from ._net_utils import Network, collapse_same_version, network_version
from .config import TRACE_LEVEL
from .logging import logger
from .models import GeofeedRecord
from .parsing import iter_records


def normalize_records(
    text: str,
    *,
    uppercase: bool = True,
    sort: bool = True,
    aggregate: bool = True,
    dedupe: bool = True,
    fix_host_bits: bool = True,
) -> list[GeofeedRecord]:
    """Normalize geofeed rows using transform toggles."""
    logger.debug(
        "Normalizing geofeed records internally: uppercase=%s sort=%s aggregate=%s dedupe=%s fix_host_bits=%s",
        uppercase,
        sort,
        aggregate,
        dedupe,
        fix_host_bits,
    )
    parsed = _parse_and_fix(
        text,
        uppercase=uppercase,
        fix_host_bits=fix_host_bits,
    )

    if aggregate:
        emitted = _aggregate(parsed)
    elif dedupe:
        emitted = _dedupe(parsed)
    else:
        emitted = [(network, country, region, city, postal) for network, country, region, city, postal, _ in parsed]

    if sort:
        emitted = sorted(
            emitted,
            key=lambda row: (network_version(row[0]), row[0]),
        )

    return [
        GeofeedRecord(
            prefix=str(network),
            country=country,
            region=region,
            city=city,
            postal_code=postal,
        )
        for network, country, region, city, postal in emitted
    ]


def _parse_and_fix(
    text: str,
    *,
    uppercase: bool,
    fix_host_bits: bool,
) -> list[tuple[Network, str, str, str, str, int]]:
    """Parse and normalize individual records with optional host-bit fixes."""
    records: list[tuple[Network, str, str, str, str, int]] = []
    skipped_lines = 0
    skipped_invalid_prefixes = 0
    host_bit_fixes = 0
    for line in iter_records(text, strict=True):
        if line.csv_error is not None:
            skipped_lines += 1
            logger.log(
                TRACE_LEVEL,
                "Skipping geofeed line during normalization due to CSV error: line=%d error=%s",
                line.lineno,
                line.csv_error,
            )
            continue
        if not line.prefix:
            skipped_lines += 1
            logger.log(
                TRACE_LEVEL,
                "Skipping geofeed line during normalization due to missing prefix: line=%d",
                line.lineno,
            )
            continue

        network = line.network
        if network is None and fix_host_bits:
            try:
                network = ipaddress.ip_network(line.prefix, strict=False)
            except ValueError:
                network = None
        if network is None:
            skipped_invalid_prefixes += 1
            logger.log(
                TRACE_LEVEL,
                "Skipping geofeed line during normalization due to invalid prefix: line=%d prefix=%r",
                line.lineno,
                line.prefix,
            )
            continue
        if fix_host_bits and str(network) != line.prefix:
            host_bit_fixes += 1
            logger.log(
                TRACE_LEVEL,
                "Normalized host bits during geofeed normalization: line=%d original_prefix=%r normalized_prefix=%s",
                line.lineno,
                line.prefix,
                network,
            )

        country, region = _normalize_case(line.country, line.region, uppercase)
        records.append((network, country, region, line.city, line.postal, line.lineno))

    logger.debug(
        "Prepared geofeed normalization records: records=%d skipped_lines=%d skipped_invalid_prefixes=%d host_bit_fixes=%d",
        len(records),
        skipped_lines,
        skipped_invalid_prefixes,
        host_bit_fixes,
    )

    return records


def _normalize_case(
    country: str,
    region: str,
    uppercase: bool,
) -> tuple[str, str]:
    """Normalize country/region casing when enabled."""
    if not uppercase:
        return country, region
    return (
        country.upper() if country else country,
        region.upper() if region else region,
    )


def _aggregate(
    records: list[tuple[Network, str, str, str, str, int]],
) -> list[tuple[Network, str, str, str, str]]:
    """Aggregate collapsible prefixes per identical metadata tuple."""
    by_key: dict[tuple, list[tuple[Network, int]]] = collections.defaultdict(list)
    for network, country, region, city, postal, lineno in records:
        by_key[(network_version(network), country, region, city, postal)].append((network, lineno))

    out: list[tuple[Network, str, str, str, str]] = []
    for (_version, country, region, city, postal), entries in by_key.items():
        unique = {network for network, _lineno in entries}
        if _version == 4:
            for network in collapse_same_version([cast(ipaddress.IPv4Network, network) for network in unique]):
                out.append((network, country, region, city, postal))
        else:
            for network in collapse_same_version([cast(ipaddress.IPv6Network, network) for network in unique]):
                out.append((network, country, region, city, postal))
    logger.debug(
        "Aggregated geofeed normalization records: input=%d groups=%d output=%d",
        len(records),
        len(by_key),
        len(out),
    )
    return out


def _dedupe(
    records: list[tuple[Network, str, str, str, str, int]],
) -> list[tuple[Network, str, str, str, str]]:
    """Drop exact duplicate network+metadata entries."""
    seen: set[tuple[Network, str, str, str, str]] = set()
    out: list[tuple[Network, str, str, str, str]] = []

    for network, country, region, city, postal, _lineno in records:
        item = (network, country, region, city, postal)
        if item in seen:
            continue
        seen.add(item)
        out.append(item)

    logger.debug(
        "Deduplicated geofeed normalization records: input=%d output=%d removed=%d",
        len(records),
        len(out),
        len(records) - len(out),
    )

    return out
