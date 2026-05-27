"""Async geofeed API built on shared sync parsing and validation helpers."""

from __future__ import annotations

import asyncio

from ._query_cache import QueryIndexCache
from .core import (
    _info_loaded,
    _normalize_loaded,
    _parse_loaded,
    _query_loaded,
    _validate_loaded,
)
from .doctor import doctor_query_async, render_doctor_text
from .io_utils import doctor_to_json, query_to_json, records_to_csv
from .loader import FetchError, decode_text, load_input_async, source_kind
from .logging import TRACE_LEVEL, logger
from .models import (
    DoctorResult,
    GeoFeedDiscoveryError,
    GeoFeedInfo,
    GeofeedRecord,
    QueryResult,
    ValidationReport,
)
from .query import load_query_records


class AsyncGeoFeed:
    """Async-native geofeed API for library consumers."""

    def __init__(self, source: str, *, cache_query_index: bool = True):
        """Initialize an async geofeed wrapper around a local path or URL."""
        self.source = source
        self._cache_query_index = cache_query_index
        self.raw: bytes | None = None
        self.content_type: str | None = None
        self.text: str | None = None
        self._query_index_state = QueryIndexCache(enabled=cache_query_index)

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
        self.raw = raw
        self.content_type = content_type
        self.text = decode_text(raw, strip_bom=True)
        self._query_index_state.invalidate()
        assert self.text is not None
        logger.debug(
            "Loaded geofeed source asynchronously from %s: %s bytes=%d chars=%d content_type=%r",
            source_kind(self.source),
            self.source,
            len(raw),
            len(self.text),
            content_type,
        )

    async def _ensure_loaded(self) -> tuple[bytes, str]:
        if self.raw is None or self.text is None:
            logger.debug("Async geofeed source not loaded yet; performing lazy load: %s", self.source)
            await self.reload()
        else:
            logger.log(TRACE_LEVEL, "Using cached async geofeed source: %s", self.source)
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
            self.source,
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
        indexed_records = self._query_index_state.get_cached()
        if indexed_records is None and self._cache_query_index:
            indexed_records = self._query_index_state.store(await asyncio.to_thread(load_query_records, text))
        return await asyncio.to_thread(
            _query_loaded,
            self.source,
            text,
            query,
            return_all=return_all,
            include_longer=include_longer,
            output=output,
            indexed_records=indexed_records,
        )

    @staticmethod
    async def doctor(
        query: str,
        *,
        return_all: bool = False,
        include_longer: bool = False,
        rdap_method: str = "rdap.org",
        output: str = "objects",
    ) -> DoctorResult | str:
        """Discover and query a published geofeed asynchronously via RDAP."""
        if output not in {"objects", "json", "text"}:
            raise ValueError("output must be one of: objects, json, text")

        result = await doctor_query_async(
            query,
            return_all=return_all,
            include_longer=include_longer,
            rdap_method=rdap_method,
        )
        if output == "objects":
            return result
        if output == "json":
            return doctor_to_json(result)
        return render_doctor_text(result)

    @staticmethod
    async def lookup(
        query: str,
        *,
        return_all: bool = False,
        include_longer: bool = False,
        rdap_method: str = "rdap.org",
        output: str = "objects",
    ) -> QueryResult | str:
        """Discover a geofeed via RDAP and return query results for an IP or prefix.

        Raises GeoFeedDiscoveryError when no geofeed URL is published for the query.
        """
        if output not in {"objects", "json", "csv"}:
            raise ValueError("output must be one of: objects, json, csv")

        result = await doctor_query_async(
            query,
            return_all=return_all,
            include_longer=include_longer,
            rdap_method=rdap_method,
        )
        if result.lookup.geofeed_url is None:
            raise GeoFeedDiscoveryError(query)
        query_result = QueryResult(query=result.query, matches=result.matches)
        if output == "objects":
            return query_result
        if output == "json":
            return query_to_json(query_result)
        return records_to_csv(list(query_result.matches), include_validation=False)

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


__all__ = ["AsyncGeoFeed", "FetchError", "GeoFeedDiscoveryError"]
