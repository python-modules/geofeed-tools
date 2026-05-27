"""Optional Typer-based command-line interface for geofeed_tools."""

from __future__ import annotations

import json
import sys
from enum import StrEnum
from pathlib import Path

from tabulate import tabulate

from geofeed_tools import GeoFeed, GeoFeedDiscoveryError
from geofeed_tools.doctor import render_doctor_text
from geofeed_tools.io_utils import doctor_to_json, report_to_json
from geofeed_tools.logging import configure_cli_structlog
from geofeed_tools.models import DoctorResult, GeofeedRecord, ValidationReport
from geofeed_tools.rdap import IANA_BOOTSTRAP_METHOD, RDAP_ORG_METHOD
from geofeed_tools.validate import render_validation_text

JSON_HELP = "Emit JSON report"
VERBOSE_HELP = "Increase verbosity (-v=INFO, -vv=DEBUG, -vvv=TRACE)"


class DumpFormat(StrEnum):
    """Supported output formats for the dump command."""

    JSON = "json"
    CSV = "csv"
    TABLE = "table"


class RdapMethod(StrEnum):
    """Supported RDAP lookup methods for doctor."""

    RDAP_ORG = RDAP_ORG_METHOD
    IANA_BOOTSTRAP = IANA_BOOTSTRAP_METHOD


def _require_cli_deps():
    """Import Typer lazily to keep CLI deps optional."""
    try:
        import typer
    except ImportError as exc:
        raise SystemExit("CLI dependencies are not installed. Install with: uv pip install '.[cli]'") from exc
    return typer


def build_app():
    """Build and return the Typer application."""
    typer = _require_cli_deps()
    app = typer.Typer(help="GeoFeed tools CLI")
    _register_dump_command(app, typer)
    _register_validate_command(app, typer)
    _register_normalize_command(app, typer)
    _register_query_command(app, typer)
    _register_doctor_command(app, typer)
    _register_lookup_command(app, typer)
    _register_info_command(app, typer)
    _register_hook_command(app, typer)
    return app


def _render_dump_table(
    records: list[GeofeedRecord],
    *,
    include_validation: bool,
) -> str:
    headers = ["Prefix", "Country", "Region", "City", "Postal code"]
    rows: list[list[str]] = []

    for record in records:
        row = [
            record.prefix,
            record.country,
            record.region,
            record.city,
            record.postal_code,
        ]
        if include_validation:
            row.extend(
                [
                    "true" if record.valid else "false",
                    "; ".join(record.validation_messages),
                ]
            )
        rows.append(row)

    if include_validation:
        headers.extend(["Valid", "Validation messages"])
    return tabulate(rows, headers=headers, tablefmt="github")


def _emit_query_payload(
    payload: str,
    *,
    output: str,
    query: str,
    empty_source: str,
    fail_on_empty_json: bool,
    typer,
) -> None:
    if output == "csv":
        if not payload.strip():
            print(f"no match for {query} in {empty_source}", file=sys.stderr)
            raise typer.Exit(code=1)
        print(payload, end="")
        return

    print(payload)
    if fail_on_empty_json and not json.loads(payload)["matches"]:
        raise typer.Exit(code=1)


def _register_dump_command(app, typer) -> None:
    """Register the dump command."""

    @app.command("dump")
    def dump_command(
        source: str,
        output_format: DumpFormat = typer.Option(
            DumpFormat.JSON,
            "--format",
            "-f",
            help="Output format: json (default), csv, or table",
        ),
        normalize_first: bool = typer.Option(
            False,
            "--normalize",
            help="Normalize records before dumping output",
        ),
        no_validation: bool = typer.Option(
            False,
            "--no-validation",
            help="Skip per-record validation annotations in JSON or table output",
        ),
        verbose: int = typer.Option(
            0,
            "-v",
            "--verbose",
            count=True,
            help=VERBOSE_HELP,
        ),
    ) -> None:
        """Dump geofeed records as JSON, geofeed CSV, or a table."""
        configure_cli_structlog(verbose)
        geofeed = GeoFeed(source)
        include_validation = not no_validation

        if output_format is DumpFormat.TABLE:
            records = geofeed.parse(
                output="objects",
                normalize=normalize_first,
                include_validation=include_validation,
            )
            assert isinstance(records, list)
            print(
                _render_dump_table(
                    records,
                    include_validation=include_validation,
                )
            )
            return

        if output_format is DumpFormat.CSV:
            payload = geofeed.parse(
                output="csv",
                normalize=normalize_first,
                include_validation=False,
            )
            assert isinstance(payload, str)
            print(payload, end="")
            return

        payload = geofeed.parse(
            output="json",
            normalize=normalize_first,
            include_validation=include_validation,
        )
        assert isinstance(payload, str)
        print(payload)


