"""Async geofeed API built on shared sync parsing and validation helpers."""

from __future__ import annotations

import asyncio

from .config import DEFAULT_RDAP_METHOD, TRACE_LEVEL
from .core import (
    _build_lookup_result,
    _GeoFeedBase,
    _serialize_doctor_result,
    _serialize_query_result,
)
from .doctor import doctor_query_async
from .loader import FetchError, load_input_async, source_kind
from .logging import logger
from .models import (
    DoctorResult,
    GeoFeedDiscoveryError,
    GeoFeedInfo,
    GeofeedRecord,
    QueryResult,
    ValidationReport,
)


class AsyncGeoFeed(_GeoFeedBase):
    """Async-native geofeed API for library consumers."""

    def __init__(self, source: str, *, cache_query_index: bool = True):
        """Initialize an async geofeed wrapper around a local path or URL."""
        super().__init__(source, cache_query_index=cache_query_index)

    @classmethod
    async def from_source(cls, source: str, *, cache_query_index: bool = True) -> AsyncGeoFeed:
        """Create an instance and eagerly load the source asynchronously."""
        logger.debug("Creating AsyncGeoFeed and eagerly loading source: %s", source)
        geofeed = cls(source, cache_query_index=cache_query_index)
        await geofeed.reload()
        return geofeed

    async def reload(self) -> None:
        """Reload the source bytes and decoded text asynchronously."""
        logger.info(
            "Loading geofeed source asynchronously from %s: %s",
            source_kind(self.source),
            self.source,
        )
        raw, content_type = await load_input_async(self.source)
        text = self._update_loaded_content(raw, content_type)
        logger.debug(
            "Loaded geofeed source asynchronously from %s: %s bytes=%d chars=%d content_type=%r",
            source_kind(self.source),
            self.source,
            len(raw),
            len(text),
            content_type,
        )

    async def _ensure_loaded(self) -> None:
        if self.raw is None or self.text is None:
            logger.debug("Async geofeed source not loaded yet; performing lazy load: %s", self.source)
            await self.reload()
        else:
            logger.log(TRACE_LEVEL, "Using cached async geofeed source: %s", self.source)

    async def parse(
        self,
        *,
        include_validation: bool = True,
        normalize: bool = False,
        output: str = "objects",
    ) -> list[GeofeedRecord] | str:
        """Parse the source asynchronously and optionally serialize the result."""
        await self._ensure_loaded()
        return await asyncio.to_thread(self._do_parse, include_validation=include_validation, normalize=normalize, output=output)

    async def validate(
        self,
        *,
        check_sort: bool = True,
        check_content_type: bool = True,
        check_aggregation: bool = False,
        output: str = "objects",
    ) -> ValidationReport | str:
        """Validate the source asynchronously and optionally serialize the report."""
        await self._ensure_loaded()
        return await asyncio.to_thread(
            self._do_validate,
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
        await self._ensure_loaded()
        return await asyncio.to_thread(
            self._do_normalize,
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
        await self._ensure_loaded()
        return await asyncio.to_thread(self._do_query, query, return_all=return_all, include_longer=include_longer, output=output)

    @staticmethod
    async def doctor(
        query: str,
        *,
        return_all: bool = False,
        include_longer: bool = False,
        rdap_method: str = DEFAULT_RDAP_METHOD,
        output: str = "objects",
    ) -> DoctorResult | str:
        """Discover and query a published geofeed asynchronously via RDAP."""
        result = await doctor_query_async(
            query,
            return_all=return_all,
            include_longer=include_longer,
            rdap_method=rdap_method,
        )
        return _serialize_doctor_result(result, output=output)

    @staticmethod
    async def lookup(
        query: str,
        *,
        return_all: bool = False,
        include_longer: bool = False,
        rdap_method: str = DEFAULT_RDAP_METHOD,
        output: str = "objects",
    ) -> QueryResult | str:
        """Discover a geofeed via RDAP and return query results for an IP or prefix.

        Raises GeoFeedDiscoveryError when no geofeed URL is published for the query.
        """
        result = await doctor_query_async(
            query,
            return_all=return_all,
            include_longer=include_longer,
            rdap_method=rdap_method,
        )
        query_result = _build_lookup_result(result)
        return _serialize_query_result(query_result, output=output)

    async def info(self, *, output: str = "objects") -> GeoFeedInfo | str:
        """Compute aggregate geofeed statistics asynchronously."""
        await self._ensure_loaded()
        return await asyncio.to_thread(self._do_info, output=output)


__all__ = ["AsyncGeoFeed", "FetchError", "GeoFeedDiscoveryError"]

