"""Normalization operations for geofeed records."""

from __future__ import annotations

import collections
import csv
import ipaddress

from .logging import TRACE_LEVEL, logger
from .models import GeofeedRecord
from .parsing import iter_data_lines, normalize_fields, parse_record

Network = ipaddress.IPv4Network | ipaddress.IPv6Network


def parse_for_normalize(
    text: str,
) -> list[tuple[Network, str, str, str, str, int]]:
    """Parse text into normalization-ready tuples."""
    records: list[tuple[Network, str, str, str, str, int]] = []
    for lineno, data in iter_data_lines(text):
        try:
            fields = parse_record(data)
        except csv.Error:
            continue
        prefix, country, region, city, postal = normalize_fields(fields)
        if not prefix:
            continue
        try:
            network = ipaddress.ip_network(prefix, strict=True)
        except ValueError:
            continue
        records.append((network, country, region, city, postal, lineno))
    return records


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
            key=lambda row: (_network_version(row[0]), row[0]),
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
    for lineno, data in iter_data_lines(text):
        parsed = _parse_line(data)
        if parsed is None:
            skipped_lines += 1
            continue

        prefix, country, region, city, postal = parsed
        network = _parse_network(prefix, fix_host_bits)
        if network is None:
            skipped_invalid_prefixes += 1
            logger.log(
                TRACE_LEVEL,
                "Skipping geofeed line during normalization due to invalid prefix: line=%d prefix=%r",
                lineno,
                prefix,
            )
            continue
        if fix_host_bits and str(network) != prefix:
            host_bit_fixes += 1
            logger.log(
                TRACE_LEVEL,
                "Normalized host bits during geofeed normalization: line=%d original_prefix=%r normalized_prefix=%s",
                lineno,
                prefix,
                network,
            )

        country, region = _normalize_case(country, region, uppercase)

        records.append((network, country, region, city, postal, lineno))

    logger.debug(
        "Prepared geofeed normalization records: records=%d skipped_lines=%d skipped_invalid_prefixes=%d host_bit_fixes=%d",
        len(records),
        skipped_lines,
        skipped_invalid_prefixes,
        host_bit_fixes,
    )

    return records


def _parse_line(data: str) -> list[str] | None:
    """Parse and normalize one CSV data line."""
    try:
        fields = parse_record(data)
    except csv.Error as exc:
        logger.log(
            TRACE_LEVEL,
            "Skipping geofeed line during normalization due to CSV error: error=%s",
            exc,
        )
        return None
    parsed = normalize_fields(fields)
    if not parsed[0]:
        logger.log(TRACE_LEVEL, "Skipping geofeed line during normalization due to missing prefix")
        return None
    return parsed


def _parse_network(
    prefix: str,
    fix_host_bits: bool,
) -> Network | None:
    """Parse a prefix and optionally normalize host bits."""
    network: Network | None = None
    try:
        network = ipaddress.ip_network(prefix, strict=True)
    except ValueError:
        if fix_host_bits:
            try:
                network = ipaddress.ip_network(prefix, strict=False)
            except ValueError:
                network = None
    return network


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
        by_key[(_network_version(network), country, region, city, postal)].append((network, lineno))

    out: list[tuple[Network, str, str, str, str]] = []
    for (_version, country, region, city, postal), entries in by_key.items():
        unique = {network for network, _lineno in entries}
        collapsed = _collapse_same_version(list(unique))
        for network in collapsed:
            out.append((network, country, region, city, postal))
    logger.debug(
        "Aggregated geofeed normalization records: input=%d groups=%d output=%d",
        len(records),
        len(by_key),
        len(out),
    )
    return out


def _network_version(network: Network) -> int:
    """Return network IP version as integer."""
    return 4 if isinstance(network, ipaddress.IPv4Network) else 6


def _collapse_same_version(networks: list[Network]) -> list[Network]:
    """Collapse networks that are known to share the same IP version."""
    if not networks:
        return []

    if isinstance(networks[0], ipaddress.IPv4Network):
        ipv4_nets = [net for net in networks if isinstance(net, ipaddress.IPv4Network)]
        return list(ipaddress.collapse_addresses(ipv4_nets))

    ipv6_nets = [net for net in networks if isinstance(net, ipaddress.IPv6Network)]
    return list(ipaddress.collapse_addresses(ipv6_nets))


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
