# Minnesota GAC parcel, address, and road monitoring

Last reviewed: **2026-10-07**

GIS Data Watchtower supports a shared Minnesota Geospatial Advisory Council (GAC)
standards engine for statewide parcel, address-point, and road-centerline field
population monitoring.

Field population is **descriptive data-quality information, not a standards
compliance grade**. Conditional, If Available, and Optional fields may
legitimately be blank.

## Supported standards

| Key | Standard | Version | Fields | Mandatory fields |
| --- | --- | ---: | ---: | ---: |
| `parcel` | MN GAC Parcel Data Standard | 1.1.3 | 91 | derived from packaged standard |
| `address` | MN GAC Address Point Data Standard | 1.3.2 | 53 | 18 |
| `road` | MN GAC Road Centerline Data Standard | 1.1.1 | 73 | 34 |

The packaged Address and Road field inventories are transcribed from the
official GAC schema workbooks. They include field names, element labels, data
types, widths, inclusion categories, domains, and element groups.

## Official statewide services

The validated public targets are:

- Address points:
  `https://enterprise.gisdata.mn.gov/aghost/rest/services/us_mn_state_mngeo/loc_addresses_open/FeatureServer/0`
- Address metadata:
  `https://enterprise.gisdata.mn.gov/aghost/rest/services/us_mn_state_mngeo/loc_addresses_open/FeatureServer/1`
- Road centerlines:
  `https://enterprise.gisdata.mn.gov/aghost/rest/services/us_mn_state_mngeo/trans_road_centerlines_open/FeatureServer/0`
- Road metadata:
  `https://enterprise.gisdata.mn.gov/aghost/rest/services/us_mn_state_mngeo/trans_road_centerlines_open/FeatureServer/1`

The data layers support server-side statistics. Watchtower therefore calculates
completeness with bounded grouped-statistics requests rather than downloading
all features.

## County grouping

Address points group by `CO_NAME`, normalized to the canonical 87 Minnesota
county names. The county-code field remains schema-checked but is not part of
the denominator grouping because code anomalies can split one named county
into multiple ArcGIS statistics groups.

Road centerlines contain left- and right-side county attribution. Watchtower
groups by `CO_NAME_L`, normalized to the canonical Minnesota county names.
This assigns each road segment to one county exactly once and avoids double
counting statewide records. Out-of-jurisdiction names are excluded from the
Minnesota county denominator and reported separately. Boundary-road side
attribution is a deterministic reporting convention, not a claim that the road
belongs exclusively to the left-side county.

## Separate participation and availability facts

For Address and Road, Watchtower also reads the corresponding public metadata
layer and keeps these facts separate:

- `ng911_upload`: whether MnGeo metadata indicates NG911 participation/upload;
- `gac_open`: whether the county is opted into GAC public viewing;
- `submitted_at`: latest Address or Road submission timestamp for the standard;
- public feature representation: whether records are actually present in the
  public statewide layer.

A county can therefore be an NG911 participant without appearing in the public
GAC layer. Watchtower reports that state as **NG911 participant / not opted into
public GAC data**, not as 0% completeness.

## Configuration

New sources use `gac_completeness`:

```json
{
  "id": "mn-address-points-open",
  "kind": "arcgis_layer",
  "url": "https://enterprise.gisdata.mn.gov/aghost/rest/services/us_mn_state_mngeo/loc_addresses_open/FeatureServer/0",
  "count": true,
  "gac_completeness": {
    "standard": "address",
    "timeout_seconds": 90,
    "batch_size": 12,
    "metadata_url": "https://enterprise.gisdata.mn.gov/aghost/rest/services/us_mn_state_mngeo/loc_addresses_open/FeatureServer/1"
  }
}
```

Road sources use the same configuration with `"standard": "road"` and the
Road service URLs.

Existing parcel deployments using `mngac_completeness` remain supported.
New parcel configuration may use `gac_completeness` with
`"standard": "parcel"`.

The batch size is bounded to 20. Provider HTTP 429 handling, wall-clock request
deadlines, redirect protection, and normal source cadence continue to apply.

## Validated 2026-10-07 observations

