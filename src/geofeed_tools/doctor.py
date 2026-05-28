"""Geofeed doctor helpers built on reusable RDAP lookup logic."""

from __future__ import annotations

import asyncio
import ipaddress

from .config import DEFAULT_RDAP_METHOD
from .io_utils import records_to_csv
from .loader import decode_text, load_input, load_input_async
from .logging import logger
from .models import DoctorResult
from .query import QueryIndex, filter_query_index, load_query_records, query_text
from .rdap import (
    ResolvedRdapLookup,
    resolve_geofeed_lookup,
    resolve_geofeed_lookup_async,
)

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


def _filter_records_to_referring_range(
    records: QueryIndex,
    start: IPAddress | None,
    end: IPAddress | None,
) -> QueryIndex:
    """Keep only records fully covered by the referring RDAP object range."""
    return filter_query_index(records, start=start, end=end)


def _build_doctor_result_from_text(
    query: str,
    resolved: ResolvedRdapLookup,
    text: str,
    *,
    return_all: bool,
    include_longer: bool,
) -> DoctorResult:
    """Build a doctor result from decoded geofeed text and resolved RDAP metadata."""
    indexed_records = load_query_records(text)
    indexed_records = _filter_records_to_referring_range(
        indexed_records,
        resolved.range_start,
        resolved.range_end,
    )
    query_result = query_text(
        text,
        query,
        return_all=return_all,
        include_longer=include_longer,
        indexed_records=indexed_records,
    )
    return DoctorResult(
        query=query,
        lookup=resolved.lookup,
        matches=query_result.matches,
    )


def doctor_query(
    query: str,
    *,
    return_all: bool = False,
    include_longer: bool = False,
    rdap_method: str = DEFAULT_RDAP_METHOD,
) -> DoctorResult:
    """Discover and query a published geofeed for an IP or prefix."""
    logger.info("Running geofeed doctor lookup: query=%s", query)
    resolved = resolve_geofeed_lookup(query, rdap_method=rdap_method)

    if resolved.lookup.geofeed_url is None:
        logger.info(
            "Doctor lookup found no geofeed reference: query=%s",
            query,
        )
        return DoctorResult(query=query, lookup=resolved.lookup, matches=())

    raw, _content_type = load_input(resolved.lookup.geofeed_url)
    text = decode_text(raw, strip_bom=True)
    result = _build_doctor_result_from_text(
        query,
        resolved,
        text,
        return_all=return_all,
        include_longer=include_longer,
    )
    logger.info(
        "Doctor lookup completed: query=%s geofeed_url=%s matches=%d",
        query,
        resolved.lookup.geofeed_url,
        len(result.matches),
    )
    return result


async def doctor_query_async(
    query: str,
    *,
    return_all: bool = False,
    include_longer: bool = False,
    rdap_method: str = DEFAULT_RDAP_METHOD,
) -> DoctorResult:
    """Discover and query a published geofeed asynchronously."""
    logger.info("Running geofeed doctor lookup: query=%s", query)
    resolved = await resolve_geofeed_lookup_async(
        query,
        rdap_method=rdap_method,
    )

    if resolved.lookup.geofeed_url is None:
        logger.info(
            "Doctor lookup found no geofeed reference: query=%s",
            query,
        )
        return DoctorResult(query=query, lookup=resolved.lookup, matches=())

    raw, _content_type = await load_input_async(resolved.lookup.geofeed_url)
    text = decode_text(raw, strip_bom=True)
    result = await asyncio.to_thread(
        _build_doctor_result_from_text,
        query,
        resolved,
        text,
        return_all=return_all,
        include_longer=include_longer,
    )
    logger.info(
        "Doctor lookup completed: query=%s geofeed_url=%s matches=%d",
        query,
        resolved.lookup.geofeed_url,
        len(result.matches),
    )
    return result


def render_doctor_text(result: DoctorResult) -> str:
    """Render a human-readable doctor result."""
    lines = [
        f"Query: {result.query}",
        f"Lookup strategy: {result.lookup.lookup_strategy}",
        f"RDAP method: {result.lookup.rdap_method}",
        f"RDAP query: {result.lookup.rdap_query}",
        f"Initial RDAP URL: {result.lookup.bootstrap_url}",
    ]

    if result.lookup.bootstrap_source_url is not None:
        lines.append(f"Bootstrap source: {result.lookup.bootstrap_source_url}")

    if result.lookup.resolved_urls:
        lines.append("RDAP trace:")
        lines.extend(f"  - {url}" for url in result.lookup.resolved_urls)

    if result.lookup.referring_handle is not None:
        lines.append(f"Referring object: {result.lookup.referring_handle}")
    if result.lookup.referring_range is not None:
        lines.append(f"Referring range: {result.lookup.referring_range}")

    lines.append(f"Geofeed URL: {result.lookup.geofeed_url or 'not found'}")
    lines.append(f"Geofeed discovered via: {result.lookup.geofeed_discovered_via or 'not found'}")
    if result.lookup.geofeed_reference_url is not None:
        lines.append(f"Geofeed reference object: {result.lookup.geofeed_reference_url}")

    lines.append("")
    lines.append("Matches:")
    if result.matches:
        csv_output = records_to_csv(
            result.matches,
            include_validation=False,
        )
        lines.append(csv_output.rstrip("\n"))
    else:
        lines.append("(none)")
    return "\n".join(lines)


__all__ = [
    "doctor_query",
    "doctor_query_async",
    "render_doctor_text",
]
