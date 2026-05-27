"""Public GeoFeed class for loading and operating on geofeed sources."""

from __future__ import annotations

from .info import build_info
from .io_utils import (
    info_to_json,
    query_to_json,
    records_to_csv,
    records_to_json,
    report_to_json,
)
from .loader import FetchError, decode_text, load_input
from .models import GeoFeedInfo, GeofeedRecord, QueryResult, ValidationReport
from .normalize import normalize_records
from .parse import annotate_validity, parse_text
from .query import query_text
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
    records = normalize_records(text) if normalize else parse_text(text)
    if include_validation:
        records = annotate_validity(
            records,
            source=source,
            raw=raw,
            content_type=content_type,
        )
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
    records = _build_parsed_records(
        source,
        raw,
        text,
        content_type,
        include_validation=include_validation,
        normalize=normalize,
    )
    if output == "objects":
        return records
    if output == "json":
        return records_to_json(
            records,
            include_validation=include_validation,
        )
    return records_to_csv(
        records,
        include_validation=include_validation,
    )


def _build_validation_report(
    source: str,
    raw: bytes,
    content_type: str | None,
    *,
    check_sort: bool = True,
    check_content_type: bool = True,
    check_aggregation: bool = False,
) -> ValidationReport:
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
    report = _build_validation_report(
        source,
        raw,
        content_type,
        check_sort=check_sort,
        check_content_type=check_content_type,
        check_aggregation=check_aggregation,
    )
    if output == "objects":
        return report
    if output == "json":
        return report_to_json(report)
    return render_validation_text(report)


def _normalize_loaded(
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
    records = normalize_records(
        text,
        uppercase=uppercase,
        sort=sort,
        aggregate=aggregate,
        dedupe=dedupe,
        fix_host_bits=fix_host_bits,
    )
    if output == "objects":
        return records
    if output == "json":
        return records_to_json(records, include_validation=False)
    return records_to_csv(records, include_validation=False)


def _query_loaded(
    text: str,
    query: str,
    *,
    return_all: bool = False,
    include_longer: bool = False,
    output: str = "objects",
) -> QueryResult | str:
    _validate_output(output, ("objects", "json", "csv"))
    result = query_text(
        text,
        query,
        return_all=return_all,
        include_longer=include_longer,
    )
    if output == "objects":
        return result
    if output == "json":
        return query_to_json(result)
    return records_to_csv(list(result.matches), include_validation=False)


def _info_loaded(
    source: str,
    raw: bytes,
    text: str,
    content_type: str | None,
    *,
    output: str = "objects",
) -> GeoFeedInfo | str:
    _validate_output(output, ("objects", "json"))
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
        return info
    return info_to_json(info)


class GeoFeed:
    """Main object-oriented API for geofeed workflows."""

    def __init__(self, source: str, *, auto_load: bool = True):
        """Initialize a geofeed source and optionally load it immediately."""
        self.source = source
        self.raw: bytes | None = None
        self.content_type: str | None = None
        self.text: str | None = None

        if auto_load:
            self.reload()

    def reload(self) -> None:
        """Reload the source bytes and decoded text from disk or HTTP."""
        raw, content_type = load_input(self.source)
        self.raw = raw
        self.content_type = content_type
        # Parser and normalizer behavior strips UTF-8 BOM before processing.
        self.text = decode_text(raw, strip_bom=True)

    def _ensure_loaded(self) -> tuple[bytes, str]:
        if self.raw is None or self.text is None:
            self.reload()
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
        return _query_loaded(
            text,
            query,
            return_all=return_all,
            include_longer=include_longer,
            output=output,
        )

    def info(self, *, output: str = "objects") -> GeoFeedInfo | str:
        """Compute aggregate statistics for the current geofeed source."""
        records = self.parse(include_validation=False, output="objects")
        assert isinstance(records, list)
        raw, text = self._ensure_loaded()
        return _info_loaded(
            self.source,
            raw,
            text,
            self.content_type,
            output=output,
        )


__all__ = ["FetchError", "GeoFeed"]