def _register_validate_command(app, typer) -> None:
    """Register the validate command."""

    @app.command("validate")
    def validate_command(
        source: str,
        json_output: bool = typer.Option(
            False,
            "--json",
            help=JSON_HELP,
        ),
        strict: bool = typer.Option(
            False,
            "--strict",
            help="Fail on warnings as well as errors",
        ),
        check_aggregation: bool = typer.Option(
            False,
            "--check-aggregation",
            help="Enable aggregation warning checks",
        ),
        no_sort_check: bool = typer.Option(
            False,
            "--no-sort-check",
            help="Disable sort-order warnings",
        ),
        no_content_type_check: bool = typer.Option(
            False,
            "--no-content-type-check",
            help="Disable content-type warnings for URL sources",
        ),
        verbose: int = typer.Option(
            0,
            "-v",
            "--verbose",
            count=True,
            help=VERBOSE_HELP,
        ),
    ) -> None:
        """Validate a geofeed source and report issues."""
        configure_cli_structlog(verbose)
        geofeed = GeoFeed(source)
        validate_options = {
            "check_sort": not no_sort_check,
            "check_content_type": not no_content_type_check,
            "check_aggregation": check_aggregation,
        }

        report = geofeed.validate(output="objects", **validate_options)
        assert isinstance(report, ValidationReport)

        payload = report_to_json(report) if json_output else render_validation_text(report)
        print(payload)

        if report.errors > 0 or (strict and report.warnings > 0):
            raise typer.Exit(code=1)


def _register_normalize_command(app, typer) -> None:
    """Register the normalize command."""

    @app.command("normalize")
    def normalize_command(
        source: str,
        output_file: str | None = typer.Option(
            None,
            "--output",
            "-o",
            help="Write normalized CSV to file",
        ),
        no_uppercase: bool = typer.Option(False, "--no-uppercase"),
        no_sort: bool = typer.Option(False, "--no-sort"),
        no_aggregate: bool = typer.Option(False, "--no-aggregate"),
        no_dedupe: bool = typer.Option(False, "--no-dedupe"),
        no_host_bit_fix: bool = typer.Option(False, "--no-host-bit-fix"),
        verbose: int = typer.Option(
            0,
            "-v",
            "--verbose",
            count=True,
            help=VERBOSE_HELP,
        ),
    ) -> None:
        """Normalize geofeed records and print or write canonical CSV."""
        configure_cli_structlog(verbose)
        geofeed = GeoFeed(source)
        csv_payload = geofeed.normalize(
            uppercase=not no_uppercase,
            sort=not no_sort,
            aggregate=not no_aggregate,
            dedupe=not no_dedupe,
            fix_host_bits=not no_host_bit_fix,
            output="csv",
        )
        assert isinstance(csv_payload, str)

        if output_file:
            Path(output_file).write_text(csv_payload, encoding="utf-8")
            return
        print(csv_payload, end="")


def _register_query_command(app, typer) -> None:
    """Register the query command."""

    @app.command("query")
    def query_command(
        source: str,
        query: str,
        show_all: bool = typer.Option(False, "--all", help="Show all matches"),
        include_longer: bool = typer.Option(
            False,
            "--longer",
            help="Include more-specific prefixes contained by the query",
        ),
        json_output: bool = typer.Option(False, "--json", help=JSON_HELP),
        verbose: int = typer.Option(
            0,
            "-v",
            "--verbose",
            count=True,
            help=VERBOSE_HELP,
        ),
    ) -> None:
        """Query a geofeed by IP or prefix."""
        configure_cli_structlog(verbose)
        geofeed = GeoFeed(source, cache_query_index=False)

        output = "json" if json_output else "csv"
        payload = geofeed.query(
            query,
            return_all=show_all,
            include_longer=include_longer,
            output=output,
        )
        assert isinstance(payload, str)
        _emit_query_payload(
            payload,
            output=output,
            query=query,
            empty_source=source,
            fail_on_empty_json=False,
            typer=typer,
        )


def _register_doctor_command(app, typer) -> None:
    """Register the doctor command."""

    @app.command("doctor")
    def doctor_command(
        query: str,
        show_all: bool = typer.Option(False, "--all", help="Show all matches"),
        include_longer: bool = typer.Option(
            False,
            "--longer",
            help="Include more-specific prefixes contained by the query",
        ),
        rdap_method: RdapMethod = typer.Option(
            RdapMethod.RDAP_ORG,
            "--rdap-method",
            help="RDAP lookup method: rdap.org (default) or iana-bootstrap",
        ),
        json_output: bool = typer.Option(False, "--json", help=JSON_HELP),
        verbose: int = typer.Option(
            0,
            "-v",
            "--verbose",
            count=True,
            help=VERBOSE_HELP,
        ),
    ) -> None:
        """Discover and query a published geofeed by IP or prefix."""
        configure_cli_structlog(verbose)
        result = GeoFeed.doctor(
            query,
            return_all=show_all,
            include_longer=include_longer,
            rdap_method=rdap_method,
            output="objects",
        )
        assert isinstance(result, DoctorResult)

        payload = doctor_to_json(result) if json_output else render_doctor_text(result)
        print(payload)

        if result.lookup.geofeed_url is None or not result.matches:
            raise typer.Exit(code=1)


