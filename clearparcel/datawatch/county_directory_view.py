"""Public presentation of confirmed county settings, separate from research."""
from __future__ import annotations

import html

from .public_values import safe_public_url

CLASSIFICATIONS = {"open": "Open GIS Data", "fee": "Fee Based GIS Data", "unknown": "Unknown"}
METHODS = {"mngeo_open": "MnGeo open", "direct_rest": "Direct REST", "direct_download": "Direct Download", "other": "Other"}
RESEARCH_NOTICE = ("Packaged research is retained for provenance and monitoring decisions. "
                   "It is not updated by Apply; current access settings appear above.")


def with_published_directory(profiles: dict, directory: dict) -> dict:
    """Attach public settings without mutating cached profiles or research fields."""
    return {slug: {**profile, "county_directory": directory[profile["county"]["fips"]]}
            if profile["county"]["fips"] in directory else profile
            for slug, profile in profiles.items()}


def published_access_summary(directory: dict, key: str = "parcel_polygons") -> str:
    item = directory["access"][key]
    methods = ", ".join(METHODS[method["kind"]] for method in item["methods"])
    return CLASSIFICATIONS[item["classification"]] + (" · " + methods if methods else "")


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
            label = (method.get("description") or "Other") if method["kind"] == "other" else METHODS[method["kind"]]
            methods.append(f'<li>{link(method["url"], label)} · {esc(method["scope"])} · {esc(method["evidence_date"])}</li>')
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
            f'<p><strong>Administrator note:</strong> {paragraph(item.get("county_direct_note") or "None recorded")}</p>'
            f'<p>{note} {link(restriction.get("url"), "Official restrictions")}{reviewed}</p>'
        )
    policy = directory["policy"]
    return (
        '<div class="card published-county-access"><h2>County GIS data access</h2>'
        f'<p>Published revision {esc(directory["public_revision"])} · {esc(directory["published_at"])}</p>'
        '<p class="subtext">Current settings published from the county editor. '
        'Access methods do not indicate active Watchtower monitoring or permission to monitor.</p>'
        + "".join(access)
        + f'<h3>County GIS policy</h3><p>{paragraph(policy.get("text") or "No policy text published.")}</p>'
        f'<p>{link(policy.get("url"), "Official county policy")}</p></div>'
        '<div class="card"><h2>County GIS contacts</h2>' + contact_table + '</div>'
    )
