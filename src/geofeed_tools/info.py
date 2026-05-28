"""Detailed geofeed info builder.

Computes per-version prefix/address counts, geography uniques, per-country
breakdowns, prefix-length histograms, top regions/cities, and a preview of how
a default ``normalize()`` pass would shrink the feed.
"""

from __future__ import annotations

import collections
import ipaddress
from typing import cast

from ._net_utils import Network, collapse_same_version
from .logging import logger
from .models import (
    CountryStatistics,
    GeoFeedInfo,
    GeofeedRecord,
    NormalizationPreview,
    ValidationReport,
)

DEFAULT_TOP_N = 20

# Conversion factors from raw address space to /24 (IPv4) and /48 (IPv6) units.
_V4_SLASH_24_SIZE = 1 << 8  # 256 addresses per /24
_V6_SLASH_48_SIZE = 1 << 80  # 2**80 addresses per /48


def build_info(
    source: str,
    records: list[GeofeedRecord],
    networks: list[Network | None] | None = None,
    report: ValidationReport | None = None,
    *,
    top_n: int = DEFAULT_TOP_N,
) -> GeoFeedInfo:
    """Build a detailed GeoFeedInfo from parsed records and optional validation.

    Pass ``networks`` (the second value from ``parse_text_with_networks``) to
    enable the ``normalized`` preview and to skip the per-record CIDR re-parse.
    """
    logger.debug(
        "Building geofeed info: source=%s records=%d top_n=%d normalize_preview=%s",
        source,
        len(records),
        top_n,
        networks is not None,
    )

    have_networks = networks is not None
    if networks is None:
        networks = [None] * len(records)
    assert len(networks) == len(records)

    prefixes_v4 = 0
    prefixes_v6 = 0
    addresses_v4 = 0
    addresses_v6 = 0

    unique_prefixes: set[str] = set()
    countries: set[str] = set()
    regions: set[str] = set()
    cities: set[str] = set()
    postals: set[str] = set()

    country_v4_prefixes: collections.Counter[str] = collections.Counter()
    country_v6_prefixes: collections.Counter[str] = collections.Counter()
    country_v4_addresses: dict[str, int] = collections.defaultdict(int)
    country_v6_addresses: dict[str, int] = collections.defaultdict(int)

    length_v4: collections.Counter[int] = collections.Counter()
    length_v6: collections.Counter[int] = collections.Counter()

    region_counts: collections.Counter[str] = collections.Counter()
    city_counts: collections.Counter[str] = collections.Counter()

    for record, network in zip(records, networks, strict=True):
        if network is None:
            try:
                network = ipaddress.ip_network(record.prefix, strict=False)
            except ValueError:
                continue

        unique_prefixes.add(record.prefix)
        addresses = network.num_addresses
        country = record.country.upper() if record.country else ""

        if network.version == 4:
            prefixes_v4 += 1
            addresses_v4 += addresses
            length_v4[network.prefixlen] += 1
            if country:
                country_v4_prefixes[country] += 1
                country_v4_addresses[country] += addresses
        else:
            prefixes_v6 += 1
            addresses_v6 += addresses
            length_v6[network.prefixlen] += 1
            if country:
                country_v6_prefixes[country] += 1
                country_v6_addresses[country] += addresses

        if country:
            countries.add(country)
        if record.region:
            region_norm = record.region.upper()
            regions.add(region_norm)
            region_counts[region_norm] += 1
        if record.city:
            cities.add(record.city)
            city_counts[record.city] += 1
        if record.postal_code:
            postals.add(record.postal_code)

    by_country_keys = sorted(set(country_v4_prefixes) | set(country_v6_prefixes))
    by_country = tuple(
        sorted(
            (
                CountryStatistics(
                    country=country,
                    prefixes_v4=country_v4_prefixes.get(country, 0),
                    prefixes_v6=country_v6_prefixes.get(country, 0),
                    slash_24s=country_v4_addresses.get(country, 0) // _V4_SLASH_24_SIZE,
                    slash_48s=country_v6_addresses.get(country, 0) // _V6_SLASH_48_SIZE,
                )
                for country in by_country_keys
            ),
            key=lambda stats: (-stats.prefixes_total, stats.country),
        )
    )

    normalized_preview = _build_normalized_preview(records, networks) if have_networks else None

    info = GeoFeedInfo(
        source=source,
        prefixes_v4=prefixes_v4,
        prefixes_v6=prefixes_v6,
        unique_prefixes=len(unique_prefixes),
        duplicates=(prefixes_v4 + prefixes_v6) - len(unique_prefixes),
        slash_24s=addresses_v4 // _V4_SLASH_24_SIZE,
        slash_48s=addresses_v6 // _V6_SLASH_48_SIZE,
        unique_countries=len(countries),
        unique_regions=len(regions),
        unique_cities=len(cities),
        unique_postal_codes=len(postals),
        errors=report.errors if report is not None else 0,
        warnings=report.warnings if report is not None else 0,
        by_country=by_country,
        prefix_length_v4=tuple(sorted(length_v4.items())),
        prefix_length_v6=tuple(sorted(length_v6.items())),
        top_regions=tuple(region_counts.most_common(top_n)),
        top_cities=tuple(city_counts.most_common(top_n)),
        normalized=normalized_preview,
    )

    logger.debug(
        "Built geofeed info: source=%s prefixes=%d unique=%d countries=%d normalized=%s",
        source,
        info.prefixes_total,
        info.unique_prefixes,
        len(info.by_country),
        info.normalized.prefixes_total if info.normalized is not None else None,
    )
    return info


