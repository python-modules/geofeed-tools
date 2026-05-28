"""Public GeoFeed class for loading and operating on geofeed sources."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TypeVar

from ._query_cache import QueryIndex, QueryIndexCache
from .config import DEFAULT_RDAP_METHOD, TRACE_LEVEL
from .doctor import doctor_query, render_doctor_text
from .filtering import filter_records
from .info import DEFAULT_TOP_N, build_info
from .io_utils import (
    doctor_to_json,
    info_to_json,
    query_to_json,
    records_to_csv,
    records_to_json,
    report_to_json,
)
from .loader import FetchError, decode_text, load_input, source_kind
from .logging import logger
from .models import (
    DoctorResult,
    GeoFeedDiscoveryError,
    GeoFeedInfo,
    GeofeedRecord,
    QueryResult,
    ValidationReport,
)
from .normalize import normalize_records
from .parse import annotate_validity, parse_text, parse_text_with_networks
from .query import load_query_records, query_text
from .validate import render_validation_text, validate_bytes

T = TypeVar("T")


def _emit(
    obj: T,
    *,
    output: str,
    serializers: Mapping[str, Callable[[T], str]],
    summary: str,
) -> T | str:
    """Validate the output mode, optionally serialize, and log completion."""
    if output != "objects" and output not in serializers:
        allowed = ", ".join(("objects", *serializers))
        raise ValueError(f"output must be one of: {allowed}")
    if output == "objects":
        logger.debug("%s output=%s", summary, output)
        return obj
    payload = serializers[output](obj)
    logger.debug("%s output=%s payload_chars=%d", summary, output, len(payload))
    return payload


_QUERY_SERIALIZERS: Mapping[str, Callable[[QueryResult], str]] = {
    "json": query_to_json,
    "csv": lambda result: records_to_csv(result.matches, include_validation=False),
}

_DOCTOR_SERIALIZERS: Mapping[str, Callable[[DoctorResult], str]] = {
    "json": doctor_to_json,
    "text": render_doctor_text,
}

_INFO_SERIALIZERS: Mapping[str, Callable[[GeoFeedInfo], str]] = {
    "json": info_to_json,
}


def _records_serializers(*, include_validation: bool) -> Mapping[str, Callable[[list[GeofeedRecord]], str]]:
    return {
        "json": lambda records: records_to_json(records, include_validation=include_validation),
        "csv": lambda records: records_to_csv(records, include_validation=include_validation),
    }


def _validation_serializers() -> Mapping[str, Callable[[ValidationReport], str]]:
    return {
        "json": report_to_json,
        "text": render_validation_text,
    }


def _serialize_query_result(result: QueryResult, *, output: str) -> QueryResult | str:
    return _emit(
        result,
        output=output,
        serializers=_QUERY_SERIALIZERS,
        summary=f"Query result serialized: matches={len(result.matches)}",
    )


def _serialize_doctor_result(result: DoctorResult, *, output: str) -> DoctorResult | str:
    return _emit(
        result,
        output=output,
        serializers=_DOCTOR_SERIALIZERS,
        summary=f"Doctor result serialized: query={result.query} matches={len(result.matches)}",
    )


def _build_lookup_result(result: DoctorResult) -> QueryResult:
    if result.lookup.geofeed_url is None:
        raise GeoFeedDiscoveryError(result.query)
    return QueryResult(query=result.query, matches=result.matches)


def _build_parsed_records(
    source: str,
    raw: bytes,
    text: str,
    content_type: str | None,
    *,
    include_validation: bool,
    normalize: bool,
) -> list[GeofeedRecord]:
    records = normalize_records(text) if normalize else parse_text(text)
    if include_validation:
        records = annotate_validity(records, source=source, raw=raw, content_type=content_type)
    return records


def _parse_loaded(
    source: str,
    raw: bytes,
    text: str,
    content_type: str | None,
    *,
    include_validation: bool = True,
    normalize: bool = False,
    output: str = "objects",
) -> list[GeofeedRecord] | str:
    logger.info("Parsing geofeed records from %s source: %s", source_kind(source), source)
    records = _build_parsed_records(
        source,
        raw,
        text,
        content_type,
        include_validation=include_validation,
        normalize=normalize,
    )
    return _emit(
        records,
        output=output,
        serializers=_records_serializers(include_validation=include_validation),
        summary=f"Parse completed: source={source} records={len(records)}",
    )


def _validate_loaded(
    source: str,
    raw: bytes,
    content_type: str | None,
    *,
    check_sort: bool = True,
    check_content_type: bool = True,
    check_aggregation: bool = False,
    output: str = "objects",
) -> ValidationReport | str:
    logger.info("Validating geofeed source: %s", source)
    report = validate_bytes(
        raw,
        source,
        content_type,
        check_sort=check_sort,
        check_content_type=check_content_type,
        check_aggregation=check_aggregation,
    )
    return _emit(
        report,
        output=output,
        serializers=_validation_serializers(),
        summary=(
            f"Validation completed: source={source} records={report.records}"
            f" errors={report.errors} warnings={report.warnings}"
        ),
    )


def _filter_loaded(
    source: str,
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
    output: str = "objects",
) -> list[GeofeedRecord] | str:
    logger.info("Filtering geofeed source: %s", source)
    records = filter_records(
        text,
        prefix=prefix,
        country=country,
        region=region,
        city=city,
        postal_code=postal_code,
        family=family,
        prefix_length=prefix_length,
        include_longer=include_longer,
    )
    return _emit(
        records,
        output=output,
        serializers=_records_serializers(include_validation=False),
        summary=f"Filter completed: source={source} records={len(records)}",
    )


def _normalize_loaded(
    source: str,
    text: str,
    *,
    uppercase: bool = True,
    sort: bool = True,
    aggregate: bool = True,
    dedupe: bool = True,
    fix_host_bits: bool = True,
    output: str = "objects",
) -> list[GeofeedRecord] | str:
    logger.info("Normalizing geofeed source: %s", source)
    records = normalize_records(
        text,
        uppercase=uppercase,
        sort=sort,
        aggregate=aggregate,
        dedupe=dedupe,
        fix_host_bits=fix_host_bits,
    )
    return _emit(
        records,
        output=output,
        serializers=_records_serializers(include_validation=False),
        summary=f"Normalize completed: source={source} records={len(records)}",
    )


def _query_loaded(
    source: str,
    text: str,
    query: str,
    *,
    return_all: bool = False,
    include_longer: bool = False,
    output: str = "objects",
    indexed_records: QueryIndex | None = None,
) -> QueryResult | str:
    logger.info("Querying geofeed source: %s query=%s", source, query)
    result = query_text(
        text,
        query,
        return_all=return_all,
        include_longer=include_longer,
        indexed_records=indexed_records,
    )
    return _emit(
        result,
        output=output,
        serializers=_QUERY_SERIALIZERS,
        summary=f"Query completed: source={source} query={query} matches={len(result.matches)}",
    )


def _info_loaded(
    source: str,
    raw: bytes,
    text: str,
    content_type: str | None,
    *,
    top_n: int = DEFAULT_TOP_N,
    output: str = "objects",
) -> GeoFeedInfo | str:
    logger.info("Computing geofeed info: %s", source)
    records, networks = parse_text_with_networks(text)
    report = validate_bytes(raw, source, content_type)
    info = build_info(source, records, networks, report, text=text, top_n=top_n)
    return _emit(
        info,
        output=output,
        serializers=_INFO_SERIALIZERS,
        summary=(
            f"Info completed: source={source} prefixes={info.prefixes_total}"
            f" countries={len(info.by_country)} errors={info.errors} warnings={info.warnings}"
        ),
    )


def _doctor(
    query: str,
    *,
    return_all: bool = False,
    include_longer: bool = False,
    rdap_method: str = DEFAULT_RDAP_METHOD,
    output: str = "objects",
) -> DoctorResult | str:
    logger.info("Running doctor command for query=%s", query)
    result = doctor_query(
        query,
        return_all=return_all,
        include_longer=include_longer,
        rdap_method=rdap_method,
    )
    return _serialize_doctor_result(result, output=output)


def _lookup(
    query: str,
    *,
    return_all: bool = False,
    include_longer: bool = False,
    rdap_method: str = DEFAULT_RDAP_METHOD,
    output: str = "objects",
) -> QueryResult | str:
    logger.info("Running lookup command for query=%s", query)
    result = doctor_query(
        query,
        return_all=return_all,
        include_longer=include_longer,
        rdap_method=rdap_method,
    )
    return _serialize_query_result(_build_lookup_result(result), output=output)


class _GeoFeedBase:
    """Shared state, cache helpers, and CPU-bound work for sync and async geofeed APIs."""

    def __init__(self, source: str, *, cache_query_index: bool = True) -> None:
        self.source = source
        self._cache_query_index = cache_query_index
        self.raw: bytes | None = None
        self.content_type: str | None = None
        self.text: str | None = None
        self._query_index_state = QueryIndexCache(enabled=cache_query_index)

    def _update_loaded_content(self, raw: bytes, content_type: str | None) -> str:
        """Store loaded bytes, decode text, and invalidate the query index cache."""
        self.raw = raw
        self.content_type = content_type
        # Parser and normalizer behavior strips UTF-8 BOM before processing.
        text = decode_text(raw, strip_bom=True)
        self.text = text
        self._query_index_state.invalidate()
        return text

    def _get_cached_query_index(self) -> QueryIndex | None:
        return self._query_index_state.get_cached()

    def _store_query_index(self, index: QueryIndex) -> QueryIndex:
        return self._query_index_state.store(index)

    # ------------------------------------------------------------------
    # CPU-bound work methods — called after loading; safe for to_thread.
    # ------------------------------------------------------------------

    def _do_parse(
        self,
        *,
        include_validation: bool = True,
        normalize: bool = False,
        output: str = "objects",
    ) -> list[GeofeedRecord] | str:
        assert self.raw is not None
        assert self.text is not None
        return _parse_loaded(
            self.source,
            self.raw,
            self.text,
            self.content_type,
            include_validation=include_validation,
            normalize=normalize,
            output=output,
        )

    def _do_validate(
        self,
        *,
        check_sort: bool = True,
        check_content_type: bool = True,
        check_aggregation: bool = False,
        output: str = "objects",
    ) -> ValidationReport | str:
        assert self.raw is not None
        return _validate_loaded(
            self.source,
            self.raw,
            self.content_type,
            check_sort=check_sort,
            check_content_type=check_content_type,
            check_aggregation=check_aggregation,
            output=output,
        )

    def _do_filter(
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
        assert self.text is not None
        return _filter_loaded(
            self.source,
            self.text,
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

    def _do_normalize(
        self,
        *,
        uppercase: bool = True,
        sort: bool = True,
        aggregate: bool = True,
        dedupe: bool = True,
        fix_host_bits: bool = True,
        output: str = "objects",
    ) -> list[GeofeedRecord] | str:
        assert self.text is not None
        return _normalize_loaded(
            self.source,
            self.text,
            uppercase=uppercase,
            sort=sort,
            aggregate=aggregate,
            dedupe=dedupe,
            fix_host_bits=fix_host_bits,
            output=output,
        )

    def _do_query(
        self,
        query: str,
        *,
        return_all: bool = False,
        include_longer: bool = False,
        output: str = "objects",
    ) -> QueryResult | str:
        assert self.text is not None
        indexed_records = self._get_cached_query_index()
        if indexed_records is None and self._cache_query_index:
            indexed_records = self._store_query_index(load_query_records(self.text))
        return _query_loaded(
            self.source,
            self.text,
            query,
            return_all=return_all,
            include_longer=include_longer,
            output=output,
            indexed_records=indexed_records,
        )

    def _do_info(
        self,
        *,
        top_n: int = DEFAULT_TOP_N,
        output: str = "objects",
    ) -> GeoFeedInfo | str:
        assert self.raw is not None
        assert self.text is not None
        return _info_loaded(
            self.source,
            self.raw,
            self.text,
            self.content_type,
            top_n=top_n,
            output=output,
        )


class GeoFeed(_GeoFeedBase):
    """Main object-oriented API for geofeed workflows."""

    def __init__(
        self,
        source: str,
        *,
        auto_load: bool = True,
        cache_query_index: bool = True,
    ):
        """Initialize a geofeed source and optionally load it immediately."""
        super().__init__(source, cache_query_index=cache_query_index)
        if auto_load:
            self.reload()

    @classmethod
    def from_source(cls, source: str, *, cache_query_index: bool = True) -> GeoFeed:
        """Create an instance and eagerly load the source.

        Symmetric with ``AsyncGeoFeed.from_source``; prefer this in new code.
        """
        return cls(source, auto_load=True, cache_query_index=cache_query_index)

    def reload(self) -> None:
        """Reload the source bytes and decoded text from disk or HTTP."""
        logger.info("Loading geofeed source from %s: %s", source_kind(self.source), self.source)
        raw, content_type = load_input(self.source)
        text = self._update_loaded_content(raw, content_type)
        logger.debug(
            "Loaded geofeed source from %s: %s bytes=%d chars=%d content_type=%r",
            source_kind(self.source),
            self.source,
            len(raw),
            len(text),
            content_type,
        )

    def _ensure_loaded(self) -> None:
        if self.raw is None or self.text is None:
            logger.debug("Geofeed source not loaded yet; performing lazy load: %s", self.source)
            self.reload()
        else:
            logger.log(TRACE_LEVEL, "Using cached geofeed source: %s", self.source)

    def parse(
        self,
        *,
        include_validation: bool = True,
        normalize: bool = False,
        output: str = "objects",
    ) -> list[GeofeedRecord] | str:
        """Parse the source into records and optionally serialize the result."""
        self._ensure_loaded()
        return self._do_parse(include_validation=include_validation, normalize=normalize, output=output)

    def validate(
        self,
        *,
        check_sort: bool = True,
        check_content_type: bool = True,
        check_aggregation: bool = False,
        output: str = "objects",
    ) -> ValidationReport | str:
        """Validate the source bytes and optionally serialize the report."""
        self._ensure_loaded()
        return self._do_validate(
            check_sort=check_sort,
            check_content_type=check_content_type,
            check_aggregation=check_aggregation,
            output=output,
        )

    def normalize(
        self,
        *,
        uppercase: bool = True,
        sort: bool = True,
        aggregate: bool = True,
        dedupe: bool = True,
        fix_host_bits: bool = True,
        output: str = "objects",
    ) -> list[GeofeedRecord] | str:
        """Normalize records from the source and optionally serialize them."""
        self._ensure_loaded()
        return self._do_normalize(
            uppercase=uppercase,
            sort=sort,
            aggregate=aggregate,
            dedupe=dedupe,
            fix_host_bits=fix_host_bits,
            output=output,
        )

    def query(
        self,
        query: str,
        *,
        return_all: bool = False,
        include_longer: bool = False,
        output: str = "objects",
    ) -> QueryResult | str:
        """Query the source for an IP or prefix and return matching records."""
        self._ensure_loaded()
        return self._do_query(query, return_all=return_all, include_longer=include_longer, output=output)

    def filter(
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
        """Filter records by one or more field/property predicates (AND).

        ``include_longer=True`` switches the ``prefix`` filter from exact match
        to "this prefix or any more-specific prefix", and the ``prefix_length``
        filter from "exactly this length" to "this length or longer".
        """
        self._ensure_loaded()
        return self._do_filter(
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
    def doctor(
        query: str,
        *,
        return_all: bool = False,
        include_longer: bool = False,
        rdap_method: str = DEFAULT_RDAP_METHOD,
        output: str = "objects",
    ) -> DoctorResult | str:
        """Discover and query a published geofeed for an IP or prefix via RDAP."""
        return _doctor(
            query,
            return_all=return_all,
            include_longer=include_longer,
            rdap_method=rdap_method,
            output=output,
        )

    @staticmethod
    def lookup(
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
        return _lookup(
            query,
            return_all=return_all,
            include_longer=include_longer,
            rdap_method=rdap_method,
            output=output,
        )

    def info(
        self,
        *,
        top_n: int = DEFAULT_TOP_N,
        output: str = "objects",
    ) -> GeoFeedInfo | str:
        """Compute detailed info for the current geofeed source.

        The returned ``GeoFeedInfo`` includes total counts, geography uniques,
        per-country breakdowns, prefix-length histograms, top regions/cities,
        and a preview of what the feed would look like after normalize().
        """
        self._ensure_loaded()
        return self._do_info(top_n=top_n, output=output)


__all__ = ["FetchError", "GeoFeed", "GeoFeedDiscoveryError"]
