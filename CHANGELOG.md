# geofeed-tools Changelog

## PENDING - 0.2.0

Major changes:

- Pretty format CLI output by default with colours and better messages
- Add "--format" flag for CLI commands to choose between rich/plain/grep/json
- Add filter API/CLI command
- Remove `hook` CLI command - merged into `validate` command.
- Accept an IP address or prefix instead of file/URL to load geofeed for. If an IP/prefix is provided RDAP will be used to discover the geofeed file.

Other changes:

- Misc small fixups
- Refactor things to reduce complexity
- Drop CLI requirement for tabulate and use rich for formatting (already pulled in from tabulate)
- Update info command to provide actual useful information and statistics
- Default to showing help message without args/command provided
- Fix caching across subsequent method calls
- Split renderer for readability

## 2026-05-26 - 0.1.2

- Improve query cache handling
- Add `doctor` API and CLI support to discover geofeeds via RDAP, fetch the published geofeed, and return structured lookup metadata with matches
- Add container images for CLI
- Update GitHub actions workflows for packaging/code quality scans
- Centralise all config/settings related values into `config.py`
- Misc small fixups
- Add check to CLI for requirements to ensure they are available

## 2026-05-26 - 0.1.1

- Add GitHub actions example and instructions to validate geofeed using CLI hook command
- Add `geofeed-tools dump --format {json,csv,table}` for JSON, geofeed CSV, and tabulated output modes
- Add native library async support with `AsyncGeoFeed` and async URL loading via the `async` extra
- Add log messages at various levels for debugging. When using the CLI, structlog will pretty print log messages with colours.
- Refactor to fix multiple issues: CLI performing validation twice, stream lines from file without building line number map pre-parse, prevent duplicate list copy for CSV output, remove other redundant work
- Add cache for country/subdivision lookups
- Add cache for queries when called as module (cache is opt out, CLI opts out)

## 2026-05-26 - 0.1.0

Initial release.
