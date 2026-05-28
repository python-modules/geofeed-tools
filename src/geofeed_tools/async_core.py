"""Async geofeed API built on shared sync parsing and validation helpers."""

from __future__ import annotations

import asyncio

from .config import DEFAULT_RDAP_METHOD, TRACE_LEVEL
from .core import _GeoFeedBase, _serialize_doctor_result
from .doctor import doctor_query_async
from .info import DEFAULT_TOP_N
from .loader import FetchError, is_ip_or_prefix, load_input_async, source_kind
from .logging import logger
from .models import (
    DoctorResult,
    GeoFeedDiscoveryError,
    GeoFeedInfo,
    GeofeedRecord,
    QueryResult,
    ValidationReport,
)
from .rdap import resolve_geofeed_lookup_async


class AsyncGeoFeed(_GeoFeedBase):
    """Async-native geofeed API for library consumers."""

    def __init__(
        self,
        source: str,
        *,
        cache_query_index: bool = True,
        rdap_method: str = DEFAULT_RDAP_METHOD,
    ):
        """Initialize an async geofeed wrapper around a path, URL, or IP/prefix.

        IP/prefix inputs trigger an RDAP discovery on first load (using
        ``rdap_method``, default rdap.org).
        """
        super().__init__(
            source,
            cache_query_index=cache_query_index,
            rdap_method=rdap_method,
        )

    @classmethod
    async def from_source(
        cls,
        source: str,
        *,
        cache_query_index: bool = True,
        rdap_method: str = DEFAULT_RDAP_METHOD,
    ) -> AsyncGeoFeed:
        """Create an instance and eagerly load the source asynchronously."""
        logger.debug("Creating AsyncGeoFeed and eagerly loading source: %s", source)
        geofeed = cls(source, cache_query_index=cache_query_index, rdap_method=rdap_method)
        await geofeed.reload()
        return geofeed

    async def _maybe_resolve_source_async(self) -> None:
        """Discover the geofeed URL asynchronously when source is an IP/prefix."""
        if self.discovery is not None:
            logger.log(
                TRACE_LEVEL,
                "Skipping async RDAP discovery: source %s was already resolved to %s",
                self.original_source,
                self.source,
            )
            return
        if not is_ip_or_prefix(self.source):
            logger.log(
                TRACE_LEVEL,
                "Skipping async RDAP discovery: source %s is a %s, not an IP/prefix",
                self.source,
                source_kind(self.source),
            )
            return
        logger.info(
            "Source %s is an IP/prefix; running async RDAP geofeed discovery (method=%s)",
            self.source,
            self._rdap_method,
        )
        resolved = await resolve_geofeed_lookup_async(
            self.source,
            rdap_method=self._rdap_method,
        )
        self._apply_resolved_lookup(resolved.lookup)

    async def reload(self) -> None:
        """Reload the source bytes and decoded text asynchronously."""
        await self._maybe_resolve_source_async()
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
        return await asyncio.to_thread(
            self._do_parse, include_validation=include_validation, normalize=normalize, output=output
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
        return await asyncio.to_thread(
            self._do_query, query, return_all=return_all, include_longer=include_longer, output=output
        )

    async def filter(
        self,
        *,
        prefix: str | None = None,
        country: str | None = None,
        region: str | None = None,
        city: str | None = None,
        postal_code: str | None = None,
        family: str | int | None = None,
        prefix_length: int | None = None,
        include_longer: bool = False,
        output: str = "objects",
    ) -> list[GeofeedRecord] | str:
        """Filter records by one or more field/property predicates asynchronously."""
        await self._ensure_loaded()
        return await asyncio.to_thread(
            self._do_filter,
            prefix=prefix,
            country=country,
            region=region,
            city=city,
            postal_code=postal_code,
            family=family,
            prefix_length=prefix_length,
            include_longer=include_longer,
            output=output,
        )

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

    async def info(
        self,
        *,
        top_n: int = DEFAULT_TOP_N,
        output: str = "objects",
    ) -> GeoFeedInfo | str:
        """Compute detailed geofeed info asynchronously."""
        await self._ensure_loaded()
        return await asyncio.to_thread(self._do_info, top_n=top_n, output=output)


__all__ = ["AsyncGeoFeed", "FetchError", "GeoFeedDiscoveryError"]
