"""Geofeed query operations using longest-prefix matching."""

from __future__ import annotations

import csv
import ipaddress

from .logging import TRACE_LEVEL, logger
from .models import GeofeedRecord, QueryResult
from .parsing import iter_data_lines_with_raw, normalize_fields, parse_record

Network = ipaddress.IPv4Network | ipaddress.IPv6Network


def parse_query(query: str) -> Network:
    """Parse an IP or CIDR query into a network object."""
    return ipaddress.ip_network(query, strict=False)


def load_query_records(
    text: str,
) -> list[tuple[Network, GeofeedRecord]]:
    """Load queryable records and keep last occurrence per prefix."""
    last_by_prefix: dict[Network, GeofeedRecord] = {}
    skipped_csv_errors = 0
    skipped_missing_prefix = 0
    skipped_invalid_prefix = 0

    for lineno, raw_line, data in iter_data_lines_with_raw(text):
        try:
            fields = parse_record(data)
        except csv.Error as exc:
            skipped_csv_errors += 1
            logger.log(
                TRACE_LEVEL,
                "Skipping geofeed line during query indexing due to CSV error: line=%d error=%s",
                lineno,
                exc,
            )
            continue

        prefix, country, region, city, postal = normalize_fields(fields)
        if not prefix:
            skipped_missing_prefix += 1
            logger.log(
                TRACE_LEVEL,
                "Skipping geofeed line during query indexing due to missing prefix: line=%d",
                lineno,
            )
            continue

        try:
            network = ipaddress.ip_network(prefix, strict=True)
        except ValueError as exc:
            skipped_invalid_prefix += 1
            logger.log(
                TRACE_LEVEL,
                "Skipping geofeed line during query indexing due to invalid prefix: line=%d prefix=%r error=%s",
                lineno,
                prefix,
                exc,
            )
            continue

        last_by_prefix[network] = GeofeedRecord(
            prefix=str(network),
            country=country,
            region=region,
            city=city,
            postal_code=postal,
            line=lineno,
            raw_line=raw_line,
        )

    records = [(network, record) for network, record in last_by_prefix.items()]
    logger.debug(
        "Indexed geofeed records for querying: records=%d skipped_csv_errors=%d skipped_missing_prefix=%d skipped_invalid_prefix=%d",
        len(records),
        skipped_csv_errors,
        skipped_missing_prefix,
        skipped_invalid_prefix,
    )
    return records


def find_matches(
    records: list[tuple[Network, GeofeedRecord]],
    query_network: Network,
    *,
    include_longer: bool = False,
    return_all: bool = True,
) -> list[GeofeedRecord]:
    """Find matching geofeed records for a parsed query network."""
    if not return_all:
        best_match: GeofeedRecord | None = None
        best_prefixlen = -1

        for network, record in records:
            if _network_version(network) != _network_version(query_network):
                continue
            if _network_subnet_of(query_network, network) or (
                include_longer and _network_subnet_of(network, query_network)
            ):
                prefixlen = network.prefixlen
                if prefixlen > best_prefixlen:
                    best_prefixlen = prefixlen
                    best_match = record

        return [best_match] if best_match is not None else []

    matches: list[tuple[Network, GeofeedRecord]] = []

    for network, record in records:
        if _network_version(network) != _network_version(query_network):
            continue
        if _network_subnet_of(query_network, network) or (
            include_longer and _network_subnet_of(network, query_network)
        ):
            matches.append((network, record))

    matches.sort(key=lambda item: -item[0].prefixlen)
    return [record for _network, record in matches]


def _network_version(network: Network) -> int:
    """Return network IP version as integer."""
    return 4 if isinstance(network, ipaddress.IPv4Network) else 6


def _network_subnet_of(candidate: Network, container: Network) -> bool:
    """Check subnet relation while preserving family typing."""
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


def query_text(
    text: str,
    query: str,
    *,
    return_all: bool = False,
    include_longer: bool = False,
) -> QueryResult:
    """Query a geofeed text payload and return matching records."""
    query_network = parse_query(query)
    records = load_query_records(text)
    matches = find_matches(
        records,
        query_network,
        include_longer=include_longer,
        return_all=return_all,
    )
    original_match_count = len(matches)
    logger.debug(
        "Resolved geofeed query: query=%s indexed_records=%d matches=%d returned=%d include_longer=%s return_all=%s",
        query,
        len(records),
        original_match_count,
        len(matches),
        include_longer,
        return_all,
    )
    return QueryResult(query=query, matches=tuple(matches))
