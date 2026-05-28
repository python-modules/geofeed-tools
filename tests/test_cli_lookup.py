"""CLI tests for the lookup command behavior."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from geofeed_tools.cli.app import build_app
from geofeed_tools.models import DoctorLookup
from geofeed_tools.rdap import ResolvedRdapLookup

runner = CliRunner()

_GEOFEED_BYTES = b"203.0.113.0/24,US,US-CA,Los Angeles,\n"


def _resolved_with_url(query: str, geofeed_url: str | None) -> ResolvedRdapLookup:
    """Build a ResolvedRdapLookup with the requested geofeed URL (or None)."""
    return ResolvedRdapLookup(
        lookup=DoctorLookup(
            lookup_strategy="ip-address",
            rdap_method="rdap.org",
            rdap_query=query,
            bootstrap_url=f"https://rdap.org/ip/{query}",
            geofeed_url=geofeed_url,
        ),
        range_start=None,
        range_end=None,
    )


def _patch_rdap(
    monkeypatch,
    *,
    geofeed_url: str | None,
    geofeed_bytes: bytes = _GEOFEED_BYTES,
) -> dict[str, str]:
    """Patch the sync RDAP resolver + loader and return a dict capturing the rdap_method used."""
    captured: dict[str, str] = {}

    def fake_resolve(query, *, rdap_method="rdap.org"):
        captured["rdap_method"] = rdap_method
        return _resolved_with_url(query, geofeed_url)

    def fake_load(source):
        return geofeed_bytes, "text/csv"

    monkeypatch.setattr("geofeed_tools.core.resolve_geofeed_lookup", fake_resolve)
    monkeypatch.setattr("geofeed_tools.core.load_input", fake_load)
    return captured


def test_cli_lookup_default_rich(monkeypatch) -> None:
    """Lookup should default to rich output containing the matching prefix."""
    _patch_rdap(monkeypatch, geofeed_url="https://example.com/geofeed.csv")

    outcome = runner.invoke(build_app(), ["lookup", "203.0.113.1"], env={"COLUMNS": "200"})

    assert outcome.exit_code == 0
    assert "203.0.113.0/24" in outcome.stdout


def test_cli_lookup_grep_format(monkeypatch) -> None:
    """Lookup --format grep should emit just the CSV row."""
    _patch_rdap(monkeypatch, geofeed_url="https://example.com/geofeed.csv")

    outcome = runner.invoke(build_app(), ["lookup", "203.0.113.1", "--format", "grep"])

    assert outcome.exit_code == 0
    assert outcome.stdout.strip() == "203.0.113.0/24,US,US-CA,Los Angeles,"


def test_cli_lookup_emits_json(monkeypatch) -> None:
    """Lookup --format json should emit a QueryResult-shaped JSON payload."""
    _patch_rdap(monkeypatch, geofeed_url="https://example.com/geofeed.csv")

    outcome = runner.invoke(build_app(), ["lookup", "203.0.113.1", "--format", "json"])

    assert outcome.exit_code == 0
    payload = json.loads(outcome.stdout)
    assert payload["query"] == "203.0.113.1"
    assert payload["matches"][0]["prefix"] == "203.0.113.0/24"
    # lookup JSON must NOT include RDAP metadata (unlike doctor)
    assert "geofeed_url" not in outcome.stdout
    assert "lookup_strategy" not in outcome.stdout


def test_cli_lookup_exits_nonzero_when_no_geofeed(monkeypatch) -> None:
    """Lookup should fail with a message when no geofeed URL is discovered."""
    _patch_rdap(monkeypatch, geofeed_url=None)

    outcome = runner.invoke(build_app(), ["lookup", "203.0.113.1"])

    assert outcome.exit_code == 1
    assert "no geofeed found" in outcome.output


def test_cli_lookup_no_geofeed_json_uses_error_shape(monkeypatch) -> None:
    """Lookup --format json on discovery failure emits {query, error}."""
    _patch_rdap(monkeypatch, geofeed_url=None)

    outcome = runner.invoke(build_app(), ["lookup", "203.0.113.1", "--format", "json"])

    assert outcome.exit_code == 1
    payload = json.loads(outcome.stdout)
    assert payload["query"] == "203.0.113.1"
    assert "no geofeed" in payload["error"]


def test_cli_lookup_exits_nonzero_when_no_matches(monkeypatch) -> None:
    """Lookup should fail when the geofeed is found but has no matching records."""
    # Geofeed is discovered, but its body contains no matching prefix for the query.
    _patch_rdap(
        monkeypatch,
        geofeed_url="https://example.com/geofeed.csv",
        geofeed_bytes=b"198.51.100.0/24,US,US-CA,LA,\n",
    )

    outcome = runner.invoke(build_app(), ["lookup", "203.0.113.1"])

    assert outcome.exit_code == 1


def test_cli_lookup_exits_nonzero_when_no_matches_json(monkeypatch) -> None:
    """Lookup --format json should still exit 1 when no matches are found."""
    _patch_rdap(
        monkeypatch,
        geofeed_url="https://example.com/geofeed.csv",
        geofeed_bytes=b"198.51.100.0/24,US,US-CA,LA,\n",
    )

    outcome = runner.invoke(build_app(), ["lookup", "203.0.113.1", "--format", "json"])

    assert outcome.exit_code == 1
    assert '"matches": []' in outcome.stdout


def test_cli_lookup_accepts_rdap_method_override(monkeypatch) -> None:
    """Lookup should forward --rdap-method to the RDAP resolver."""
    captured = _patch_rdap(monkeypatch, geofeed_url="https://example.com/geofeed.csv")

    outcome = runner.invoke(
        build_app(),
        ["lookup", "203.0.113.1", "--rdap-method", "iana-bootstrap"],
        env={"COLUMNS": "200"},
    )

    assert outcome.exit_code == 0
    assert captured["rdap_method"] == "iana-bootstrap"
