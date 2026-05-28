"""Optional Typer-based command-line interface for geofeed_tools."""

from __future__ import annotations

import sys
from enum import StrEnum
from pathlib import Path

from geofeed_tools import GeoFeed, GeoFeedDiscoveryError
from geofeed_tools.cli.render import (
    ALL_FORMATS,
    FORMAT_GREP,
    FORMAT_JSON,
    FORMAT_PLAIN,
    FORMAT_RICH,
    render_doctor,
    render_hook,
    render_info,
    render_query,
    render_records,
    render_validation,
)
from geofeed_tools.info import DEFAULT_TOP_N
from geofeed_tools.io_utils import doctor_to_json
from geofeed_tools.logging import configure_cli_structlog
from geofeed_tools.models import DoctorResult, GeoFeedInfo, QueryResult, ValidationReport
from geofeed_tools.rdap import IANA_BOOTSTRAP_METHOD, RDAP_ORG_METHOD

_CLI_EXTRAS = ("typer", "structlog", "rich")
_MISSING_CLI_DEPS: list[str] = []
for _dep in _CLI_EXTRAS:
    try:
        __import__(_dep)
    except ImportError:
        _MISSING_CLI_DEPS.append(_dep)


def _check_cli_deps() -> None:
    """Emit a helpful error and exit when CLI extras are not installed."""
    if _MISSING_CLI_DEPS:
        print(
            "geofeed-tools CLI requires optional dependencies that are not installed.\n"
            f"  Missing: {', '.join(_MISSING_CLI_DEPS)}\n"
            "\n"
            "Install the CLI extras with:\n"
            "  pip install 'geofeed-tools[cli]'\n"
            "  uv pip install 'geofeed-tools[cli]'",
            file=sys.stderr,
        )
        sys.exit(1)


VERBOSE_HELP = "Increase verbosity (-v=INFO, -vv=DEBUG, -vvv=TRACE)"
FORMAT_HELP = "Output format: " + ", ".join(ALL_FORMATS) + " (default: rich)"


class OutputFormat(StrEnum):
    """Supported CLI output formats; default is RICH for every command."""

    RICH = FORMAT_RICH
    PLAIN = FORMAT_PLAIN
    GREP = FORMAT_GREP
    JSON = FORMAT_JSON


class RdapMethod(StrEnum):
    """Supported RDAP lookup methods for doctor."""

    RDAP_ORG = RDAP_ORG_METHOD
    IANA_BOOTSTRAP = IANA_BOOTSTRAP_METHOD


SOURCE_HELP = "Local file path or HTTP(S) URL of the geofeed source"
QUERY_HELP = "IP address or CIDR prefix to look up"


def _source_argument(typer):
    """Shared SOURCE positional argument for commands that load a geofeed."""
    return typer.Argument(..., help=SOURCE_HELP)


def _query_argument(typer):
    """Shared QUERY positional argument for IP/CIDR lookups."""
    return typer.Argument(..., help=QUERY_HELP)


def _verbose_option(typer):
    """Shared --verbose/-v option."""
    return typer.Option(0, "-v", "--verbose", count=True, help=VERBOSE_HELP)


def _format_option(typer):
    """Shared --format/-f option for output mode selection."""
    return typer.Option(OutputFormat.RICH, "--format", "-f", help=FORMAT_HELP)


def _all_option(typer):
    """Shared --all option for query/doctor/lookup commands."""
    return typer.Option(False, "--all", help="Show all matches")


def _longer_option(typer):
    """Shared --longer option for query/doctor/lookup commands."""
    return typer.Option(
        False,
        "--longer",
        help="Include more-specific prefixes contained by the query",
    )


def _rdap_method_option(typer):
    """Shared --rdap-method option for doctor/lookup commands."""
    return typer.Option(
        RdapMethod.RDAP_ORG,
        "--rdap-method",
        help="RDAP lookup method: rdap.org (default) or iana-bootstrap",
    )


def build_app():
    """Build and return the Typer application."""
    import typer as _typer

    app = _typer.Typer(help="GeoFeed tools CLI")
    _register_dump_command(app, _typer)
    _register_validate_command(app, _typer)
    _register_normalize_command(app, _typer)
    _register_query_command(app, _typer)
    _register_doctor_command(app, _typer)
    _register_lookup_command(app, _typer)
    _register_info_command(app, _typer)
    _register_hook_command(app, _typer)
    return app


