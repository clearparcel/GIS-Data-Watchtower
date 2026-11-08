# GIS Data Watchtower v0.5.0

Release candidate; production promotion is pending.

This release includes the county editor improvements and source enrollment from
merged PRs #225–#227. Explicitly reviewed direct services and data files can join
regular cloud or local checks and publish their results through the existing
public snapshot. Service checks read details and one count; file checks read
update headers. County terms holds, stop decisions and provider backoff remain
in force, and permission evidence stays private.

The editor adds section navigation, clear save/retry feedback, change review,
field validation and protection against losing unsaved edits. Internal dashboard
fixes preserve refresh preferences and show the correct count observation date.

The feature source passed 1,057 local tests with Node required and the complete
Windows/Linux CI matrix. Independent review of the final feature revision found
no remaining concrete issues in the reviewed boundaries. The release candidate
must also pass its CI matrix, visible-version preflight, installed-image synthetic
acceptance and the scoped storage access checks before promotion.

The [source monitoring guide](county-source-monitoring.md) describes the private
registry input and exact-object worker permission required for activation.
Application rollout retains the existing provider schedule. Deployment evidence
and rollback configuration stay in the private release record.
