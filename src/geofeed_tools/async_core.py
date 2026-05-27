"""Async geofeed API built on shared sync parsing and validation helpers."""

from __future__ import annotations

import asyncio

from .core import (
    _info_loaded,
    _normalize_loaded,
    _parse_loaded,
    _query_loaded,
    _validate_loaded,
)
from .loader import FetchError, decode_text, load_input_async
from .models import GeoFeedInfo, GeofeedRecord, QueryResult, ValidationReport


class AsyncGeoFeed:
    """Async-native geofeed API for library consumers."""

    def __init__(self, source: str):
        """Initialize an async geofeed wrapper around a local path or URL."""
        self.source = source
        self.raw: bytes | None = None
        self.content_type: str | None = None
        self.text: str | None = None

    @classmethod
    async def from_source(cls, source: str) -> AsyncGeoFeed:
        """Create an instance and eagerly load the source asynchronously."""
        geofeed = cls(source)
        await geofeed.reload()
        return geofeed

    async def reload(self) -> None:
        """Reload the source bytes and decoded text asynchronously."""
        raw, content_type = await load_input_async(self.source)
        self.raw = raw
        self.content_type = content_type
        self.text = decode_text(raw, strip_bom=True)

    async def _ensure_loaded(self) -> tuple[bytes, str]:
        if self.raw is None or self.text is None:
            await self.reload()
        assert self.raw is not None
        assert self.text is not None
        return self.raw, self.text

    async def parse(
        self,
        *,
        include_validation: bool = True,
        normalize: bool = False,
        output: str = "objects",
    ) -> list[GeofeedRecord] | str:
        """Parse the source asynchronously and optionally serialize the result."""
        raw, text = await self._ensure_loaded()
        return await asyncio.to_thread(
            _parse_loaded,
            self.source,
            raw,
            text,
            self.content_type,
            include_validation=include_validation,
            normalize=normalize,
            output=output,
        )

    async def validate(
        self,
        *,
        check_sort: bool = True,
        check_content_type: bool = True,
        check_aggregation: bool = False,
        output: str = "objects",
    ) -> ValidationReport | str:
        """Validate the source asynchronously and optionally serialize the report."""
        raw, _text = await self._ensure_loaded()
        return await asyncio.to_thread(
            _validate_loaded,
            self.source,
            raw,
            self.content_type,
            check_sort=check_sort,
            check_content_type=check_content_type,
            check_aggregation=check_aggregation,
            output=output,
        )

    async def normalize(
        self,
        *,
        uppercase: bool = True,
        sort: bool = True,
        aggregate: bool = True,
        dedupe: bool = True,
        fix_host_bits: bool = True,
        output: str = "objects",
    ) -> list[GeofeedRecord] | str:
        """Normalize records asynchronously and optionally serialize them."""
        _raw, text = await self._ensure_loaded()
        return await asyncio.to_thread(
            _normalize_loaded,
            text,
            uppercase=uppercase,
            sort=sort,
            aggregate=aggregate,
            dedupe=dedupe,
            fix_host_bits=fix_host_bits,
            output=output,
        )

    async def query(
        self,
        query: str,
        *,
        return_all: bool = False,
        include_longer: bool = False,
        output: str = "objects",
    ) -> QueryResult | str:
        """Query the source asynchronously for an IP or prefix."""
        _raw, text = await self._ensure_loaded()
        return await asyncio.to_thread(
            _query_loaded,
            text,
            query,
            return_all=return_all,
            include_longer=include_longer,
            output=output,
        )

    async def info(self, *, output: str = "objects") -> GeoFeedInfo | str:
        """Compute aggregate geofeed statistics asynchronously."""
        raw, text = await self._ensure_loaded()
        return await asyncio.to_thread(
            _info_loaded,
            self.source,
            raw,
            text,
            self.content_type,
            output=output,
        )


__all__ = ["AsyncGeoFeed", "FetchError"]