def _register_dump_command(app, typer) -> None:
    """Register the dump command."""

    @app.command("dump")
    def dump_command(
        source: str = _source_argument(typer),
        output_format: OutputFormat = _format_option(typer),
        normalize_first: bool = typer.Option(
            False,
            "--normalize",
            help="Normalize records before dumping output",
        ),
        no_validation: bool = typer.Option(
            False,
            "--no-validation",
            help="Skip per-record validation annotations in rich/plain/json output",
        ),
        verbose: int = _verbose_option(typer),
    ) -> None:
        """Dump geofeed records in the chosen format."""
        configure_cli_structlog(verbose)
        geofeed = GeoFeed(source)
        include_validation = not no_validation

        records = geofeed.parse(
            output="objects",
            normalize=normalize_first,
            include_validation=include_validation,
        )
        assert isinstance(records, list)
        render_records(
            records,
            format=output_format.value,
            title=f"Records ({len(records)})",
            include_validation=include_validation,
        )


def _register_validate_command(app, typer) -> None:
    """Register the validate command."""

    @app.command("validate")
    def validate_command(
        source: str = _source_argument(typer),
        output_format: OutputFormat = _format_option(typer),
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
        verbose: int = _verbose_option(typer),
    ) -> None:
        """Validate a geofeed source and report issues."""
        configure_cli_structlog(verbose)
        geofeed = GeoFeed(source)
        report = geofeed.validate(
            check_sort=not no_sort_check,
            check_content_type=not no_content_type_check,
            check_aggregation=check_aggregation,
            output="objects",
        )
        assert isinstance(report, ValidationReport)

        render_validation(report, format=output_format.value)

        if report.errors > 0 or (strict and report.warnings > 0):
            raise typer.Exit(code=1)


def _register_normalize_command(app, typer) -> None:
    """Register the normalize command."""

    @app.command("normalize")
    def normalize_command(
        source: str = _source_argument(typer),
        output_format: OutputFormat = _format_option(typer),
        output_file: str | None = typer.Option(
            None,
            "--output",
            "-o",
            help="Write canonical CSV to a file (forces --format grep)",
        ),
        no_uppercase: bool = typer.Option(False, "--no-uppercase"),
        no_sort: bool = typer.Option(False, "--no-sort"),
        no_aggregate: bool = typer.Option(False, "--no-aggregate"),
        no_dedupe: bool = typer.Option(False, "--no-dedupe"),
        no_host_bit_fix: bool = typer.Option(False, "--no-host-bit-fix"),
        verbose: int = _verbose_option(typer),
    ) -> None:
        """Normalize geofeed records and emit them in the chosen format."""
        configure_cli_structlog(verbose)
        geofeed = GeoFeed(source)

        if output_file:
            csv_payload = geofeed.normalize(
                uppercase=not no_uppercase,
                sort=not no_sort,
                aggregate=not no_aggregate,
                dedupe=not no_dedupe,
                fix_host_bits=not no_host_bit_fix,
                output="csv",
            )
            assert isinstance(csv_payload, str)
            Path(output_file).write_text(csv_payload, encoding="utf-8")
            return

        records = geofeed.normalize(
            uppercase=not no_uppercase,
            sort=not no_sort,
            aggregate=not no_aggregate,
            dedupe=not no_dedupe,
            fix_host_bits=not no_host_bit_fix,
            output="objects",
        )
        assert isinstance(records, list)
        render_records(
            records,
            format=output_format.value,
            title=f"Normalized records ({len(records)})",
            include_validation=False,
        )


def _register_query_command(app, typer) -> None:
    """Register the query command."""

    @app.command("query")
    def query_command(
        source: str = _source_argument(typer),
        query: str = _query_argument(typer),
        output_format: OutputFormat = _format_option(typer),
        show_all: bool = _all_option(typer),
        include_longer: bool = _longer_option(typer),
        verbose: int = _verbose_option(typer),
    ) -> None:
        """Query a geofeed by IP or prefix."""
        configure_cli_structlog(verbose)
        geofeed = GeoFeed(source, cache_query_index=False)
        result = geofeed.query(
            query,
            return_all=show_all,
            include_longer=include_longer,
            output="objects",
        )
        assert isinstance(result, QueryResult)
        render_query(result, format=output_format.value, source_label="Query")

        if output_format is OutputFormat.JSON:
            # JSON conveys empty matches as data — no exit code change.
            return
        if not result.matches:
            raise typer.Exit(code=1)


