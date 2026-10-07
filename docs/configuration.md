# Configuration reference

Last reviewed: **2026-10-05**

Start from `config/example_sources.json`. The public example is deliberately provider-neutral.

## Core top-level keys

| Key | Purpose | Default |
| --- | --- | --- |
| `timeout_seconds` | Overall wall-clock budget for one provider HTTP request, including redirects/fallback | `20` |
| `retries` | Provider-aware source retry count | `1` |
| `retry_delay_seconds` | Delay between retryable source attempts | `1` |
| `state_file` | Current saved state | required by normal checks |
| `history_file` | Bounded JSONL history | required by normal checks |
| `alerts_file` | Structured alert output | optional |
| `alerts_text_file` | Human-readable alert output | optional |
| `history_max_mb` | Rotate history when this approximate size is reached | `10` |
| `run_lock_stale_seconds` | Legacy compatibility key; ignored by process-owned locks. Process termination releases the lock immediately; age never transfers ownership. | `7200` |
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
| `dashboard_execution_profile` | Built-in dashboard refresh profile (`cloud` or `local`); required when sources have profile assignments. `WATCHTOWER_EXECUTION_PROFILE` overrides this value. Invalid values fail startup. | unset |
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

Minnesota GAC completeness is implemented by a shared standards engine. New
sources use `gac_completeness` with `standard` set to `parcel`, `address`, or
`road`. Existing parcel deployments using `mngac_completeness` remain supported
for backward compatibility.

```json
"gac_completeness": {
  "standard": "address",
  "timeout_seconds": 90,
  "batch_size": 12,
  "population_scope": "mandatory",
  "metadata_url": "https://enterprise.gisdata.mn.gov/aghost/rest/services/us_mn_state_mngeo/loc_addresses_open/FeatureServer/1"
}
```

Parcel retains `CO_NAME` / `CO_CODE`. Address defaults to canonicalized
`CO_NAME` grouping, while Road defaults to canonicalized `CO_NAME_L` so
each statewide road segment contributes to one Minnesota county denominator.
Address/Road county-code fields remain schema-checked but are not used for
grouping because code anomalies can split one named county into multiple
provider statistics groups. The grouping fields may be overridden only when a
deployment has an evidence-backed compatible schema.

For Address and Road, `population_scope` defaults to `mandatory`: every
standard field is schema-checked, but routine population statistics are
calculated only for Mandatory fields. `population_scope: "all"` is supported
for deliberate deeper validation but is materially heavier and should not be
enabled at routine production cadence without provider-specific validation.

The source must expose the configured county field, an object-id field, and GAC
field names. Standard fields are split into bounded grouped-statistics requests.
`batch_size` is capped at 20, but **12 is the validated routine default**;
full live scans with 20-field batches produced ArcGIS 503 wait-timeouts.
Address and Road metadata may additionally report NG911 participation, GAC
public-data opt-in, and latest submission time. See
[`gac-standards.md`](gac-standards.md) for the complete methodology and
[`mngac-completeness.md`](mngac-completeness.md) for the parcel-specific
historical methodology.

Adapter-specific keys include `expected_layers` for WMS, `expected_feature_types`/`version` for WFS, `query`/`expected_columns`/`tracked_values` for Soil Data Access, and `expected_content_type` for `http_file`. The `http_file` adapter performs a HEAD-only check and tracks ETag, Last-Modified, Content-Length, and content type without downloading the file body.

## Public PostHog analytics

Browser analytics are **disabled unless** both the Watchtower project token and
the explicit IP-discard confirmation are configured. The intended deployment
uses a dedicated Watchtower PostHog project rather than sharing unrelated
application analytics.

- `WATCHTOWER_POSTHOG_PROJECT_TOKEN` — browser-safe PostHog project token.
- `WATCHTOWER_POSTHOG_HOST` — HTTPS ingestion origin; defaults to
  `https://us.i.posthog.com`.
- `WATCHTOWER_POSTHOG_SCRIPT_URL` — optional explicit HTTPS
  `.../array.js` loader URL for a compatible PostHog deployment.
- `WATCHTOWER_POSTHOG_IP_DISCARD_CONFIRMED=true` — required activation gate;
  set it only after the dedicated PostHog project's **Discard client IP data**
  setting has been enabled and verified.

A token alone does not activate analytics. Watchtower requires both the project
token and the explicit IP-discard confirmation.

When enabled, Watchtower deliberately configures explicit custom events only:
autocapture, automatic pageviews/pageleaves, exception capture, Session Replay
and feature-flag requests are disabled. Browser persistence is memory-only,
person profiles are identified-only, Watchtower never calls `identify()`, and a
pre-send filter removes automatic URL/referrer properties.

Client IP discard is controlled by the PostHog organization/project setting,
not by the JavaScript SDK. Do not activate Watchtower analytics until its
dedicated project has **Discard client IP data** enabled. The public CSP adds
only the configured PostHog script and ingestion origins, and only while the
token is configured.

## Dependency and build reproducibility

