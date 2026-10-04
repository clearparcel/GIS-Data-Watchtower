# GIS Data Watchtower

Private standalone extraction of ClearParcel GIS Data Watchtower.

GIS Data Watchtower monitors published GIS services for availability, update signals, schema and record-count changes, bounded parcel QA, and provider-friendly operational health.

## Status

This repository is **private and pre-public-release**. GERTKEN-PC remains the authoritative processor while the standalone repository is independently validated. Do not redistribute raw provider parcel records.

## Quick start

```bash
python -m venv .venv
# activate the environment
pip install -e .
watchtower --config config/data_sources.json status --json
watchtower --config config/data_sources.json check --no-save
```

## Dashboard

```bash
watchtower --config config/data_sources.json dashboard --host 127.0.0.1 --port 8765
```

Wildcard/public binds require authentication. The current private-LAN deployment uses a specific private address rather than a wildcard bind.

## Provider use and public release

Read `docs/data-watchtower-provider-compliance.md` before changing polling behavior. See `docs/data-watchtower-standalone-readiness.md` for the public-release gate.

This repository is not approved for public release yet.
