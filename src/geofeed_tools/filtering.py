"""Field- and prefix-based filtering for geofeed records."""

from __future__ import annotations

import ipaddress

from ._net_utils import Network, network_subnet_of
from .logging import logger
from .models import GeofeedRecord
from .parse import parse_text_with_networks


def parse_family(family: str | int | None) -> int | None:
    """Normalize ``family`` to ``4``, ``6``, or ``None``.

    Accepts ints (``4`` / ``6``) and strings (``"4"``, ``"6"``, ``"v4"``,
    ``"v6"``, ``"ipv4"``, ``"ipv6"`` — case-insensitive).
    """
    if family is None:
        return None
    if isinstance(family, int):
        if family in (4, 6):
            return family
        raise ValueError(f"family must be 4 or 6, got {family!r}")
    text = str(family).strip().lower()
    if text in ("4", "v4", "ipv4"):
        return 4
    if text in ("6", "v6", "ipv6"):
        return 6
    raise ValueError(f"family must be one of 4/6/v4/v6/ipv4/ipv6, got {family!r}")


def filter_records(
    text: str,
    *,
    prefix: str | None = None,
    country: str | None = None,
    region: str | None = None,
    city: str | None = None,
    postal_code: str | None = None,
    family: str | int | None = None,
    prefix_length: int | None = None,
    include_longer: bool = False,
) -> list[GeofeedRecord]:
    """Return records from ``text`` that match every supplied filter.

    Thin wrapper around :func:`filter_parsed` that parses ``text`` first; use
    :func:`filter_parsed` directly when the caller already has the parse output.
    """
    records, networks = parse_text_with_networks(text)
    return filter_parsed(
        records,
        networks,
        prefix=prefix,
        country=country,
        region=region,
        city=city,
        postal_code=postal_code,
        family=family,
        prefix_length=prefix_length,
        include_longer=include_longer,
    )


def filter_parsed(
    records: list[GeofeedRecord],
    networks: list[Network | None],
    *,
    prefix: str | None = None,
    country: str | None = None,
    region: str | None = None,
    city: str | None = None,
    postal_code: str | None = None,
    family: str | int | None = None,
    prefix_length: int | None = None,
    include_longer: bool = False,
) -> list[GeofeedRecord]:
    """Filter already-parsed records by one or more predicates (logical AND).

    With ``include_longer=False`` (default), ``prefix`` matches the exact
    network and ``prefix_length`` matches the exact length. With
    ``include_longer=True``, both filters also match more-specific entries —
    records contained by ``prefix`` and records with length >= ``prefix_length``.

    Country/region/city/postal-code comparisons are case-insensitive.
    """
    family_int = parse_family(family)
    prefix_net: Network | None = None
    if prefix is not None:
        prefix_net = ipaddress.ip_network(prefix, strict=False)

    country_norm = country.upper() if country else None
    region_norm = region.upper() if region else None
    city_norm = city.casefold() if city else None
    postal_norm = postal_code.casefold() if postal_code else None

    logger.debug(
        "Filtering geofeed records: prefix=%s country=%s region=%s city=%s postal_code=%s"
        " family=%s prefix_length=%s include_longer=%s",
        prefix,
        country,
        region,
        city,
        postal_code,
        family_int,
        prefix_length,
        include_longer,
    )

    out: list[GeofeedRecord] = []
    for record, network in zip(records, networks, strict=True):
        if network is None:
            continue
        if family_int is not None and network.version != family_int:
            continue
        if prefix_length is not None:
            if include_longer:
                if network.prefixlen < prefix_length:
                    continue
            elif network.prefixlen != prefix_length:
                continue
        if prefix_net is not None:
            if include_longer:
                if not network_subnet_of(network, prefix_net):
                    continue
            elif network != prefix_net:
                continue
        if country_norm is not None and record.country.upper() != country_norm:
            continue
        if region_norm is not None and record.region.upper() != region_norm:
            continue
        if city_norm is not None and record.city.casefold() != city_norm:
            continue
        if postal_norm is not None and record.postal_code.casefold() != postal_norm:
            continue
        out.append(record)

    logger.debug(
        "Filtered geofeed records: input=%d output=%d include_longer=%s",
        len(records),
        len(out),
        include_longer,
    )
    return out


__all__ = ["filter_parsed", "filter_records", "parse_family"]
