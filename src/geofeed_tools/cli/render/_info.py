"""Renderer for ``GeoFeedInfo`` summaries.

JSON, plain, and grep dispatch to the library renderers in ``info_render``;
rich rendering lives here because it depends on the rich library.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from geofeed_tools.info_render import (
    info_geography_rows,
    render_info_grep,
    render_info_text,
)
from geofeed_tools.io_utils import info_to_json
from geofeed_tools.models import GeoFeedInfo

from ._helpers import (
    FORMAT_GREP,
    FORMAT_JSON,
    FORMAT_PLAIN,
    format_count,
    kv_grid,
    signed_delta,
)

if TYPE_CHECKING:
    from rich.table import Table


def render_info(info: GeoFeedInfo, *, format: str) -> None:
    """Render a GeoFeedInfo summary in the requested format."""
    if format == FORMAT_JSON:
        print(info_to_json(info))
    elif format == FORMAT_GREP:
        print(render_info_grep(info), end="")
    elif format == FORMAT_PLAIN:
        print(render_info_text(info))
    else:
        _info_rich(info)


def _info_rich(info: GeoFeedInfo) -> None:
    from rich.box import ROUNDED
    from rich.console import Console, Group
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    console = Console()
    error_color = "red" if info.errors else "green"
    warning_color = "yellow" if info.warnings else "green"
    overview = kv_grid(
        [
            (
                "Total prefixes",
                f"{format_count(info.prefixes_total)}  "
                f"([cyan]IPv4 {format_count(info.prefixes_v4)}[/cyan]  "
                f"[magenta]IPv6 {format_count(info.prefixes_v6)}[/magenta])",
            ),
            ("Unique prefixes", format_count(info.unique_prefixes)),
            ("Duplicates", format_count(info.duplicates)),
            ("IPv4 /24-equivalents", f"[cyan]{format_count(info.slash_24s)}[/cyan]"),
            ("IPv6 /48-equivalents", f"[magenta]{format_count(info.slash_48s)}[/magenta]"),
            ("Errors", f"[{error_color}]{format_count(info.errors)}[/{error_color}]"),
            ("Warnings", f"[{warning_color}]{format_count(info.warnings)}[/{warning_color}]"),
        ]
    )
    console.print(
        Panel(
            overview,
            title=f"[bold]Geofeed info —[/bold] [magenta]{info.source}[/magenta]",
            border_style="cyan",
            box=ROUNDED,
            padding=(1, 2),
        )
    )

    console.print()
    console.print(
        Panel(
            kv_grid(info_geography_rows(info), key_style="bold magenta"),
            title="Geography",
            border_style="magenta",
            box=ROUNDED,
            padding=(1, 2),
        )
    )

    if info.normalized is not None:
        n = info.normalized
        delta_total = signed_delta(n.prefixes_total - info.prefixes_total)
        delta_color = "yellow" if n.prefixes_total != info.prefixes_total else "green"
        norm_grid = kv_grid(
            [
                (
                    "Prefixes",
                    f"{format_count(n.prefixes_total)}  "
                    f"[{delta_color}]({delta_total})[/{delta_color}]  "
                    f"([cyan]IPv4 {format_count(n.prefixes_v4)}[/cyan]  "
                    f"[magenta]IPv6 {format_count(n.prefixes_v6)}[/magenta])",
                ),
                ("IPv4 /24-equivalents", f"[cyan]{format_count(n.slash_24s)}[/cyan]"),
                ("IPv6 /48-equivalents", f"[magenta]{format_count(n.slash_48s)}[/magenta]"),
                ("Invalid removed", f"[red]{format_count(n.invalid_removed)}[/red]"),
                ("Aggregated / deduped", f"[yellow]{format_count(n.aggregated)}[/yellow]"),
            ]
        )
        console.print()
        console.print(
            Panel(
                norm_grid,
                title="If normalized",
                border_style="yellow",
                box=ROUNDED,
                padding=(1, 2),
            )
        )

    if info.by_country:
        country_table = Table(box=ROUNDED, border_style="blue", header_style="bold blue", expand=False)
        country_table.add_column("Country", no_wrap=True)
        country_table.add_column("v4 prefixes", justify="right")
        country_table.add_column("v6 prefixes", justify="right")
        country_table.add_column("v4 /24s", justify="right")
        country_table.add_column("v6 /48s", justify="right")
        for entry in info.by_country:
            country_table.add_row(
                entry.country,
                format_count(entry.prefixes_v4),
                format_count(entry.prefixes_v6),
                format_count(entry.slash_24s),
                format_count(entry.slash_48s),
            )
        console.print()
        console.print(
            Panel(
                country_table,
                title=f"By country ({len(info.by_country)})",
                border_style="blue",
                box=ROUNDED,
                padding=(1, 2),
            )
        )

    if info.prefix_length_v4 or info.prefix_length_v6:
        v4 = _length_table_rich(info.prefix_length_v4, "IPv4", "cyan")
        v6 = _length_table_rich(info.prefix_length_v6, "IPv6", "magenta")
        items: list = []
        if v4 is not None:
            items.append(v4)
        if v6 is not None:
            if items:
                items.append(Text())
            items.append(v6)
        console.print()
        console.print(
            Panel(
                Group(*items),
                title="Prefix length distribution",
                border_style="cyan",
                box=ROUNDED,
                padding=(1, 2),
            )
        )

    if info.top_regions:
        console.print()
        console.print(
            Panel(
                _ranked_table_rich(info.top_regions, label="Region", color="magenta"),
                title=f"Top regions ({len(info.top_regions)})",
                border_style="magenta",
                box=ROUNDED,
                padding=(1, 2),
            )
        )

    if info.top_cities:
        console.print()
        console.print(
            Panel(
                _ranked_table_rich(info.top_cities, label="City", color="yellow"),
                title=f"Top cities ({len(info.top_cities)})",
                border_style="yellow",
                box=ROUNDED,
                padding=(1, 2),
            )
        )


def _ranked_table_rich(rows: tuple[tuple[str, int], ...], *, label: str, color: str) -> Table:
    from rich.box import ROUNDED
    from rich.table import Table

    table = Table(box=ROUNDED, border_style=color, header_style=f"bold {color}", expand=False)
    table.add_column(label, no_wrap=(label != "City"))
    table.add_column("Prefixes", justify="right")
    for name, count in rows:
        table.add_row(name, format_count(count))
    return table


def _length_table_rich(rows: tuple[tuple[int, int], ...], label: str, color: str):
    if not rows:
        return None
    from rich.box import SIMPLE
    from rich.table import Table

    table = Table(
        title=label,
        title_style=f"bold {color}",
        box=SIMPLE,
        border_style=color,
        header_style=f"bold {color}",
        expand=False,
    )
    table.add_column("Prefix length", justify="right", no_wrap=True)
    table.add_column("Count", justify="right")
    for prefixlen, count in rows:
        table.add_row(f"/{prefixlen}", format_count(count))
    return table


__all__ = ["render_info"]
