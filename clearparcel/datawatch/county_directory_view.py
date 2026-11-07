"""Public presentation of confirmed county settings, separate from research."""
from __future__ import annotations

import datetime as dt
import html
from zoneinfo import ZoneInfo

from .public_values import safe_public_url

CLASSIFICATIONS = {"open": "Open GIS Data", "fee": "Fee Based GIS Data", "unknown": "Unknown"}
METHODS = {"mngeo_open": "MnGeo open", "direct_rest": "Direct REST", "direct_download": "Direct Download", "other": "Other"}
LINK_LABELS = {"mngeo_open": "Open statewide data (MnGeo)", "direct_rest": "Connect in GIS software",
               "direct_download": "Download GIS data", "other": "Open data page"}
RESEARCH_NOTICE = ("Earlier source research and supporting evidence appear below. "
                   "The latest access information is shown above. Finding a public link does not grant permission for automated checks.")


def with_published_directory(profiles: dict, directory: dict) -> dict:
    """Attach public settings without mutating cached profiles or research fields."""
    return {slug: {**profile, "county_directory": directory[profile["county"]["fips"]]}
            if profile["county"]["fips"] in directory else profile
            for slug, profile in profiles.items()}


def published_access_summary(directory: dict, key: str = "parcel_polygons", *, plain: bool = False) -> str:
    item = directory["access"][key]
    labels = LINK_LABELS if plain else METHODS
    methods = ", ".join(labels[method["kind"]] for method in item["methods"])
    return CLASSIFICATIONS[item["classification"]] + (" · " + methods if methods else "")


def county_access_summary(directory: dict) -> str:
    """Keep a statewide-only link from implying a county download exists."""
    item = directory["access"]["parcel_polygons"]
    direct = [method for method in item["methods"] if method["kind"] != "mngeo_open"]
    if item["classification"] == "open" and not direct and item["methods"]:
        return "Only a statewide link is listed"
    labels = {"open": "Open GIS data", "fee": "Fee-based parcel data", "unknown": "Access not confirmed"}
    return labels[item["classification"]] + (" · " + ", ".join(LINK_LABELS[m["kind"]] for m in direct) if direct else "")


def _updated_time(value: str) -> str:
    try:
        instant = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.tzinfo is not None:
            return instant.astimezone(ZoneInfo("America/Chicago")).strftime("%b %d, %Y · %I:%M %p %Z")
    except (ValueError, AttributeError):
        pass
    return "Not available"


def render_published_directory(directory: dict) -> str:
    def esc(value):
        return html.escape(str(value), quote=True)

    def link(value, label):
        url = safe_public_url(value)
        return f'<a href="{esc(url)}" rel="noopener">{esc(label)}</a>' if url else ""

    def paragraph(value):
        return esc(value or "").replace("\n", "<br>")

    contacts = []
    for person in directory["contacts"]:
        contact = [esc(person.get(key) or "—") for key in ("name", "role", "department", "phone", "email")]
        contact.extend([link(person.get("website"), "Website"), link(person.get("source_url"), "Public source"),
                        esc(person.get("verified_on") or "—")])
        contacts.append("<tr>" + "".join(f"<td>{value}</td>" for value in contact) + "</tr>")
    contact_table = (
        '<table class="contacts-table"><thead><tr><th>Name</th><th>Role</th><th>Department</th>'
        '<th>Phone</th><th>Email</th><th>Website</th><th>Source</th><th>Verified</th></tr></thead><tbody>'
        + "".join(contacts) + "</tbody></table>" if contacts else "<p>No contact is currently listed.</p>"
    )
    access = []
    for key, name in (("parcel_polygons", "Parcel Polygons"), ("road_centerlines", "Road Centerlines"),
                      ("address_points", "Address Points")):
        item = directory["access"][key]
        classification = CLASSIFICATIONS[item["classification"]]
        methods = []
        for method in item["methods"]:
            label = (method.get("description") or "Open data page") if method["kind"] == "other" else LINK_LABELS[method["kind"]]
            if method["kind"] == "direct_download" and key == "parcel_polygons":
                label = "Download parcel data"
            methods.append(f'<li>{link(method["url"], label)}'
                           f'<details class="profile-evidence"><summary>Technical details</summary>'
                           f'<p>{esc(method["scope"])} · Link reviewed: {esc(method["evidence_date"])}</p></details></li>')
        method_list = "<ul>" + "".join(methods) + "</ul>" if methods else ""
        restriction = item["restrictions"]
        note = {
            "unreviewed": "Use restrictions not yet reviewed",
            "reviewed_none": "No use restrictions recorded; confirm provider terms.",
            "restricted": paragraph(restriction.get("text")),
        }[restriction["status"]]
        reviewed = f' · Reviewed {esc(restriction["reviewed_on"])}' if restriction.get("reviewed_on") else ""
        access.append(
            f'<h3>{name}</h3><p><strong>{classification}</strong></p>{method_list}'
            f'<p><strong>County access note:</strong> {paragraph(item.get("county_direct_note") or "None recorded")}</p>'
            f'<p>{note} {link(restriction.get("url"), "Official restrictions")}{reviewed}</p>'
        )
    policy = directory["policy"]
    return (
        '<div class="card published-county-access"><h2>County GIS data access</h2>'
        f'<p>Access information updated: {esc(_updated_time(directory["published_at"]))}</p>'
        '<p class="subtext">These links describe how to get data. Watchtower check status is shown separately. '
        'Confirm the provider’s terms before reuse or automated access.</p>'
        + "".join(access)
        + f'<h3>County GIS policy</h3><p>{paragraph(policy.get("text") or "No policy text published.")}</p>'
        f'<p>{link(policy.get("url"), "Official county policy")}</p></div>'
        '<div class="card"><h2>County GIS contacts</h2>' + contact_table + '</div>'
    )