`constraints.txt` pins the resolved Python runtime dependency set. Docker builds
use that constraint file and pin the Python base image by OCI digest. CI runs a
pinned dependency vulnerability audit, CodeQL analysis, and a Trivy scan that
fails on fixable High/Critical container findings. The container lane also
generates CycloneDX SBOM and build-provenance JSON files and uploads them with
the built image ID as a workflow artifact.

The lock and base-image digest are deliberate release inputs. Refresh them in a
reviewed dependency-update change rather than allowing an ordinary rebuild to
silently select different Python packages or a different base image.

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
- `WATCHTOWER_REDIRECT_ALLOW_HOSTS` — comma-separated explicit host allowlist for any redirected host that would otherwise be rejected, including private same-host hops.
- `WATCHTOWER_PUBLIC_REQUEST_TIMEOUT_SECONDS` — anonymous public server idle socket timeout and absolute accepted-connection socket deadline; 10 seconds default, bounded to 2–60; malformed values use the default.

Enabled redirects bind urllib/curl connections to captured validated addresses and preserve Host/TLS hostname checks. Effective proxies reject redirected requests before dispatch because the proxy cannot enforce the binding. Initial operator URLs/proxy use remain supported; non-allowlisted redirect destinations must resolve exclusively public. All curl requests ignore local curl configuration (`--disable` first); curlrc options are unsupported, including automatic redirect/TLS overrides. Initial environment proxy behavior remains supported. Provider request deadlines also bound DNS caller waits; native DNS calls may continue in up to eight daemon workers, retaining capacity until completion. Resolver saturation fails closed. An observed final HTTP 429 stops remaining optional checks and retries for that source even when curl reports a failed/truncated/oversized transfer or a timeout with a usable final 429 marker.

Do not use the redirect allowlist to bypass provider access controls or to authorize cloud metadata, loopback, link-local, private, or other privileged endpoints without a deliberate network-boundary review.

## Static county parcel-source inventory

`clearparcel/datawatch/minnesota_county_parcel_access.json` uses schema v3 and
requires exactly the 87 canonical Minnesota county names in
`minnesota_counties.json`. Sparse schema v2 research fixtures remain supported.
Legacy `research_complete` describes county-direct access review only; overall
profile completion additionally requires reviews of all four inventory categories.

Every county preserves its direct-access classification, fee, terms, evidence
and review log, and adds `comments` and `source_inventory`. The inventory keys
are `mngac_public_parcels`, `mngeo_public_repository`, `county_arcgis_rest` and
`county_download`. These categories are independent: REST evidence does not
establish a download product or distinct MnGeo repository membership. Each
category contains `review_status` (`pending`, `reviewed`, `not-found`, `blocked`),
`availability` (`yes`, `no`, `unknown`), `review_date`, `finding`, `evidence` and
`sources`. Evidence references are URL strings present in the county's existing
`evidence` array. A reviewed absence requires a review date, factual finding
and official evidence references. Positive sources can be preserved while the
broader category review remains pending.

Each source contains `inventory_id`, `name`, `authority`, `dataset_type`,
`layer_id` (nullable), `approved_public_links` (`{label, href}` objects),
`review_date`, `monitoring_decision` and `evidence` references. Optional
`geometry_type` and `file_type` retain evidenced stable product facts. Geometry uses
recognized ArcGIS geometry names; file type is a validated MIME scalar for an
explicitly offered file. Both may be omitted or null. File Geodatabase/Shapefile
advertisement alone does not establish a MIME type or archive contents. Safe live
metadata takes precedence, with validated evidence used only when it lacks a value.
Profile interfaces remain unchanged (`geometry_type` and `file.type`). Optional
`monitored_source_id` joins an already monitored aggregate source; discovery
never activates monitoring. Approved links pass the shared offline
`safe_public_url` check, which rejects credentials, private/local hosts and
sensitive query parameters. Static category and source fields are allowlisted:
live counts, health, headers, provider edit/check/success dates, fingerprints and
worker telemetry belong in aggregate state.

Repository acquisition/refresh dates require a safe, exact catalog `data_url`
match to an evidence-backed approved product reference (a dataset/item, selected
REST layer or offered archive), unique among that county's repository products.
When `layer_id` is present, the exact reference must select that same REST layer
or carry the matching dataset layer suffix. Unqualified maps/items, service roots
and archives cannot identify a selected county subdataset. Generic county/Hub/search
links and ambiguous shared references cannot join dates.
Unmatched repository dates remain null; county contribution dates for the observed
statewide source retain their separate county-catalog association. Catalog checks,
health and counts never become repository dataset observations.

Migration retains all 35 existing direct-access findings and four terms holds.
The other 52 counties are seeded using existing official county contact URLs,
with pending reviews and unknown availability. Their legacy statewide coverage
`available` and `verified_date` are nullable in v3 to represent missing research
honestly. Historical statewide findings remain separate from current observed
membership. Public classification is `OPEN` for verified free machine-readable
access, `FEE BASED` for county-direct dataset fees, and `AMBIGUOUS` for incomplete
or viewer-only findings; free statewide access does not override a direct fee.
