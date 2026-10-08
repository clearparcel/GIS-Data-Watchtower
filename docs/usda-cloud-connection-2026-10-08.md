# USDA Google Cloud connection — 2026-10-08

Both USDA sources are connected to the existing Google Cloud worker through
private staging registry version **11**. Only `usda-ssurgo-wfs` and
`usda-ssurgo-mn-catalog` changed from `execution_profiles: ["local"]` to
`["cloud"]`. The registry contains **33 cloud / 2 local** sources; Beltrami
and Rice remained local at that step. The subsequent [county migration](county-cloud-migration-2026-10-08.md)
published version 12 with all 35 sources assigned to cloud. Endpoints, query, retries, timeouts, credentials and
all other configuration were preserved. The worker already mounts `latest`.

## Actual worker validation

Cloud Run execution `gis-data-watchtower-staging-5l25h`, us-central1, used the
existing staging image
`sha256:354da814dc0dc24137e4818e57761769ab13320cda9311d6088cb7662803eec1`
and staging service account. Its execution-only command was:

```text
watchtower --config /secrets/data_sources.json check --source usda --no-save --json
```

The source filter selected exactly the two USDA sources from registry version
10, regardless of their then-local assignment. Both complete configured
adapters returned **OK**, no errors, **one attempt each**, at
`2026-10-08T16:27:32.085241+00:00`. The execution succeeded. This verifies
the real Cloud Run image, adapter operations and egress path in addition to
the earlier Cloud Build connectivity probe.

An initial execution `gis-data-watchtower-staging-9bjcn` failed at argument
parsing because PowerShell flattened an unquoted comma-separated argument
list. It made no provider requests. The corrected execution's argument array
was verified before interpreting results.

After the successful adapter validation, version 11 was published and read
back. A comparison against version 10 verified that only the two USDA profile
assignments changed; another comparison before publication checked for
concurrent registry changes. The saved version exactly matched the candidate.

## Authority, publication and rollback

The persistent staging job's normal `cloud-job --json` command is unchanged.
No provider schedule was enabled: Cloud Scheduler still contains only the
existing sanitized publisher. The authoritative local installation and
scheduling were not changed. Cloud development bootstrap remains synthetic
and receives no private registry or credentials.

Validation used `--no-save`: no worker aggregate, history or production
observations were replaced. A read-back confirmed both aggregate USDA
observations still belong to the local worker and retain their October 7
timestamps. The aggregate's existing 31-cloud/4-local observations must not
be confused with the new registry's 33-cloud/2-local assignments. Public
dashboard metrics therefore retain their existing observation provenance.

Version 10 remains available for rollback. For a scoped rollback, copy the
then-current private registry, restore just the two USDA assignments to local,
verify all other values are unchanged, and publish a new version through the
normal approval boundary. Do not blindly restore an older whole registry over
later unrelated changes. No temporary probe job, secret, build, or deployment
was created; temporary private registry exports and diagnostic files were
removed after validation. Standard execution audit records remain.

One successful Cloud Run run establishes a working connection today, not
multi-day reliability or completion of the broader hybrid activation gate.
The [county ambiguity reassessment](cloud-provider-access-reassessment-2026-10-08.md#what-remains-ambiguous-for-rice-and-beltrami)
separately explains Rice and Beltrami.
