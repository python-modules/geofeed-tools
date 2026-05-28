"""Renderers for ``ValidationReport`` and hook output."""

from __future__ import annotations

from geofeed_tools.io_utils import report_to_json
from geofeed_tools.models import ValidationReport
from geofeed_tools.validate import render_validation_text

from ._helpers import (
    FORMAT_GREP,
    FORMAT_JSON,
    FORMAT_PLAIN,
    format_count,
    issues_table_rich,
    kv_grid,
)


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
    overview = kv_grid(
        [
            ("Records", format_count(report.records)),
            ("Errors", f"[{error_color}]{format_count(report.errors)}[/{error_color}]"),
            ("Warnings", f"[{warning_color}]{format_count(report.warnings)}[/{warning_color}]"),
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
            issues_table_rich(report, show_raw=show_raw),
            title=f"Issues ({len(report.issues)})",
            border_style="blue",
            box=ROUNDED,
            padding=(1, 2),
        )
    )


def _hook_rich(report: ValidationReport, source: str, *, show_issues: bool, failed: bool) -> None:
    from rich.box import ROUNDED
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text

    console = Console(stderr=True)
    if show_issues and report.issues:
        console.print(
            Panel(
                issues_table_rich(report, show_raw=True),
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


__all__ = ["render_hook", "render_validation"]
