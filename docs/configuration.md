# Configuration reference

Last reviewed: **2026-10-11**

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

Automatic whole-source retries stop after HTTP 401, 403, 404, or 410, as well as
the separate HTTP 429 stop/backoff signal. Changing transport does not turn these
responses into retryable failures. Transient failures, including timeouts and
HTTP 5xx, retain the configured bounded retry behavior. This does not change the
normal daily schedule or authorize another provider request.

Cloud jobs persist both `history.jsonl` and its one retained rotated file,
`history.jsonl.1`, using independent conditional object writes. The history is
bounded to those two generations. The PowerShell helper installs editable and
GCS dependencies under `constraints.txt`; update that lock deliberately when
refreshing the supported runtime set.

The repository example configuration is available to source and container
users. A wheel installation without that repository tree must pass `--config`
or set `CLEARPARCEL_WATCHTOWER_CONFIG`; the CLI reports this requirement before
it attempts a check.

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

- `id` — unique across the whole registry, compared case-insensitively, including disabled sources and sources assigned to other execution profiles. A missing, blank or duplicate ID fails the run (exit 3) before any provider request, dispatch-slot claim or state write.
- `name`
- `provider`
- `category`
- `kind` (or `adapter`)
- `url`

Optional common controls include:

- `enabled`: set `false` to park a source. A disabled source is never polled,
  is excluded from candidate manifests, and is reported in the run's
  `skipped_sources` with reason `disabled`. Defaults to enabled.
- `timeout_seconds`
- `retries`
- `prefer_curl`
- `execution_profiles`: for example `["cloud"]`, `["local"]`, or `["any"]`.
  A worker polls an assigned source only when it declares a matching profile
  through `--execution-profile` or `WATCHTOWER_EXECUTION_PROFILE` (the
  command-line flag wins). Without a declared profile, only unassigned legacy
  sources and `["any"]` sources run; other assigned sources are skipped with
  reason `execution-profile-unresolved`.
- `thresholds`

