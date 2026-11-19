# GIS Data Watchtower v0.6.0

Release candidate for the sixth-review fixes merged in [PR #285](https://github.com/clearparcel/GIS-Data-Watchtower/pull/285).

- The public dashboard can show healthy updates while withholding observations with unreliable clocks. A worker's first failure after a clock correction is visible. A rebuilt worker preserves the original measurement and its reporting history.
- A source whose retirement time is unknown can return only after a genuine provider check newer than the last accepted aggregate showing it retired. Unrelated sources continue to publish during recovery.
- Public records pass the field allowlist after recovery. Unrecognized worker assignments and blank check times no longer make sources appear current.
- ArcGIS service discovery retains the chosen layer's GAC evidence. Statistics batches reconcile excluded groups, malformed county participation rows preserve the last good evidence, and parcel completeness settings agree with preflight.
- Extent comparisons use the coordinate system of the bounds. Catalog dates and timestamps use consistent UTC precision, and implausible future history cannot extend a source's expected update interval.
