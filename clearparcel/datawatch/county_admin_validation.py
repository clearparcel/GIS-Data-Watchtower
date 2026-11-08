"""Safe field hints after an editor draft fails authoritative validation."""
from __future__ import annotations

from .county_attachments import _event_time
from .county_directory import DATASETS, _project_contacts, _project_methods, _project_access, _public_fields
from .county_monitoring import build_county_monitoring_sources
from .county_profiles import county_identities


def editor_validation_errors(draft: object, *, monitoring_profiles=("cloud", "local")) -> list[dict]:
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
    try:
        county = next((item for item in county_identities().values() if item["fips"] == draft.get("fips")), None)
        if county is not None:
            build_county_monitoring_sources(county, draft, execution_profiles=monitoring_profiles)
    except ValueError as exc:
        monitoring_failure = str(exc)
        access = draft.get("access", {})
        found_monitoring = False
        for dataset in DATASETS:
            data = access.get(dataset, {}) if isinstance(access, dict) else {}
            for index, method in enumerate(data.get("methods", []) if isinstance(data, dict) else []):
                monitoring = method.get("monitoring") if isinstance(method, dict) else None
                if isinstance(monitoring, dict) and monitoring.get("enabled") is True:
                    path = f"access.{dataset}.methods.{index}.monitoring"
                    if "terms" in monitoring_failure:
                        suffix, hint = ".terms_url", "Enter the public provider-terms link, review date, and confirm that regular checks are allowed."
                        if "terms allow" in monitoring_failure:
                            suffix, hint = ".terms_confirmed", "Confirm the provider terms allow regular checks."
                    elif "worker" in monitoring_failure:
                        suffix, hint = ".execution_profile", "Choose which monitoring worker should run this source."
                    elif "current monitoring decision" in monitoring_failure:
                        suffix, hint = ".enabled", "This county's current monitoring review does not allow a new direct check."
                    elif "asked Watchtower" in monitoring_failure:
                        suffix, hint = ".enabled", "The county asked Watchtower not to check its direct sources."
                    elif "permission for service" in monitoring_failure:
                        suffix, hint = ".county_permission.received_on", "Record the date the county approved this limited check."
                    elif "county" in monitoring_failure or "permission" in monitoring_failure:
                        suffix, hint = ".county_permission.reply", "Record affirmative county permission for the limited check, with its date and private response reference."
                        if "public permission" in monitoring_failure:
                            suffix, hint = ".county_permission.evidence_url", "Add a public link documenting the county's permission."
                        elif "private reference" in monitoring_failure:
                            suffix, hint = ".county_permission.reference", "Add a private reference to the county's permission response."
                    elif "restrictions" in monitoring_failure:
                        suffix, hint = ".enabled", "Review the data-use restrictions before enabling regular checks."
                    elif "open data" in monitoring_failure:
                        suffix, hint = ".enabled", "Only open data sources can be included in regular checks."
                    elif "ArcGIS REST" in monitoring_failure or "download link" in monitoring_failure:
                        path = f"access.{dataset}.methods.{index}"
                        suffix, hint = ".url", "Use a direct ArcGIS layer link or a direct link to a supported data file."
                    else:
                        suffix, hint = ".enabled", "Check the link and regular-check settings for this source."
                    add(path + suffix, hint)
                    found_monitoring = True
                    break
            if found_monitoring:
                break
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