def _register_doctor_command(app, typer) -> None:
    """Register the doctor command."""

    @app.command("doctor")
    def doctor_command(
        query: str = _query_argument(typer),
        output_format: OutputFormat = _format_option(typer),
        show_all: bool = _all_option(typer),
        include_longer: bool = _longer_option(typer),
        rdap_method: RdapMethod = _rdap_method_option(typer),
        verbose: int = _verbose_option(typer),
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
        render_doctor(result, format=output_format.value)

        if result.lookup.geofeed_url is None or not result.matches:
            raise typer.Exit(code=1)


def _register_lookup_command(app, typer) -> None:
    """Register the lookup command."""

    @app.command("lookup")
    def lookup_command(
        query: str = _query_argument(typer),
        output_format: OutputFormat = _format_option(typer),
        show_all: bool = _all_option(typer),
        include_longer: bool = _longer_option(typer),
        rdap_method: RdapMethod = _rdap_method_option(typer),
        verbose: int = _verbose_option(typer),
    ) -> None:
        """Discover a published geofeed via RDAP and query it by IP or prefix."""
        configure_cli_structlog(verbose)
        try:
            result = GeoFeed.lookup(
                query,
                return_all=show_all,
                include_longer=include_longer,
                rdap_method=rdap_method,
                output="objects",
            )
        except GeoFeedDiscoveryError as exc:
            _emit_discovery_error(exc, output_format)
            raise typer.Exit(code=1) from exc

        assert isinstance(result, QueryResult)
        render_query(result, format=output_format.value, source_label="Lookup")

        # lookup always exits 1 when no records were matched, including JSON
        # mode (the discovery half of the workflow is the point of the command).
        if not result.matches:
            raise typer.Exit(code=1)


def _emit_discovery_error(exc: GeoFeedDiscoveryError, output_format: OutputFormat) -> None:
    """Emit a discovery-failure message in a format-appropriate way."""
    if output_format is OutputFormat.JSON:
        from geofeed_tools.io_utils import query_to_json

        # Synthesise an empty QueryResult so the JSON shape is stable.
        empty = QueryResult(query=exc.query, matches=())
        print(query_to_json(empty))
        return
    if output_format is OutputFormat.GREP:
        # grep mode is silent on failure; the caller reads the exit code.
        return
    if output_format is OutputFormat.PLAIN:
        print(str(exc), file=sys.stderr)
        return
    from rich.console import Console
    from rich.text import Text

    Console(stderr=True).print(Text(str(exc), style="bold yellow"))


def _register_info_command(app, typer) -> None:
    """Register the info command."""

    @app.command("info")
    def info_command(
        source: str = _source_argument(typer),
        output_format: OutputFormat = _format_option(typer),
        top_n: int = typer.Option(
            DEFAULT_TOP_N,
            "--top-n",
            "-n",
            help="Limit the size of top-region / top-city breakdowns",
        ),
        verbose: int = _verbose_option(typer),
    ) -> None:
        """Show detailed geofeed info: counts, geography, per-country breakdown, normalize preview."""
        configure_cli_structlog(verbose)
        geofeed = GeoFeed(source)
        info = geofeed.info(top_n=top_n, output="objects")
        assert isinstance(info, GeoFeedInfo)
        render_info(info, format=output_format.value)


def _register_hook_command(app, typer) -> None:
    """Register the hook command."""

    @app.command("hook")
    def hook_command(
        source: str = _source_argument(typer),
        output_format: OutputFormat = _format_option(typer),
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
        verbose: int = _verbose_option(typer),
    ) -> None:
        """Run validation and return hook-friendly exit codes."""
        configure_cli_structlog(verbose)
        geofeed = GeoFeed(source)
        report = geofeed.validate(output="objects")
        assert isinstance(report, ValidationReport)

        failed = render_hook(
            report,
            source,
            format=output_format.value,
            show_issues=show_issues,
            strict=strict,
        )
        if failed:
            raise typer.Exit(code=1)


def main() -> None:
    """CLI entrypoint used by project scripts."""
    _check_cli_deps()
    app = build_app()
    app()


# Re-exported for `from geofeed_tools.cli.app import doctor_to_json` if needed.
__all__ = ["OutputFormat", "build_app", "doctor_to_json", "main"]