A bounded live validation against the official MnGeo public services passed
with the provider-safe routine configuration. Address and Road population
checks default to the standard's **Mandatory fields only** while all standard
fields remain schema-checked. Text population uses ArcGIS
`COUNT(NULLIF(field, ''))`; numeric/date population uses native
`COUNT(field)`. This preserves empty-string-as-missing semantics without the
much heavier per-row `SUM(CASE...)` expressions used by the parcel-specific
path.

| Metric | Address Points | Road Centerlines |
| --- | ---: | ---: |
| Source features | 2,116,804 | 439,374 |
| Minnesota county-grouped records | 2,116,804 | 437,805 |
| Ungrouped/excluded records | 0 | 1,569 |
| Standard fields present | 53/53 | 73/73 |
| Routine population-scanned fields | 18 Mandatory | 34 Mandatory |
| Minnesota counties represented | 56 | 71 |
| All-field population | Not scanned by default | Not scanned by default |
| Mandatory-field population | 97.21% | 95.94% |
| Grouped statistics requests | 2 | 3 |
| Metadata county records | 87 | 87 |
| NG911 upload participants | 85 | 85 |
| GAC public opt-in flags | 56 | 55 |
| Latest reported standard submission | 2026-05-20 | 2026-05-20 |

The Road layer also returned two non-Minnesota grouping labels,
`Howard` and `Out of Jurisdiction`; Watchtower excludes those labels from
Minnesota county completeness and retains their presence as an explicit
diagnostic. The difference between 439,374 source features and 437,805
Minnesota-grouped records remains visible as `ungrouped_record_count`.

Metadata public-opt-in counts and actual represented counties are separate
facts. The Road public layer currently contains Minnesota-grouped records for
more counties than have `gac_open=true` in the metadata response. Watchtower
does not reinterpret either source; it reports both so the discrepancy remains
auditable.

A batch size of **12** is the validated routine setting. A 20-field batch can
complete in isolation, but full Address/Road scans at that size produced ArcGIS
503 wait-timeout responses during validation. Watchtower therefore keeps 12 as
the normal default and does not increase provider request timeouts to force a
larger batch.

## Stored observation

Each generic GAC completeness observation includes:

- standard identity/version;
- grouping convention;
- represented county count;
- record count;
- standard and Mandatory field counts;
- missing source-schema fields;
- bounded statistics-query count;
- the population-scan scope and scanned-field count;
- record-weighted all-field population when an all-field scan was explicitly run;
- record-weighted Mandatory-field population;
- per-field statewide population and median county population for scanned fields;
- per-county population for scanned fields;
- optional county metadata with NG911/public-opt-in/submission facts.

The public projection allowlists only the typed summary fields. Provider URLs,
raw diagnostics, statistics query internals, arbitrary nested metadata, and
private provenance remain excluded.

## Dashboard and exports

`/mngac` remains the standards surface and supports:

- `/mngac?standard=parcel`
- `/mngac?standard=address`
- `/mngac?standard=road`

The Parcel view remains backward compatible. Address and Road use the same
interactive county map, percentage classes, field filtering, JSON export and
CSV field summary. Routine Address/Road pages offer Mandatory summary/fields
for map selection while still listing every standard field for schema coverage.
Unscanned Conditional/Optional fields are labeled as schema-only rather than
being assigned a false population value. County dashboards include
Address/Road summary cards when the corresponding observations exist.

Statewide Excel retains the legacy parcel `MNGAC` sheets and also adds normalized
`GAC Standards`, `GAC Counties`, `GAC Fields`, and `GAC Detail` sheets with a
`standard` column spanning parcel, address, and road. County JSON carries a
generic `gac` block, county CSV includes Address/Road record, Mandatory-field,
NG911, public-opt-in, and submission summaries, and county Excel includes the
same normalized GAC sheets for available standards.

## Source retirement and freshness

Hybrid full-fleet reports now write explicit source-retirement tombstones.
Public publication will not accept disappearance of a previously published
source unless a newer retirement record authorizes that omission. A newer
observation may subsequently reactivate the source.

Worker reporting clocks are also distinct:

- `last_report_at`: latest completed worker report;
- `last_success_at`: latest all-clear worker run.

A warning/error worker report advances the report clock but no longer falsely
advances the Last success clock.
