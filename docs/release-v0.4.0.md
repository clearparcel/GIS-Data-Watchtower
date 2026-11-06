# ClearParcel GIS Data Watchtower v0.4.0

The public dashboard and the protected county editor went live on November 6,
2026. The county editor has a separate private attachment scanner. Production
source is `f2af1474b07394a6b72b1cc13ae26b1816163470`. The
[merged source checks](https://github.com/clearparcel/GIS-Data-Watchtower/actions/runs/42291064936)
and production image checks passed.

- The public dashboard verified 87 county identities and 116 contacts. It
  continued to report 24 monitored sources with cloud worker provenance.
  A live Fillmore profile and its JSON, CSV, XLSX, and PDF exports loaded
  successfully.
- The approved pilot signed in and opened a county record. The first
  production county edit and attachment check remain pending.
- Staging verified publication and recovery, public export privacy,
  scanner outage and recovery, and attachment quarantine and rejection.
  The final v0.4.0 artifact also passed staging publication, stale-save
  rejection, and clean and encrypted PDF checks.

The existing read-only private dashboard, provider jobs, and schedules were
outside this release. Production rollback details are in the private
deployment record.
