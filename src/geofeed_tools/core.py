"""Public GeoFeed class for loading and operating on geofeed sources."""

from __future__ import annotations

from ._query_cache import QueryIndex, QueryIndexCache
from .info import build_info
from .io_utils import (
    info_to_json,
    query_to_json,
    records_to_csv,
    records_to_json,
    report_to_json,
)
from .loader import FetchError, decode_text, load_input, source_kind
from .logging import TRACE_LEVEL, logger
from .models import GeoFeedInfo, GeofeedRecord, QueryResult, ValidationReport
from .normalize import normalize_records
from .parse import annotate_validity, parse_text
from .query import load_query_records, query_text
from .validate import render_validation_text, validate_bytes


def _validate_output(output: str, allowed: tuple[str, ...]) -> None:
    if output not in allowed:
        raise ValueError(f"output must be one of: {', '.join(allowed)}")


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
    _validate_output(output, ("objects", "json", "csv"))
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
    if output == "objects":
        logger.debug(
            "Query completed: source=%s query=%s matches=%d output=%s",
            source,
            query,
            len(result.matches),
            output,
        )
        return result
    if output == "json":
        payload = query_to_json(result)
        logger.debug(
            "Query completed: source=%s query=%s matches=%d output=%s payload_chars=%d",
            source,
            query,
            len(result.matches),
            output,
            len(payload),
        )
        return payload
    payload = records_to_csv(result.matches, include_validation=False)
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
    records = _build_parsed_records(
        source,
        raw,
        text,
        content_type,
        include_validation=False,
        normalize=False,
    )
    report = _build_validation_report(
        source,
        raw,
        content_type,
    )
    info = build_info(source, records, report)
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


class GeoFeed:
    """Main object-oriented API for geofeed workflows."""

    def __init__(
        self,
        source: str,
        *,
        auto_load: bool = True,
        cache_query_index: bool = True,
    ):
        """Initialize a geofeed source and optionally load it immediately."""
        self.source = source
        self._cache_query_index = cache_query_index
        self.raw: bytes | None = None
        self.content_type: str | None = None
        self.text: str | None = None
        self._query_index_state = QueryIndexCache(enabled=cache_query_index)

        if auto_load:
            self.reload()

    def reload(self) -> None:
        """Reload the source bytes and decoded text from disk or HTTP."""
        logger.info("Loading geofeed source from %s: %s", source_kind(self.source), self.source)
        raw, content_type = load_input(self.source)
        self.raw = raw
        self.content_type = content_type
        # Parser and normalizer behavior strips UTF-8 BOM before processing.
        self.text = decode_text(raw, strip_bom=True)
        self._query_index_state.invalidate()
        assert self.text is not None
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
        indexed_records = self._query_index_state.get_cached()
        if indexed_records is None and self._cache_query_index:
            indexed_records = self._query_index_state.store(load_query_records(text))
        return _query_loaded(
            self.source,
            text,
            query,
            return_all=return_all,
            include_longer=include_longer,
            output=output,
            indexed_records=indexed_records,
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


__all__ = ["FetchError", "GeoFeed"]
