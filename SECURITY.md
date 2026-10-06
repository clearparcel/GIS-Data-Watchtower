# Security Policy

## Supported versions

Until the first stable release, security fixes are applied to the current `main` branch.

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability. Use GitHub's **Report a vulnerability** / private vulnerability reporting flow for this repository, or use the ClearParcel contact channel published on the project website if GitHub reporting is unavailable.

Include the affected version/commit, reproduction details, impact, and any suggested mitigation. Do not include secrets or sensitive provider data in reports.

## Deployment guidance

The dashboard is private by default. Do not expose it through a wildcard or Internet-facing bind without authentication and appropriate TLS/reverse-proxy controls. Keep credentials in environment variables or a secrets manager, never in configuration committed to Git.

Provider responses are bounded by `WATCHTOWER_MAX_RESPONSE_BYTES` (16 MiB by default, hard-capped at 128 MiB). Redirect following is disabled by default. A deployment may opt in with WATCHTOWER_MAX_REDIRECTS; any enabled redirects are bounded and every HTTP(S) hop is validated. Every redirected destination, including same-host hops, must resolve only to globally routable addresses unless its hostname is explicitly listed in `WATCHTOWER_REDIRECT_ALLOW_HOSTS`. urllib and curl connect to the captured validated addresses while preserving the original Host header and TLS hostname/certificate checks. Redirects fail closed when an effective proxy cannot enforce this binding. Initial operator-selected URLs and proxy use remain supported; private redirected hosts require the explicit allowlist. All curl requests ignore curl configuration files (`--disable` first) to prevent hidden redirect, TLS, authentication, and transport overrides; curlrc options are unsupported. Initial environment proxy behavior remains supported. Do not add private, loopback, link-local, metadata, or otherwise privileged destinations to that allowlist unless the deployment intentionally monitors them and the network trust boundary has been reviewed.

Provider requests have an overall wall-clock deadline across DNS waits, connection/TLS, headers, response bodies, redirects, and fallback. An observed final HTTP 429 propagates through optional quality checks and fallback and stops the source's remaining requests/retries, even if curl also reports a failed/truncated/oversized transfer or a timeout with a usable final 429 marker. Native DNS calls cannot be interrupted: callers stop waiting at the deadline, with at most eight outstanding resolver threads retaining their capacity slots until completion; saturation fails closed.

Cloud-backed state, history, alert, and aggregate read/modify/write operations use storage-version preconditions so a stale worker fails closed rather than overwriting a newer object. The built-in private dashboard also bounds request bodies, socket time, and concurrent handlers. The anonymous public server also bounds accepted connections with both an idle socket timeout and an absolute socket deadline (`WATCHTOWER_PUBLIC_REQUEST_TIMEOUT_SECONDS`, default 10 seconds, bounded 2–60). Its deadline interrupts blocking socket I/O even when a client drips headers; it does not cancel application computation. Deployment proxies should retain their own connection, request-size, and timeout limits as defense in depth.

Public dashboard publication uses a deliberately reduced schema. Both static publication and the hosted read-only renderer exclude detailed change payloads, fingerprints, tracked values, operational provider URLs, provenance details, worker telemetry, and other private diagnostic fields. The hosted public renderer should receive read-only access only to the sanitized public destination object. Only the separate publisher should receive the private source-aggregate read access and sanitized destination write access needed for publication. Neither the public renderer nor the publisher should receive the private provider registry or provider credentials.
