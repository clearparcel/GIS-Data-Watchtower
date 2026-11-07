"""Plain-language presentation helpers; stored metrics and contracts stay unchanged."""
import html

COMPLETENESS_NOTE = (
    "Completeness is the share of fields with a value across the records shown. "
    "Filled values may still be inaccurate. These percentages are not compliance scores; "
    "conditional and optional fields may legitimately be blank."
)
REQUIREMENTS = {"Mandatory": "Required", "Conditional": "Required in some cases",
                "If Available": "When available", "Optional": "Optional"}


def source_status_label(value: str) -> str:
    return {"ok": "Source responding", "warn": "Warning", "error": "Error",
            "paused": "Paused", "awaiting-permission": "Awaiting permission"}.get(
                str(value or "unknown").strip().lower(), "Unknown")


def statewide_copy_label(record: dict | None, live_available: bool | None) -> str:
    if live_available is True:
        return "Available free through MnGeo"
    if live_available is False:
        return "Not included in the latest statewide data"
    if ((record or {}).get("statewide_open_coverage") or {}).get("available") is True:
        return "Listed as available through MnGeo (earlier research)"
    return "Availability not confirmed"


def requirement_label(value: str) -> str:
    return REQUIREMENTS.get(value, value)


def technical_field_details(field: str, section: str, present: str, scan: str) -> str:
    values = [html.escape(str(value), quote=True) for value in (field, section, present, scan)]
    return ('<details class="profile-evidence"><summary>Technical details</summary>'
            f'<p>Field name: <code>{values[0]}</code><br>Section: {values[1]}'
            f'<br>Field exists in source: {values[2]}<br>Values checked: {values[3]}</p></details>')
