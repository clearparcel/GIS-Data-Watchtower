# GIS Data Watchtower v0.3.4 (provider job only)

**Status: release candidate.** The owner approved merging the certifi fix
(#119) and the v0.3.3 release record (#118), then rebuilding and redeploying
the daily provider job as v0.3.4. This record is completed with build and
deployment evidence after rollout.

## Scope

v0.3.4 is a security maintenance release for the provider job. Its only
change from [v0.3.3](release-v0.3.3.md) is certifi 2026.10.19
([#119](https://github.com/clearparcel/GIS-Data-Watchtower/pull/119)), which
removes the emSign roots affected by
[GHSA-6q48-6c7w-9gw2](https://osv.dev/vulnerability/GHSA-6q48-6c7w-9gw2).
Watchtower's provider polling uses the container's system CA store; certifi is
used by the Google client libraries for storage traffic.

The public and private dashboards (v0.3.2) and the public publisher job
(v0.3.0) also carry the old certifi pin. Rebuilding them is a separate
coordinated release and is not part of this rollout.

## Planned rollout

1. Merge this version bump after CI.
2. Run `python scripts/check_release_version.py` (live v0.3.2 to v0.3.4).
3. Build only the `watchtower` image from a committed-only archive of merged
   `main`, as for v0.3.3, adding an in-image check that certifi is 2026.10.19.
4. Update only the provider job image. Keep the v0.3.3 receipt and delivery
   environment variables (delivery stays disabled) and every other setting.
5. Do not execute the job; the next ordinary scheduled run validates.

## Rollback

Restore the provider job image to the v0.3.3 digest
`watchtower@sha256:18c77b2337ff0aa8ade8b2f1305fe795a7ead5974dcccc26e276fae447b80e80`
(same environment), or to v0.3.0 as described in the v0.3.3 record.
