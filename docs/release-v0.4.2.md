# GIS Data Watchtower v0.4.2

Public dashboard rollout: November 6, 2026 (Central time).
Source: `20ceac8a79eadd8e9dc7c5a046eac974b060778e`.

[PR #219](https://github.com/clearparcel/GIS-Data-Watchtower/pull/219) replaces
lengthy county profile PDFs with three pages: contacts and access; policy,
restrictions and monitoring; and MN GAC summaries. Each page uses the GIS Data
Watchtower logo and name. The report links to the full online profile for
additional contacts, text, and field details. JSON, CSV and Excel retain the
detailed public data.

The version preflight passed from v0.4.1. Local tests passed (1,013 tests,
three platform skips, Node 24 required), and required PR and [merged-source
CI](https://github.com/clearparcel/GIS-Data-Watchtower/actions/runs/42342548640)
passed. The installed image passed its identity and three-page PDF checks.
All 87 county summary snapshots rendered to three pages; Aitkin's full
snapshot was inspected with all three MN GAC datasets. Live Aitkin, Fillmore,
and Hennepin PDFs verified the page count and header. Aitkin's live statistics
and links were checked, along with its profile, list, popup, and other exports.

The public dashboard alone was updated. County directory and monitoring
content, service settings and IAM matched their predeployment baselines.
The previous revision remains available for rollback. Private operational
identities and artifact checks are in the deployment receipt.
