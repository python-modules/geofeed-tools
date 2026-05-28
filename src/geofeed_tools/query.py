"""Geofeed query operations using longest-prefix matching."""

from __future__ import annotations

import csv
import ipaddress
from dataclasses import dataclass

from .logging import TRACE_LEVEL, logger
from .models import GeofeedRecord, QueryResult
from .parsing import iter_data_lines_with_raw, normalize_fields, parse_record

Network = ipaddress.IPv4Network | ipaddress.IPv6Network


@dataclass(frozen=True, slots=True)
class QueryEntry:
    """One parsed queryable geofeed record and its normalized network."""

    network: Network
    record: GeofeedRecord


@dataclass(slots=True)
class _RadixNode:
    """Binary radix tree node keyed by network address bits."""

    zero: _RadixNode | None = None
    one: _RadixNode | None = None
    entry_index: int | None = None


@dataclass(frozen=True, slots=True)
class QueryIndex:
    """Prefix index for efficient longest-prefix and subtree matching."""

    entries: tuple[QueryEntry, ...]
    ipv4_root: _RadixNode
    ipv6_root: _RadixNode

    @classmethod
    def from_items(
        cls,
        items: list[tuple[Network, GeofeedRecord]],
    ) -> QueryIndex:
        """Build a radix-backed query index from parsed network records."""
        ipv4_root = _RadixNode()
        ipv6_root = _RadixNode()
        entries: list[QueryEntry] = []

        for entry_index, (network, record) in enumerate(items):
            entries.append(QueryEntry(network=network, record=record))
            _insert_entry(
                ipv4_root if network.version == 4 else ipv6_root,
                network,
                entry_index,
            )

        return cls(
            entries=tuple(entries),
            ipv4_root=ipv4_root,
            ipv6_root=ipv6_root,
        )

    def __len__(self) -> int:
        """Return the number of indexed geofeed entries."""
        return len(self.entries)


def parse_query(query: str) -> Network:
    """Parse an IP or CIDR query into a network object."""
    return ipaddress.ip_network(query, strict=False)


def load_query_records(
    text: str,
) -> QueryIndex:
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

    index = QueryIndex.from_items(list(last_by_prefix.items()))
    logger.debug(
        "Indexed geofeed records for querying: records=%d skipped_csv_errors=%d skipped_missing_prefix=%d skipped_invalid_prefix=%d",
        len(index),
        skipped_csv_errors,
        skipped_missing_prefix,
        skipped_invalid_prefix,
    )
    return index


def filter_query_index(
    index: QueryIndex,
    *,
    start: ipaddress.IPv4Address | ipaddress.IPv6Address | None,
    end: ipaddress.IPv4Address | ipaddress.IPv6Address | None,
) -> QueryIndex:
    """Return a new query index limited to a referring RDAP address range."""
    if start is None or end is None:
        return index

    start_value = int(start)
    end_value = int(end)
    filtered = [
        (entry.network, entry.record)
        for entry in index.entries
        if entry.network.version == start.version
        and int(entry.network.network_address) >= start_value
        and int(entry.network.broadcast_address) <= end_value
    ]
    return QueryIndex.from_items(filtered)


def find_matches(
    records: QueryIndex,
    query_network: Network,
    *,
    include_longer: bool = False,
    return_all: bool = True,
) -> list[GeofeedRecord]:
    """Find matching geofeed records for a parsed query network."""
    node, ancestor_indices = _walk_query_path(records, query_network)

    if not return_all:
        best_index = _best_match_index(records, ancestor_indices)
        if include_longer and node is not None:
            descendant_indices: list[int] = []
            _collect_descendant_indices(node, descendant_indices)
            longer_best_index = _best_match_index(records, descendant_indices)
            best_index = _prefer_more_specific(records, best_index, longer_best_index)

        if best_index is None:
            return []
        return [records.entries[best_index].record]

    match_indices = list(ancestor_indices)
    if include_longer and node is not None:
        _collect_descendant_indices(node, match_indices)

    return [records.entries[index].record for index in _sorted_unique_indices(records, match_indices)]


def _insert_entry(
    root: _RadixNode,
    network: Network,
    entry_index: int,
) -> None:
    """Insert one network into the radix tree."""
    node = root
    address_value = int(network.network_address)
    max_prefixlen = network.max_prefixlen

    for depth in range(network.prefixlen):
        bit = (address_value >> (max_prefixlen - depth - 1)) & 1
        if bit == 0:
            if node.zero is None:
                node.zero = _RadixNode()
            node = node.zero
        else:
            if node.one is None:
                node.one = _RadixNode()
            node = node.one

    node.entry_index = entry_index


def _walk_query_path(
    index: QueryIndex,
    query_network: Network,
) -> tuple[_RadixNode | None, list[int]]:
    """Walk the query bits and collect all covering prefixes on the path."""
    node = index.ipv4_root if query_network.version == 4 else index.ipv6_root
    indices: list[int] = []
    if node.entry_index is not None:
        indices.append(node.entry_index)

    address_value = int(query_network.network_address)
    max_prefixlen = query_network.max_prefixlen

    for depth in range(query_network.prefixlen):
        bit = (address_value >> (max_prefixlen - depth - 1)) & 1
        next_node = node.zero if bit == 0 else node.one
        if next_node is None:
            return None, indices
        node = next_node
        if node.entry_index is not None:
            indices.append(node.entry_index)

    return node, indices


def _collect_descendant_indices(
    node: _RadixNode,
    indices: list[int],
) -> None:
    """Collect every record stored in a radix subtree."""
    stack = [node]
    while stack:
        current = stack.pop()
        if current.entry_index is not None:
            indices.append(current.entry_index)
        if current.one is not None:
            stack.append(current.one)
        if current.zero is not None:
            stack.append(current.zero)


def _best_match_index(
    index: QueryIndex,
    indices: list[int],
) -> int | None:
    """Return the most specific match, preferring earlier source order on ties."""
    best_index: int | None = None
    for candidate_index in indices:
        best_index = _prefer_more_specific(index, best_index, candidate_index)
    return best_index


def _prefer_more_specific(
    index: QueryIndex,
    left: int | None,
    right: int | None,
) -> int | None:
    """Choose the more specific candidate, preferring stable source order on ties."""
    if left is None:
        return right
    if right is None:
        return left

    left_prefixlen = index.entries[left].network.prefixlen
    right_prefixlen = index.entries[right].network.prefixlen
    if right_prefixlen > left_prefixlen:
        return right
    if right_prefixlen == left_prefixlen and right < left:
        return right
    return left


def _sorted_unique_indices(
    index: QueryIndex,
    indices: list[int],
) -> list[int]:
    """Sort unique match indices by specificity while preserving source order ties."""
    return sorted(
        set(indices),
        key=lambda entry_index: (
            -index.entries[entry_index].network.prefixlen,
            entry_index,
        ),
    )


def query_text(
    text: str,
    query: str,
    *,
    return_all: bool = False,
    include_longer: bool = False,
    indexed_records: QueryIndex | None = None,
) -> QueryResult:
    """Query a geofeed text payload and return matching records."""
    query_network = parse_query(query)
    records = indexed_records if indexed_records is not None else load_query_records(text)
    matches = find_matches(
        records,
        query_network,
        include_longer=include_longer,
        return_all=return_all,
    )
    logger.debug(
        "Resolved geofeed query: query=%s indexed_records=%d matches=%d include_longer=%s return_all=%s",
        query,
        len(records),
        len(matches),
        include_longer,
        return_all,
    )
    return QueryResult(query=query, matches=tuple(matches))
