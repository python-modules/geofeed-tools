# geofeed-tools

`geofeed-tools` is a Python library and CLI for working with [RFC 8805](https://datatracker.ietf.org/doc/html/rfc8805) geofeeds. It parses, validates, normalizes, queries, and summarizes geofeeds from local files and HTTP(S) sources, and discovers published geofeeds for an IP/prefix via RDAP.

- [geofeed-tools](#geofeed-tools)
  - [Install](#install)
  - [CLI quick start](#cli-quick-start)
  - [Output formats](#output-formats)
  - [CLI command reference](#cli-command-reference)
    - [`validate`](#validate)
    - [`dump`](#dump)
    - [`normalize`](#normalize)
    - [`query`](#query)
    - [`doctor`](#doctor)
    - [`lookup`](#lookup)
    - [`info`](#info)
    - [`hook`](#hook)
  - [Python API](#python-api)
    - [Python API quick start](#python-api-quick-start)
    - [`GeoFeed` class](#geofeed-class)
    - [`AsyncGeoFeed` class](#asyncgeofeed-class)
    - [Static helpers (`doctor` / `lookup`)](#static-helpers-doctor--lookup)
    - [Data models](#data-models)
      - [`GeofeedRecord`](#geofeedrecord)
      - [`ValidationIssue`](#validationissue)
      - [`ValidationReport`](#validationreport)
      - [`QueryResult`](#queryresult)
      - [`DoctorLookup`](#doctorlookup)
      - [`DoctorResult`](#doctorresult)
      - [`GeoFeedInfo`](#geofeedinfo)
    - [Error handling](#error-handling)
  - [GitHub Actions integration](#github-actions-integration)
  - [Testing](#testing)
  - [Configuration](#configuration)

## Install

```bash
# Core library only
pip install geofeed-tools

# Library + CLI
pip install 'geofeed-tools[cli]'

# Library + async HTTP support for AsyncGeoFeed URL loading
pip install 'geofeed-tools[async]'

# Library + everything for development
pip install 'geofeed-tools[dev]'
```

Run the CLI under `uv` without installing:

```bash
uv tool run 'geofeed-tools[cli]' --help
```

Or via Docker (no Python needed on the host):

```bash
docker run --rm pythonmodules/geofeed-tools:latest doctor 31.133.128.1
```

Published images:
  - `ghcr.io/python-modules/geofeed-tools`
  - `pythonmodules/geofeed-tools`

Tags: `python3`, `python3.11`, `python3.12`, `python3.13`, and `latest` (tracks `python3`).

## CLI quick start

```bash
# Discover a published geofeed for an IP via RDAP and show matches
geofeed-tools doctor 31.133.128.1

# Validate a geofeed source
geofeed-tools validate geofeeds.csv

# Show summary statistics
geofeed-tools info geofeeds.csv

# Query a geofeed for an IP or prefix
geofeed-tools query geofeeds.csv 192.0.2.200

# Normalize the feed and write canonical CSV to a file
geofeed-tools normalize geofeeds.csv --output normalized.csv

# Validate in CI / pre-commit mode (machine-friendly exit codes)
geofeed-tools hook geofeeds.csv --strict
```

Per-command help is always available:

```bash
geofeed-tools --help
geofeed-tools doctor --help
```

## Output formats

Every command supports `--format` / `-f` with four values:

| Format  | Best for                          | Notes                                                                 |
| ------- | --------------------------------- | --------------------------------------------------------------------- |
| `rich`  | terminal (default)                | Colored panels, trees, and tables                                     |
| `plain` | redirected to file or scrollback  | Same content, no colors, no box-drawing characters                    |
| `grep`  | piping to `grep`/`awk`/scripting  | One record per line, no headers or summary lines                      |
| `json`  | piping to `jq` or programmatic    | Stable structured JSON identical to the matching `output="json"` API  |

Examples:

```bash
geofeed-tools validate geofeeds.csv --format grep | grep error
geofeed-tools info geofeeds.csv --format grep | grep ^errors=
geofeed-tools doctor 31.133.128.1 --format json | jq .lookup.geofeed_url
geofeed-tools query geofeeds.csv 192.0.2.1 --format json | jq '.matches[0]'
```

Exit codes follow the most useful semantic per format:

- `validate` / `hook`: exit 1 when errors are found (or warnings with `--strict`), regardless of format.
- `query` / `lookup`: exit 1 on no match in any non-JSON format; exit 0 in `json` mode (the empty `matches` array is the answer). `lookup` always exits 1 when no geofeed is discovered.
- `doctor`: exit 1 when no geofeed is discovered or no record matches, regardless of format.
- `dump` / `normalize` / `info`: exit 0 on success.

## CLI command reference

### `validate`

```bash
geofeed-tools validate SOURCE [--format ...] [--strict] [--check-aggregation] [--no-sort-check] [--no-content-type-check] [-v]
```

Validate a geofeed and report issues.

| Option                    | Default | Meaning                                                          |
| ------------------------- | ------- | ---------------------------------------------------------------- |
| `--format`, `-f`          | `rich`  | Output format.                                                   |
| `--strict`                | off     | Exit 1 when warnings are present, not just errors.               |
| `--check-aggregation`     | off     | Warn for prefixes that could be safely aggregated.               |
| `--no-sort-check`         | off     | Disable sort-order warnings.                                     |
| `--no-content-type-check` | off     | Disable `Content-Type` warnings for URL sources.                 |
| `-v`, `--verbose`         | `0`     | Increase log verbosity (`-v` INFO, `-vv` DEBUG, `-vvv` TRACE).   |

`--format grep` emits one line per issue in `path:line:severity:code:message` form, identical to GCC/grep style for easy pipeline use.

### `dump`

```bash
geofeed-tools dump SOURCE [--format ...] [--normalize] [--no-validation] [-v]
```

Dump parsed records in the chosen format. `--normalize` rebuilds rows from normalized output; `--no-validation` strips the `valid` / `validation_messages` columns from rich, plain, and JSON output. The `grep` format always emits 5-column geofeed CSV without validation columns.

### `normalize`

```bash
geofeed-tools normalize SOURCE [--format ...] [--output FILE] [--no-uppercase] [--no-sort] [--no-aggregate] [--no-dedupe] [--no-host-bit-fix] [-v]
```

Normalize a geofeed. `--output FILE` always writes canonical CSV regardless of `--format` because that is the only useful payload to persist.

| Option              | Default | Meaning                                                                  |
| ------------------- | ------- | ------------------------------------------------------------------------ |
| `--no-uppercase`    | off     | Do not uppercase country and region fields.                              |
| `--no-sort`         | off     | Do not sort by IP family and prefix.                                     |
| `--no-aggregate`    | off     | Do not collapse compatible prefixes into larger prefixes.                |
| `--no-dedupe`       | off     | Do not remove exact duplicate rows when aggregation is disabled.         |
| `--no-host-bit-fix` | off     | Do not coerce prefixes with host bits set to their containing network.   |

### `query`

```bash
geofeed-tools query SOURCE QUERY [--format ...] [--all] [--longer] [-v]
```

Look up an IP or CIDR. `--all` returns every match instead of only the most specific one; `--longer` includes more-specific prefixes contained by a queried prefix.

### `doctor`

```bash
geofeed-tools doctor QUERY [--format ...] [--all] [--longer] [--rdap-method rdap.org|iana-bootstrap] [-v]
```

Discover the published geofeed for an IP or prefix via RDAP, fetch it, and query it. The rich format renders the RDAP trace as a tree plus a "Geofeed discovery" panel (green ✓ when found, yellow ✗ when not). The plain format prints the same information as labeled lines.

`--rdap-method rdap.org` (default) uses the rdap.org proxy for fast lookups. `--rdap-method iana-bootstrap` reads IANA bootstrap data and queries the selected RIR endpoint directly.

### `lookup`

```bash
geofeed-tools lookup QUERY [--format ...] [--all] [--longer] [--rdap-method rdap.org|iana-bootstrap] [-v]
```

Same RDAP discovery flow as `doctor`, but the output contains only the matching geofeed records (no RDAP metadata). Use `lookup` when you only need the geographic answer; use `doctor` when you also want to see how the answer was discovered.

### `info`

```bash
geofeed-tools info SOURCE [--format ...] [-v]
```

Show record, geography, and validation counts. The grep format emits one `key=value` line per metric for easy piping into `grep`/`awk`.

### `hook`

```bash
geofeed-tools hook SOURCE [--format ...] [--strict] [--show-issues/--no-issues] [-v]
```

Hook-friendly validation: writes a colorized panel + summary to stderr in rich mode, an emitted `path:line:severity:code:message` list in grep mode (stdout for easy piping), and exits 1 on errors (or warnings with `--strict`).

## Python API

The library is fully usable from Python without the CLI dependencies installed.

### Python API quick start

Sync:

```python
from geofeed_tools import GeoFeed

geofeed = GeoFeed("https://api.cloudflare.com/local-ip-ranges.csv")

records = geofeed.parse()                              # list[GeofeedRecord]
records_json = geofeed.parse(output="json")            # JSON string

report = geofeed.validate(check_aggregation=True)      # ValidationReport
canonical_csv = geofeed.normalize(output="csv")        # str

match = geofeed.query("192.0.2.1")                     # QueryResult
deep = geofeed.query("192.0.2.0/24", return_all=True, include_longer=True)

# RDAP discovery is a static helper — no instance required
diagnosis = GeoFeed.doctor("31.133.128.1")             # DoctorResult
matches = GeoFeed.lookup("31.133.128.1")               # QueryResult

summary = geofeed.info()                               # GeoFeedInfo

# Eager constructor alternative (symmetric with AsyncGeoFeed.from_source)
loaded = GeoFeed.from_source("geofeeds.csv")
```

Async:

```python
from geofeed_tools import AsyncGeoFeed

geofeed = AsyncGeoFeed("https://api.cloudflare.com/local-ip-ranges.csv")

# Loading is lazy by default; the first awaited operation fetches the source.
records = await geofeed.parse()
report = await geofeed.validate(check_aggregation=True)
summary = await geofeed.info()

# RDAP discovery does not require an instance
diagnosis = await AsyncGeoFeed.doctor("31.133.128.1")
matches = await AsyncGeoFeed.lookup("31.133.128.1")

# Eager-load factory
preloaded = await AsyncGeoFeed.from_source("https://api.cloudflare.com/local-ip-ranges.csv")
```

### `GeoFeed` class

```python
GeoFeed(source: str, *, auto_load: bool = True, cache_query_index: bool = True)
GeoFeed.from_source(source: str, *, cache_query_index: bool = True) -> GeoFeed
```

| Argument            | Default | Meaning                                                                            |
| ------------------- | ------- | ---------------------------------------------------------------------------------- |
| `source`            | —       | Local file path or HTTP(S) URL.                                                    |
| `auto_load`         | `True`  | If `True`, load the source immediately; otherwise lazily on first operation.       |
| `cache_query_index` | `True`  | Cache the parsed query index between `query()` calls for repeated lookups.         |

After loading: `source`, `raw`, `content_type`, and `text` are populated.

Methods (every method also accepts `output="objects"` (default), `"json"`, and, where applicable, `"csv"` or `"text"`):

| Method                                       | Return                                | Notes                                                                                       |
| -------------------------------------------- | ------------------------------------- | ------------------------------------------------------------------------------------------- |
| `reload()`                                   | `None`                                | Re-fetch / re-read the source.                                                              |
| `parse(*, include_validation, normalize)`    | `list[GeofeedRecord] \| str`          | Records, optionally annotated with `valid`/`validation_messages`.                           |
| `validate(*, check_sort, check_content_type, check_aggregation)` | `ValidationReport \| str` | Structured validation report.                                                               |
| `normalize(*, uppercase, sort, aggregate, dedupe, fix_host_bits)` | `list[GeofeedRecord] \| str` | Canonical normalized records.                                                               |
| `query(query, *, return_all, include_longer)` | `QueryResult \| str`                  | Longest-prefix match (default) or all matches.                                              |
| `info()`                                     | `GeoFeedInfo \| str`                  | Aggregate statistics.                                                                       |

Behavior notes:

- `parse()`: malformed CSV rows and rows with empty prefixes are skipped. Rows with invalid CIDRs are still returned and, with `include_validation=True`, marked invalid. With `normalize=True`, source line numbers are not preserved.
- `normalize()`: `aggregate=True` implies dedupe within each metadata group. `fix_host_bits=False` skips rows like `192.0.2.5/24` instead of coercing them.
- `query()`: for IP queries the default returns the most specific covering prefix. `return_all=True` returns every match ordered most-specific first; `include_longer=True` also includes more-specific prefixes contained by the queried CIDR.

### `AsyncGeoFeed` class

```python
AsyncGeoFeed(source: str, *, cache_query_index: bool = True)
await AsyncGeoFeed.from_source(source: str, *, cache_query_index: bool = True) -> AsyncGeoFeed
```

Mirrors `GeoFeed` but loads, parses, validates, normalizes, queries, and computes info asynchronously. CPU-bound work runs in a worker thread so the event loop stays responsive. URL fetches use `httpx` and require the `geofeed-tools[async]` extra; local file reads are offloaded via `asyncio.to_thread`. `AsyncGeoFeed` has no `auto_load` flag — use `from_source` for one-step construction + load.

### Static helpers (`doctor` / `lookup`)

```python
GeoFeed.doctor(query, *, return_all=False, include_longer=False, rdap_method="rdap.org", output="objects") -> DoctorResult | str
GeoFeed.lookup(query, *, return_all=False, include_longer=False, rdap_method="rdap.org", output="objects") -> QueryResult | str

await AsyncGeoFeed.doctor(...)
await AsyncGeoFeed.lookup(...)
```

`doctor()` returns the full `DoctorResult` (RDAP trace + matches). `lookup()` returns only the `QueryResult` and raises `GeoFeedDiscoveryError` when no geofeed URL is published.

| `rdap_method`     | Behavior                                                                              |
| ----------------- | ------------------------------------------------------------------------------------- |
| `"rdap.org"`      | Default. Fast gateway lookups via the rdap.org proxy.                                 |
| `"iana-bootstrap"` | Reads IANA bootstrap data and queries the selected RIR service directly.              |

Discovery walks `rdap-up` parents and supports both direct `rel=geofeed` links and remarks/comments containing `Geofeed: https://…`.

### Data models

All public dataclasses are exported from `geofeed_tools`. Every one provides an `as_dict()` method.

#### `GeofeedRecord`

| Field                 | Type                | Meaning                                                            |
| --------------------- | ------------------- | ------------------------------------------------------------------ |
| `prefix`              | `str`               | Network prefix.                                                    |
| `country`             | `str`               | ISO 3166-1 alpha-2 code.                                           |
| `region`              | `str`               | ISO 3166-2 subdivision code.                                       |
| `city`                | `str`               | City field.                                                        |
| `postal_code`         | `str`               | Postal code field.                                                 |
| `line`                | `int`               | Source line number (`0` for synthesized normalized records).       |
| `raw_line`            | `str \| None`       | Original source line when available.                               |
| `valid`               | `bool`              | `True` when no validation errors attached.                         |
| `validation_messages` | `tuple[str, ...]`   | Record-level validation messages.                                  |

#### `ValidationIssue`

| Field      | Type           | Meaning                                                |
| ---------- | -------------- | ------------------------------------------------------ |
| `severity` | `str`          | Usually `"error"` or `"warning"`.                      |
| `line`     | `int \| None`  | Source line, or `None` for file-level issues.          |
| `code`     | `str`          | Stable machine-readable code (`invalid-prefix`, etc.). |
| `message`  | `str`          | Human-readable message.                                |
| `raw_line` | `str \| None`  | Original line text when available.                     |

#### `ValidationReport`

| Field      | Type                            | Meaning                              |
| ---------- | ------------------------------- | ------------------------------------ |
| `source`   | `str`                           | Original path or URL.                |
| `records`  | `int`                           | Number of records processed.         |
| `errors`   | `int`                           | Error count.                         |
| `warnings` | `int`                           | Warning count.                       |
| `valid`    | `bool`                          | `True` when `errors == 0`.           |
| `issues`   | `tuple[ValidationIssue, ...]`   | Full issue list.                     |

#### `QueryResult`

| Field     | Type                          | Meaning                                       |
| --------- | ----------------------------- | --------------------------------------------- |
| `query`   | `str`                         | Original query.                               |
| `matches` | `tuple[GeofeedRecord, ...]`   | Matching records, most-specific first.        |

#### `DoctorLookup`

RDAP discovery metadata returned inside `DoctorResult.lookup`.

| Field                     | Type            | Meaning                                                     |
| ------------------------- | --------------- | ----------------------------------------------------------- |
| `lookup_strategy`         | `str`           | `"ip-address"` or `"prefix-network-address"`.               |
| `rdap_method`             | `str`           | `"rdap.org"` or `"iana-bootstrap"`.                         |
| `rdap_query`              | `str`           | IP address used for the RDAP lookup.                        |
| `bootstrap_url`           | `str`           | First RDAP URL queried.                                     |
| `bootstrap_source_url`    | `str \| None`   | Bootstrap source (rdap.org or an IANA JSON file).           |
| `resolved_urls`           | `tuple[str,…]`  | RDAP URLs visited, ordered most-specific to broader.        |
| `referring_handle`        | `str \| None`   | Handle of the RDAP object that published the geofeed.       |
| `referring_range`         | `str \| None`   | IP range of the referring RDAP object.                      |
| `geofeed_url`             | `str \| None`   | Published geofeed URL or `None` if not found.               |
| `geofeed_discovered_via`  | `str \| None`   | How the reference was found (link / remarks / comments).    |
| `geofeed_reference_url`   | `str \| None`   | RDAP URL where the geofeed reference appears.               |

#### `DoctorResult`

| Field     | Type                          | Meaning                                  |
| --------- | ----------------------------- | ---------------------------------------- |
| `query`   | `str`                         | Original query string.                   |
| `lookup`  | `DoctorLookup`                | RDAP discovery metadata.                 |
| `matches` | `tuple[GeofeedRecord, ...]`   | Matching geofeed rows.                   |

#### `GeoFeedInfo`

| Field                  | Type                  | Meaning                                  |
| ---------------------- | --------------------- | ---------------------------------------- |
| `source`               | `str`                 | Original path or URL.                    |
| `total_records`        | `int`                 | Number of parsed records.                |
| `unique_prefixes`      | `int`                 | Distinct prefix count.                   |
| `ipv4_records`         | `int`                 | IPv4 record count.                       |
| `ipv6_records`         | `int`                 | IPv6 record count.                       |
| `unique_countries`     | `int`                 | Distinct country count.                  |
| `unique_regions`       | `int`                 | Distinct region count.                   |
| `unique_cities`        | `int`                 | Distinct city count.                     |
| `unique_postal_codes`  | `int`                 | Distinct postal-code count.              |
| `duplicates`           | `int`                 | `total_records - unique_prefixes`.       |
| `errors`               | `int`                 | Validation error count.                  |
| `warnings`             | `int`                 | Validation warning count.                |
| `metadata`             | `dict[str, object]`   | Reserved for extensible metadata.        |

### Error handling

| Exception                                  | Raised when                                                          |
| ------------------------------------------ | -------------------------------------------------------------------- |
| `ValueError`                               | Invalid `output` mode or unparseable query string.                   |
| `geofeed_tools.GeoFeedDiscoveryError`      | `lookup()` finds no published geofeed URL.                           |
| `geofeed_tools.loader.FetchError`          | Remote HTTP(S) or RDAP fetch failure.                                |
| `FileNotFoundError` / `OSError`            | Local file read failure.                                             |

```python
from geofeed_tools import GeoFeed
from geofeed_tools.loader import FetchError

try:
    geofeed = GeoFeed("https://example.com/geofeed.csv")
    report = geofeed.validate(check_content_type=True)
except FetchError as exc:
    print(f"fetch failed: {exc}")
```

## GitHub Actions integration

The `hook` command is designed as a CI quality gate. This repository publishes a reusable workflow at [.github/workflows/geofeed-validation.yml](.github/workflows/geofeed-validation.yml) and a caller example at [examples/github-actions/geofeed-validation.yml](examples/github-actions/geofeed-validation.yml).

Minimal caller workflow:

```yaml
name: Validate geofeed

on:
  pull_request:
    paths: ["path/to/geofeed.csv"]
  push:
    branches: [main]
    paths: ["path/to/geofeed.csv"]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  geofeed-validation:
    uses: python-modules/geofeed-tools/.github/workflows/geofeed-validation.yml@main
    with:
      geofeed_path: path/to/geofeed.csv
      strict: false   # set true to fail on warnings as well as errors
```

## Testing

```bash
make test                # unit tests (no network)
make test-integration    # real HTTP fetches
make test-html           # writes reports/pytest-report.html
```

Equivalent direct invocations:

```bash
pytest -m "not integration"
pytest -m integration
```

`pytest-html` is wired up in `pyproject.toml`; running `pytest` always produces a self-contained `reports/pytest-report.html`.

Integration tests depend on HTTP access to well-known public geofeed files. Their contents may change at any time and produce test failures unrelated to code changes.

## Configuration

All tuneable defaults and external endpoints live in [`src/geofeed_tools/config.py`](src/geofeed_tools/config.py). Most users never need to touch them; the most relevant are:

| Constant                      | Default                          | Purpose                                                   |
| ----------------------------- | -------------------------------- | --------------------------------------------------------- |
| `FETCH_TIMEOUT`               | `30`                             | HTTP timeout in seconds.                                  |
| `USER_AGENT`                  | `geofeed-tools/<version>`        | User-Agent header.                                        |
| `DEFAULT_RDAP_METHOD`         | `"rdap.org"`                     | RDAP method used when none is specified.                  |
| `MAX_RDAP_DEPTH`              | `8`                              | RDAP redirect hop cap.                                    |
| `LRU_COUNTRY_CACHE_SIZE`      | `512`                            | ISO 3166-1 lookup cache size.                             |
| `LRU_SUBDIVISION_CACHE_SIZE`  | `4096`                           | ISO 3166-2 lookup cache size.                             |
| `TRACE_LEVEL`                 | `5`                              | Numeric level below DEBUG used by `-vvv`.                 |

See the source file for the full list and inline docstrings.
