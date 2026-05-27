"""Reusable RDAP lookup helpers for geofeed discovery and future features."""

from __future__ import annotations

import ipaddress
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass

from .loader import ASYNC_HTTP_ERROR, FETCH_TIMEOUT, USER_AGENT, FetchError
from .logging import logger
from .models import DoctorLookup
from .query import Network, parse_query

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
BootstrapIndex = list[tuple[Network, tuple[str, ...]]]

RDAP_ACCEPT = "application/rdap+json, application/json, */*"
JSON_ACCEPT = "application/json, */*"
RDAP_ORG_METHOD = "rdap.org"
IANA_BOOTSTRAP_METHOD = "iana-bootstrap"
RDAP_LOOKUP_METHODS = (RDAP_ORG_METHOD, IANA_BOOTSTRAP_METHOD)
RDAP_ORG_ROOT_URL = "https://rdap.org/"
RDAP_ORG_QUERY_TEMPLATE = "https://rdap.org/ip/{}"
IANA_BOOTSTRAP_URLS = {
    4: "https://data.iana.org/rdap/ipv4.json",
    6: "https://data.iana.org/rdap/ipv6.json",
}
MAX_RDAP_DEPTH = 8
LINK_GEOFEED_SOURCE = "rdap link rel=geofeed"
GEOFEED_URL_RE = re.compile(
    r"geofeed(?:\s*:)?\s*(https?://\S+)",
    re.IGNORECASE,
)

_bootstrap_index_cache: dict[int, BootstrapIndex] = {}


@dataclass(frozen=True)
class ResolvedRdapLookup:
    """Resolved doctor lookup metadata including RDAP range bounds."""

    lookup: DoctorLookup
    range_start: IPAddress | None
    range_end: IPAddress | None


def _string(value: object) -> str | None:
    """Return a string value when present."""
    return value if isinstance(value, str) else None


def _mapping_items(value: object) -> list[Mapping[str, object]]:
    """Return only mapping items from a list-like object."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_items(value: object) -> list[str]:
    """Return only string items from a list-like object."""
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, str)]


def _string_lines(value: object) -> list[str]:
    """Return only string lines from a list-like object."""
    return _string_items(value)


def validate_rdap_method(rdap_method: str) -> None:
    """Validate that an RDAP lookup method is supported."""
    if rdap_method not in RDAP_LOOKUP_METHODS:
        supported = ", ".join(RDAP_LOOKUP_METHODS)
        raise ValueError(f"rdap_method must be one of: {supported}")


def normalize_rdap_target(query: str) -> tuple[Network, str, str]:
    """Normalize doctor input and choose the RDAP lookup address."""
    query_network = parse_query(query)
    if "/" in query:
        return (
            query_network,
            "prefix-network-address",
            str(query_network.network_address),
        )
    return query_network, "ip-address", str(ipaddress.ip_address(query))


def _build_rdap_org_query_url(address: str) -> str:
    """Build the rdap.org lookup URL for a single IP address."""
    quoted_address = urllib.parse.quote(address, safe=":")
    return RDAP_ORG_QUERY_TEMPLATE.format(quoted_address)


def _build_registry_query_url(base_url: str, address: str) -> str:
    """Build a registry-specific RDAP query URL for a single IP address."""
    normalized_base = base_url if base_url.endswith("/") else f"{base_url}/"
    quoted_address = urllib.parse.quote(address, safe=":")
    return urllib.parse.urljoin(normalized_base, f"ip/{quoted_address}")


def _fetch_json_urllib(
    url: str,
    *,
    accept: str = JSON_ACCEPT,
) -> tuple[dict[str, object], str]:
    """Fetch a JSON document using urllib."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": accept,
    }
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(
            request,
            timeout=FETCH_TIMEOUT,
        ) as response:
            payload = response.read()
            resolved_url = response.geturl()
            status_code = response.status
    except urllib.error.HTTPError as exc:
        raise FetchError(url, status_code=exc.code, reason=exc.reason) from exc
    except urllib.error.URLError as exc:
        raise FetchError(
            url,
            status_code=None,
            reason=str(exc.reason),
        ) from exc

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise FetchError(
            resolved_url,
            status_code=status_code,
            reason=f"Invalid JSON response: {exc.msg}",
        ) from exc

    if not isinstance(data, dict):
        raise FetchError(
            resolved_url,
            status_code=status_code,
            reason="Invalid JSON response: expected an object",
        )
    return data, resolved_url


