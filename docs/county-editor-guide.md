# County information editor

Available in v0.5.0, deployed November 7, 2026 following the UI review.
The editor manages contacts, data access, policy and private records.

## Editing a county

Choose a county, or use **Find a county or contact** to search county names,
contact names, email addresses, departments and roles. Contact counts are labelled.
An empty search explains how to clear it; **Refresh county list** retries a failed
directory read. Phones use a compact county selector.

Use **Contacts**, **Data access**, **Policy** and **Private correspondence** to
move within the editing area. The county name and save controls remain visible.
Save controls occupy a separate area and do not overlay the form. Dataset cards
summarize access and expand to show their links, verification dates, coverage
and restrictions. Access information does not grant permission for automated
monitoring. A statewide copy remains separate from county-direct access.

Direct service and download links include **Regular Watchtower checks**. Choose
**Include this source in regular checks** after reviewing restrictions, provider
terms and affirmative county permission. Save records the
enrollment for the next regular run. Service checks read details and one record
count; file checks read update headers. Permission references stay private.
Existing terms holds and county stop decisions remain in force. See the
[source monitoring guide](county-source-monitoring.md) for supported links,
save recovery and deployment prerequisites. The hosted editor uses the active
regular cloud schedule; a worker choice appears only when explicitly configured.

**Remove contact** changes the draft. **Undo contact removal** restores the most
recent removal. **Discard unsaved changes** asks before reloading a saved record.
Switching counties or leaving the page also protects unsaved work.

## Reviewing and saving

**Review changes** shows before/after values from known editable fields, with
public and private changes labelled. Public contacts, data-access details and
policy text/links are published when changed and saved. Private correspondence,
notes and PDF links remain private. IDs, CRM references and unrelated stored
fields are excluded from the review and conflict editing-copy download.

**Save changes** shows progress. Missing or invalid values appear in a linked
error summary and beside the relevant field. Following an error opens its dataset
section and focuses the field. Server validation remains authoritative; safe
field hints supplement it without returning private diagnostics.

A confirmed save remains confirmed even if refreshing the county list fails.
Use **Refresh county list** to repair that separate read. An unconfirmed save
keeps the exact request and locks its fields; **Retry save** resends it. A saved
record with pending public publication shows **Retry publication** separately.
Private-only saves never claim a new public publication. **View public page**
opens the public county page in a separate tab.

If another editor changed the record, the local draft stays in the form.
Compare it with the latest saved values. **Download my edits (private text)**
provides an editing copy of known editable values before a confirmed reload;
the file can contain private correspondence and should be stored accordingly.
Loading the latest record does not automatically overwrite or merge anyone's
saved changes.

## Private files and correspondence

Files must be PDFs of at most 20 MB. Select a file, use **Upload PDF**, then
**Save changes** to link the upload to the record. A selected file survives
unrelated form updates; **Clear selected file** clears an unuploaded selection.
Saving asks you to upload or clear any remaining selection first.

An uploaded file stays private and is downloadable only after its linked file
check passes. Pending files explain whether to save their link first or use
**Retry file check**. Rejected files remain unavailable. **Remove from this
record** removes the reference; it does not delete the stored PDF. Private policy
PDFs are not published with the public policy text.

**Log an email** records correspondence; it sends no email. Enter Central dates
and times. The editor resolves ordinary times automatically, rejects nonexistent
spring times, and asks which occurrence you mean only during the repeated fall
hour. Private dates and attachment references retain server validation.