The `arcgis_county_catalog` adapter (MnGeo's county catalog) also accepts:

- `item_metadata`: `true` reads the county's own ArcGIS item metadata record
  for each catalog county whose `data_url` links a hub or opendata dataset
  page on an arcgis.com host (generic `?id=` item links are ignored because
  they may name a web app rather than the data layer), from
  `https://www.arcgis.com/sharing/rest/content/items/<id>/info/metadata/metadata.xml`.
  Each item is read once per run. The publication, revision, content and
  metadata dates (FGDC or ArcGIS format) are stored as `item_metadata` on the
  county's catalog record and shown separately from MnGeo's acquisition date.
  Hold-for-terms counties are never read (`held`). A failed read marks the
  county `unavailable` and keeps the last good dates (`retained`, for at most
  30 days and never for a held county) without failing the catalog source. A host under an HTTP 429 backoff is not
  contacted (`deferred`); a new 429 stops the run's metadata reads, persists
  that host's backoff and keeps the catalog observation. XML declaring a DTD
  or entity is refused. The metadata never changes the catalog or observation
  hashes, and only typed dates and the read status reach the public snapshot.
  Off by default.
- `item_metadata_max_items` (default 100, at most 200),
  `item_metadata_budget_seconds` (default 90, at most 300) and
  `item_metadata_timeout_seconds` (default 10, never above the source timeout)
  bound the reads; counties past a bound are marked `skipped`.

## Run-safety environment variables

State, backup, alert, and local aggregate files are replaced atomically and keep
the permissions of the file they replace. A file created for the first time is
owner-only (0600 on POSIX); grant read access explicitly (permissions or ACLs)
if a dashboard or publisher runs as a different user.

| Variable | Effect |
| --- | --- |
| `WATCHTOWER_ALLOW_INVENTORY_SHRINK=1` | Marks the run's fleet report as a deliberate inventory drain so it may retire most or all of the worker's sources. Without it, an empty run is an error and a report covering under half of the worker's sources retires nothing. |
| `WATCHTOWER_ALLOW_EXAMPLE_CONFIG=1` | Lets `cloud-job` run against a configuration whose sources all use reserved example hosts. For synthetic tests only. |
| `WATCHTOWER_RUN_RECEIPTS=1` | After each `cloud-job` run, appends a private execution receipt (exit code, start/end, minimized original worker report) to `runs/receipts.json` in the job's storage. Off by default; never changes the exit code. See [alert routing](alert-routing.md). |
| `WATCHTOWER_MIN_DISPATCH_HOURS` | Minimum hours (1–168) between provider-polling runs of one execution profile. When set, `cloud-job`, `check` and the private dashboard's refresh claim a slot in the private `runs/dispatch-guard-<profile>.json` object (compare-and-swap) before any provider request, and a run that starts sooner than the minimum after the previous run of that profile is refused with exit 4. `--override-min-interval REASON` runs anyway and records the reason in the guard history (the reason is not logged). Off when unset. See [provider-run spacing](#provider-run-spacing). |
| `WATCHTOWER_DISPATCH_TOLERANCE_MINUTES` | Start-delay tolerance for the spacing guard, 0–30 minutes (default 10). It absorbs scheduler jitter and container cold starts so the 05:00 America/Chicago run on the spring daylight-saving change, exactly 23 elapsed hours after the previous run, is not skipped. The effective floor is the minimum less this tolerance. |
| `WATCHTOWER_ALERT_DELIVERY_CONFIG` | Also supplies routing for `watchtower alert-test`. Private JSON (`{"delivery": {...}, "routing": {...}}`, from Secret Manager) for the alert stage that runs after a receipt is recorded. Requires `WATCHTOWER_RUN_RECEIPTS=1`; `delivery.enabled` still defaults to false. |

## Provider rate limits (HTTP 429)

A 429 response is a stop signal for the provider's **host**, not only for the
source that received it. Watchtower:

1. stops retrying that source immediately (no fallback transport) and keeps its
   last good observation alongside the error, so change detection survives the
   backoff;
2. backs off the host that actually returned the 429 (which can be a source's
   `metadata_url` host rather than its main URL) and makes no further requests
   to it for the rest of the run. Every source configured to contact that host
   is recorded with `"deferred": {"reason": "provider-rate-limit"}`, its previous
   observation (including `checked_at`) retained so provider-check freshness
   does not advance without a real check, and status `warn` (or `error` if the
   last real result was an error);
3. persists a per-host `not_before` time in the worker's private `state.json`
   (`rate_limits`) and skips the host on later runs until that time passes.
   The backoff is written to `state.json` as soon as the 429 arrives, before
   any other source runs, so a run that later fails or is interrupted still
   leaves it on disk. That checkpoint keeps the previous observations; this
   run's observations are saved only when the run completes. If the backoff
   cannot be written, the run stops instead of polling further. A cloud job
   whose run fails uploads that checkpoint to its state object with the same
   version precondition as a normal upload. A job killed outright before the
   upload (for example, the container is terminated) can still lose it.

Numeric dispatch options (`timeout_seconds` and `retries` on any source, and
the top-level `timeout_seconds`, `retries`, `retry_delay_seconds`, and
`rate_limit_default_backoff_seconds`) are validated with the registry before
any request, so a malformed later entry can no longer abort a run after an
earlier host has signaled a 429.

`not_before` honors `Retry-After` (delta-seconds or HTTP-date) in full, with a
60-second minimum and a one-year maximum (an effectively indefinite hold); a
requested backoff is never shortened. Backoffs longer than a week are marked
`"operator_review": true` in the private `rate_limits` entry so an operator can
confirm the provider's intent. A request at or beyond the maximum is also
marked `"hold_until_cleared": true` and is never resumed automatically.
Clearing either early is a deliberate, manual change to private state. When the header is absent or unparseable the
top-level `rate_limit_default_backoff_seconds` applies (default `3600`).
During a run, redirects to a host under backoff are refused before any
lookup or request, whichever source would follow them; that source stops at
once, without retries or a fallback transport.
Backoff timing and hostnames are private worker state; they are not included
in worker reports, the shared aggregate, or the public projection. Runs with
`--no-save` do not write state and therefore do not record a backoff; avoid
repeating them against a host that has just returned 429.

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
`text_population_mode` defaults to `nonblank`, using
`COUNT(NULLIF(field,''))` so NULL and empty-string text values are unpopulated.
A faster `non_null` mode exists for provider-specific diagnostics but may count
empty strings as populated and is not the validated routine default.

The source must expose the configured county field, an object-id field, and GAC
field names. Standard fields are split into bounded grouped-statistics requests.
Any response marked `exceededTransferLimit` or any mismatch in county groups
or record counts between field batches fails the configured quality check; it
does not publish statewide percentages from partial results. A failed configured
GAC check marks the source `warn` and retains the last successful GAC observation
with its own `observed_at` time.
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

## Content Security Policy

Both dashboards send a Content-Security-Policy whose `script-src` lists
`'self'` plus the SHA-256 hash of each inline script that Watchtower's
templates wrote (`clearparcel/datawatch/csp.py`). It never includes
`'unsafe-inline'`. Templates open their scripts with `csp.SCRIPT_TAG`, which
carries a marker attribute whose name is random per process. Before a response
is sent, `secure_html()` hashes only the marked scripts and removes the
marker, so a `<script>` that reached the page through data is not hashed and
does not run. The pages use no inline event-handler attributes, so injected
handlers are blocked too. New inline scripts must use `SCRIPT_TAG`, and
`tests/test_csp.py` checks every rendered page. Hashes come from the response
body, so cached pages and 304 revalidation keep working. The policy also sets
`object-src 'none'`, `base-uri 'none'`, `frame-ancestors 'none'` and
`form-action 'self'`. Inline styles still use `'unsafe-inline'`.

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
Dependabot proposes monthly updates for GitHub Actions, Python packages and the
Docker base image; the Dockerfile is the only place the base-image digest is
written (CI reads it from there for the provenance record). Every workflow
action is pinned to a full commit SHA, and a test enforces that.

Container builds with `WATCHTOWER_BUILD_ENVIRONMENT=preview` or `production`
fail unless `WATCHTOWER_BUILD_REVISION` is the full source commit SHA, so a
deployable image always carries its provenance. Development builds may omit it.
The OS `curl` package (the fallback transport) comes from the pinned base
image's Debian release and is not version-pinned separately, because Debian
removes superseded package versions from its archive; Trivy fails CI on fixable
High/Critical findings instead.

CI runs on pushes to `main`, on every pull request (whatever its base branch),
and on manual dispatch. A newer push to a pull request cancels the older run.
CodeQL runs for branches in this repository; pull requests from forks get a
read-only token, so they skip the CodeQL upload but still run tests and the
dependency audit.

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
- `WATCHTOWER_WORKDIR` (optional; when unset, each `cloud-job` run uses its
  own temporary directory, removed when the run ends)
- `WATCHTOWER_EXECUTION_PROFILE`
- `WATCHTOWER_AGGREGATE_OBJECT`

GCS support requires the `gcs` package extra.

Local storage treats object names (for example `WATCHTOWER_AGGREGATE_OBJECT`)
as GCS-style keys under `WATCHTOWER_STORAGE_ROOT`: relative, `/`-separated,
with no absolute, drive, UNC, backslash, `.` or `..` segments. A name that
would resolve outside the root, including through a symlink or junction, is
rejected before any read or write.

Every shared object write is version-conditional (`upload_if_version`); the
storage backends deliberately have no unconditional upload. A GCS read that
races a writer backs off briefly (with jitter) before retrying, up to three
attempts.

## Exit codes

`check`, `status` and `cloud-job` exit with:

| Code | Meaning |
| --- | --- |
| 0 | Every checked source is OK. |
| 1 | At least one warning (an expected non-zero exit for scheduled runs). |
| 2 | A source reported an error, or the run checked no sources (`scope.type=empty`). |
| 3 | Watchtower itself failed: bad configuration, a storage conflict, a refused aggregate merge or an unexpected exception. |
| 4 | The run was refused by the minimum provider-run spacing (`WATCHTOWER_MIN_DISPATCH_HOURS`) before any provider request. No report or run receipt is written. An invalid guard setting or unreadable guard record exits 3. |

Command-line usage errors (an unknown option or an invalid `--worker`) are
rejected by the argument parser with its conventional exit code 2 before any
work starts. A run that would publish to the shared aggregate must use the
`cloud` or `local` execution profile; any other profile (including `any`) is
refused with exit 3 before any provider request.

Keep the Cloud Run Job at `--max-retries=0` so a non-zero exit never repeats
provider requests.

### Provider-run spacing

`WATCHTOWER_MIN_DISPATCH_HOURS` makes the minimum spacing between
provider-polling runs a technical control rather than a procedure. Every
`cloud-job` and `check` run (including `check --source` and `--no-save`) and
every private-dashboard refresh claims the slot before polling, so a
scheduled run, a manual execution and a single-source recheck all count
toward the same spacing. The claim is a version-conditional write: of two runs
started together, only one proceeds. Slots are kept per execution profile
(`cloud`, `local`), because hybrid workers poll different sources while
sharing one storage backend. While the guard is on, a run that declares no
profile or `any` is refused (exit 4), because it can poll sources shared with
every worker. A run with its own separate storage has its own guard.

A refused run exits 4 and logs one `watchtower_dispatch_refused` line; a
`cloud-job` that cannot poll (for example a placeholder configuration) is
refused before it claims a slot. An override (`--override-min-interval "reason"`) is recorded with the run in
`runs/dispatch-guard.json` (the newest 60 runs are kept, with each run's hours
since the previous one) so cadence reviews can see it. A stored previous run
more than two minutes in the future refuses runs (exit 4), and an unreadable
guard record stops them (exit 3), until an operator reviews it.

## Public publisher and public server

The sanitized publisher (`watchtower public-publish`) reads the private
aggregate, projects it through the public allowlist, validates it, and
publishes it to public storage with compare-and-swap protection against
rollback; it never contacts GIS providers.

| Variable | Purpose | Default |
| --- | --- | --- |
| `WATCHTOWER_PUBLIC_SOURCE_BUCKET` | Bucket holding the private aggregate (required) | — |
| `WATCHTOWER_PUBLIC_SOURCE_PREFIX` | Object prefix in the source bucket | empty |
| `WATCHTOWER_PUBLIC_SOURCE_OBJECT` | Private aggregate object name | `aggregate-state.json` |
| `WATCHTOWER_PUBLIC_DEST_BUCKET` | Bucket that receives the sanitized snapshot (required) | — |
| `WATCHTOWER_PUBLIC_DEST_PREFIX` | Object prefix in the destination bucket | empty |
| `WATCHTOWER_PUBLIC_DEST_OBJECT` | Sanitized snapshot object name | `aggregate-state.json` |
| `WATCHTOWER_PUBLIC_PUBLISH_WORKDIR` | Parent of the unique temporary directory each publication uses | `/tmp/watchtower-public-publish` |

The anonymous public server (`watchtower public-dashboard`) reads the sanitized
snapshot through the ordinary storage settings (`WATCHTOWER_STORAGE`,
`WATCHTOWER_AGGREGATE_OBJECT`, GCS bucket/prefix) and also reads:

| Variable | Purpose | Default (bounds) |
| --- | --- | --- |
| `WATCHTOWER_PUBLIC_WORKDIR` | Local cache directory for the downloaded snapshot | `/tmp/watchtower-public` |
| `WATCHTOWER_PUBLIC_REFRESH_SECONDS` | How often the server re-downloads the snapshot | `30` (5–300) |
| `WATCHTOWER_PUBLIC_MAX_PUBLICATION_AGE_SECONDS` | Age after which publication reporting shows "Overdue" and `/healthz` returns 503 | `1800` (60–86400) |
| `WATCHTOWER_PUBLIC_MAX_CONNECTIONS` | Concurrent request handler bound | `64` (1–256) |
| `WATCHTOWER_PUBLIC_REQUEST_TIMEOUT_SECONDS` | See [network hardening](#network-hardening) | `10` (2–60) |

Values are clamped to the bounds shown. A non-integer value for the refresh,
connection, or publication-age setting stops the server at startup; only the
request timeout falls back to its default.

## Network hardening

- `WATCHTOWER_MAX_RESPONSE_BYTES` — response budget; 16 MiB default, hard-capped at 128 MiB.
- `WATCHTOWER_MAX_REDIRECTS` — bounded redirect count. Keep at the default unless redirects are operationally required.
- `WATCHTOWER_REDIRECT_ALLOW_HOSTS` — comma-separated explicit host allowlist for any redirected host that would otherwise be rejected, including private same-host hops.
- `WATCHTOWER_PUBLIC_REQUEST_TIMEOUT_SECONDS` — anonymous public server idle socket timeout and absolute accepted-connection socket deadline; 10 seconds default, bounded to 2–60; malformed values use the default.

Enabled redirects bind urllib/curl connections to captured validated addresses and preserve Host/TLS hostname checks. Effective proxies reject redirected requests before dispatch because the proxy cannot enforce the binding. Initial operator URLs/proxy use remain supported; non-allowlisted redirect destinations must resolve exclusively public. All curl requests ignore local curl configuration (`--disable` first); curlrc options are unsupported, including automatic redirect/TLS overrides. Initial environment proxy behavior remains supported. Provider request deadlines also bound DNS caller waits; native DNS calls may continue in up to eight daemon workers, retaining capacity until completion. Resolver saturation fails closed. An observed final HTTP 429 stops remaining optional checks and retries for that source even when curl reports a failed/truncated/oversized transfer or a timeout with a usable final 429 marker.

Redirects from HTTPS to plain HTTP are always refused, including for
allowlisted hosts. `NaN`, `Infinity` and out-of-range numbers in provider
JSON (and in older state files) are read as missing values (`null`), and state
is always written as standard JSON. Provider field names are used in
ArcGIS `where`/`having` clauses only when they are plain identifiers
(`[A-Za-z_][A-Za-z0-9_]*`). The curl fallback is bounded by the response
budget (`--max-filesize` plus a size check before reading), `--max-time` and
the request's shared deadline; Watchtower adds no extra retry layer on top of
the per-source `retries` setting.

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

## Observation and dashboard contracts

- Each source's `checked_at` (and `provenance.observed_at`) is when that
  source's check began; the run's `generated_at` is when the run began.
- An enabled county-direct parcel source (one with a `county_slug` and a
  `Parcels` category) for a county whose `monitoring.decision` is
  `hold-for-terms` in `minnesota_county_parcel_access.json` is never polled,
  on any host; the run reports it under `skipped_sources` as `hold-for-terms`.
  The MnGeo catalog still skips ArcGIS Online item metadata for those held
  counties only. The same record may include outreach fields `contacted_date`,
  `reply`, `scope` (`none`, `details-and-count`, or `full`), and
  `stop_requested`. With no affirmative permission, a `not-assessed` parcel
  source is skipped as `awaiting-permission` only when its URL is a server the
  county operates. That gate does not cover MnGeo (`gisdata.mn.gov`), the
  Geospatial Commons, or ArcGIS Online item metadata. `stop_requested` skips
  the county's own server and a direct query of the county's ArcGIS Online
  hosted feature or map service (`services.arcgis.com` or `servicesN.arcgis.com`).
  `details-and-count` keeps service metadata and a record count on those same
  hosts and turns off parcel-quality, geometry-sample, GAC completeness, and
  owner, address, and duplicate-ID queries. A permitted scope does not override
  `hold-for-terms`. The data file is read on every run. Public pages say when
  a county-server check is paused or awaiting permission; that state is not
  shown as a failed check.
- A run whose source filter matches nothing is an empty run (exit 2), and the
  shared aggregate refuses any report with no source observations except an
  explicit fleet drain. A fleet report whose inventory shrink is refused
  keeps the worker's fleet-level health from its last complete report and
  cannot take sources over from another worker.
- `last_available_at` is the source's own check time.
- Aggregate source records carry `last_success_at` (last check with status
  `ok`) and `last_available_at` (last check where the provider answered,
  status `ok` or `warn`; rate-limit deferrals do not count).
- A GAC quality observation reports `observation_status` `none` when the
  schema was checked but no field population was scanned.
- The public state lists only the `cloud` and `local` workers; other worker
  names are dropped, since they may be host names. `aggregate --worker`
  accepts only those two.
- The public server answers `HEAD` with the same status and headers as `GET`.

Catalog retention timestamps/flags, public GAC observation time, compact read-only summary and revision-bound county routes, and private worker identity/receipt semantics are documented in [October 7 remediation](archive/watchtower-remediation-2026-10-07.md). These additions do not change provider cadence or execution-profile assignments.
