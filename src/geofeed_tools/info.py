"""Geofeed information and statistics helpers."""

from __future__ import annotations

import ipaddress

from .models import GeoFeedInfo, GeofeedRecord, ValidationReport


def build_info(
    source: str,
    records: list[GeofeedRecord],
    report: ValidationReport | None = None,
) -> GeoFeedInfo:
    """Build aggregate geofeed statistics from records and validation."""

    unique_prefixes = {record.prefix for record in records}

    ipv4 = 0
    ipv6 = 0
    countries = set()
    regions = set()
    cities = set()
    postals = set()

    for record in records:
        network = ipaddress.ip_network(record.prefix, strict=False)
        if network.version == 4:
            ipv4 += 1
        else:
            ipv6 += 1

        if record.country:
            countries.add(record.country)
        if record.region:
            regions.add(record.region)
        if record.city:
            cities.add(record.city)
        if record.postal_code:
            postals.add(record.postal_code)

    duplicate_count = len(records) - len(unique_prefixes)

    errors = report.errors if report is not None else 0
    warnings = report.warnings if report is not None else 0

    return GeoFeedInfo(
        source=source,
        total_records=len(records),
        unique_prefixes=len(unique_prefixes),
        ipv4_records=ipv4,
        ipv6_records=ipv6,
        unique_countries=len(countries),
        unique_regions=len(regions),
        unique_cities=len(cities),
        unique_postal_codes=len(postals),
        duplicates=duplicate_count,
        errors=errors,
        warnings=warnings,
    )
