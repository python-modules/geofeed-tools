"""Shared helpers for CLI rendering modules.

Includes format constants, rich-specific building blocks (grids, severity
styling, issues tables), and import-time aliases for the library's count
formatters so every renderer reaches for the same helpers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from geofeed_tools.info_render import format_count, signed_delta
from geofeed_tools.models import ValidationReport

if TYPE_CHECKING:
    from rich.table import Table

FORMAT_RICH = "rich"
FORMAT_PLAIN = "plain"
FORMAT_GREP = "grep"
FORMAT_JSON = "json"
ALL_FORMATS: tuple[str, ...] = (FORMAT_RICH, FORMAT_PLAIN, FORMAT_GREP, FORMAT_JSON)

SEVERITY_STYLE = {
    "error": "bold red",
    "warning": "bold yellow",
    "info": "bold cyan",
}


def kv_grid(rows: list[tuple[str, str]], *, key_style: str = "bold cyan") -> Table:
    """Build a two-column rich grid for label/value pairs."""
    from rich.table import Table

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style=key_style, justify="right", no_wrap=True)
    grid.add_column(overflow="fold")
    for key, value in rows:
        grid.add_row(key, value)
    return grid


def issues_table_rich(report: ValidationReport, *, show_raw: bool) -> Table:
    """Build a rich Table listing validation issues, optionally with raw lines."""
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
        severity_style = SEVERITY_STYLE.get(issue.severity, "white")
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


__all__ = [
    "ALL_FORMATS",
    "FORMAT_GREP",
    "FORMAT_JSON",
    "FORMAT_PLAIN",
    "FORMAT_RICH",
    "SEVERITY_STYLE",
    "format_count",
    "issues_table_rich",
    "kv_grid",
    "signed_delta",
]