def _build_normalized_preview(
    records: list[GeofeedRecord],
    networks: list[Network | None],
) -> NormalizationPreview:
    """Compute the normalize preview from in-memory parse output.

    Mirrors the default ``normalize_records()`` behavior (uppercase + aggregate
    + dedupe + host-bit fix) without re-parsing the source text.
    """
    # Group unique networks by (version, uppercased country/region, city, postal)
    # to match the default aggregation key used by ``normalize_records``.
    by_key: dict[tuple[int, str, str, str, str], set[Network]] = collections.defaultdict(set)
    valid_only_count = 0
    for record, network in zip(records, networks, strict=True):
        if network is None:
            continue
        valid_only_count += 1
        country = record.country.upper() if record.country else ""
        region = record.region.upper() if record.region else ""
        key = (network.version, country, region, record.city, record.postal_code)
        by_key[key].add(network)

    aggregated_v4: list[ipaddress.IPv4Network] = []
    aggregated_v6: list[ipaddress.IPv6Network] = []
    for (version, _country, _region, _city, _postal), unique_networks in by_key.items():
        if version == 4:
            aggregated_v4.extend(
                collapse_same_version([cast(ipaddress.IPv4Network, n) for n in unique_networks])
            )
        else:
            aggregated_v6.extend(
                collapse_same_version([cast(ipaddress.IPv6Network, n) for n in unique_networks])
            )

    addresses_v4 = sum(n.num_addresses for n in aggregated_v4)
    addresses_v6 = sum(n.num_addresses for n in aggregated_v6)
    prefixes_v4 = len(aggregated_v4)
    prefixes_v6 = len(aggregated_v6)

    invalid_removed = max(0, len(records) - valid_only_count)
    aggregated = max(0, valid_only_count - (prefixes_v4 + prefixes_v6))

    return NormalizationPreview(
        prefixes_total=prefixes_v4 + prefixes_v6,
        prefixes_v4=prefixes_v4,
        prefixes_v6=prefixes_v6,
        slash_24s=addresses_v4 // _V4_SLASH_24_SIZE,
        slash_48s=addresses_v6 // _V6_SLASH_48_SIZE,
        invalid_removed=invalid_removed,
        aggregated=aggregated,
    )


__all__ = ["DEFAULT_TOP_N", "build_info"]
