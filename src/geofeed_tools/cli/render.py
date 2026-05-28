"""Format dispatchers for CLI output.

Every renderer accepts a ``format`` string (one of ``rich``, ``plain``, ``grep``,
``json``) and routes to a per-format implementation. Rich is imported lazily so
``app.py`` can still emit a friendly "missing CLI extras" message.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from geofeed_tools.doctor import render_doctor_text
from geofeed_tools.io_utils import (
    doctor_to_json,
    info_to_json,
    query_to_json,
    records_to_csv,
    records_to_json,
    report_to_json,
)
from geofeed_tools.models import (
    DoctorResult,
    GeoFeedInfo,
    GeofeedRecord,
    QueryResult,
    ValidationReport,
)
from geofeed_tools.validate import render_validation_text

if TYPE_CHECKING:
    from rich.table import Table

FORMAT_RICH = "rich"
FORMAT_PLAIN = "plain"
FORMAT_GREP = "grep"
FORMAT_JSON = "json"
ALL_FORMATS: tuple[str, ...] = (FORMAT_RICH, FORMAT_PLAIN, FORMAT_GREP, FORMAT_JSON)

_SEVERITY_STYLE = {
    "error": "bold red",
    "warning": "bold yellow",
    "info": "bold cyan",
}


# ──────────────────────────────────────────────────────────────────────────
# Public dispatchers
# ──────────────────────────────────────────────────────────────────────────


def render_validation(report: ValidationReport, *, format: str, show_raw: bool = False) -> None:
    """Render a ValidationReport in the requested format."""
    if format == FORMAT_JSON:
        print(report_to_json(report))
    elif format == FORMAT_GREP:
        _validation_grep(report)
    elif format == FORMAT_PLAIN:
        print(render_validation_text(report))
    else:
        _validation_rich(report, show_raw=show_raw)


def render_records(
    records: list[GeofeedRecord],
    *,
    format: str,
    title: str = "Records",
    include_validation: bool = False,
) -> None:
    """Render a list of GeofeedRecord in the requested format."""
    if format == FORMAT_JSON:
        print(records_to_json(records, include_validation=include_validation))
    elif format == FORMAT_GREP:
        print(records_to_csv(records, include_validation=False), end="")
    elif format == FORMAT_PLAIN:
        _records_plain(records, title=title, include_validation=include_validation)
    else:
        _records_rich(records, title=title, include_validation=include_validation)


def render_query(result: QueryResult, *, format: str, source_label: str) -> None:
    """Render a QueryResult in the requested format."""
    if format == FORMAT_JSON:
        print(query_to_json(result))
        return
    matches = list(result.matches)
    label = "match" if len(matches) == 1 else "matches"
    title = f"{source_label} — {result.query}  ({len(matches)} {label})"
    render_records(matches, format=format, title=title, include_validation=False)


def render_info(info: GeoFeedInfo, *, format: str) -> None:
    """Render a GeoFeedInfo summary in the requested format."""
    if format == FORMAT_JSON:
        print(info_to_json(info))
    elif format == FORMAT_GREP:
        _info_grep(info)
    elif format == FORMAT_PLAIN:
        _info_plain(info)
    else:
        _info_rich(info)


def render_doctor(result: DoctorResult, *, format: str) -> None:
    """Render a DoctorResult in the requested format."""
    if format == FORMAT_JSON:
        print(doctor_to_json(result))
    elif format == FORMAT_GREP:
        # Matches only — the diagnostic metadata is dropped for grep mode.
        print(records_to_csv(result.matches, include_validation=False), end="")
    elif format == FORMAT_PLAIN:
        print(render_doctor_text(result))
    else:
        _doctor_rich(result)


def render_hook(
    report: ValidationReport,
    source: str,
    *,
    format: str,
    show_issues: bool,
    strict: bool,
) -> bool:
    """Render hook output and return True if the hook should fail."""
    failed = report.errors > 0 or (strict and report.warnings > 0)
    if format == FORMAT_JSON:
        print(report_to_json(report))
        return failed
    if format == FORMAT_GREP:
        # path:line:severity:code:message — stdout only, no summary.
        if show_issues:
            for issue in report.issues:
                line = "" if issue.line is None else str(issue.line)
                print(f"{source}:{line}:{issue.severity}:{issue.code}:{issue.message}")
        return failed
    if format == FORMAT_PLAIN:
        _hook_plain(report, source, show_issues=show_issues, failed=failed)
        return failed
    _hook_rich(report, source, show_issues=show_issues, failed=failed)
    return failed


# ──────────────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────────────


def _validation_grep(report: ValidationReport) -> None:
    for issue in report.issues:
        line = "" if issue.line is None else str(issue.line)
        print(f"{report.source}:{line}:{issue.severity}:{issue.code}:{issue.message}")


def _validation_rich(report: ValidationReport, *, show_raw: bool) -> None:
    from rich.box import ROUNDED
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text

    console = Console()
    error_color = "red" if report.errors else "green"
    warning_color = "yellow" if report.warnings else "green"
    verdict = "[bold green]VALID[/bold green]" if report.valid else "[bold red]INVALID[/bold red]"
    overview = _kv_grid(
        [
            ("Records", _format_count(report.records)),
            ("Errors", f"[{error_color}]{_format_count(report.errors)}[/{error_color}]"),
            ("Warnings", f"[{warning_color}]{_format_count(report.warnings)}[/{warning_color}]"),
            ("Verdict", verdict),
        ]
    )
    border = "green" if report.valid else "red"
    console.print(
        Panel(
            overview,
            title=f"[bold]Validation —[/bold] [magenta]{report.source}[/magenta]",
            border_style=border,
            box=ROUNDED,
            padding=(1, 2),
        )
    )

    if not report.issues:
        console.print()
        console.print(Text("no issues found", style="bold green"))
        return

    console.print()
    console.print(
        Panel(
            _issues_table_rich(report, show_raw=show_raw),
            title=f"Issues ({len(report.issues)})",
            border_style="blue",
            box=ROUNDED,
            padding=(1, 2),
        )
    )


# ──────────────────────────────────────────────────────────────────────────
# Records
# ──────────────────────────────────────────────────────────────────────────


def _records_rich(records: list[GeofeedRecord], *, title: str, include_validation: bool) -> None:
    from rich.box import ROUNDED
    from rich.console import Console
    from rich.table import Table
    from rich.text import Text

    console = Console()
    if not records:
        console.print(Text(title, style="bold blue"))
        console.print(Text("(none)", style="dim italic"))
        return

    table = Table(
        title=title,
        title_style="bold blue",
        box=ROUNDED,
        border_style="blue",
        header_style="bold blue",
        expand=False,
    )
    table.add_column("Prefix", style="white", no_wrap=True)
    table.add_column("Country")
    table.add_column("Region")
    table.add_column("City")
    table.add_column("Postal")
    if include_validation:
        table.add_column("Valid", no_wrap=True)
        table.add_column("Messages", overflow="fold")

    for record in records:
        row: list = [record.prefix, record.country, record.region, record.city, record.postal_code]
        if include_validation:
            row.append(Text("✓", style="green") if record.valid else Text("✗", style="red"))
            row.append("; ".join(record.validation_messages))
        table.add_row(*row)
    console.print(table)


def _records_plain(records: list[GeofeedRecord], *, title: str, include_validation: bool) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console(no_color=True, highlight=False)
    print(title)
    print()
    if not records:
        print("(none)")
        return

    table = Table(box=None, show_header=True, show_edge=False, padding=(0, 2), pad_edge=False)
    table.add_column("Prefix", no_wrap=True)
    table.add_column("Country")
    table.add_column("Region")
    table.add_column("City")
    table.add_column("Postal")
    if include_validation:
        table.add_column("Valid", no_wrap=True)
        table.add_column("Messages", overflow="fold")

    for record in records:
        row = [record.prefix, record.country, record.region, record.city, record.postal_code]
        if include_validation:
            row.append("yes" if record.valid else "no")
            row.append("; ".join(record.validation_messages))
        table.add_row(*row)
    console.print(table)


# ──────────────────────────────────────────────────────────────────────────
# Info
# ──────────────────────────────────────────────────────────────────────────


def _info_grep(info: GeoFeedInfo) -> None:
    pairs = [
        ("source", info.source),
        ("total_records", info.total_records),
        ("unique_prefixes", info.unique_prefixes),
        ("ipv4_records", info.ipv4_records),
        ("ipv6_records", info.ipv6_records),
        ("unique_countries", info.unique_countries),
        ("unique_regions", info.unique_regions),
        ("unique_cities", info.unique_cities),
        ("unique_postal_codes", info.unique_postal_codes),
        ("duplicates", info.duplicates),
        ("errors", info.errors),
        ("warnings", info.warnings),
    ]
    for key, value in pairs:
        print(f"{key}={value}")


def _info_plain(info: GeoFeedInfo) -> None:
    print(f"Geofeed info — {info.source}")
    print()
    sections: list[tuple[str, list[tuple[str, int]]]] = [
        (
            "Records",
            [
                ("Total records", info.total_records),
                ("Unique prefixes", info.unique_prefixes),
                ("IPv4 records", info.ipv4_records),
                ("IPv6 records", info.ipv6_records),
                ("Duplicates", info.duplicates),
            ],
        ),
        (
            "Geography",
            [
                ("Countries", info.unique_countries),
                ("Regions", info.unique_regions),
                ("Cities", info.unique_cities),
                ("Postal codes", info.unique_postal_codes),
            ],
        ),
        (
            "Validation",
            [
                ("Errors", info.errors),
                ("Warnings", info.warnings),
            ],
        ),
    ]
    for index, (heading, rows) in enumerate(sections):
        if index:
            print()
        print(f"{heading}:")
        key_width = max(len(key) for key, _ in rows)
        for key, value in rows:
            print(f"  {key.ljust(key_width)}  {_format_count(value)}")


def _info_rich(info: GeoFeedInfo) -> None:
    from rich.box import ROUNDED
    from rich.console import Console, Group
    from rich.panel import Panel
    from rich.text import Text

    console = Console()
    records_grid = _kv_grid(
        [
            ("Total records", _format_count(info.total_records)),
            ("Unique prefixes", _format_count(info.unique_prefixes)),
            ("IPv4 records", _format_count(info.ipv4_records)),
            ("IPv6 records", _format_count(info.ipv6_records)),
            ("Duplicates", _format_count(info.duplicates)),
        ]
    )
    geo_grid = _kv_grid(
        [
            ("Countries", _format_count(info.unique_countries)),
            ("Regions", _format_count(info.unique_regions)),
            ("Cities", _format_count(info.unique_cities)),
            ("Postal codes", _format_count(info.unique_postal_codes)),
        ],
        key_style="bold magenta",
    )
    error_color = "red" if info.errors else "green"
    warning_color = "yellow" if info.warnings else "green"
    validation_grid = _kv_grid(
        [
            ("Errors", f"[{error_color}]{_format_count(info.errors)}[/{error_color}]"),
            ("Warnings", f"[{warning_color}]{_format_count(info.warnings)}[/{warning_color}]"),
        ],
        key_style="bold yellow",
    )

    body = Group(
        Text("Records", style="bold underline"),
        records_grid,
        Text(),
        Text("Geography", style="bold underline"),
        geo_grid,
        Text(),
        Text("Validation", style="bold underline"),
        validation_grid,
    )
    console.print(
        Panel(
            body,
            title=f"[bold]Geofeed info —[/bold] [magenta]{info.source}[/magenta]",
            border_style="cyan",
            box=ROUNDED,
            padding=(1, 2),
        )
    )


# ──────────────────────────────────────────────────────────────────────────
# Doctor
# ──────────────────────────────────────────────────────────────────────────


def _doctor_rich(result: DoctorResult) -> None:
    from rich.box import ROUNDED
    from rich.console import Console, Group
    from rich.panel import Panel
    from rich.text import Text
    from rich.tree import Tree

    console = Console()
    lookup = result.lookup

    overview_rows: list[tuple[str, str]] = [
        ("Lookup strategy", lookup.lookup_strategy),
        ("RDAP method", lookup.rdap_method),
        ("RDAP query", lookup.rdap_query),
        ("Initial URL", lookup.bootstrap_url),
    ]
    if lookup.bootstrap_source_url is not None:
        overview_rows.append(("Bootstrap source", lookup.bootstrap_source_url))
    if lookup.referring_handle is not None:
        overview_rows.append(("Referring handle", lookup.referring_handle))
    if lookup.referring_range is not None:
        overview_rows.append(("Referring range", lookup.referring_range))

    console.print(
        Panel(
            _kv_grid(overview_rows),
            title=f"[bold]Doctor —[/bold] [magenta]{result.query}[/magenta]",
            border_style="cyan",
            box=ROUNDED,
            padding=(1, 2),
        )
    )

    if lookup.resolved_urls:
        tree = Tree("[bold]RDAP trace[/bold]", guide_style="dim")
        for url in lookup.resolved_urls:
            tree.add(f"[link={url}]{url}[/link]")
        console.print(tree)
        console.print()

    if lookup.geofeed_url is not None:
        discovery_rows: list[tuple[str, str]] = [
            ("Geofeed URL", f"[link={lookup.geofeed_url}]{lookup.geofeed_url}[/link]"),
        ]
        if lookup.geofeed_discovered_via is not None:
            discovery_rows.append(("Discovered via", lookup.geofeed_discovered_via))
        if lookup.geofeed_reference_url is not None:
            discovery_rows.append(("Reference object", lookup.geofeed_reference_url))
        body = Group(
            Text("✓ geofeed published", style="bold green"),
            Text(),
            _kv_grid(discovery_rows, key_style="bold green"),
        )
        console.print(Panel(body, title="Geofeed discovery", border_style="green", box=ROUNDED, padding=(1, 2)))
    else:
        console.print(
            Panel(
                Text("✗ no geofeed reference published for this range", style="bold yellow"),
                title="Geofeed discovery",
                border_style="yellow",
                box=ROUNDED,
                padding=(1, 2),
            )
        )

    console.print()
    title = f"Matches ({len(result.matches)})" if result.matches else "Matches"
    _records_rich(list(result.matches), title=title, include_validation=False)


# ──────────────────────────────────────────────────────────────────────────
# Hook
# ──────────────────────────────────────────────────────────────────────────


def _hook_rich(report: ValidationReport, source: str, *, show_issues: bool, failed: bool) -> None:
    from rich.box import ROUNDED
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text

    console = Console(stderr=True)
    if show_issues and report.issues:
        console.print(
            Panel(
                _issues_table_rich(report, show_raw=True),
                title=f"Issues ({len(report.issues)})",
                border_style="red" if failed else "yellow",
                box=ROUNDED,
                padding=(1, 2),
            )
        )
    if failed:
        console.print(
            Text(
                f"✗ hook FAIL — {report.errors} error(s), {report.warnings} warning(s) in {source}",
                style="bold red",
            )
        )
    else:
        console.print(
            Text(
                f"✓ hook OK — {report.records} record(s), {report.warnings} warning(s) in {source}",
                style="bold green",
            )
        )


def _hook_plain(report: ValidationReport, source: str, *, show_issues: bool, failed: bool) -> None:
    import sys

    if show_issues:
        for issue in report.issues:
            print(issue.format(), file=sys.stderr)
            if issue.raw_line is not None:
                print(f"  > {issue.raw_line}", file=sys.stderr)
    if failed:
        print(
            f"hook: FAIL — {report.errors} error(s), {report.warnings} warning(s) in {source}",
            file=sys.stderr,
        )
    else:
        print(
            f"hook: OK — {report.records} record(s), {report.warnings} warning(s) in {source}",
            file=sys.stderr,
        )


# ──────────────────────────────────────────────────────────────────────────
# Shared building blocks
# ──────────────────────────────────────────────────────────────────────────


def _kv_grid(rows: list[tuple[str, str]], *, key_style: str = "bold cyan") -> Table:
    from rich.table import Table

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style=key_style, justify="right", no_wrap=True)
    grid.add_column(overflow="fold")
    for key, value in rows:
        grid.add_row(key, value)
    return grid


def _issues_table_rich(report: ValidationReport, *, show_raw: bool) -> Table:
    from rich.box import ROUNDED
    from rich.table import Table
    from rich.text import Text

    table = Table(box=ROUNDED, border_style="blue", header_style="bold blue", expand=False)
    table.add_column("Severity", no_wrap=True)
    table.add_column("Line", justify="right", no_wrap=True)
    table.add_column("Code", no_wrap=True)
    table.add_column("Message", overflow="fold")
    if show_raw:
        table.add_column("Raw line", overflow="fold", style="dim")

    for issue in report.issues:
        severity_style = _SEVERITY_STYLE.get(issue.severity, "white")
        row: list = [
            Text(issue.severity.upper(), style=severity_style),
            "" if issue.line is None else str(issue.line),
            issue.code,
            issue.message,
        ]
        if show_raw:
            row.append(issue.raw_line or "")
        table.add_row(*row)
    return table


def _format_count(value: int) -> str:
    return f"{value:,}"