async def _fetch_json_httpx(
    url: str,
    *,
    accept: str = JSON_ACCEPT,
) -> tuple[dict[str, object], str]:
    """Fetch a JSON document asynchronously using httpx."""
    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError(ASYNC_HTTP_ERROR) from exc

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": accept,
    }
    try:
        async with httpx.AsyncClient(
            headers=headers,
            timeout=FETCH_TIMEOUT,
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            resolved_url = str(response.url)
            try:
                data = response.json()
            except ValueError as exc:
                raise FetchError(
                    resolved_url,
                    status_code=response.status_code,
                    reason=f"Invalid JSON response: {exc}",
                ) from exc
    except httpx.HTTPStatusError as exc:
        raise FetchError(
            url,
            status_code=exc.response.status_code,
            reason=exc.response.reason_phrase,
        ) from exc
    except httpx.RequestError as exc:
        raise FetchError(url, status_code=None, reason=str(exc)) from exc

    if not isinstance(data, dict):
        raise FetchError(
            resolved_url,
            status_code=response.status_code,
            reason="Invalid JSON response: expected an object",
        )
    return data, resolved_url


def _select_registry_base_url(base_urls: tuple[str, ...]) -> str:
    """Choose the preferred RDAP base URL for a bootstrap entry."""
    for base_url in base_urls:
        if base_url.startswith("https://"):
            return base_url
    return base_urls[0]


def _parse_bootstrap_index(
    payload: Mapping[str, object],
    *,
    source_url: str,
) -> BootstrapIndex:
    """Parse an IANA RDAP bootstrap payload into queryable entries."""
    services = payload.get("services")
    if not isinstance(services, list):
        raise FetchError(
            source_url,
            status_code=None,
            reason="Invalid IANA RDAP bootstrap payload: missing services",
        )

    index: BootstrapIndex = []
    for service in services:
        if not isinstance(service, list) or len(service) < 2:
            continue
        prefixes = _string_items(service[0])
        base_urls = tuple(_string_items(service[1]))
        if not prefixes or not base_urls:
            continue
        for prefix_text in prefixes:
            try:
                network = ipaddress.ip_network(prefix_text, strict=True)
            except ValueError:
                logger.warning(
                    "Skipping invalid IANA RDAP bootstrap prefix: "
                    "source=%s prefix=%r",
                    source_url,
                    prefix_text,
                )
                continue
            index.append((network, base_urls))

    if not index:
        raise FetchError(
            source_url,
            status_code=None,
            reason="Invalid IANA RDAP bootstrap payload: no services",
        )
    index.sort(key=lambda item: item[0].prefixlen, reverse=True)
    return index


def _get_bootstrap_index_urllib(version: int) -> BootstrapIndex:
    """Load and cache the IANA RDAP bootstrap index synchronously."""
    cached = _bootstrap_index_cache.get(version)
    if cached is not None:
        return cached

    source_url = IANA_BOOTSTRAP_URLS[version]
    payload, _resolved_url = _fetch_json_urllib(source_url)
    index = _parse_bootstrap_index(payload, source_url=source_url)
    _bootstrap_index_cache[version] = index
    return index


async def _get_bootstrap_index_httpx(version: int) -> BootstrapIndex:
    """Load and cache the IANA RDAP bootstrap index asynchronously."""
    cached = _bootstrap_index_cache.get(version)
    if cached is not None:
        return cached

    source_url = IANA_BOOTSTRAP_URLS[version]
    payload, _resolved_url = await _fetch_json_httpx(source_url)
    index = _parse_bootstrap_index(payload, source_url=source_url)
    _bootstrap_index_cache[version] = index
    return index


def clear_bootstrap_cache() -> None:
    """Clear cached IANA bootstrap data."""
    _bootstrap_index_cache.clear()


def _bootstrap_query_url_from_iana(address: str) -> tuple[str, str]:
    """Resolve a registry query URL from IANA bootstrap data."""
    ip_address = ipaddress.ip_address(address)
    index = _get_bootstrap_index_urllib(ip_address.version)
    for network, base_urls in index:
        if ip_address in network:
            base_url = _select_registry_base_url(base_urls)
            return (
                _build_registry_query_url(base_url, address),
                IANA_BOOTSTRAP_URLS[ip_address.version],
            )
    raise FetchError(
        IANA_BOOTSTRAP_URLS[ip_address.version],
        status_code=None,
        reason=f"No IANA RDAP service matched {address}",
    )


async def _bootstrap_query_url_from_iana_async(
    address: str,
) -> tuple[str, str]:
    """Resolve a registry query URL from IANA bootstrap data asynchronously."""
    ip_address = ipaddress.ip_address(address)
    index = await _get_bootstrap_index_httpx(ip_address.version)
    for network, base_urls in index:
        if ip_address in network:
            base_url = _select_registry_base_url(base_urls)
            return (
                _build_registry_query_url(base_url, address),
                IANA_BOOTSTRAP_URLS[ip_address.version],
            )
    raise FetchError(
        IANA_BOOTSTRAP_URLS[ip_address.version],
        status_code=None,
        reason=f"No IANA RDAP service matched {address}",
    )


def initial_rdap_query_url(
    address: str,
    *,
    rdap_method: str,
) -> tuple[str, str | None]:
    """Resolve the initial RDAP query URL for a configured lookup method."""
    validate_rdap_method(rdap_method)
    if rdap_method == RDAP_ORG_METHOD:
        return _build_rdap_org_query_url(address), RDAP_ORG_ROOT_URL
    return _bootstrap_query_url_from_iana(address)


async def initial_rdap_query_url_async(
    address: str,
    *,
    rdap_method: str,
) -> tuple[str, str | None]:
    """Resolve the initial async RDAP query URL for a method."""
    validate_rdap_method(rdap_method)
    if rdap_method == RDAP_ORG_METHOD:
        return _build_rdap_org_query_url(address), RDAP_ORG_ROOT_URL
    return await _bootstrap_query_url_from_iana_async(address)


def _clean_url(url: str) -> str:
    """Trim punctuation that may trail URLs in free-form remark text."""
    return url.rstrip(".,);]'\"")


def _link_geofeed_candidates(
    payload: Mapping[str, object],
) -> list[tuple[str, str]]:
    """Collect direct geofeed link candidates from an RDAP object."""
    candidates: list[tuple[str, str]] = []

    for link in _mapping_items(payload.get("links")):
        href = _string(link.get("href"))
        relation = _string(link.get("rel"))
        content_type = _string(link.get("type"))
        relation_tokens = (
            set(relation.split()) if relation is not None else set()
        )
        if href is None:
            continue
        if (
            "geofeed" in relation_tokens
            or content_type == "application/geofeed+csv"
        ):
            candidates.append((_clean_url(href), LINK_GEOFEED_SOURCE))

    return candidates


def _remarks_geofeed_candidates(
    payload: Mapping[str, object],
) -> list[tuple[str, str]]:
    """Collect geofeed URL candidates from RDAP remarks-like fields."""
    candidates: list[tuple[str, str]] = []

    for field_name in ("remarks", "comments"):
        for entry in _mapping_items(payload.get(field_name)):
            description = "\n".join(_string_lines(entry.get("description")))
            if not description:
                continue
            for match in GEOFEED_URL_RE.finditer(description):
                candidates.append(
                    (
                        _clean_url(match.group(1)),
                        f"rdap {field_name} geofeed url",
                    )
                )

    return candidates


def _extract_geofeed_reference(
    payload: Mapping[str, object],
) -> tuple[str | None, str | None]:
    """Extract a single geofeed reference from an RDAP object."""
    candidates = _link_geofeed_candidates(payload)
    candidates.extend(_remarks_geofeed_candidates(payload))

    geofeed_url: str | None = None
    geofeed_source: str | None = None

    if candidates:
        unique_urls: dict[str, list[str]] = {}
        for url, source in candidates:
            unique_urls.setdefault(url, []).append(source)

        if len(unique_urls) == 1:
            geofeed_url, sources = next(iter(unique_urls.items()))
            if LINK_GEOFEED_SOURCE in sources:
                geofeed_source = LINK_GEOFEED_SOURCE
            else:
                geofeed_source = sources[0]
        else:
            logger.warning(
                "Ignoring RDAP object with multiple geofeed references: "
                "candidates=%s",
                sorted(unique_urls),
            )

    return geofeed_url, geofeed_source


def _extract_parent_url(
    payload: Mapping[str, object],
    current_url: str,
) -> str | None:
    """Return the nearest RDAP parent URL, when present."""
    for link in _mapping_items(payload.get("links")):
        href = _string(link.get("href"))
        relation = _string(link.get("rel"))
        if href is None or relation is None:
            continue
        relation_tokens = set(relation.split())
        if "rdap-up" in relation_tokens or "up" in relation_tokens:
            return urllib.parse.urljoin(current_url, href)
    return None


def _extract_range(
    payload: Mapping[str, object],
) -> tuple[IPAddress | None, IPAddress | None, str | None]:
    """Extract start and end addresses from an RDAP object."""
    start_text = _string(payload.get("startAddress"))
    end_text = _string(payload.get("endAddress"))
    start: IPAddress | None = None
    end: IPAddress | None = None
    range_text: str | None = None

    if start_text is not None and end_text is not None:
        try:
            parsed_start = ipaddress.ip_address(start_text)
            parsed_end = ipaddress.ip_address(end_text)
        except ValueError:
            parsed_start = None
            parsed_end = None

        if (
            parsed_start is not None
            and parsed_end is not None
            and parsed_start.version == parsed_end.version
            and int(parsed_start) <= int(parsed_end)
        ):
            start = parsed_start
            end = parsed_end
            if start == end:
                range_text = str(start)
            else:
                range_text = f"{start} - {end}"

    return start, end, range_text


def resolve_geofeed_lookup(
    query: str,
    *,
    rdap_method: str = RDAP_ORG_METHOD,
) -> ResolvedRdapLookup:
    """Resolve geofeed discovery metadata for a query using RDAP."""
    _query_network, lookup_strategy, rdap_query = normalize_rdap_target(query)
    bootstrap_url, bootstrap_source_url = initial_rdap_query_url(
        rdap_query,
        rdap_method=rdap_method,
    )
    resolved_urls: list[str] = []
    seen_urls: set[str] = set()
    current_url: str | None = bootstrap_url

    default_handle: str | None = None
    default_range: str | None = None
    default_start: IPAddress | None = None
    default_end: IPAddress | None = None

    geofeed_url: str | None = None
    geofeed_discovered_via: str | None = None
    geofeed_reference_url: str | None = None
    referring_handle: str | None = None
    referring_range: str | None = None
    range_start: IPAddress | None = None
    range_end: IPAddress | None = None

    while current_url is not None and len(resolved_urls) < MAX_RDAP_DEPTH:
        if current_url in seen_urls:
            break
        seen_urls.add(current_url)

        payload, resolved_url = _fetch_json_urllib(
            current_url,
            accept=RDAP_ACCEPT,
        )
        if resolved_url not in seen_urls:
            seen_urls.add(resolved_url)
        if resolved_url not in resolved_urls:
            resolved_urls.append(resolved_url)

        handle = _string(payload.get("handle"))
        start, end, range_text = _extract_range(payload)
        if len(resolved_urls) == 1:
            default_handle = handle
            default_range = range_text
            default_start = start
            default_end = end

        current_geofeed_url, current_geofeed_via = _extract_geofeed_reference(
            payload,
        )
        if current_geofeed_url is not None:
            geofeed_url = current_geofeed_url
            geofeed_discovered_via = current_geofeed_via
            geofeed_reference_url = resolved_url
            referring_handle = handle
            referring_range = range_text
            range_start = start
            range_end = end
            break

        current_url = _extract_parent_url(payload, resolved_url)

    if geofeed_url is None:
        referring_handle = default_handle
        referring_range = default_range
        range_start = default_start
        range_end = default_end

    lookup = DoctorLookup(
        lookup_strategy=lookup_strategy,
        rdap_method=rdap_method,
        rdap_query=rdap_query,
        bootstrap_url=bootstrap_url,
        bootstrap_source_url=bootstrap_source_url,
        resolved_urls=tuple(resolved_urls),
        referring_handle=referring_handle,
        referring_range=referring_range,
        geofeed_url=geofeed_url,
        geofeed_discovered_via=geofeed_discovered_via,
        geofeed_reference_url=geofeed_reference_url,
    )
    return ResolvedRdapLookup(
        lookup=lookup,
        range_start=range_start,
        range_end=range_end,
    )


async def resolve_geofeed_lookup_async(
    query: str,
    *,
    rdap_method: str = RDAP_ORG_METHOD,
) -> ResolvedRdapLookup:
    """Resolve geofeed discovery metadata for a query asynchronously."""
    _query_network, lookup_strategy, rdap_query = normalize_rdap_target(query)
    bootstrap_url, bootstrap_source_url = await initial_rdap_query_url_async(
        rdap_query,
        rdap_method=rdap_method,
    )
    resolved_urls: list[str] = []
    seen_urls: set[str] = set()
    current_url: str | None = bootstrap_url

    default_handle: str | None = None
    default_range: str | None = None
    default_start: IPAddress | None = None
    default_end: IPAddress | None = None

    geofeed_url: str | None = None
    geofeed_discovered_via: str | None = None
    geofeed_reference_url: str | None = None
    referring_handle: str | None = None
    referring_range: str | None = None
    range_start: IPAddress | None = None
    range_end: IPAddress | None = None

    while current_url is not None and len(resolved_urls) < MAX_RDAP_DEPTH:
        if current_url in seen_urls:
            break
        seen_urls.add(current_url)

        payload, resolved_url = await _fetch_json_httpx(
            current_url,
            accept=RDAP_ACCEPT,
        )
        if resolved_url not in seen_urls:
            seen_urls.add(resolved_url)
        if resolved_url not in resolved_urls:
            resolved_urls.append(resolved_url)

        handle = _string(payload.get("handle"))
        start, end, range_text = _extract_range(payload)
        if len(resolved_urls) == 1:
            default_handle = handle
            default_range = range_text
            default_start = start
            default_end = end

        current_geofeed_url, current_geofeed_via = _extract_geofeed_reference(
            payload,
        )
        if current_geofeed_url is not None:
            geofeed_url = current_geofeed_url
            geofeed_discovered_via = current_geofeed_via
            geofeed_reference_url = resolved_url
            referring_handle = handle
            referring_range = range_text
            range_start = start
            range_end = end
            break

        current_url = _extract_parent_url(payload, resolved_url)

    if geofeed_url is None:
        referring_handle = default_handle
        referring_range = default_range
        range_start = default_start
        range_end = default_end

    lookup = DoctorLookup(
        lookup_strategy=lookup_strategy,
        rdap_method=rdap_method,
        rdap_query=rdap_query,
        bootstrap_url=bootstrap_url,
        bootstrap_source_url=bootstrap_source_url,
        resolved_urls=tuple(resolved_urls),
        referring_handle=referring_handle,
        referring_range=referring_range,
        geofeed_url=geofeed_url,
        geofeed_discovered_via=geofeed_discovered_via,
        geofeed_reference_url=geofeed_reference_url,
    )
    return ResolvedRdapLookup(
        lookup=lookup,
        range_start=range_start,
        range_end=range_end,
    )


__all__ = [
    "IANA_BOOTSTRAP_METHOD",
    "RDAP_LOOKUP_METHODS",
    "RDAP_ORG_METHOD",
    "ResolvedRdapLookup",
    "clear_bootstrap_cache",
    "resolve_geofeed_lookup",
    "resolve_geofeed_lookup_async",
    "validate_rdap_method",
]
