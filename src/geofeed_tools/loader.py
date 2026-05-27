"""Source loading helpers for file and URL geofeeds."""

from __future__ import annotations

import asyncio
import urllib.error
import urllib.request
from importlib.metadata import version

from .logging import TRACE_LEVEL, logger

USER_AGENT = f"geofeed-tools/{version('geofeed-tools')}"
URL_SCHEMES = ("http://", "https://")
FETCH_TIMEOUT = 30
ASYNC_HTTP_ERROR = "Async HTTP support requires httpx. Install with: uv pip install 'geofeed-tools[async]'"


class FetchError(Exception):
    """Raised when URL loading fails."""

    def __init__(self, source: str, *, status_code: int | None, reason: str):
        """Initialize a fetch error with the originating source and cause."""
        self.source = source
        self.status_code = status_code
        self.reason = reason
        if status_code is None:
            message = f"Network error fetching {source}: {reason}"
        else:
            message = f"HTTP {status_code} fetching {source}: {reason}"
        super().__init__(message)


def is_url(source: str) -> bool:
    """Return True when a source string looks like an HTTP URL."""
    return source.startswith(URL_SCHEMES)


def load_input(source: str) -> tuple[bytes, str | None]:
    """Load raw bytes from a file path or HTTP(S) URL."""
    if is_url(source):
        return _fetch_urllib(source)

    logger.info("reading file: %s", source)
    data = _read_file_bytes(source)
    return data, None


async def load_input_async(source: str) -> tuple[bytes, str | None]:
    """Load raw bytes asynchronously from a file path or HTTP(S) URL."""
    if is_url(source):
        return await _fetch_httpx(source)

    logger.info("reading file: %s", source)
    data = await asyncio.to_thread(_read_file_bytes, source)
    return data, None


def _read_file_bytes(source: str) -> bytes:
    with open(source, "rb") as handle:
        return handle.read()


def _fetch_urllib(source: str) -> tuple[bytes, str | None]:
    """Fetch content via urllib fallback."""
    logger.info("fetching %s via urllib", source)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/csv, */*"}
    request = urllib.request.Request(source, headers=headers)
    logger.log(
        TRACE_LEVEL,
        "prepared urllib request method=%s url=%s headers=%s timeout=%s",
        request.get_method(),
        source,
        headers,
        FETCH_TIMEOUT,
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=FETCH_TIMEOUT,
        ) as response:
            content_type = response.headers.get("Content-Type")
            logger.log(
                TRACE_LEVEL,
                "urllib response status=%s reason=%s content_type=%s",
                response.status,
                getattr(response, "reason", ""),
                content_type,
            )
            return response.read(), content_type
    except urllib.error.HTTPError as exc:
        raise FetchError(
            source,
            status_code=exc.code,
            reason=exc.reason,
        ) from exc
    except urllib.error.URLError as exc:
        raise FetchError(
            source,
            status_code=None,
            reason=str(exc.reason),
        ) from exc


async def _fetch_httpx(source: str) -> tuple[bytes, str | None]:
    """Fetch content asynchronously via httpx."""
    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError(ASYNC_HTTP_ERROR) from exc

    logger.info("fetching %s via httpx", source)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/csv, */*"}
    logger.log(
        TRACE_LEVEL,
        "prepared httpx request method=%s url=%s headers=%s timeout=%s",
        "GET",
        source,
        headers,
        FETCH_TIMEOUT,
    )
    try:
        async with httpx.AsyncClient(
            headers=headers,
            timeout=FETCH_TIMEOUT,
            follow_redirects=True,
        ) as client:
            response = await client.get(source)
            response.raise_for_status()
            content_type = response.headers.get("Content-Type")
            logger.log(
                TRACE_LEVEL,
                "httpx response status=%s reason=%s content_type=%s",
                response.status_code,
                response.reason_phrase,
                content_type,
            )
            return response.content, content_type
    except httpx.HTTPStatusError as exc:
        raise FetchError(
            source,
            status_code=exc.response.status_code,
            reason=exc.response.reason_phrase,
        ) from exc
    except httpx.RequestError as exc:
        raise FetchError(
            source,
            status_code=None,
            reason=str(exc),
        ) from exc


def decode_text(raw: bytes, *, strip_bom: bool = False) -> str:
    """Decode UTF-8 bytes and optionally strip UTF-8 BOM."""
    if raw.startswith(b"\xef\xbb\xbf") and strip_bom:
        raw = raw[3:]
    return raw.decode("utf-8")
