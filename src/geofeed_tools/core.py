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


class GeoFeed:
    """Main object-oriented API for geofeed workflows."""

    _ERR_OUTPUT_JSON_CSV = "output must be one of: objects, json, csv"
    _ERR_OUTPUT_JSON_TEXT = "output must be one of: objects, json, text"
    _ERR_OUTPUT_JSON_ONLY = "output must be one of: objects, json"

    def __init__(self, source: str, *, auto_load: bool = True):
        """Initialize a geofeed source and optionally load it immediately."""
        self.source = source
        self.raw: bytes | None = None
        self.content_type: str | None = None
        self.text: str | None = None

        if auto_load:
            self.reload()

    @staticmethod
    def _validate_output(output: str, allowed: tuple[str, ...]) -> None:
        if output not in allowed:
            raise ValueError(f"output must be one of: {', '.join(allowed)}")

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
        self._validate_output(output, ("objects", "json", "csv"))
        raw, text = self._ensure_loaded()
        if normalize:
            records = normalize_records(text)
        else:
            records = parse_text(text)

        if include_validation:
            records = annotate_validity(
                records,
                source=self.source,
                raw=raw,
                content_type=self.content_type,
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

    def validate(
        self,
        *,
        check_sort: bool = True,
        check_content_type: bool = True,
        check_aggregation: bool = False,
        output: str = "objects",
    ) -> ValidationReport | str:
        """Validate the source bytes and optionally serialize the report."""
        self._validate_output(output, ("objects", "json", "text"))
        raw, _text = self._ensure_loaded()
        report = validate_bytes(
            raw,
            self.source,
            self.content_type,
            check_sort=check_sort,
            check_content_type=check_content_type,
            check_aggregation=check_aggregation,
        )

        if output == "objects":
            return report
        if output == "json":
            return report_to_json(report)
        return render_validation_text(report)

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
        self._validate_output(output, ("objects", "json", "csv"))
        _raw, text = self._ensure_loaded()
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

    def query(
        self,
        query: str,
        *,
        return_all: bool = False,
        include_longer: bool = False,
        output: str = "objects",
    ) -> QueryResult | str:
        """Query the source for an IP or prefix and return matching records."""
        self._validate_output(output, ("objects", "json", "csv"))
        _raw, text = self._ensure_loaded()
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
        return records_to_csv(
            list(result.matches),
            include_validation=False,
        )

    def info(self, *, output: str = "objects") -> GeoFeedInfo | str:
        """Compute aggregate statistics for the current geofeed source."""
        self._validate_output(output, ("objects", "json"))
        records = self.parse(include_validation=False, output="objects")
        assert isinstance(records, list)
        report = self.validate(output="objects")
        assert isinstance(report, ValidationReport)
        info = build_info(self.source, records, report)

        if output == "objects":
            return info
        return info_to_json(info)


__all__ = ["FetchError", "GeoFeed"]
