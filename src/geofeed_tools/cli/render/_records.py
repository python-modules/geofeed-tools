"""Renderers for ``GeofeedRecord`` lists and ``QueryResult`` payloads."""

from __future__ import annotations

from geofeed_tools.io_utils import (
    query_to_json,
    records_to_csv,
    records_to_json,
)
from geofeed_tools.models import GeofeedRecord, QueryResult

from ._helpers import FORMAT_GREP, FORMAT_JSON, FORMAT_PLAIN


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


__all__ = ["render_query", "render_records"]
