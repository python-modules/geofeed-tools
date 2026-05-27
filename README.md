# geofeed-tools

`geofeed-tools` is a Python library and CLI for working with RFC 8805 geofeeds. It supports parsing, validation, normalization, querying, and summary reporting for local files and remote HTTP(S) sources.

- [geofeed-tools](#geofeed-tools)
  - [Basic Overview](#basic-overview)
  - [Installation](#installation)
  - [Python API](#python-api)
    - [Quick Start](#quick-start)
    - [Public Imports](#public-imports)
    - [`AsyncGeoFeed`](#asyncgeofeed)
    - [`GeoFeed`](#geofeed)
      - [Constructor](#constructor)
      - [`reload()`](#reload)
      - [`parse()`](#parse)
      - [`validate()`](#validate)
      - [`normalize()`](#normalize)
      - [`query()`](#query)
      - [`info()`](#info)
    - [Public Data Models](#public-data-models)
      - [`GeofeedRecord`](#geofeedrecord)
      - [`ValidationIssue`](#validationissue)
      - [`ValidationReport`](#validationreport)
      - [`QueryResult`](#queryresult)
      - [`GeoFeedInfo`](#geofeedinfo)
    - [Error Handling](#error-handling)
  - [CLI Usage](#cli-usage)
    - [Quick Start](#quick-start-1)
    - [Common CLI Behavior](#common-cli-behavior)
    - [Command Reference](#command-reference)
      - [`validate`](#validate-1)
      - [`dump`](#dump)
      - [`normalize`](#normalize-1)
      - [`query`](#query-1)
      - [`info`](#info-1)
      - [`hook`](#hook)
    - [GitHub Actions Integration](#github-actions-integration)
      - [How To Use It In Another Repository](#how-to-use-it-in-another-repository)
  - [Testing](#testing)
    - [HTML test reports](#html-test-reports)
    - [Test Notes](#test-notes)


## Basic Overview

- Validate geofeed quality and RFC 8805 compliance
- Normalize records - ensure there are no duplicates, invalid prefixes (eg. host bits set), case is correct
- Query geofeeds by searching for IPs or prefixes
- Use as either a Python API or a CLI
- CLI hook command available for use in version control hooks or CI/CD tests

## Installation

To install the core library with only the API available:

```bash
uv pip install geofeed-tools
```

To install the full library including the CLI:

```bash
uv pip install 'geofeed-tools[cli]'
```

To install the library with async HTTP support for `AsyncGeoFeed` URL loading:

```bash
uv pip install 'geofeed-tools[async]'
```

Install development dependencies:

```bash
uv pip install 'geofeed-tools[dev]'
```

## Python API

### Quick Start

```python
from geofeed_tools import GeoFeed

geofeed = GeoFeed("https://api.cloudflare.com/local-ip-ranges.csv")

# Parse into GeofeedRecord objects
records = geofeed.parse()

# Parse into JSON
json_records = geofeed.parse(output="json")

# Validate with optional extra aggregation checks enabled
report = geofeed.validate(check_aggregation=True)

# Normalize into canonical CSV output
normalized_csv = geofeed.normalize(output="csv")

# Longest-prefix query for an IP address
match_ip = geofeed.query("192.0.2.1")

# Query a prefix and include all matching sub-prefixes
all_matches = geofeed.query("192.0.2.0/24", return_all=True, include_longer=True)

# Build a high-level summary
summary = geofeed.info()
```

Async quick start:

```python
from geofeed_tools import AsyncGeoFeed

geofeed = AsyncGeoFeed("https://api.cloudflare.com/local-ip-ranges.csv")

# Methods mirror GeoFeed, but are awaitable
records = await geofeed.parse()
report = await geofeed.validate(check_aggregation=True)
summary = await geofeed.info()

# Or eagerly load first with the async factory
preloaded = await AsyncGeoFeed.from_source("https://api.cloudflare.com/local-ip-ranges.csv")
```

### Public Imports

The top-level package exports the main API object plus the public dataclasses:

```python
from geofeed_tools import (
  AsyncGeoFeed,
	GeoFeed,
	GeoFeedInfo,
	GeofeedRecord,
	QueryResult,
	ValidationIssue,
	ValidationReport,
)
```

### `AsyncGeoFeed`

`AsyncGeoFeed` is the native async counterpart to `GeoFeed` for library users who want to integrate geofeed processing into an asyncio application.

Constructor:

```python
AsyncGeoFeed(source: str)
```

Async factory for eager loading:

```python
await AsyncGeoFeed.from_source(source: str) -> AsyncGeoFeed
```

Available async methods:

- `await reload() -> None`
- `await parse(...) -> list[GeofeedRecord] | str`
- `await validate(...) -> ValidationReport | str`
- `await normalize(...) -> list[GeofeedRecord] | str`
- `await query(...) -> QueryResult | str`
- `await info(...) -> GeoFeedInfo | str`

Behavior notes:

- `AsyncGeoFeed` accepts the same flags and output modes as `GeoFeed` for `parse()`, `validate()`, `normalize()`, `query()`, and `info()`.
- Local file loading is performed asynchronously via thread offloading.
- Remote URL loading uses async HTTP and requires the `geofeed-tools[async]` extra.
- Parsing, validation, normalization, querying, and info generation run off the event loop in worker threads so library consumers can use the API without blocking the loop on large feeds.

### `GeoFeed`

#### Constructor

```python
GeoFeed(source: str, *, auto_load: bool = True)
```

Create a geofeed wrapper around a local file path or an HTTP(S) URL.

| Argument | Type | Default | Meaning |
| --- | --- | --- | --- |
| `source` | `str` | required | Local file path or remote HTTP(S) geofeed URL. |
| `auto_load` | `bool` | `True` | Load the source immediately. If `False`, the first call to `parse()`, `validate()`, `normalize()`, `query()`, `info()`, or `reload()` performs the load. |

After loading, the object keeps these attributes populated:

- `source`: original path or URL
- `raw`: raw bytes fetched from the source
- `content_type`: HTTP `Content-Type` header for URL sources, otherwise `None`
- `text`: decoded UTF-8 text with any UTF-8 BOM stripped during load

#### `reload()`

```python
reload() -> None
```

Re-read a local file or re-fetch a remote URL and refresh `raw`, `content_type`, and `text`.

#### `parse()`

```python
parse(
	*,
	include_validation: bool = True,
	normalize: bool = False,
	output: str = "objects",
) -> list[GeofeedRecord] | str
```

Parse the current source into geofeed records.

| Argument | Type | Default | Meaning |
| --- | --- | --- | --- |
| `include_validation` | `bool` | `True` | Annotate each returned record with `valid` and `validation_messages` based on validation errors. |
| `normalize` | `bool` | `False` | Normalize the feed first, then return normalized records instead of the original parsed rows. |
| `output` | `str` | `"objects"` | One of `"objects"`, `"json"`, or `"csv"`. Any other value raises `ValueError`. |

Return modes:

- `output="objects"`: returns `list[GeofeedRecord]`
- `output="json"`: returns a JSON array string
- `output="csv"`: returns CSV text

Notes:

- Malformed CSV rows and rows with a missing prefix are skipped during parsing.
- Rows with invalid prefixes are still returned by `parse()`. With `include_validation=True`, those records are marked invalid and include the corresponding validation messages.
- For `output="json"` and `output="csv"`, `include_validation=True` includes the `valid` state and validation messages in the serialized output.
- With `normalize=True`, records are rebuilt from normalized output. That is useful for producing clean data, but it does not preserve original source line numbers. If you need original per-line validation context, use `normalize=False`.

#### `validate()`

```python
validate(
	*,
	check_sort: bool = True,
	check_content_type: bool = True,
	check_aggregation: bool = False,
	output: str = "objects",
) -> ValidationReport | str
```

Validate the current source and return a structured report.

| Argument | Type | Default | Meaning |
| --- | --- | --- | --- |
| `check_sort` | `bool` | `True` | Check whether records are emitted in sorted prefix order. |
| `check_content_type` | `bool` | `True` | For HTTP(S) sources, warn when the response `Content-Type` is not `text/csv`. |
| `check_aggregation` | `bool` | `False` | Warn when multiple prefixes with identical geo metadata could be safely aggregated. |
| `output` | `str` | `"objects"` | One of `"objects"`, `"json"`, or `"text"`. Any other value raises `ValueError`. |

Return modes:

- `output="objects"`: returns `ValidationReport`
- `output="json"`: returns a JSON object string
- `output="text"`: returns a human-readable text report

#### `normalize()`

```python
normalize(
	*,
	uppercase: bool = True,
	sort: bool = True,
	aggregate: bool = True,
	dedupe: bool = True,
	fix_host_bits: bool = True,
	output: str = "objects",
) -> list[GeofeedRecord] | str
```

Normalize records into a cleaner, more canonical form.

| Argument | Type | Default | Meaning |
| --- | --- | --- | --- |
| `uppercase` | `bool` | `True` | Uppercase country and region fields. |
| `sort` | `bool` | `True` | Sort normalized output by IP family and network value. |
| `aggregate` | `bool` | `True` | Collapse prefixes that share identical geo metadata into larger prefixes when possible. |
| `dedupe` | `bool` | `True` | Remove exact duplicate `prefix + metadata` rows when `aggregate=False`. |
| `fix_host_bits` | `bool` | `True` | Accept prefixes with host bits set and coerce them to the containing network. If `False`, such rows are skipped. |
| `output` | `str` | `"objects"` | One of `"objects"`, `"json"`, or `"csv"`. Any other value raises `ValueError`. |

Return modes:

- `output="objects"`: returns `list[GeofeedRecord]`
- `output="json"`: returns a JSON array string
- `output="csv"`: returns CSV text

Notes:

- `aggregate=True` already removes exact duplicate networks within each metadata group, so `dedupe` only has an effect when `aggregate=False`.
- Normalized records are synthetic output rows. They do not preserve original line numbers, raw input lines, or validation metadata.

#### `query()`

```python
query(
	query: str,
	*,
	return_all: bool = False,
	include_longer: bool = False,
	output: str = "objects",
) -> QueryResult | str
```

Query the current geofeed with an IP address or CIDR prefix.

| Argument | Type | Default | Meaning |
| --- | --- | --- | --- |
| `query` | `str` | required | IP address or CIDR prefix to look up. |
| `return_all` | `bool` | `False` | Return every match instead of only the most specific one. |
| `include_longer` | `bool` | `False` | When the query is a prefix, include more-specific records that are contained inside that prefix. |
| `output` | `str` | `"objects"` | One of `"objects"`, `"json"`, or `"csv"`. Any other value raises `ValueError`. |

Return modes:

- `output="objects"`: returns `QueryResult`
- `output="json"`: returns a JSON object string
- `output="csv"`: returns CSV text containing matching records only

Matching behavior:

- For IP queries, the default behavior is effectively longest-prefix match.
- For prefix queries, the default behavior returns the most specific covering prefix.
- `return_all=True` returns every match sorted from most specific to least specific.
- `include_longer=True` also returns more-specific prefixes contained by the queried network.

#### `info()`

```python
info(*, output: str = "objects") -> GeoFeedInfo | str
```

Compute summary statistics for the current geofeed.

| Argument | Type | Default | Meaning |
| --- | --- | --- | --- |
| `output` | `str` | `"objects"` | One of `"objects"` or `"json"`. Any other value raises `ValueError`. |

Return modes:

- `output="objects"`: returns `GeoFeedInfo`
- `output="json"`: returns a JSON object string

### Public Data Models

#### `GeofeedRecord`

Represents a single geofeed row.

| Field | Type | Meaning |
| --- | --- | --- |
| `prefix` | `str` | Network prefix from the feed. |
| `country` | `str` | ISO 3166-1 alpha-2 country code when present. |
| `region` | `str` | Region or subdivision field. |
| `city` | `str` | City field. |
| `postal_code` | `str` | Postal code field. |
| `line` | `int` | Source line number when the record came directly from parsing. Normalized records may use `0`. |
| `raw_line` | `str | None` | Original source line when available. Query results include this when sourced from the original feed. |
| `valid` | `bool` | `True` when no validation errors were attached to the record. |
| `validation_messages` | `tuple[str, ...]` | Record-level validation error messages. |

Helper:

```python
record.as_dict(include_validation: bool = True, include_raw_line: bool = False) -> dict[str, object]
```

#### `ValidationIssue`

Represents one validation error or warning.

| Field | Type | Meaning |
| --- | --- | --- |
| `severity` | `str` | Usually `"error"` or `"warning"`. |
| `line` | `int | None` | Source line number, or `None` for file-level issues. |
| `code` | `str` | Stable machine-readable issue code. |
| `message` | `str` | Human-readable message text. |
| `raw_line` | `str | None` | Original line text when available. |

Helper:

```python
issue.format() -> str
```

#### `ValidationReport`

Overall validation result for a feed.

| Field | Type | Meaning |
| --- | --- | --- |
| `source` | `str` | Original path or URL. |
| `records` | `int` | Number of data records processed. |
| `errors` | `int` | Number of validation errors. |
| `warnings` | `int` | Number of validation warnings. |
| `valid` | `bool` | `True` when `errors == 0`. |
| `issues` | `tuple[ValidationIssue, ...]` | Full issue list. |

Helper:

```python
report.as_dict() -> dict[str, object]
```

#### `QueryResult`

Lookup result returned by `GeoFeed.query()`.

| Field | Type | Meaning |
| --- | --- | --- |
| `query` | `str` | Original query string. |
| `matches` | `tuple[GeofeedRecord, ...]` | Matching records, ordered most-specific first. |

Helper:

```python
result.as_dict() -> dict[str, object]
```

#### `GeoFeedInfo`

Summary statistics returned by `GeoFeed.info()`.

| Field | Type | Meaning |
| --- | --- | --- |
| `source` | `str` | Original path or URL. |
| `total_records` | `int` | Number of parsed records. |
| `unique_prefixes` | `int` | Number of unique prefixes. |
| `ipv4_records` | `int` | Number of IPv4 records. |
| `ipv6_records` | `int` | Number of IPv6 records. |
| `unique_countries` | `int` | Count of distinct country values. |
| `unique_regions` | `int` | Count of distinct region values. |
| `unique_cities` | `int` | Count of distinct city values. |
| `unique_postal_codes` | `int` | Count of distinct postal-code values. |
| `duplicates` | `int` | Total records minus unique prefixes. |
| `errors` | `int` | Validation error count. |
| `warnings` | `int` | Validation warning count. |
| `metadata` | `dict[str, object]` | Reserved extensible metadata dictionary. |

Helper:

```python
info.as_dict() -> dict[str, object]
```

### Error Handling

Common exceptions to expect when using the Python API:

- `ValueError`: invalid `output` mode or an invalid query string passed to `query()`
- `FileNotFoundError` or other `OSError` subclasses: local file read failures
- `geofeed_tools.loader.FetchError`: remote HTTP(S) fetch failures

Example:

```python
from geofeed_tools import GeoFeed
from geofeed_tools.loader import FetchError

try:
	geofeed = GeoFeed("https://example.com/geofeed.csv")
	report = geofeed.validate(check_content_type=True)
except FetchError as exc:
	print(f"fetch failed: {exc}")
```

## CLI Usage

### Quick Start

The CLI entrypoint is:

```bash
geofeed-tools <command> [options]
```

Common quick-start examples:

```bash
# Validate and print a human-readable report
geofeed-tools validate geofeeds.csv

# Dump parsed records as JSON
geofeed-tools dump geofeeds.csv

# Dump parsed records as geofeed CSV
geofeed-tools dump geofeeds.csv --format csv

# Dump parsed records as a table
geofeed-tools dump geofeeds.csv --format table

# Normalize to canonical CSV and write to a file
geofeed-tools normalize geofeeds.csv --output normalized.csv

# Query by IP address or prefix
geofeed-tools query geofeeds.csv 192.0.2.200

# Show summary statistics
geofeed-tools info geofeeds.csv

# Use hook mode in CI or pre-commit checks
geofeed-tools hook geofeeds.csv --strict
```

For command-specific help:

```bash
geofeed-tools --help
geofeed-tools validate --help
```

### Common CLI Behavior

- Every command takes a `source` positional argument pointing to a local file or HTTP(S) URL.
- Every command supports cumulative `-v` or `--verbose` flags.
- Verbosity levels are:
	- `-v`: INFO
	- `-vv`: DEBUG
	- `-vvv`: TRACE
- CLI support is optional. If the CLI extra is not installed, running the command exits with a message telling you to install `.[cli]`.

### Command Reference

#### `validate`

Usage:

```bash
geofeed-tools validate SOURCE [OPTIONS]
```

Validate a geofeed source and print either a text report or JSON.

| Option | Default | Meaning |
| --- | --- | --- |
| `--json` | off | Emit the validation report as JSON instead of text. |
| `--strict` | off | Exit with code `1` when warnings are present, not just errors. |
| `--check-aggregation` | off | Enable warnings for prefixes that could be safely aggregated. |
| `--no-sort-check` | off | Disable sort-order warnings. |
| `--no-content-type-check` | off | Disable `Content-Type` warnings for URL sources. |
| `-v`, `--verbose` | `0` | Increase log verbosity. |

Examples:

```bash
geofeed-tools validate geofeeds.csv
geofeed-tools validate geofeeds.csv --json
geofeed-tools validate geofeeds.csv --check-aggregation
geofeed-tools validate geofeeds.csv --no-sort-check --no-content-type-check
geofeed-tools validate geofeeds.csv --strict
```

Exit behavior:

- Exits `0` when there are no validation errors.
- Exits `1` when validation errors are found.
- With `--strict`, exits `1` when warnings are found too.

#### `dump`

Usage:

```bash
geofeed-tools dump SOURCE [OPTIONS]
```

Parse the geofeed and print records as a JSON array.

| Option | Default | Meaning |
| --- | --- | --- |
| `--format`, `-f` | `json` | Output format: `json`, `csv`, or `table`. |
| `--normalize` | off | Normalize records before dumping them. |
| `--no-validation` | off | Skip per-record validation annotations in JSON or table output. |
| `-v`, `--verbose` | `0` | Increase log verbosity. |

Examples:

```bash
geofeed-tools dump geofeeds.csv
geofeed-tools dump geofeeds.csv --format csv
geofeed-tools dump geofeeds.csv --format table
geofeed-tools dump geofeeds.csv --no-validation
geofeed-tools dump geofeeds.csv --normalize
```

Output notes:

- Default output is JSON.
- `--format csv` emits standard 5-column geofeed rows.
- `--format table` emits a GitHub-style table rendered with `tabulate`.
- By default, JSON and table output include `valid` and `validation_messages` fields.
- `--no-validation` affects JSON and table output only. CSV output always uses plain geofeed rows.
- With `--normalize`, the output reflects normalized records rather than the original parsed rows.

#### `normalize`

Usage:

```bash
geofeed-tools normalize SOURCE [OPTIONS]
```

Normalize a geofeed and emit canonical CSV.

| Option | Default | Meaning |
| --- | --- | --- |
| `--output`, `-o` | stdout | Write normalized CSV to a file instead of stdout. |
| `--no-uppercase` | off | Do not uppercase country and region fields. |
| `--no-sort` | off | Do not sort output by IP family and network. |
| `--no-aggregate` | off | Do not collapse compatible prefixes into larger prefixes. |
| `--no-dedupe` | off | Do not remove exact duplicate rows when aggregation is disabled. |
| `--no-host-bit-fix` | off | Do not coerce prefixes with host bits set to their containing network. |
| `-v`, `--verbose` | `0` | Increase log verbosity. |

Examples:

```bash
geofeed-tools normalize geofeeds.csv
geofeed-tools normalize geofeeds.csv --output normalized.csv
geofeed-tools normalize geofeeds.csv --no-uppercase --no-sort --no-aggregate --no-dedupe --no-host-bit-fix
```

Output notes:

- Output is always CSV.
- Without `--output`, the normalized CSV is printed to stdout.
- With `--output`, the destination file is written using UTF-8 encoding.

#### `query`

Usage:

```bash
geofeed-tools query SOURCE QUERY [OPTIONS]
```

Query a geofeed using an IP address or CIDR prefix.

| Argument | Meaning |
| --- | --- |
| `SOURCE` | Local file path or HTTP(S) geofeed URL. |
| `QUERY` | IP address or CIDR prefix to look up. |

| Option | Default | Meaning |
| --- | --- | --- |
| `--all` | off | Return all matches instead of only the most specific match. |
| `--longer` | off | Include more-specific prefixes contained by the query prefix. |
| `--json` | off | Emit a JSON result object instead of CSV rows. |
| `-v`, `--verbose` | `0` | Increase log verbosity. |

Examples:

```bash
geofeed-tools query geofeeds.csv 192.0.2.200
geofeed-tools query geofeeds.csv 192.0.2.200 --json
geofeed-tools query geofeeds.csv 192.0.2.0/24 --all --longer --json
```

Output and exit notes:

- Default output is CSV containing matching rows only.
- With `--json`, output is a JSON object with `query` and `matches`.
- In CSV mode, no match prints an error to stderr and exits with code `1`.
- In JSON mode, no match returns an empty `matches` array and exits successfully.

#### `info`

Usage:

```bash
geofeed-tools info SOURCE [OPTIONS]
```

Display high-level geofeed statistics.

| Option | Default | Meaning |
| --- | --- | --- |
| `--json` | off | Emit summary information as JSON instead of tables. |
| `-v`, `--verbose` | `0` | Increase log verbosity. |

Examples:

```bash
geofeed-tools info geofeeds.csv
geofeed-tools info geofeeds.csv --json
```

Output notes:

- Default output is a human-readable summary rendered as multiple GitHub-style tables.
- JSON mode returns the same data as the Python `GeoFeed.info(output="json")` API.

#### `hook`

Usage:

```bash
geofeed-tools hook SOURCE [OPTIONS]
```

Run validation in a hook-friendly mode for CI, pre-commit, or automated checks.

| Option | Default | Meaning |
| --- | --- | --- |
| `--strict` | off | Fail when warnings are present, not just errors. |
| `--show-issues` / `--no-issues` | `--show-issues` | Print or suppress individual validation issue lines. |
| `-v`, `--verbose` | `0` | Increase log verbosity. |

Examples:

```bash
geofeed-tools hook geofeeds.csv
geofeed-tools hook geofeeds.csv --no-issues
geofeed-tools hook geofeeds.csv --strict
```

Output and exit notes:

- Issue lines and summary messages are written to stderr.
- By default, the command fails only on errors.
- With `--strict`, the command also fails on warnings.
- Success summary format is `hook: OK ...`; failure summary format is `hook: FAIL ...`.

### GitHub Actions Integration

The `hook` command is designed to work well as a CI quality gate. This repository publishes a reusable workflow at [.github/workflows/geofeed-validation.yml](.github/workflows/geofeed-validation.yml) and also includes a caller example at [examples/github-actions/geofeed-validation.yml](examples/github-actions/geofeed-validation.yml).

#### How To Use It In Another Repository

Create a small workflow in your repository that calls the shared workflow with `uses`:

```yaml
name: Validate geofeed

on:
  pull_request:
    paths:
      - "path/to/geofeed.csv"
  push:
    branches:
      - main
    paths:
      - "path/to/geofeed.csv"
  workflow_dispatch:

permissions:
  contents: read

jobs:
  geofeed-validation:
    uses: python-modules/geofeed-tools/.github/workflows/geofeed-validation.yml@main
    with:
      geofeed_path: path/to/geofeed.csv
      strict: false
```

Replace `path/to/geofeed.csv` with the tracked geofeed file path in your repository.

The above example disables strict mode validation - warnings are logged but permitted. To require strict mode validation set `strict` to `true`.

## Testing

Recommended workflow commands:

```bash
make test
make test-html
make test-integration
```

`make test-html` writes a self-contained report to:

- `reports/pytest-report.html`

Run non-integration tests:

```bash
pytest -m "not integration"
```

Run integration tests (real HTTP requests):

```bash
pytest -m integration
```

### HTML test reports

`pytest-html` is configured in `pyproject.toml`. Running `pytest` generates a
self-contained HTML report at:

- `reports/pytest-report.html`

Open it in a browser after test execution.

### Test Notes

- Integration tests depend HTTP access to a set of well known geofeed files. The content of those files may change at any time resulting in different test failures.
