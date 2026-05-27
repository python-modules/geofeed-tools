# geofeed-tools

`geofeed-tools` is a Python library and CLI for working with RFC 8805 geofeeds. It supports parsing, validation, normalization, querying, and summary reporting for local files and remote HTTP(S) sources.

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

Install development dependencies:

```bash
uv pip install 'geofeed-tools[dev]'
```

## Python API Quick Start

```python
from geofeed_tools import GeoFeed

# Set up module and load the geofeed (retrieving the file)
geofeed = GeoFeed("https://api.cloudflare.com/local-ip-ranges.csv")

# Parse the geofeed returning a set of GeofeedRecord objects
# Optionally normalize the geofeed before parsing by supplying "normalize=true"
records = geofeed.parse()

# Parse the geofeed returning JSON data
json_records = geofeed.parse(output="json")

# Validate the geofeed returning a list of ValidationIssue objects for any errors/warnings
report = geofeed.validate()

# Normalize the geofeed back into a CSV again
csv_output = geofeed.normalize(output="csv")

# Query for an IP address
match_ip = geofeed.query("192.0.2.1")

# Query for a network prefix
match_prefix = geofeed.query("192.0.2.0/24")

# Summarize
summary = geofeed.info()
```

## CLI Usage

### Validate a geofeed

```bash
geofeed-tools validate geofeeds.csv
```

JSON output:

```bash
geofeed-tools validate geofeeds.csv --json
```

Strict mode (warnings fail the command):

```bash
geofeed-tools validate geofeeds.csv --strict
```

Enable aggregation checks:

```bash
geofeed-tools validate geofeeds.csv --check-aggregation
```

Disable sort-order or content-type warnings:

```bash
geofeed-tools validate geofeeds.csv --no-sort-check --no-content-type-check
```

### Dump records as JSON

Dump parsed records as a JSON array of objects:

```bash
geofeed-tools dump geofeeds.csv
```

Skip per-record validation fields in the JSON output:

```bash
geofeed-tools dump geofeeds.csv --no-validation
```

Normalize records before dumping JSON:

```bash
geofeed-tools dump geofeeds.csv --normalize
```

### Query by IP or prefix

CSV output (default):

```bash
geofeed-tools query geofeeds.csv 192.0.2.200
```

JSON output:

```bash
geofeed-tools query geofeeds.csv 192.0.2.200 --json
```

Show all matches and include more-specific prefixes:

```bash
geofeed-tools query geofeeds.csv 192.0.2.0/24 --all --longer --json
```

### Normalize records

```bash
geofeed-tools normalize geofeeds.csv --output normalized.csv
```

Disable individual normalization steps:

```bash
geofeed-tools normalize geofeeds.csv --no-uppercase --no-sort --no-aggregate --no-dedupe --no-host-bit-fix
```

### Info summary

```bash
geofeed-tools info geofeeds.csv
```

JSON output:

```bash
geofeed-tools info geofeeds.csv --json
```

### Hook mode (CI/pre-commit friendly)

Print all issues + summary line:

```bash
geofeed-tools hook geofeeds.csv
```

Suppress individual issue lines and only show summary:

```bash
geofeed-tools hook geofeeds.csv --no-issues
```

Fail on warnings too:

```bash
geofeed-tools hook geofeeds.csv --strict
```

### Verbosity levels

All CLI commands support `-v/--verbose` with cumulative levels:

- `-v`: INFO
- `-vv`: DEBUG
- `-vvv`: TRACE

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
