"""Public GeoFeed class for loading and operating on geofeed sources."""

from __future__ import annotations

from ._query_cache import QueryIndex, QueryIndexCache
from .doctor import doctor_query, render_doctor_text
from .info import build_info
from .io_utils import (
    doctor_to_json,
    info_to_json,
    query_to_json,
    records_to_csv,
    records_to_json,
    report_to_json,
)
from .loader import FetchError, decode_text, load_input, source_kind
from .logging import TRACE_LEVEL, logger
from .models import DoctorResult, GeoFeedInfo, GeofeedRecord, GeoFeedDiscoveryError, QueryResult, ValidationReport
from .normalize import normalize_records
from .parse import annotate_validity, parse_text, parse_text_with_networks
from .query import load_query_records, query_text
from .validate import render_validation_text, validate_bytes


def _validate_output(output: str, allowed: tuple[str, ...]) -> None:
    if output not in allowed:
        raise ValueError(f"output must be one of: {', '.join(allowed)}")


def _serialize_query_result(
    result: QueryResult,
    *,
    output: str,
) -> QueryResult | str:
    _validate_output(output, ("objects", "json", "csv"))
    if output == "objects":
        return result
    if output == "json":
        return query_to_json(result)
    return records_to_csv(result.matches, include_validation=False)


def _serialize_doctor_result(
    result: DoctorResult,
    *,
    output: str,
) -> DoctorResult | str:
    _validate_output(output, ("objects", "json", "text"))
    if output == "objects":
        return result
    if output == "json":
        return doctor_to_json(result)
    return render_doctor_text(result)


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
    logger.debug(
        "Building parsed geofeed records: source=%s include_validation=%s normalize=%s",
        source,
        include_validation,
        normalize,
    )
    records = normalize_records(text) if normalize else parse_text(text)
    if include_validation:
        records = annotate_validity(
            records,
            source=source,
            raw=raw,
            content_type=content_type,
        )
    logger.debug("Built parsed geofeed records: source=%s records=%d", source, len(records))
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
    _validate_output(output, ("objects", "json", "csv"))
    logger.info("Parsing geofeed records from %s source: %s", source_kind(source), source)
    logger.debug(
        "Parse options: source=%s include_validation=%s normalize=%s output=%s",
        source,
        include_validation,
        normalize,
        output,
    )
    records = _build_parsed_records(
        source,
        raw,
        text,
        content_type,
        include_validation=include_validation,
        normalize=normalize,
    )
    if output == "objects":
        logger.debug("Parse completed: source=%s records=%d output=%s", source, len(records), output)
        return records
    if output == "json":
        payload = records_to_json(
            records,
            include_validation=include_validation,
        )
        logger.debug(
            "Parse completed: source=%s records=%d output=%s payload_chars=%d",
            source,
            len(records),
            output,
            len(payload),
        )
        return payload
    payload = records_to_csv(
        records,
        include_validation=include_validation,
    )
    logger.debug(
        "Parse completed: source=%s records=%d output=%s payload_chars=%d",
        source,
        len(records),
        output,
        len(payload),
    )
    return payload


