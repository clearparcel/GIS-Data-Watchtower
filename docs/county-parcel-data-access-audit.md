# Minnesota county parcel-data access audit

Last updated: **2026-10-05**

## Purpose

GIS Data Watchtower is auditing the Minnesota counties that are currently shown as `needs-source` / "Direct source not yet identified."

That existing status is **registry-derived**, not a completed research conclusion. It currently means that Watchtower has no county-specific source configured for direct monitoring while a county/catalog record exists. It does **not** mean that a thorough search proved that no parcel dataset is available.

The audit will replace that ambiguous state with evidence-backed parcel-data access classifications.

## Scope: parcel data itself

This review is intentionally limited to access to the **parcel dataset itself**.

A county is **not** classified as fee-based merely because it charges for:

- staff time or custom GIS analysis;
- custom exports or special file preparation;
- printed maps;
- plats, deeds, recorded documents, or other land-record documents;
- subscriptions or services associated with parcel information;
- custom coordinate conversion, mailing lists, or consulting;
- third-party viewer features.

The public label **Fee-based parcel data** is used only when an official county source establishes that obtaining the parcel dataset itself requires payment.

## Evidence priority

For every county, use this order:

1. Official county government website.
2. Official county GIS / mapping / assessor / land-records page.
3. Official county open-data/download portal or ArcGIS Hub/REST service clearly owned or linked by the county.
4. Official county fee schedule, GIS data policy, data request form, resolution, or ordinance.
5. A county-authorized third-party parcel/GIS portal, when linked from the official county site.
6. MnGeo / Minnesota Geospatial Information Office as corroborating statewide context.

Search engines may be used to discover candidate pages, but a search-result snippet is not sufficient evidence for the final classification.

The MnGeo county open-data status layer is useful context, but it does **not** by itself determine whether parcel data specifically is free, fee-based, viewer-only, or restricted.

## Public classifications

The audit should use these parcel-specific classifications:

### Free parcel data

Use when an official source provides a parcel dataset for download or machine-readable access at no charge.

### Fee-based parcel data

Use only when an official county policy, fee schedule, order page, or equivalent evidence states that the parcel dataset itself is sold or supplied for a fee.

### Parcel viewer only

Use when public parcel information can be viewed interactively, but no free parcel dataset download or machine-readable county source is verified.

### Parcel data by request / restricted

Use when the parcel dataset appears obtainable only by request, approval, agreement, restricted access, or other non-public-download process and a specific dataset fee is not established.

### Statewide parcel coverage only

Use when parcel information is available through a statewide source such as MnGeo, but no county-direct parcel dataset access method has been verified.

### No direct parcel dataset verified

Use only after the defined official-source review is complete and no direct county parcel dataset, parcel download, fee-based parcel dataset, or request path can be verified.

This is the appropriate researched replacement for the current ambiguous "Direct source not yet identified" wording.

## Audit population

The current production aggregate places **35 counties** in the registry-derived `needs-source` category:

1. Blue Earth
2. Brown
3. Cottonwood
4. Dodge
5. Faribault
6. Freeborn
7. Goodhue
8. Hubbard
9. Jackson
10. Kanabec
11. Kandiyohi
12. Kittson
13. Lac qui Parle
14. Lake of the Woods
15. Le Sueur
16. Lincoln
17. Mahnomen
18. Marshall
19. Martin
20. Meeker
21. Murray
22. Nicollet
23. Nobles
24. Norman
25. Pennington
26. Pine
27. Red Lake
28. Redwood
29. Rock
30. Roseau
31. Sibley
32. Todd
33. Wadena
34. Watonwan
35. Winona

## Current audit state

The 35-county parcel-data audit is **in progress**.

Already established:

- the current "Direct source not yet identified" label is not backed by a completed source-discovery audit;
- official county websites/contact pages have previously been checked for all 35 counties as part of a separate GIS-contact verification effort, providing useful official-domain starting points;
- MnGeo's statewide county open-data status layer has been queried as supporting context;
- that statewide layer cannot be treated as a parcel-specific access classification;
- the remaining work is a county-by-county review of parcel download, parcel GIS service, parcel-data request, and parcel-data fee evidence.

Do **not** promote preliminary findings to public parcel-access labels until parcel-specific evidence is recorded.

## Recommended audit record

Each county should ultimately have a stored record similar to:

```json
{
  "county": "Example",
  "reviewed": "YYYY-MM-DD",
  "classification": "fee-based-parcel-data",
  "research_complete": true,
  "official_county_url": "https://...",
  "parcel_page_url": "https://...",
  "download_or_service_url": "https://...",
  "fee_policy_url": "https://...",
  "parcel_dataset_fee": "$...",
  "viewer_url": "https://...",
  "evidence_note": "Official county fee schedule states that the parcel GIS dataset is available for ...",
  "source_authority": "county"
}
```

The audit data should remain separate from the monitoring observations so that source-access research can be updated without conflating it with service health.

## UI implication

Until this audit is complete, the public v2 label should avoid implying that exhaustive research has already failed.

Preferred interim wording:

**No direct county parcel source currently monitored**

After audit completion, the label should be replaced with the evidence-backed parcel classification above.
