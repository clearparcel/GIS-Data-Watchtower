# Configuration reference

Last reviewed: **2026-10-05**

Start from `config/example_sources.json`. The public example is deliberately provider-neutral.

## Core top-level keys

| Key | Purpose | Default |
| --- | --- | --- |
| `timeout_seconds` | Default timeout for one provider request/check | `20` |
| `retries` | Provider-aware source retry count | `1` |
| `retry_delay_seconds` | Delay between retryable source attempts | `1` |
| `state_file` | Current saved state | required by normal checks |
| `history_file` | Bounded JSONL history | required by normal checks |
| `alerts_file` | Structured alert output | optional |
| `alerts_text_file` | Human-readable alert output | optional |
| `history_max_mb` | Rotate history when this approximate size is reached | `10` |
| `run_lock_stale_seconds` | Age at which an abandoned local run lock may be recovered | `7200` |
| `sources` | Source definitions | `[]` |

The supported history size key is `history_max_mb`. Older experimental keys such as `history_max_lines` and `history_max_bytes` are not supported.

## Dashboard and aggregate keys

| Key | Purpose | Default |
| --- | --- | --- |
| `aggregate_state_file` | Prefer a unified hybrid aggregate for dashboard/status reads | unset |
| `aggregate_object` | Shared object name to publish profiled worker results | unset |
| `worker_stale_minutes` | Worker freshness threshold | `1560` |
| `source_stale_minutes` | Source freshness threshold | `1560` |
| `dashboard_refresh_cooldown_seconds` | Minimum interval between built-in manual refresh actions | `300` |
| `dashboard_request_timeout_seconds` | Built-in dashboard socket timeout | `10` |
| `dashboard_max_connections` | Built-in dashboard concurrent handler bound | `32` |
| `public_dashboard.internet_exposure` | Marks a deployment as Internet-exposed; authentication is then required | `false` |

The dashboard API always serves a **sanitized state representation**. There is no `raw_state_api` switch.

## Common source keys

Every source normally defines:

- `id`
- `name`
- `provider`
- `category`
- `kind` (or `adapter`)
- `url`

Optional common controls include:

- `timeout_seconds`
- `retries`
- `prefer_curl`
- `execution_profiles`: for example `["cloud"]`, `["local"]`, or `["any"]`
- `thresholds`

ArcGIS layer checks may use `count`, `expected_geometry`, `expected_wkid`, `required_fields`, `parcel_quality`, `geometry_sample`, and `geometry_sample_size`.

For a layer that follows the Minnesota GAC parcel-transfer schema, `mngac_completeness` enables grouped field-population statistics. It may be `true` for defaults or an object such as:

```json
"mngac_completeness": {
  "timeout_seconds": 90,
  "batch_size": 12
}
```

The source must expose `CO_NAME`, `CO_CODE`, an object-id field, and GAC field names. Watchtower batches the standard fields into bounded grouped-statistics requests; the current 91-field MnGeo layer uses eight requests at the default batch size. See [`mngac-completeness.md`](mngac-completeness.md) for methodology and interpretation.

Adapter-specific keys include `expected_layers` for WMS, `expected_feature_types`/`version` for WFS, and `query`/`expected_columns`/`tracked_values` for Soil Data Access.

## Path environment overrides

- `CLEARPARCEL_WATCHTOWER_ROOT`
- `CLEARPARCEL_WATCHTOWER_STATE_FILE`
- `CLEARPARCEL_WATCHTOWER_HISTORY_FILE`
- `CLEARPARCEL_WATCHTOWER_ALERTS_FILE`
- `CLEARPARCEL_WATCHTOWER_ALERTS_TEXT_FILE`
- `CLEARPARCEL_WATCHTOWER_AGGREGATE_STATE_FILE`
- `CLEARPARCEL_WATCHTOWER_CONFIG`

Relative configured paths are resolved from the Watchtower root.

## Dashboard authentication

- `CLEARPARCEL_WATCHTOWER_DASHBOARD_USER`
- `CLEARPARCEL_WATCHTOWER_DASHBOARD_PASSWORD`

A wildcard/public bind fails closed without a password. For Internet exposure, place the service behind TLS and a trusted authentication/reverse-proxy layer.

## Storage and hybrid execution

- `WATCHTOWER_STORAGE=local|gcs`
- `WATCHTOWER_STORAGE_ROOT`
- `WATCHTOWER_GCS_BUCKET`
- `WATCHTOWER_GCS_PREFIX`
- `WATCHTOWER_WORKDIR`
- `WATCHTOWER_EXECUTION_PROFILE`
- `WATCHTOWER_AGGREGATE_OBJECT`

GCS support requires the `gcs` package extra.

## Network hardening

- `WATCHTOWER_MAX_RESPONSE_BYTES` — response budget; 16 MiB default, hard-capped at 128 MiB.
- `WATCHTOWER_MAX_REDIRECTS` — bounded redirect count. Keep at the default unless redirects are operationally required.
- `WATCHTOWER_REDIRECT_ALLOW_HOSTS` — comma-separated explicit host allowlist for cross-host redirects that would otherwise be rejected.

Do not use the redirect allowlist to bypass provider access controls or to authorize cloud metadata, loopback, link-local, private, or other privileged endpoints without a deliberate network-boundary review.
