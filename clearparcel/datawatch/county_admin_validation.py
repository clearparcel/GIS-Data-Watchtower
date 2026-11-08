"""Safe field hints after an editor draft fails authoritative validation."""
from __future__ import annotations

from .county_attachments import _event_time
from .county_directory import DATASETS, _project_contacts, _project_methods, _project_access, _public_fields


def editor_validation_errors(draft: object) -> list[dict]:
    """Return field paths and fixed messages; never echo draft values or diagnostics.

    These hints do not replace validation in the save/store and public projector.
    """
    errors = []
    def add(field, message):
        errors.append({"field": field, "message": message})

    if not isinstance(draft, dict):
        return [{"message": "Reload the record and try again. The editing record is invalid."}]
    contacts = draft.get("contacts", [])
    for index, contact in enumerate(contacts if isinstance(contacts, list) else []):
        if not isinstance(contact, dict) or contact.get("removed"):
            continue
        base = f"contacts.{index}"
        try:
            _project_contacts([contact])
        except ValueError as exc:
            message = str(exc)
            field = next((key for key in ("email", "verified_on", "website", "source_url", "name", "department", "phone", "role") if key in message), "name")
            hint = ("Enter a valid email address." if field == "email" else
                    "Enter a valid verification date." if field == "verified_on" else
                    "Use a public http or https link without credentials." if field in ("website", "source_url") else
                    "Enter a contact name or department, and use text for contact details.")
            add(f"{base}.{field}", hint)
    access = draft.get("access", {})
    for dataset in DATASETS:
        data = access.get(dataset, {}) if isinstance(access, dict) else {}
        if not isinstance(data, dict):
            add(f"access.{dataset}.classification", "Choose how this data is available.")
            continue
        base = f"access.{dataset}"
        methods = data.get("methods", [])
        if data.get("classification") == "open" and isinstance(methods, list):
            if not methods:
                add(base + ".classification", "Choose at least one way to access this data.")
            for index, method in enumerate(methods):
                try:
                    _project_methods([method])
                except ValueError as exc:
                    message = str(exc)
                    field = ("evidence_date" if "evidence_date" in message else "description" if "description" in message else
                             "url" if "URL" in message or "url" in message or not isinstance(method, dict) or not method.get("url") else "scope")
                    hint = {"evidence_date": "Enter the date this link was verified.", "description": "Describe this access method.",
                            "url": "Enter a public http or https data link without credentials.", "scope": "Describe what this data link covers."}[field]
                    add(f"{base}.methods.{index}.{field}", hint)
        try:
            _project_access({**data, "classification": "unknown"})
        except ValueError as exc:
            message = str(exc)
            field = ("county_direct_note" if "county_direct_note" in message else
                     "restrictions.reviewed_on" if "reviewed_on" in message else
                     "restrictions.url" if "url" in message else "restrictions.text")
            add(f"{base}.{field}", "Check the public note, restriction details, link or review date for this dataset.")
    policy = draft.get("policy", {})
    if isinstance(policy, dict):
        try:
            _public_fields(policy, text=("text",), urls=("url",))
        except ValueError:
            add("policy.url", "Check the public policy text and use a public http or https policy link without credentials.")
    events = draft.get("correspondence", [])
    for index, event in enumerate(events if isinstance(events, list) else []):
        if not isinstance(event, dict):
            continue
        for key in ("sent_at", "reply_at"):
            try:
                _event_time(event.get(key))
            except (ValueError, TypeError):
                add(f"correspondence.{index}.{key}.time", "Enter a valid Central date and time, choosing an occurrence if the time repeats.")
    return errors[:100] or [{"message": "Check this record's information and private file links. Your edits have been kept."}]
