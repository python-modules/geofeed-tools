# geofeed-tools

`geofeed-tools` is a Python library and CLI for working with [RFC 8805](https://datatracker.ietf.org/doc/html/rfc8805) geofeeds. It parses, validates, normalizes, queries, and summarizes geofeeds from local files, HTTP(S) sources, **or directly from an IP address / CIDR prefix** — in the IP/prefix case the geofeed URL is auto-discovered via RDAP before the operation runs.

- [geofeed-tools](#geofeed-tools)
  - [Install](#install)
  - [CLI quick start](#cli-quick-start)
  - [Source argument: file, URL, or IP/prefix](#source-argument-file-url-or-ipprefix)
  - [Output formats](#output-formats)
  - [CLI command reference](#cli-command-reference)
    - [`validate`](#validate)
    - [`dump`](#dump)
    - [`normalize`](#normalize)
    - [`filter`](#filter)
    - [`query`](#query)
    - [`doctor`](#doctor)
    - [`lookup`](#lookup)
    - [`info`](#info)
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
      - [`GeoFeedInfo` / `CountryStatistics` / `NormalizationPreview`](#geofeedinfo--countrystatistics--normalizationpreview)
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

# Show detailed info — works against a file, a URL, OR an IP/prefix (auto-RDAP-discovered)
geofeed-tools info geofeeds.csv
geofeed-tools info 31.133.128.1            # discovers the geofeed via RDAP, then info
geofeed-tools info https://example.com/geofeed.csv

# Query a geofeed for an IP or prefix
geofeed-tools query geofeeds.csv 192.0.2.200

# Filter records by country, region, prefix length, etc. (combinable)
geofeed-tools filter geofeeds.csv --country CA --family ipv4 --prefix-length 24 --longer

# Normalize the feed and write canonical CSV to a file
geofeed-tools normalize geofeeds.csv --output normalized.csv

# Validate in CI / pre-commit mode (machine-friendly exit codes + machine-readable output)
geofeed-tools validate geofeeds.csv --hook --strict
```

Per-command help is always available:

```bash
geofeed-tools --help
geofeed-tools doctor --help
```

## Source argument: file, URL, or IP/prefix

Every command that takes a `SOURCE` (`validate`, `dump`, `normalize`, `filter`, `query`, `info`) accepts three input shapes:

| Input                                         | Behavior                                                                                  |
| --------------------------------------------- | ----------------------------------------------------------------------------------------- |
| Local file path (`./geofeeds.csv`)            | Read from disk.                                                                           |
| HTTP(S) URL (`https://example.com/foo.csv`)   | Fetch and use directly.                                                                   |
| IP address or CIDR prefix (`1.1.1.1`, `2001:db8::/32`) | RDAP-discover the published geofeed URL (rdap.org by default), then load and run on it.  |

Discovery failures (no geofeed URL published for the IP/prefix) exit 1 with a friendly message. The same auto-discovery works in the Python API — `GeoFeed("1.1.1.1").info()` does the right thing.

The `query`, `doctor`, and `lookup` commands take a separate `QUERY` argument (always an IP or prefix). `lookup` is now equivalent to `GeoFeed(QUERY).query(QUERY)` — it shares the same discovery path as `info <IP>`.

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

- `validate` (with or without `--hook`): exit 1 when errors are found (or warnings with `--strict`), regardless of format.
- `query` / `lookup`: exit 1 on no match in any non-JSON format; exit 0 in `json` mode (the empty `matches` array is the answer). `lookup` always exits 1 when no geofeed is discovered.
- `doctor`: exit 1 when no geofeed is discovered or no record matches, regardless of format.
- `dump` / `normalize` / `info`: exit 0 on success; exit 1 when an IP/prefix source can't be resolved via RDAP.

## CLI command reference

### `validate`

```bash
geofeed-tools validate SOURCE [--format ...] [--strict] [--hook] [--show-issues/--no-issues]
                              [--check-aggregation] [--no-sort-check] [--no-content-type-check] [-v]
```

Validate a geofeed and report issues. Add `--hook` for CI/CD integration — it renders machine-friendly hook output (issues table / status line on stderr in rich mode, `path:line:severity:code:message` rows on stdout in grep mode) while keeping the same exit-code policy.

| Option                    | Default | Meaning                                                                       |
| ------------------------- | ------- | ----------------------------------------------------------------------------- |
| `--format`, `-f`          | `rich`  | Output format.                                                                |
| `--strict`                | off     | Exit 1 when warnings are present, not just errors.                            |
| `--hook`                  | off     | CI-friendly rendering (status line + issues), same exit codes.                |
| `--show-issues`/`--no-issues` | on  | In `--hook` mode, print individual validation issues. Ignored otherwise.      |
| `--check-aggregation`     | off     | Warn for prefixes that could be safely aggregated.                            |
| `--no-sort-check`         | off     | Disable sort-order warnings.                                                  |
| `--no-content-type-check` | off     | Disable `Content-Type` warnings for URL sources.                              |
| `-v`, `--verbose`         | `0`     | Increase log verbosity (`-v` INFO, `-vv` DEBUG, `-vvv` TRACE).                |

`--format grep` emits one line per issue in `path:line:severity:code:message` form, identical to GCC/grep style for easy pipeline use. The standalone `hook` subcommand was removed in 0.2.0 — use `validate --hook` instead.

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

### `filter`

```bash
geofeed-tools filter SOURCE [--format ...]
                            [--prefix CIDR] [--country CC] [--region SUB]
                            [--city NAME] [--postal-code PC]
                            [--family ipv4|ipv6]
                            [--prefix-length N]
                            [--longer]
                            [-v]
```

Return records matching every supplied predicate (AND).

| Option            | Default | Meaning                                                                                       |
| ----------------- | ------- | --------------------------------------------------------------------------------------------- |
| `--prefix`        | —       | CIDR prefix. Exact match unless `--longer` is set.                                            |
| `--country`       | —       | ISO 3166-1 alpha-2 code (case-insensitive).                                                   |
| `--region`        | —       | ISO 3166-2 subdivision code (case-insensitive).                                               |
| `--city`          | —       | City name (case-insensitive).                                                                 |
| `--postal-code`   | —       | Postal code (case-insensitive).                                                               |
| `--family`        | both    | Restrict to `ipv4` or `ipv6`.                                                                 |
| `--prefix-length` | —       | Filter by CIDR length. Exact match unless `--longer` is set.                                  |
| `--longer`        | off     | For `--prefix`, also match subnets contained by it. For `--prefix-length`, match length >= N. |

Filters combine. Examples:

```bash
# All Canadian IPv4 records covering /24-or-longer
geofeed-tools filter geofeeds.csv --country CA --family ipv4 --prefix-length 24 --longer

# Records inside 192.0.2.0/24 in Ontario, Canada
geofeed-tools filter geofeeds.csv --country CA --region CA-ON --prefix 192.0.2.0/24 --longer

# All IPv6 records for a specific city, as raw CSV
geofeed-tools filter geofeeds.csv --family ipv6 --city Toronto --format grep
```

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

Same RDAP discovery flow as `doctor`, but the output contains only the matching geofeed records (no RDAP metadata). Internally this is equivalent to `GeoFeed(QUERY).query(QUERY)` — i.e. the same code path used when an IP/prefix is passed as a `SOURCE` to other commands. Use `lookup` when you only need the geographic answer; use `doctor` when you also want to see how the answer was discovered, including the RDAP trace and a query result that's filtered to the RIR-published address range.

### `info`

```bash
geofeed-tools info SOURCE [--format ...] [--top-n N] [-v]
```

Comprehensive geofeed analysis. `SOURCE` may be a file, URL, or IP/prefix (RDAP auto-discovered). The command runs the feed through parsing, validation, and a virtual normalize pass and reports:

- **Overview** — total prefixes, unique prefixes, duplicates, errors and warnings.
- **/24- and /48-equivalents** — total address coverage measured as `sum_addresses // 256` for IPv4 and `sum_addresses // 2^80` for IPv6. Prefixes shorter than the divisor contribute whole multiples (a /23 = 2 /24s); fragments smaller than the divisor (a lone /25) round down to zero.
- **Geography summary** — distinct counts of countries, regions, cities, and postal codes.
- **Per-country breakdown** — prefix and slash counts split by IP version, sorted by total prefix count.
- **Prefix-length histograms** — sorted ascending for IPv4 and IPv6.
- **Top regions and top cities** — sized by `--top-n` (default 20).
- **If normalized** — projected prefix counts, /24- and /48-equivalents, the number of invalid rows that would be dropped, and the number of rows merged by aggregation/dedupe.

The library `info()` method also exposes the plain and grep renderings directly via `output="text"` and `output="grep"`, so consumers without rich installed can produce the same human/machine output as the CLI.

The `grep` format emits one `key=value` line per metric, including the normalize preview and ranked keys for top regions/cities:

```
prefixes_total=3
unique_prefixes=3
slash_24s=1
slash_48s=65536
unique_countries=1
country.US.prefixes_v4=2
normalized.prefixes_total=2
normalized.invalid_removed=0
normalized.aggregated=1
top_city.1.name="San Francisco"
top_city.1.count=2
```

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

# Filter records by any combination of fields (all kwargs optional, AND'd)
canada = geofeed.filter(country="CA")
narrow = geofeed.filter(country="CA", region="CA-ON", prefix="192.0.2.0/24")
small_v4 = geofeed.filter(family="ipv4", prefix_length=24, include_longer=True)

# IP/prefix source: GeoFeed auto-discovers the published geofeed via RDAP
discovered = GeoFeed("1.1.1.1")                        # RDAP-discovers + loads
discovered.discovery.geofeed_url                       # where it landed
discovered.original_source                             # "1.1.1.1"
discovered.source                                      # resolved URL after RDAP

# RDAP discovery static helpers (instance-less convenience wrappers)
diagnosis = GeoFeed.doctor("31.133.128.1")             # DoctorResult (RDAP trace + matches)
matches = GeoFeed.lookup("31.133.128.1")               # QueryResult — same as GeoFeed(q).query(q)

summary = geofeed.info()                               # GeoFeedInfo (incl. normalize preview)
text = geofeed.info(output="text")                     # str — human-readable plain rendering
grep = geofeed.info(output="grep")                     # str — key=value lines

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
GeoFeed(source: str, *, auto_load: bool = True, cache_query_index: bool = True, rdap_method: str = "rdap.org")
GeoFeed.from_source(source: str, *, cache_query_index: bool = True, rdap_method: str = "rdap.org") -> GeoFeed
```

| Argument            | Default       | Meaning                                                                                       |
| ------------------- | ------------- | --------------------------------------------------------------------------------------------- |
| `source`            | —             | Local file path, HTTP(S) URL, or IP/prefix (auto-RDAP-discovered).                            |
| `auto_load`         | `True`        | If `True`, load the source immediately; otherwise lazily on first operation.                  |
| `cache_query_index` | `True`        | Cache the parsed query index between `query()` calls for repeated lookups.                    |
| `rdap_method`       | `"rdap.org"`  | RDAP discovery method used when `source` is an IP/prefix. `"iana-bootstrap"` is also accepted. |

When `source` is an IP or CIDR prefix, the first load triggers an RDAP discovery. The resolved geofeed URL is then loaded and used for every operation; subsequent `reload()` calls reuse the discovered URL without re-resolving. Raises `GeoFeedDiscoveryError` if no geofeed URL is published for the input.

After loading: `source`, `raw`, `content_type`, and `text` are populated. When discovery happened, `original_source` holds the input IP/prefix and `discovery: DoctorLookup` holds the full RDAP metadata. For file/URL sources, `original_source == source` and `discovery is None`.

Parsed records (and their networks) are also cached on the instance and shared across `parse()`, `filter()`, `info()`, etc.; the cache is invalidated by `reload()`.

Methods (every method also accepts `output="objects"` (default), `"json"`, and, where applicable, `"csv"` or `"text"`):

| Method                                       | Return                                | Notes                                                                                       |
| -------------------------------------------- | ------------------------------------- | ------------------------------------------------------------------------------------------- |
| `reload()`                                   | `None`                                | Re-fetch / re-read the source.                                                              |
| `parse(*, include_validation, normalize)`    | `list[GeofeedRecord] \| str`          | Records, optionally annotated with `valid`/`validation_messages`.                           |
| `validate(*, check_sort, check_content_type, check_aggregation)` | `ValidationReport \| str` | Structured validation report.                                                               |
| `normalize(*, uppercase, sort, aggregate, dedupe, fix_host_bits)` | `list[GeofeedRecord] \| str` | Canonical normalized records.                                                               |
| `query(query, *, return_all, include_longer)` | `QueryResult \| str`                  | Longest-prefix match (default) or all matches.                                              |
| `filter(*, prefix=None, country=None, region=None, city=None, postal_code=None, family=None, prefix_length=None, include_longer=False)` | `list[GeofeedRecord] \| str` | Records matching every supplied predicate (AND). See [`filter` CLI section](#filter) for semantics. |
| `info(*, top_n=20)`                          | `GeoFeedInfo \| str`                  | Detailed breakdowns: counts, geography, per-country prefixes/slash counts, length histogram, top regions/cities, and a normalize preview. Also supports `output="text"` (human plain text) and `output="grep"` (`key=value` lines) in addition to `"objects"` / `"json"`. |

Behavior notes:

- `parse()`: malformed CSV rows and rows with empty prefixes are skipped. Rows with invalid CIDRs are still returned and, with `include_validation=True`, marked invalid. With `normalize=True`, source line numbers are not preserved.
- `normalize()`: `aggregate=True` implies dedupe within each metadata group. `fix_host_bits=False` skips rows like `192.0.2.5/24` instead of coercing them.
- `query()`: for IP queries the default returns the most specific covering prefix. `return_all=True` returns every match ordered most-specific first; `include_longer=True` also includes more-specific prefixes contained by the queried CIDR.

### `AsyncGeoFeed` class

```python
AsyncGeoFeed(source: str, *, cache_query_index: bool = True, rdap_method: str = "rdap.org")
await AsyncGeoFeed.from_source(source: str, *, cache_query_index: bool = True, rdap_method: str = "rdap.org") -> AsyncGeoFeed
```

Mirrors `GeoFeed` but loads, parses, validates, normalizes, queries, and computes info asynchronously. CPU-bound work runs in a worker thread so the event loop stays responsive. URL fetches use `httpx` and require the `geofeed-tools[async]` extra; local file reads are offloaded via `asyncio.to_thread`. RDAP discovery for IP/prefix sources runs asynchronously via `httpx` as well. `AsyncGeoFeed` has no `auto_load` flag — use `from_source` for one-step construction + load.

### Static helpers (`doctor` / `lookup`)

```python
GeoFeed.doctor(query, *, return_all=False, include_longer=False, rdap_method="rdap.org", output="objects") -> DoctorResult | str
GeoFeed.lookup(query, *, return_all=False, include_longer=False, rdap_method="rdap.org", output="objects") -> QueryResult | str

await AsyncGeoFeed.doctor(...)
await AsyncGeoFeed.lookup(...)
```

`doctor()` returns the full `DoctorResult` (RDAP trace + matches, filtered to the RIR-published address range). `lookup()` is a thin wrapper around `GeoFeed(query, rdap_method=...).query(query, ...)` — same auto-discovery as passing an IP/prefix as a source — and raises `GeoFeedDiscoveryError` when no geofeed URL is published. Both helpers accept the same `rdap_method` values; `lookup` does not apply RIR range filtering.

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

#### `GeoFeedInfo` / `CountryStatistics` / `NormalizationPreview`

Returned by `GeoFeed.info()` and `AsyncGeoFeed.info()`.

`GeoFeedInfo`:

| Field                  | Type                                  | Meaning                                                                                              |
| ---------------------- | ------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `source`               | `str`                                 | Original path or URL.                                                                                |
| `prefixes_v4`          | `int`                                 | IPv4 prefix count.                                                                                   |
| `prefixes_v6`          | `int`                                 | IPv6 prefix count.                                                                                   |
| `unique_prefixes`      | `int`                                 | Distinct prefix string count.                                                                        |
| `duplicates`           | `int`                                 | `prefixes_total - unique_prefixes`.                                                                  |
| `slash_24s`            | `int`                                 | IPv4 address space in /24-equivalents (`sum_addresses // 256`).                                       |
| `slash_48s`            | `int`                                 | IPv6 address space in /48-equivalents (`sum_addresses // 2**80`).                                     |
| `unique_countries`     | `int`                                 | Distinct country count.                                                                              |
| `unique_regions`       | `int`                                 | Distinct region count.                                                                               |
| `unique_cities`        | `int`                                 | Distinct city count.                                                                                 |
| `unique_postal_codes`  | `int`                                 | Distinct postal-code count.                                                                          |
| `errors`               | `int`                                 | Validation error count.                                                                              |
| `warnings`             | `int`                                 | Validation warning count.                                                                            |
| `by_country`           | `tuple[CountryStatistics, ...]`       | Per-country breakdown, sorted by descending total prefix count.                                      |
| `prefix_length_v4`     | `tuple[tuple[int, int], ...]`         | Sorted `(prefixlen, count)` histogram for IPv4.                                                      |
| `prefix_length_v6`     | `tuple[tuple[int, int], ...]`         | Sorted `(prefixlen, count)` histogram for IPv6.                                                      |
| `top_regions`          | `tuple[tuple[str, int], ...]`         | Top-`top_n` `(region, count)` pairs by prefix count.                                                 |
| `top_cities`           | `tuple[tuple[str, int], ...]`         | Top-`top_n` `(city, count)` pairs by prefix count.                                                   |
| `normalized`           | `NormalizationPreview \| None`        | Projected state after a default `normalize()`; `None` if the builder was called without text input.  |
| `metadata`             | `dict[str, object]`                   | Reserved for extensible metadata.                                                                    |

Properties: `prefixes_total` (= `prefixes_v4 + prefixes_v6`) and `total_records` (alias of `prefixes_total`).

`CountryStatistics` (one row in `by_country`):

| Field           | Type    | Meaning                                       |
| --------------- | ------- | --------------------------------------------- |
| `country`       | `str`   | ISO 3166-1 alpha-2 code, uppercased.          |
| `prefixes_v4`   | `int`   | IPv4 prefix count for this country.           |
| `prefixes_v6`   | `int`   | IPv6 prefix count for this country.           |
| `slash_24s`     | `int`   | IPv4 coverage in /24-equivalents.             |
| `slash_48s`     | `int`   | IPv6 coverage in /48-equivalents.             |

Properties: `prefixes_total`.

`NormalizationPreview` (the `normalized` field of `GeoFeedInfo`):

| Field             | Type   | Meaning                                                                                  |
| ----------------- | ------ | ---------------------------------------------------------------------------------------- |
| `prefixes_total`  | `int`  | Projected total prefix count after `normalize()`.                                        |
| `prefixes_v4`     | `int`  | Projected IPv4 prefix count.                                                             |
| `prefixes_v6`     | `int`  | Projected IPv6 prefix count.                                                             |
| `slash_24s`       | `int`  | Projected IPv4 /24-equivalents.                                                          |
| `slash_48s`       | `int`  | Projected IPv6 /48-equivalents.                                                          |
| `invalid_removed` | `int`  | Rows dropped because their prefix could not be parsed (even with host-bit fixing).       |
| `aggregated`      | `int`  | Rows folded into a supernet or removed as exact duplicates during aggregation/dedupe.    |

### Error handling

| Exception                                  | Raised when                                                                       |
| ------------------------------------------ | --------------------------------------------------------------------------------- |
| `ValueError`                               | Invalid `output` mode or unparseable query string.                                |
| `geofeed_tools.GeoFeedDiscoveryError`      | `GeoFeed(ip)`/`lookup()` finds no published geofeed URL for the input IP/prefix. |
| `geofeed_tools.loader.FetchError`          | Remote HTTP(S) or RDAP fetch failure.                                             |
| `FileNotFoundError` / `OSError`            | Local file read failure.                                                          |

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

The `validate --hook` command is designed as a CI quality gate. This repository publishes a reusable workflow at [.github/workflows/geofeed-validation.yml](.github/workflows/geofeed-validation.yml) and a caller example at [examples/github-actions/geofeed-validation.yml](examples/github-actions/geofeed-validation.yml).

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
