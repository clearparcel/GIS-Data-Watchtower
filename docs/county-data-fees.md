# County data fees

Watchtower posts the fees Minnesota counties charge for their own parcel,
address point and road centerline GIS data. Fee research is kept in
[`clearparcel/datawatch/minnesota_county_data_fees.json`](../clearparcel/datawatch/minnesota_county_data_fees.json)
and validated by [`data_fees.py`](../clearparcel/datawatch/data_fees.py). It
is separate from parcel-access classification and from monitoring: a recorded
fee never activates, holds or changes a monitoring path.

## Where fees appear

- **County profile** (`/county?slug=…` and the county panel): a *Data fees*
  table with one row per layer.
- **Minnesota Counties** (`/counties`): a statewide *County data fees* card that
  lists every recorded fee and counts counties with a fee, a confirmed no-fee
  layer, or no information yet.
- **Exports**: `/county-data-fees.csv` (one row per county and layer, 261 rows),
  a *Data Fees* sheet in `/snapshot.xlsx`, and `data_fees` in each county's
  `parcel_source_profile` in the JSON snapshots.

## Record shape

Each county record lists only the layers with information. Each layer entry has:

| Field | Meaning |
| --- | --- |
| `fee_status` | `fee` (the county publishes or confirmed a fee for some form of this data), `no-fee` (the county confirmed there is no fee), or `unconfirmed` (only in a county response that answered the access question without stating fees; no amount allowed). |
| `rest_download` | Whether downloading through the county's REST service or another direct route is charged: `fee`, `no-fee`, `unconfirmed`, or `not-offered` (the county says the route is not public; data only by request). `not-offered` requires a county response. |
| `amount`, `product` | The fee text as the county states it, and what it buys. Required for `fee`. |
| `source_kind` | `published-fee-schedule` (requires the official `source_url`) or `county-response` (a reply to ClearParcel's inquiry). |
| `source_url`, `source_date` | Official citation and the date it was read or the reply was received. |
| `note` | Public explanation of scope. |

Rules the validator enforces:

- **Missing is not free.** A county or layer with no entry is shown as
  *Not yet confirmed*. It is never counted as $0 or "no fee".
- **A published schedule does not answer the REST question.** Fee schedules
  price files, bundles and staff requests. Seeded records keep
  `rest_download: unconfirmed` until the county says otherwise.
- `no-fee` requires `rest_download: no-fee`; `rest_download: fee` requires
  `fee_status: fee`.
- County correspondence is private. A `county-response` entry cites the reply
  date only; never add names, email addresses or message text (text fields
  containing `@` are rejected).
- Free statewide routes such as MnGeo Plan Parcels Open are reported in the
  access sections, not as a county fee.

## Current data

The October 23, 2026 seed copies the 13 parcel fees already verified in the
parcel-access research (review date 2026-10-06): Blue Earth, Brown,
Faribault, Goodhue, Jackson, Kandiyohi, Le Sueur, Lincoln, Nicollet, Nobles,
Redwood, Swift and Winona. Blue Earth's Basic Bundle also covers road
centerlines at the same bundle price. A regression test requires every
research `parcel_dataset_fee` to have a matching fee record with the same
amount and policy URL.

County responses so far:

- **Aitkin (2026-10-23):** the county GIS coordinator said the county does
  not charge for GIS data. Recorded as no fee, including REST download, for
  all three layers; the reply was one statement, not layer by layer.
- **Becker (2026-10-23):** the county confirmed all data on its GIS data
  download page is free with no license terms. Recorded as no fee for all
  three layers; the route is a file download page, not a REST service.
- **Brown (2026-10-23):** the county GIS office said its parcel REST service
  is no longer public or authoritative; data comes only by signed data
  request and disclosure form. The county confirmed its 2025-effective fee
  schedule figures: complete parcel dataset $697, partial parcels $0.04 each
  ($20 minimum) plus the service fee, street centerlines $500, rural address
  points $300 (cities not included) and professional service $75/hour. It
  expects fee changes in the new year. The parcel-access research record and
  the private source registry still describe the earlier REST service and
  need a separate owner-approved update.
- **Carver (2026-10-23):** the county IT office said there are no fees for
  parcel, address point or road centerline REST services, and no license or
  attribution terms apply. Recorded as no fee, including REST download, for
  all three layers.

- **Chippewa (2026-10-29):** the county said its REST services are not
  currently available to the public and it is deciding how to handle data
  requests. No fees were stated, so all three layers stay *Not yet
  confirmed* with REST marked not offered. Earlier research showing free
  public parcel data does not apply to the REST service.

The County Terms Outreach emails ask every county whether using its REST
services or downloading parcel, address point and road centerline data
carries a fee. Record each answer as a `county-response` entry, dated, and
update `rest_download` for the layers the county addressed.