def _build_validation_report(
    source: str,
    raw: bytes,
    content_type: str | None,
    *,
    check_sort: bool = True,
    check_content_type: bool = True,
    check_aggregation: bool = False,
) -> ValidationReport:
    logger.debug(
        "Building validation report: source=%s check_sort=%s check_content_type=%s check_aggregation=%s",
        source,
        check_sort,
        check_content_type,
        check_aggregation,
    )
    return validate_bytes(
        raw,
        source,
        content_type,
        check_sort=check_sort,
        check_content_type=check_content_type,
        check_aggregation=check_aggregation,
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
    _validate_output(output, ("objects", "json", "text"))
    logger.info("Validating geofeed source: %s", source)
    logger.debug(
        "Validation options: source=%s check_sort=%s check_content_type=%s check_aggregation=%s output=%s",
        source,
        check_sort,
        check_content_type,
        check_aggregation,
        output,
    )
    report = _build_validation_report(
        source,
        raw,
        content_type,
        check_sort=check_sort,
        check_content_type=check_content_type,
        check_aggregation=check_aggregation,
    )
    if output == "objects":
        logger.debug(
            "Validation completed: source=%s records=%d errors=%d warnings=%d output=%s",
            source,
            report.records,
            report.errors,
            report.warnings,
            output,
        )
        return report
    if output == "json":
        payload = report_to_json(report)
        logger.debug(
            "Validation completed: source=%s records=%d errors=%d warnings=%d output=%s payload_chars=%d",
            source,
            report.records,
            report.errors,
            report.warnings,
            output,
            len(payload),
        )
        return payload
    payload = render_validation_text(report)
    logger.debug(
        "Validation completed: source=%s records=%d errors=%d warnings=%d output=%s payload_chars=%d",
        source,
        report.records,
        report.errors,
        report.warnings,
        output,
        len(payload),
    )
    return payload


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
    _validate_output(output, ("objects", "json", "csv"))
    logger.info("Normalizing geofeed source: %s", source)
    logger.debug(
        "Normalize options: source=%s uppercase=%s sort=%s aggregate=%s dedupe=%s fix_host_bits=%s output=%s",
        source,
        uppercase,
        sort,
        aggregate,
        dedupe,
        fix_host_bits,
        output,
    )
    records = normalize_records(
        text,
        uppercase=uppercase,
        sort=sort,
        aggregate=aggregate,
        dedupe=dedupe,
        fix_host_bits=fix_host_bits,
    )
    if output == "objects":
        logger.debug("Normalize completed: source=%s records=%d output=%s", source, len(records), output)
        return records
    if output == "json":
        payload = records_to_json(records, include_validation=False)
        logger.debug(
            "Normalize completed: source=%s records=%d output=%s payload_chars=%d",
            source,
            len(records),
            output,
            len(payload),
        )
        return payload
    payload = records_to_csv(records, include_validation=False)
    logger.debug(
        "Normalize completed: source=%s records=%d output=%s payload_chars=%d",
        source,
        len(records),
        output,
        len(payload),
    )
    return payload


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
    logger.debug(
        "Query options: source=%s query=%s return_all=%s include_longer=%s output=%s",
        source,
        query,
        return_all,
        include_longer,
        output,
    )
    result = query_text(
        text,
        query,
        return_all=return_all,
        include_longer=include_longer,
        indexed_records=indexed_records,
    )
    serialized = _serialize_query_result(result, output=output)
    if output == "objects":
        logger.debug(
            "Query completed: source=%s query=%s matches=%d output=%s",
            source,
            query,
            len(result.matches),
            output,
        )
        return serialized
    payload = serialized
    assert isinstance(payload, str)
    if output == "json":
        logger.debug(
            "Query completed: source=%s query=%s matches=%d output=%s payload_chars=%d",
            source,
            query,
            len(result.matches),
            output,
            len(payload),
        )
    else:
        logger.debug(
            "Query completed: source=%s query=%s matches=%d output=%s payload_chars=%d",
            source,
            query,
            len(result.matches),
            output,
            len(payload),
        )
    return payload


def _info_loaded(
    source: str,
    raw: bytes,
    text: str,
    content_type: str | None,
    *,
    output: str = "objects",
) -> GeoFeedInfo | str:
    _validate_output(output, ("objects", "json"))
    logger.info("Computing geofeed summary: %s", source)
    records, networks = parse_text_with_networks(text)
    report = _build_validation_report(
        source,
        raw,
        content_type,
    )
    info = build_info(source, records, report, networks=networks)
    if output == "objects":
        logger.debug(
            "Computed geofeed summary: source=%s total_records=%d errors=%d warnings=%d output=%s",
            source,
            info.total_records,
            info.errors,
            info.warnings,
            output,
        )
        return info
    payload = info_to_json(info)
    logger.debug(
        "Computed geofeed summary: source=%s total_records=%d errors=%d warnings=%d output=%s payload_chars=%d",
        source,
        info.total_records,
        info.errors,
        info.warnings,
        output,
        len(payload),
    )
    return payload


def _doctor(
    query: str,
    *,
    return_all: bool = False,
    include_longer: bool = False,
    rdap_method: str = "rdap.org",
    output: str = "objects",
) -> DoctorResult | str:
    logger.info("Running doctor command for query=%s", query)
    result = doctor_query(
        query,
        return_all=return_all,
        include_longer=include_longer,
        rdap_method=rdap_method,
    )
    serialized = _serialize_doctor_result(result, output=output)
    if output == "objects":
        logger.debug(
            "Doctor completed: query=%s geofeed_url=%s matches=%d output=%s",
            query,
            result.lookup.geofeed_url,
            len(result.matches),
            output,
        )
        return serialized
    payload = serialized
    assert isinstance(payload, str)
    if output == "json":
        logger.debug(
            "Doctor completed: query=%s geofeed_url=%s matches=%d output=%s payload_chars=%d",
            query,
            result.lookup.geofeed_url,
            len(result.matches),
            output,
            len(payload),
        )
    else:
        logger.debug(
            "Doctor completed: query=%s geofeed_url=%s matches=%d output=%s payload_chars=%d",
            query,
            result.lookup.geofeed_url,
            len(result.matches),
            output,
            len(payload),
        )
    return payload


def _lookup(
    query: str,
    *,
    return_all: bool = False,
    include_longer: bool = False,
    rdap_method: str = "rdap.org",
    output: str = "objects",
) -> QueryResult | str:
    logger.info("Running lookup command for query=%s", query)
    result = doctor_query(
        query,
        return_all=return_all,
        include_longer=include_longer,
        rdap_method=rdap_method,
    )
    query_result = _build_lookup_result(result)
    serialized = _serialize_query_result(query_result, output=output)
    if output == "objects":
        logger.debug(
            "Lookup completed: query=%s geofeed_url=%s matches=%d output=%s",
            query,
            result.lookup.geofeed_url,
            len(query_result.matches),
            output,
        )
        return serialized
    payload = serialized
    assert isinstance(payload, str)
    if output == "json":
        logger.debug(
            "Lookup completed: query=%s geofeed_url=%s matches=%d output=%s payload_chars=%d",
            query,
            result.lookup.geofeed_url,
            len(query_result.matches),
            output,
            len(payload),
        )
    else:
        logger.debug(
            "Lookup completed: query=%s geofeed_url=%s matches=%d output=%s payload_chars=%d",
            query,
            result.lookup.geofeed_url,
            len(query_result.matches),
            output,
            len(payload),
    )
    return payload


class _GeoFeedBase:
    """Shared state and cache helpers for sync and async geofeed APIs."""

    def __init__(self, source: str, *, cache_query_index: bool = True) -> None:
        self.source = source
        self._cache_query_index = cache_query_index
        self.raw: bytes | None = None
        self.content_type: str | None = None
        self.text: str | None = None
        self._query_index_state = QueryIndexCache(enabled=cache_query_index)

    def _update_loaded_content(
        self,
        raw: bytes,
        content_type: str | None,
    ) -> None:
        self.raw = raw
        self.content_type = content_type
        # Parser and normalizer behavior strips UTF-8 BOM before processing.
        self.text = decode_text(raw, strip_bom=True)
        self._query_index_state.invalidate()
        assert self.text is not None

    def _get_cached_query_index(self) -> QueryIndex | None:
        return self._query_index_state.get_cached()

    def _store_query_index(self, index: QueryIndex) -> QueryIndex:
        return self._query_index_state.store(index)


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

    def reload(self) -> None:
        """Reload the source bytes and decoded text from disk or HTTP."""
        logger.info("Loading geofeed source from %s: %s", source_kind(self.source), self.source)
        raw, content_type = load_input(self.source)
        self._update_loaded_content(raw, content_type)
        logger.debug(
            "Loaded geofeed source from %s: %s bytes=%d chars=%d content_type=%r",
            source_kind(self.source),
            self.source,
            len(raw),
            len(self.text),
            content_type,
        )

    def _ensure_loaded(self) -> tuple[bytes, str]:
        if self.raw is None or self.text is None:
            logger.debug("Geofeed source not loaded yet; performing lazy load: %s", self.source)
            self.reload()
        else:
            logger.log(TRACE_LEVEL, "Using cached geofeed source: %s", self.source)
        assert self.raw is not None
        assert self.text is not None
        return self.raw, self.text

    def parse(
        self,
        *,
        include_validation: bool = True,
        normalize: bool = False,
        output: str = "objects",
    ) -> list[GeofeedRecord] | str:
        """Parse the source into records and optionally serialize the result."""
        raw, text = self._ensure_loaded()
        return _parse_loaded(
            self.source,
            raw,
            text,
            self.content_type,
            include_validation=include_validation,
            normalize=normalize,
            output=output,
        )

    def validate(
        self,
        *,
        check_sort: bool = True,
        check_content_type: bool = True,
        check_aggregation: bool = False,
        output: str = "objects",
    ) -> ValidationReport | str:
        """Validate the source bytes and optionally serialize the report."""
        raw, _text = self._ensure_loaded()
        return _validate_loaded(
            self.source,
            raw,
            self.content_type,
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
        _raw, text = self._ensure_loaded()
        return _normalize_loaded(
            self.source,
            text,
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
        _raw, text = self._ensure_loaded()
        indexed_records = self._get_cached_query_index()
        if indexed_records is None and self._cache_query_index:
            indexed_records = self._store_query_index(load_query_records(text))
        return _query_loaded(
            self.source,
            text,
            query,
            return_all=return_all,
            include_longer=include_longer,
            output=output,
            indexed_records=indexed_records,
        )

    @staticmethod
    def doctor(
        query: str,
        *,
        return_all: bool = False,
        include_longer: bool = False,
        rdap_method: str = "rdap.org",
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
        rdap_method: str = "rdap.org",
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

    def info(self, *, output: str = "objects") -> GeoFeedInfo | str:
        """Compute aggregate statistics for the current geofeed source."""
        raw, text = self._ensure_loaded()
        return _info_loaded(
            self.source,
            raw,
            text,
            self.content_type,
            output=output,
        )


__all__ = ["FetchError", "GeoFeed", "GeoFeedDiscoveryError"]
