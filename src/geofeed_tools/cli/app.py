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
from geofeed_tools.loader import is_ip_or_prefix, source_kind
from geofeed_tools.logging import configure_cli_structlog, logger
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


class AddressFamily(StrEnum):
    """Filterable IP address families exposed by the filter command."""

    IPV4 = "ipv4"
    IPV6 = "ipv6"


SOURCE_HELP = (
    "Geofeed source: local file path, HTTP(S) URL, or IP/prefix "
    "(auto-discovered via RDAP)"
)
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
    """Shared --all option for query/doctor commands."""
    return typer.Option(False, "--all", help="Show all matches")


def _longer_option(typer):
    """Shared --longer option for query/doctor commands."""
    return typer.Option(
        False,
        "--longer",
        help="Include more-specific prefixes contained by the query",
    )


def _rdap_method_option(typer):
    """Shared --rdap-method option for the doctor command."""
    return typer.Option(
        RdapMethod.RDAP_ORG,
        "--rdap-method",
        help="RDAP lookup method: rdap.org (default) or iana-bootstrap",
    )


def _strict_option(typer):
    """Shared --strict option for the validate command (plain + hook modes)."""
    return typer.Option(
        False,
        "--strict",
        help="Fail on warnings as well as errors",
    )


def _load_geofeed(source: str, output_format: OutputFormat, typer, **kwargs) -> GeoFeed:
    """Construct a GeoFeed, rendering a friendly message on RDAP-discovery failure.

    Accepts the same ``source`` shapes as ``GeoFeed`` itself (file path, URL, or
    IP/prefix). When the IP/prefix discovery cannot find a published geofeed,
    emits a format-appropriate error and exits 1 instead of dumping a traceback.
    """
    logger.debug(
        "Loading geofeed: source=%s kind=%s options=%s",
        source,
        source_kind(source),
        kwargs,
    )
    try:
        return GeoFeed(source, **kwargs)
    except GeoFeedDiscoveryError as exc:
        logger.info(
            "Aborting CLI command: no published geofeed could be discovered for %s",
            exc.query,
        )
        _emit_source_discovery_error(exc, output_format)
        raise typer.Exit(code=1) from exc


def _emit_source_discovery_error(exc: GeoFeedDiscoveryError, output_format: OutputFormat) -> None:
    """Emit a discovery-failure message when an IP/prefix source can't be resolved."""
    logger.debug(
        "Emitting RDAP discovery failure to CLI: query=%s output_format=%s",
        exc.query,
        output_format.value,
    )
    if output_format is OutputFormat.JSON:
        import json

        print(json.dumps({"query": exc.query, "error": str(exc)}, indent=2))
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


