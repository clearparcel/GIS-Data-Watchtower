# Hosted county administration staging handoff

The candidate starts from local commit
`7d27cc3a7594b73ee6a5aeaba11b9854972e257e` on
`codex/county-admin-contract`, with current GitHub main at
`9a0e643aeddc85d373c0f15a826eb50885fb7584`. Codex implemented the hosted
write path and scanner. The earlier independent model review covers only
the initial public projection. The user declined a further review.

The editor validates signed IAP assertions against the configured issuer,
audience, lifetime, and allowed subject. The CSRF secret is shared across
replicas and bound to the authenticated subject and origin. The scanner
uses separate Cloud Run invoker IAM and a service identity without access
to county storage. The editor preserves quarantine until the scanner
confirms a verdict from a current signature database.

The published CCE pin was `34bb01ef001eb4950fd72b8806c20098950d2461`. The
`gis-data-watchtower` record retained hash
`ec82d16ee47381f92e65976bbe38a293cb4ad8d16c28506dfec7679c6f8b630a`, with
status `needs-review` and review due October 14, 2026. Repository and live
public export evidence drove the verification.

## Migration receipt

The public dashboard export was created at 2026-11-06 11:08:50 Central.
It matched 87 county identities, 116 contacts, parcel fee and statewide
evidence, and the direct access methods used in the packaged seed. The
verifier reported zero exceptions and zero statewide observation differences.

- Public export SHA-256 `25b45051b4b06e27be0e934fabe397f6665016182450a4c839768deeecbebd5b`.
- Packaged seed SHA-256 `d85ce26441b4ecaee7069ab5f9fcbbb6a7971ef9328cb273a8925c0c3a3824fc`.

## Staging boundary

The Cloud CLI session required reauthentication during the read-only service
inventory. Staging service names, ingress, IAM, bucket bindings, and rollback
remain unverified. This task prepared the branch and ran local checks.
Follow the [staging acceptance checklist](../../county-directory-staging.md)
when the staging target and access are available.
