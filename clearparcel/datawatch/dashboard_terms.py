"""Private dashboard "Provider terms" view (#185): CRM terms status, read-only.

Overdue follow-ups come first, each row links to the CRM record, and the page
renders from the cached copy (with its age) when the CRM is unreachable.
"""
from __future__ import annotations

import datetime as dt

from clearparcel.datawatch import dashboard as _dashboard
from clearparcel.datawatch.county_profile_panel import profile_time
from clearparcel.datawatch.product import page_title
from clearparcel.datawatch.provider_terms import (
    OUTCOMES, PURPOSES, STAGES, WAITING_DAYS, days_waiting, is_overdue, sort_for_attention, summarize,
)

_esc = _dashboard._esc


def _card(label: str, value: int, note: str) -> str:
    return (f'<div class="card"><div class="muted">{_esc(label)}</div><div class="metric">{value}</div>'
            f'<span class="subtext">{_esc(note)}</span></div>')


def _row(provider: dict, now: dt.datetime) -> str:
    inquiry = provider.get("open_inquiry")
    name = _esc(provider.get("name") or "Provider")
    link = provider.get("crm_url")
    name_html = f'<a href="{_esc(link)}" target="_blank" rel="noopener"><strong>{name}</strong></a>' if link else f"<strong>{name}</strong>"
    if provider.get("archived"):
        name_html += ' <span class="subtext">archived</span>'
    stage = STAGES.get((inquiry or {}).get("stage") or "", "") if inquiry else ""
    stage_html = _esc(stage) if stage else '<span class="muted">No open inquiry</span>'
    if provider.get("terms_stopped"):
        stage_html += ' <span class="pill error">Stop requested</span>'
    purposes = ", ".join(PURPOSES[p] for p in (inquiry or {}).get("purposes") or []) or "—"
    due = (inquiry or {}).get("follow_up_due_on")
    if due and is_overdue(provider, now):
        follow_up = f'<span class="pill overdue">Overdue</span> {_esc(due)}'
    elif due:
        follow_up = _esc(due)
    else:
        follow_up = '<span class="muted">Not set</span>' if inquiry else "—"
    waiting = days_waiting(provider, now)
    last_email = _esc(profile_time(provider.get("last_email_at"))) if provider.get("last_email_at") else "—"
    if waiting is not None and waiting >= WAITING_DAYS:
        last_email += f'<br><span class="subtext">No reply in {waiting} days</span>'
    last_reply = _esc(profile_time(provider.get("last_reply_at"))) if provider.get("last_reply_at") else "—"
    outcome = OUTCOMES.get(provider.get("latest_outcome") or "", "—")
    gate = provider.get("watchtower_gate_url")
    if gate:
        outcome += f' · <a href="{_esc(gate)}" target="_blank" rel="noopener">gate change</a>'
    return (f"<tr><td>{name_html}</td><td>{stage_html}</td><td>{_esc(purposes)}</td><td>{follow_up}</td>"
            f"<td>{last_email}</td><td>{last_reply}</td><td>{outcome}</td></tr>")


def render_terms_body(snapshot: dict | None, *, now: dt.datetime | None = None) -> str:
    """The page body for a TermsCache snapshot (None when the CRM link is not configured)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    intro = ('<p class="muted">Where each county and state agency stands on data-use terms, read from the private CRM. '
             'Read-only: change inquiries in the CRM. Kept apart from monitoring decisions, which change only '
             'through reviewed gate changes.</p>')
    if snapshot is None:
        return intro + ('<div class="card"><h2>Not connected</h2><p class="muted">The CRM terms link is not configured '
                        'for this dashboard (WATCHTOWER_CRM_TERMS_URL, WATCHTOWER_CRM_ACCESS_CLIENT_ID and '
                        'WATCHTOWER_CRM_ACCESS_CLIENT_SECRET).'
                        '</p></div>')
    status = snapshot.get("status")
    notice = ""
    if snapshot.get("last_error"):
        notice = (f'<div class="card"><strong>CRM not reachable.</strong> {_esc(snapshot["last_error"])}. '
                  + (f"Showing the copy from {_esc(profile_time(snapshot.get('fetched_at')))}."
                     if status else "No earlier copy is available yet.") + "</div>")
    if not status:
        if not notice:
            notice = '<div class="card"><p class="muted">Loading terms status from the CRM… reload in a moment.</p></div>'
        return intro + notice
    providers = status.get("providers") or []
    counts = summarize(providers, now)
    cards = ('<div class="grid">'
             + _card("Open inquiries", counts["open"], "Providers with a terms inquiry in progress.")
             + _card("Follow-ups overdue", counts["overdue"], "Follow-up date before today (Central).")
             + _card("Due in the next 7 days", counts["due_this_week"], "Including today.")
             + _card(f"No reply in {WAITING_DAYS}+ days", counts["waiting"], "Our last email is still unanswered.")
             + _card("Asked us to stop", counts["stopped"], "Including archived providers.")
             + "</div>")
    if counts["no_follow_up"]:
        cards += (f'<p class="subtext">{counts["no_follow_up"]} open inquiry(ies) have no follow-up date; '
                  "set one in the CRM so overdue tracking can work.</p>")
    rows = "".join(_row(p, now) for p in sort_for_attention(providers, now))
    table = ('<div class="card"><h2>Providers</h2><p class="subtext">Overdue follow-ups first, then the soonest '
             f'follow-up, then the longest wait. As of {_esc(profile_time(snapshot.get("fetched_at")))}.</p>'
             '<table id="provider-terms"><thead><tr><th>Provider</th><th>Stage</th><th>Purposes</th>'
             '<th>Follow-up</th><th>Last email</th><th>Last reply</th><th>Outcome</th></tr></thead>'
             f"<tbody>{rows}</tbody></table></div>") if providers else '<div class="card">No providers in the CRM yet.</div>'
    return intro + notice + cards + table


def render_terms(config: dict) -> str:
    cache = config.get("_terms_cache")
    body = render_terms_body(cache.snapshot() if cache is not None else None)
    return _dashboard._layout(page_title("Provider terms"), '<p><a href="/">← Watchtower overview</a></p>' + body,
                              csrf_token=str(config.get("_csrf_token") or ""))


__all__ = ["render_terms", "render_terms_body"]