def build_app():
    """Build and return the Typer application."""
    import typer as _typer

    app = _typer.Typer(help="GeoFeed tools CLI")
    _register_dump_command(app, _typer)
    _register_validate_command(app, _typer)
    _register_normalize_command(app, _typer)
    _register_filter_command(app, _typer)
    _register_query_command(app, _typer)
    _register_doctor_command(app, _typer)
    _register_info_command(app, _typer)
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
        geofeed = _load_geofeed(source, output_format, typer)
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
        strict: bool = _strict_option(typer),
        hook: bool = typer.Option(
            False,
            "--hook",
            help=(
                "Render hook-style output for CI/CD integration "
                "(machine-readable summary + issues on stderr)"
            ),
        ),
        show_issues: bool = typer.Option(
            True,
            "--show-issues/--no-issues",
            help="In --hook mode, print individual validation issues",
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
        """Validate a geofeed source and report issues (use --hook for CI/CD integration)."""
        configure_cli_structlog(verbose)
        geofeed = _load_geofeed(source, output_format, typer)
        report = geofeed.validate(
            check_sort=not no_sort_check,
            check_content_type=not no_content_type_check,
            check_aggregation=check_aggregation,
            output="objects",
        )
        assert isinstance(report, ValidationReport)

        if hook:
            render_hook(
                report,
                source,
                format=output_format.value,
                show_issues=show_issues,
                strict=strict,
            )
        else:
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
        geofeed = _load_geofeed(source, output_format, typer)

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


def _register_filter_command(app, typer) -> None:
    """Register the filter command."""

    @app.command("filter")
    def filter_command(
        source: str = _source_argument(typer),
        output_format: OutputFormat = _format_option(typer),
        prefix: str | None = typer.Option(
            None,
            "--prefix",
            help="Filter by CIDR prefix (exact unless --longer is set)",
        ),
        country: str | None = typer.Option(
            None,
            "--country",
            help="Filter by ISO 3166-1 alpha-2 country code (case-insensitive)",
        ),
        region: str | None = typer.Option(
            None,
            "--region",
            help="Filter by ISO 3166-2 subdivision code (case-insensitive)",
        ),
        city: str | None = typer.Option(
            None,
            "--city",
            help="Filter by city (case-insensitive)",
        ),
        postal_code: str | None = typer.Option(
            None,
            "--postal-code",
            help="Filter by postal code (case-insensitive)",
        ),
        family: AddressFamily | None = typer.Option(
            None,
            "--family",
            help="Restrict to one IP address family",
        ),
        prefix_length: int | None = typer.Option(
            None,
            "--prefix-length",
            help="Filter by prefix length (exact unless --longer is set)",
        ),
        include_longer: bool = typer.Option(
            False,
            "--longer",
            help=(
                "Match --prefix subnets contained by the supplied CIDR and "
                "--prefix-length values >= the supplied length"
            ),
        ),
        verbose: int = _verbose_option(typer),
    ) -> None:
        """Filter geofeed records by one or more fields (combined with AND)."""
        configure_cli_structlog(verbose)
        geofeed = _load_geofeed(source, output_format, typer)
        records = geofeed.filter(
            prefix=prefix,
            country=country,
            region=region,
            city=city,
            postal_code=postal_code,
            family=family.value if family is not None else None,
            prefix_length=prefix_length,
            include_longer=include_longer,
            output="objects",
        )
        assert isinstance(records, list)
        render_records(
            records,
            format=output_format.value,
            title=f"Filtered records ({len(records)})",
            include_validation=False,
        )


def _register_query_command(app, typer) -> None:
    """Register the query command."""

    @app.command("query")
    def query_command(
        source: str = _source_argument(typer),
        query: str | None = typer.Argument(
            None,
            help=(
                "IP address or CIDR prefix to look up. "
                "Optional when SOURCE is itself an IP/prefix; in that case the "
                "source value is also used as the query."
            ),
        ),
        output_format: OutputFormat = _format_option(typer),
        show_all: bool = _all_option(typer),
        include_longer: bool = _longer_option(typer),
        rdap_method: RdapMethod = _rdap_method_option(typer),
        verbose: int = _verbose_option(typer),
    ) -> None:
        """Query a geofeed by IP or prefix.

        Pass an IP/prefix as SOURCE to auto-discover the published geofeed via
        RDAP and search it — QUERY then defaults to the same value.
        """
        configure_cli_structlog(verbose)
        if query is None:
            if not is_ip_or_prefix(source):
                logger.debug(
                    "Rejecting query invocation: no QUERY provided and SOURCE %r is not an IP/prefix",
                    source,
                )
                raise typer.BadParameter(
                    "QUERY is required unless SOURCE is an IP address or CIDR prefix",
                )
            logger.info(
                "No QUERY provided; reusing SOURCE %r as the lookup target (IP/prefix source)",
                source,
            )
            query = source
        else:
            logger.debug(
                "Running query against geofeed: source=%s query=%s show_all=%s include_longer=%s",
                source,
                query,
                show_all,
                include_longer,
            )
        geofeed = _load_geofeed(
            source,
            output_format,
            typer,
            cache_query_index=False,
            rdap_method=rdap_method,
        )
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
        geofeed = _load_geofeed(source, output_format, typer)
        info = geofeed.info(top_n=top_n, output="objects")
        assert isinstance(info, GeoFeedInfo)
        render_info(info, format=output_format.value)


def main() -> None:
    """CLI entrypoint used by project scripts.

    With no arguments, prints the help text and exits 0 (same as ``--help``)
    instead of typer's default "Missing command" error.
    """
    _check_cli_deps()
    app = build_app()
    argv = sys.argv[1:]
    if not argv:
        argv = ["--help"]
    app(argv, standalone_mode=True)


# Re-exported for `from geofeed_tools.cli.app import doctor_to_json` if needed.
__all__ = ["OutputFormat", "build_app", "doctor_to_json", "main"]
