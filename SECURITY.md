# Security Policy

## Supported versions

Until the first stable release, security fixes are applied to the current `main` branch.

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability. Report security concerns privately to the repository owner through GitHub's private vulnerability reporting feature when enabled, or through the ClearParcel contact channel published on the project website.

Include the affected version/commit, reproduction details, impact, and any suggested mitigation. Do not include secrets or sensitive provider data in reports.

## Deployment guidance

The dashboard is private by default. Do not expose it through a wildcard or Internet-facing bind without authentication and appropriate TLS/reverse-proxy controls. Keep credentials in environment variables or a secrets manager, never in configuration committed to Git.

Provider responses are bounded by `WATCHTOWER_MAX_RESPONSE_BYTES` (16 MiB by default, hard-capped at 128 MiB). Redirect following is disabled by default. A deployment may opt in with WATCHTOWER_MAX_REDIRECTS; any enabled redirects are bounded and every HTTP(S) hop is validated. Cross-host redirect destinations must resolve only to globally routable addresses unless their hostname is explicitly listed in `WATCHTOWER_REDIRECT_ALLOW_HOSTS`. Do not add private, loopback, link-local, metadata, or otherwise privileged destinations to that allowlist unless the deployment intentionally monitors them and the network trust boundary has been reviewed.

Cloud-backed state, history, alert, and aggregate read/modify/write operations use storage-version preconditions so a stale worker fails closed rather than overwriting a newer object. The built-in private dashboard also bounds request bodies, socket time, and concurrent handlers. Deployment proxies should retain their own connection, request-size, and timeout limits as defense in depth.

Static dashboard publication uses a deliberately reduced public schema. Detailed change payloads, fingerprints, tracked values, provider URLs, and other private diagnostic fields are not copied into public `state.json`.
