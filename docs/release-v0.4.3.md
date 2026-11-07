# GIS Data Watchtower v0.4.3 — prepared

The owner requested deployment of the internal UI improvements in PR #222,
built on the shared presentation changes in PR #221. This candidate adds a new
application version and explicitly refreshes the Debian zlib runtime package;
the vulnerability scan remains enforced.

The intended rollout updates the read-only internal dashboard only. Its
authentication, non-image runtime settings, provider jobs and schedules are
preserved. The public website remains on its existing v0.4.2 release.

CI, exact build identity, rollback capture and authenticated live checks are
required before this record can state that the release is deployed. Private
operational evidence belongs in the private deployment receipt.