def _register_lookup_command(app, typer) -> None:
    """Register the lookup command."""

    @app.command("lookup")
    def lookup_command(
        query: str,
        show_all: bool = typer.Option(False, "--all", help="Show all matches"),
        include_longer: bool = typer.Option(
            False,
            "--longer",
            help="Include more-specific prefixes contained by the query",
        ),
        rdap_method: RdapMethod = typer.Option(
            RdapMethod.RDAP_ORG,
            "--rdap-method",
            help="RDAP lookup method: rdap.org (default) or iana-bootstrap",
        ),
        json_output: bool = typer.Option(False, "--json", help=JSON_HELP),
        verbose: int = typer.Option(
            0,
            "-v",
            "--verbose",
            count=True,
            help=VERBOSE_HELP,
        ),
    ) -> None:
        """Discover a published geofeed via RDAP and query it by IP or prefix."""
        configure_cli_structlog(verbose)
        output = "json" if json_output else "csv"
        try:
            payload = GeoFeed.lookup(
                query,
                return_all=show_all,
                include_longer=include_longer,
                rdap_method=rdap_method,
                output=output,
            )
        except GeoFeedDiscoveryError as exc:
            print(str(exc), file=sys.stderr)
            raise typer.Exit(code=1) from exc
        assert isinstance(payload, str)
        _emit_query_payload(
            payload,
            output=output,
            query=query,
            empty_source="discovered geofeed",
            fail_on_empty_json=True,
            typer=typer,
        )


def _register_info_command(app, typer) -> None:
    """Register the info command."""

    @app.command("info")
    def info_command(
        source: str,
        json_output: bool = typer.Option(False, "--json", help=JSON_HELP),
        verbose: int = typer.Option(
            0,
            "-v",
            "--verbose",
            count=True,
            help=VERBOSE_HELP,
        ),
    ) -> None:
        """Show geofeed statistics."""
        configure_cli_structlog(verbose)
        geofeed = GeoFeed(source)
        output = "json" if json_output else "objects"
        info = geofeed.info(output=output)

        if isinstance(info, str):
            print(info)
            return

        print(f"Source: {info.source}\n")

        record_rows: list[list[object]] = [
            ["Total records", info.total_records],
            ["Unique prefixes", info.unique_prefixes],
            ["IPv4 records", info.ipv4_records],
            ["IPv6 records", info.ipv6_records],
            ["Duplicates", info.duplicates],
        ]
        print(tabulate(record_rows, headers=["Records", ""], tablefmt="github"))

        geo_rows: list[list[object]] = [
            ["Countries", info.unique_countries],
            ["Regions", info.unique_regions],
            ["Cities", info.unique_cities],
            ["Postal codes", info.unique_postal_codes],
        ]
        print()
        print(
            tabulate(
                geo_rows,
                headers=["Geographic coverage", "Unique"],
                tablefmt="github",
            )
        )

        validation_rows: list[list[object]] = [
            ["Errors", info.errors],
            ["Warnings", info.warnings],
        ]
        print()
        print(
            tabulate(
                validation_rows,
                headers=["Validation", ""],
                tablefmt="github",
            )
        )


def _register_hook_command(app, typer) -> None:
    """Register the hook command."""

    @app.command("hook")
    def hook_command(
        source: str,
        strict: bool = typer.Option(
            False,
            "--strict",
            help="Fail when warnings are present",
        ),
        show_issues: bool = typer.Option(
            True,
            "--show-issues/--no-issues",
            help="Print individual validation issues",
        ),
        verbose: int = typer.Option(
            0,
            "-v",
            "--verbose",
            count=True,
            help=VERBOSE_HELP,
        ),
    ) -> None:
        """Run validation and return hook-friendly exit codes."""
        configure_cli_structlog(verbose)
        geofeed = GeoFeed(source)
        report = geofeed.validate(output="objects")
        assert isinstance(report, ValidationReport)

        if show_issues:
            for issue in report.issues:
                typer.echo(issue.format(), err=True)
                if issue.raw_line is not None:
                    typer.echo(f"  > {issue.raw_line}", err=True)

        failed = report.errors > 0 or (strict and report.warnings > 0)
        if failed:
            msg = f"hook: FAIL — {report.errors} error(s), {report.warnings} warning(s) in {source}"
            typer.echo(msg, err=True)
            raise typer.Exit(code=1)
        typer.echo(
            f"hook: OK — {report.records} record(s), {report.warnings} warning(s) in {source}",
            err=True,
        )


def main() -> None:
    """CLI entrypoint used by project scripts."""
    app = build_app()
    app()
