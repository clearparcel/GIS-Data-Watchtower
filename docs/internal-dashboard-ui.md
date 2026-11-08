# Internal dashboard UI

Deployed to the internal dashboard with v0.4.3 on November 7, 2026. This builds
on the shared presentation changes in PR #221, which are merged and await a
separate public rollout. The private hosted dashboard remains read-only.

## Daily review

1. **Overview** starts with **Needs attention**. Follow a source to its failure
   reason, latest attempt and last successful check. Monitoring-system reports
   and comparative charts are under **Monitoring systems and diagnostics**.
2. **Data sources** searches names, providers, categories and source IDs. Filter
   check results and check timing independently; sort by attention, name, oldest
   check or oldest success. Clear filters restores the full list.
3. **Recent changes** shows previous/current values and dates from saved
   observations, with source/type/date filters and links to source evidence.
   It reads up to 1,000 retained runs, deduplicates the same source-check event,
   and displays at most 500 changes. This is not a complete provider edit log.
   A source no longer in the current state is labelled without a broken link.
4. **Provider Terms** remains a CRM status view. Search providers or filter
   overdue follow-ups, unanswered inquiries, missing dates and stop requests.
   Use the provider link to update its CRM record. Recorded outcomes describe
   their stated purposes and never change monitoring permission. Connection
   failures show the saved copy's sync time; setup details remain expandable.
5. **Counties** opens profiles with Summary, Data access, Checks, Fields and
   Research sections. Detailed field results have one linked destination;
   research remains expandable. Access rights, check results, check timing and
   publisher data age retain separate meanings.

## Reading and navigation

The **More** menu exposes Provider Terms, changes, alerts, downloads and any
configured county-editor link on phones. Navigation marks the current page;
source and county pages include breadcrumbs. Escape closes navigation and
download menus. Deep links open the containing evidence section.

Open details/menus and focused inputs hold automatic reload. **Update view**
loads saved results while preserving filters, open sections, focus and scroll.
**Pause refresh** remains a persistent user choice. Updating this view does not
start provider checks. The footer shows application version/build and whether
the dashboard is view-only. An ordinary writable local dashboard retains its
existing separately controlled **Check now** action.

## Measurements and downloads

Source pages show relevant checks. A measured zero is retained; absent metrics
say **Not checked** or **Unavailable** without a misleading unit suffix.
Publisher data age stays unknown when there is no valid publisher update time.
Trends state units, date range and retained-observation counts, leaving gaps
unconnected. Retained observations are not an uptime/service guarantee.

**Downloads** is a page, rather than an immediate global workbook download.
The page menu labels **All monitoring data**, **This county** or **This source**
explicitly. Source JSON/CSV/Excel exports use an allowlist and exact source ID;
no registry URL, diagnostic or CRM content is added. The source CSV and Excel
summary include export time and latest check time in UTC. Existing global and
county export schemas are retained. Files contain summary observations, not
raw parcel records.

All added internal routes retain the private server's authentication and
read-only POST rejection. They are not added to the public server. Provider
polling, permission gates, scheduling, state/configuration and deployment are
outside this candidate.

## Validation scope

Validation uses synthetic local state, retained history and an invented CRM
cache. Browser checks cover desktop/tablet/phone layouts, navigation, filters,
source change links, downloads and refresh reading holds. Repository regressions
cover exact source identity, event deduplication/caps, measured zero, escaping,
export allowlists/formula handling, private-route authentication and POST refusal.
The live revision identity, settings and IAM were checked after promotion, and
the owner confirmed the updated signed-in UI. Follow-up read-only checks verified
saved source results, worker provenance and successful live requests without
server errors in the checked sample. See [the release record](release-v0.4.3.md)
for the exact deployed source and verification scope.
