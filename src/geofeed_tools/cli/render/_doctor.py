"""Renderer for ``DoctorResult`` RDAP-discovery output."""

from __future__ import annotations

from geofeed_tools.doctor import render_doctor_text
from geofeed_tools.io_utils import doctor_to_json, records_to_csv
from geofeed_tools.models import DoctorResult

from ._helpers import FORMAT_GREP, FORMAT_JSON, FORMAT_PLAIN, kv_grid
from ._records import _records_rich


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
            kv_grid(overview_rows),
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
            kv_grid(discovery_rows, key_style="bold green"),
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


__all__ = ["render_doctor"]
