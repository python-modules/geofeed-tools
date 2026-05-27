"""Geofeed query operations using longest-prefix matching."""

from __future__ import annotations

import csv
import ipaddress

from .models import GeofeedRecord, QueryResult
from .parsing import iter_data_lines, normalize_fields, parse_record

Network = ipaddress.IPv4Network | ipaddress.IPv6Network


def parse_query(query: str) -> Network:
    """Parse an IP or CIDR query into a network object."""
    return ipaddress.ip_network(query, strict=False)


def load_query_records(
    text: str,
) -> list[tuple[Network, GeofeedRecord]]:
    """Load queryable records and keep last occurrence per prefix."""
    last_by_prefix: dict[Network, GeofeedRecord] = {}
    line_map = dict(enumerate(text.splitlines(), start=1))

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

        last_by_prefix[network] = GeofeedRecord(
            prefix=str(network),
            country=country,
            region=region,
            city=city,
            postal_code=postal,
            line=lineno,
            raw_line=line_map.get(lineno),
        )

    return [(network, record) for network, record in last_by_prefix.items()]


def find_matches(
    records: list[tuple[Network, GeofeedRecord]],
    query_network: Network,
    *,
    include_longer: bool = False,
) -> list[GeofeedRecord]:
    """Find matching geofeed records for a parsed query network."""
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
    )
    if not return_all:
        matches = matches[:1]
    return QueryResult(query=query, matches=tuple(matches))
