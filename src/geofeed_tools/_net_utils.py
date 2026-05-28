"""Shared helpers for IPv4/IPv6 network objects."""

from __future__ import annotations

import ipaddress
from typing import TypeVar

Network = ipaddress.IPv4Network | ipaddress.IPv6Network
NetworkV = TypeVar("NetworkV", ipaddress.IPv4Network, ipaddress.IPv6Network)


def network_version(network: Network) -> int:
    """Return network IP version as integer."""
    return 4 if isinstance(network, ipaddress.IPv4Network) else 6


def network_subnet_of(candidate: Network, container: Network) -> bool:
    """Check subnet relation while preserving type safety across families."""
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


def network_lt(left: Network, right: Network) -> bool:
    """Compare two same-family networks for ordering."""
    if isinstance(left, ipaddress.IPv4Network) and isinstance(
        right,
        ipaddress.IPv4Network,
    ):
        return left < right
    if isinstance(left, ipaddress.IPv6Network) and isinstance(
        right,
        ipaddress.IPv6Network,
    ):
        return left < right
    return False


def collapse_same_version(networks: list[NetworkV]) -> list[NetworkV]:
    """Collapse a same-version network list with stable typing."""
    if not networks:
        return []
    return list(ipaddress.collapse_addresses(networks))
