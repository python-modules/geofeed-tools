"""Plain-text and key=value renderers for ``GeoFeedInfo``.

These mirror the CLI ``--format plain`` and ``--format grep`` modes but live in
the library so they're available without the CLI extras and so the CLI rich
renderer can reuse the same data-extraction helpers.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from .models import GeoFeedInfo


def format_count(value: int) -> str:
    """Format an integer count with thousand-separator commas."""
    return f"{value:,}"


def signed_delta(value: int) -> str:
    """Render an int with a leading ``+`` for non-negative values."""
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:,}"


def info_overview_rows(info: GeoFeedInfo) -> list[tuple[str, str]]:
    """Return the (label, value) rows for the overview section."""
    return [
        ("Total prefixes", format_count(info.prefixes_total)),
        ("  IPv4", format_count(info.prefixes_v4)),
        ("  IPv6", format_count(info.prefixes_v6)),
        ("Unique prefixes", format_count(info.unique_prefixes)),
        ("Duplicates", format_count(info.duplicates)),
        ("/24 equivalents (IPv4)", format_count(info.slash_24s)),
        ("/48 equivalents (IPv6)", format_count(info.slash_48s)),
        ("Errors", format_count(info.errors)),
        ("Warnings", format_count(info.warnings)),
    ]


def info_geography_rows(info: GeoFeedInfo) -> list[tuple[str, str]]:
    """Return the (label, value) rows for the geography section."""
    return [
        ("Countries", format_count(info.unique_countries)),
        ("Regions", format_count(info.unique_regions)),
        ("Cities", format_count(info.unique_cities)),
        ("Postal codes", format_count(info.unique_postal_codes)),
    ]


def info_normalized_rows(info: GeoFeedInfo) -> list[tuple[str, str]] | None:
    """Return the (label, value) rows for the normalize preview, or None."""
    if info.normalized is None:
        return None
    n = info.normalized
    delta_total = signed_delta(n.prefixes_total - info.prefixes_total)
    return [
        ("Prefixes", f"{format_count(n.prefixes_total)} ({delta_total})"),
        ("  IPv4", format_count(n.prefixes_v4)),
        ("  IPv6", format_count(n.prefixes_v6)),
        ("/24 equivalents (IPv4)", format_count(n.slash_24s)),
        ("/48 equivalents (IPv6)", format_count(n.slash_48s)),
        ("Invalid removed", format_count(n.invalid_removed)),
        ("Aggregated / deduped", format_count(n.aggregated)),
    ]


def render_info_text(info: GeoFeedInfo) -> str:
    """Render a ``GeoFeedInfo`` as a human-readable plain-text report."""
    parts: list[str] = [f"Geofeed info — {info.source}", ""]

    parts.append("Overview:")
    parts.append(_kv_rows(info_overview_rows(info)))

    parts.append("")
    parts.append("Geography:")
    parts.append(_kv_rows(info_geography_rows(info)))

    normalized = info_normalized_rows(info)
    if normalized is not None:
        parts.append("")
        parts.append("If normalized:")
        parts.append(_kv_rows(normalized))

    if info.by_country:
        parts.append("")
        parts.append(f"By country ({len(info.by_country)}):")
        headers = ("Country", "v4 prefixes", "v6 prefixes", "v4 /24s", "v6 /48s")
        rows = [
            (
                c.country,
                format_count(c.prefixes_v4),
                format_count(c.prefixes_v6),
                format_count(c.slash_24s),
                format_count(c.slash_48s),
            )
            for c in info.by_country
        ]
        parts.append(_aligned_rows(headers, rows))

    if info.prefix_length_v4 or info.prefix_length_v6:
        parts.append("")
        parts.append("Prefix length distribution:")
        if info.prefix_length_v4:
            parts.append("  IPv4:")
            parts.append(_kv_rows([(f"/{pl}", format_count(c)) for pl, c in info.prefix_length_v4], indent="    "))
        if info.prefix_length_v6:
            parts.append("  IPv6:")
            parts.append(_kv_rows([(f"/{pl}", format_count(c)) for pl, c in info.prefix_length_v6], indent="    "))

    if info.top_regions:
        parts.append("")
        parts.append(f"Top regions ({len(info.top_regions)}):")
        parts.append(_kv_rows([(region, format_count(count)) for region, count in info.top_regions]))

    if info.top_cities:
        parts.append("")
        parts.append(f"Top cities ({len(info.top_cities)}):")
        parts.append(_kv_rows([(city, format_count(count)) for city, count in info.top_cities]))

    return "\n".join(parts)


def render_info_grep(info: GeoFeedInfo) -> str:
    """Render a ``GeoFeedInfo`` as a flat ``key=value`` document for grep/awk."""
    lines: list[str] = [
        f"source={info.source}",
        f"prefixes_total={info.prefixes_total}",
        f"prefixes_v4={info.prefixes_v4}",
        f"prefixes_v6={info.prefixes_v6}",
        f"unique_prefixes={info.unique_prefixes}",
        f"duplicates={info.duplicates}",
        f"slash_24s={info.slash_24s}",
        f"slash_48s={info.slash_48s}",
        f"unique_countries={info.unique_countries}",
        f"unique_regions={info.unique_regions}",
        f"unique_cities={info.unique_cities}",
        f"unique_postal_codes={info.unique_postal_codes}",
        f"errors={info.errors}",
        f"warnings={info.warnings}",
    ]
    if info.normalized is not None:
        n = info.normalized
        lines.extend(
            [
                f"normalized.prefixes_total={n.prefixes_total}",
                f"normalized.prefixes_v4={n.prefixes_v4}",
                f"normalized.prefixes_v6={n.prefixes_v6}",
                f"normalized.slash_24s={n.slash_24s}",
                f"normalized.slash_48s={n.slash_48s}",
                f"normalized.invalid_removed={n.invalid_removed}",
                f"normalized.aggregated={n.aggregated}",
            ]
        )
    for entry in info.by_country:
        lines.extend(
            [
                f"country.{entry.country}.prefixes_v4={entry.prefixes_v4}",
                f"country.{entry.country}.prefixes_v6={entry.prefixes_v6}",
                f"country.{entry.country}.slash_24s={entry.slash_24s}",
                f"country.{entry.country}.slash_48s={entry.slash_48s}",
            ]
        )
    for prefixlen, count in info.prefix_length_v4:
        lines.append(f"prefixlen.v4.{prefixlen}={count}")
    for prefixlen, count in info.prefix_length_v6:
        lines.append(f"prefixlen.v6.{prefixlen}={count}")
    for rank, (region, count) in enumerate(info.top_regions, start=1):
        lines.append(f"top_region.{rank}.name={region}")
        lines.append(f"top_region.{rank}.count={count}")
    for rank, (city, count) in enumerate(info.top_cities, start=1):
        lines.append(f'top_city.{rank}.name="{city}"')
        lines.append(f"top_city.{rank}.count={count}")
    return "\n".join(lines) + "\n"


def _kv_rows(rows: Iterable[tuple[str, str]], *, indent: str = "  ") -> str:
    """Render label/value pairs as aligned ``indent + label + value`` lines."""
    rows_list = list(rows)
    if not rows_list:
        return ""
    key_width = max(len(label) for label, _ in rows_list)
    return "\n".join(f"{indent}{label.ljust(key_width)}  {value}" for label, value in rows_list)


def _aligned_rows(
    headers: tuple[str, ...],
    rows: Sequence[tuple[str, ...]],
    *,
    indent: str = "  ",
) -> str:
    """Render a fixed-width table with a header row."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    lines = [f"{indent}{'  '.join(headers[i].ljust(widths[i]) for i in range(len(headers)))}"]
    for row in rows:
        lines.append(f"{indent}{'  '.join(row[i].ljust(widths[i]) for i in range(len(headers)))}")
    return "\n".join(lines)


__all__ = [
    "format_count",
    "info_geography_rows",
    "info_normalized_rows",
    "info_overview_rows",
    "render_info_grep",
    "render_info_text",
    "signed_delta",
]
