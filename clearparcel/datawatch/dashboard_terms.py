"""Read-only provider terms action list from the private CRM cache."""
from __future__ import annotations

import datetime as dt
from urllib.parse import urlsplit

from . import dashboard
from .csp import SCRIPT_TAG
from .dashboard_activity import compact_time
from .product import page_title
from .provider_terms import (
    PURPOSES, STAGES, WAITING_DAYS, days_waiting, is_overdue, sort_for_attention, summarize,
)
from .watch import _safe_diagnostic

_esc = dashboard._esc


def _crm_link(value) -> str | None:
    # TermsCache already confines CRM and review links to their expected origins.
    # Private CRM hosts need not pass the public GIS-link host policy.
    if not isinstance(value, str) or any(c.isspace() or ord(c) < 32 for c in value):
        return None
    try:
        parsed = urlsplit(value)
        return value if parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password else None
    except ValueError:
        return None

_OUTCOMES = {"full": "Recorded scope: full", "details-and-count": "Recorded scope: details and count only",
             "none": "Recorded scope: none", "hold-for-terms": "Held pending terms", "stop-requested": "Stop requested"}


def _card(label: str, value: int, note: str) -> str:
    return (f'<div class="card"><div class="muted">{_esc(label)}</div><div class="metric">{value}</div>'
            f'<span class="subtext">{_esc(note)}</span></div>')


def _row(provider: dict, now: dt.datetime) -> str:
    inquiry = provider.get("open_inquiry") or {}
    name = _esc(provider.get("name") or "Provider")
    link = _crm_link(provider.get("crm_url"))
    name_html = f'<a href="{_esc(link)}" target="_blank" rel="noopener"><strong>{name}</strong></a>' if link else f'<strong>{name}</strong>'
    if provider.get("archived"):
        name_html += ' <span class="subtext">Archived</span>'
    stage = STAGES.get(inquiry.get("stage") or "", "No open inquiry")
    stage_html = _esc(stage)
    if provider.get("terms_stopped"):
        stage_html += ' <span class="pill error">Stop requested</span>'
    purposes = ", ".join(PURPOSES.get(p, "Other") for p in inquiry.get("purposes") or []) or "Not recorded"
    due = inquiry.get("follow_up_due_on")
    overdue = is_overdue(provider, now)
    follow_up = (('<span class="pill overdue">Overdue</span> ' if overdue else '') + _esc(due)) if due else ('No date set' if inquiry else 'No open inquiry')
    waiting = days_waiting(provider, now)
    unanswered = waiting is not None and waiting >= WAITING_DAYS
    last_email = compact_time(provider.get("last_email_at"))
    if unanswered:
        last_email += f'<br><span class="subtext">No reply in {waiting} days</span>'
    outcome = _esc(_OUTCOMES.get(provider.get("latest_outcome") or "", "No outcome recorded"))
    gate = _crm_link(provider.get("watchtower_gate_url"))
    if gate:
        outcome += f'<br><a href="{_esc(gate)}" target="_blank" rel="noopener">Review monitoring decision</a>'
    actions = [key for key, yes in (("overdue", overdue), ("waiting", unanswered),
               ("no-date", bool(inquiry) and not due), ("stopped", provider.get("terms_stopped")), ("open", bool(inquiry))) if yes]
    search = ' '.join(str(x) for x in (provider.get("name") or '', stage, purposes)).lower()
    cells = [("Stage", stage_html), ("Purposes", _esc(purposes)), ("Follow-up", follow_up),
             ("Last email", last_email), ("Last reply", compact_time(provider.get("last_reply_at"))), ("Recorded outcome", outcome)]
    return (f'<tr data-search="{_esc(search)}" data-actions="{" ".join(actions)}"><th scope="row">{name_html}</th>'
            + ''.join(f'<td data-label="{label}">{value}</td>' for label, value in cells) + '</tr>')


def render_terms_body(snapshot: dict | None, *, now: dt.datetime | None = None) -> str:
    now = now or dt.datetime.now(dt.timezone.utc)
    intro = ('<p>Provider data-use inquiries, read from the private CRM. This page is read-only; open a provider to update its CRM record. '
             'Recorded outcomes apply to their stated purposes. They do not change Watchtower monitoring permission, including holds and stop requests.</p>')
    if snapshot is None:
        return intro + ('<section class="card"><h2>Provider terms · Not connected</h2><p>A CRM terms connection has not been set up for this dashboard.</p>'
                        '<details class="technical"><summary>Administrator setup details</summary><p>Configure WATCHTOWER_CRM_TERMS_URL, '
                        'WATCHTOWER_CRM_ACCESS_CLIENT_ID and WATCHTOWER_CRM_ACCESS_CLIENT_SECRET in the deployment environment.</p></details></section>')
    status = snapshot.get("status")
    if snapshot.get("last_error"):
        notice = ('<section class="card"><h2>CRM not reachable</h2>'
                  + (f'<p>Showing a saved CRM copy. Showing the copy from {compact_time(snapshot.get("fetched_at"))}.</p>' if status else '<p>No earlier copy is available yet.</p>')
                  + f'<details class="technical"><summary>Connection details</summary><p>{_esc(_safe_diagnostic(snapshot["last_error"]))}</p></details></section>')
    else:
        notice = f'<p class="subtext">Last successful CRM sync: {compact_time(snapshot.get("fetched_at"))}.</p>' if status else '<section class="card"><h2>Waiting for the CRM</h2><p>No terms copy has loaded yet. The dashboard will try again automatically.</p></section>'
    if not status:
        return intro + notice
    providers = status.get("providers") or []
    counts = summarize(providers, now)
    cards = ('<div class="grid terms-summary">'
             + _card("Open inquiries", counts["open"], "Providers with an inquiry in progress.")
             + _card("Follow-ups overdue", counts["overdue"], "Follow-up date before today (Central).")
             + _card("Due in the next 7 days", counts["due_this_week"], "Including today.")
             + _card(f"No reply in {WAITING_DAYS}+ days", counts["waiting"], "Our last email is still unanswered.")
             + _card("No follow-up date", counts["no_follow_up"], "Set the date in the CRM.")
             + _card("Asked us to stop", counts["stopped"], "Including archived providers.") + '</div>')
    rows = ''.join(_row(p, now) for p in sort_for_attention(providers, now))
    table = f'''<section class="card"><h2>Providers</h2><p>Overdue follow-ups first, then soonest follow-up and longest wait. Outcomes are CRM records; reviewed monitoring decisions remain separate.</p>
<div class="filters"><input id="terms-q" type="search" aria-label="Search providers" placeholder="Search providers, stages or purposes…"><select id="terms-status" aria-label="Filter provider action"><option value="">All providers</option><option value="overdue">Follow-up overdue</option><option value="waiting">No reply in {WAITING_DAYS}+ days</option><option value="no-date">No follow-up date</option><option value="stopped">Stop requested</option><option value="open">Open inquiry</option></select><button type="button" id="terms-clear">Clear filters</button></div>
<p id="terms-results" role="status"></p><table class="ops-table" id="provider-terms"><thead><tr><th>Provider</th><th>Stage</th><th>Purposes</th><th>Follow-up</th><th>Last email</th><th>Last reply</th><th>Recorded outcome</th></tr></thead><tbody>{rows}</tbody></table><p id="terms-empty" hidden>No providers match these filters.</p></section>
{SCRIPT_TAG}(function(){{const q=document.getElementById('terms-q'),s=document.getElementById('terms-status'),rows=[...document.querySelectorAll('#provider-terms tbody tr')];function filter(){{let n=0;rows.forEach(r=>{{r.hidden=!(r.dataset.search.includes(q.value.toLowerCase())&&(!s.value||r.dataset.actions.split(' ').includes(s.value)));if(!r.hidden)n++}});document.getElementById('terms-results').textContent=n+' of '+rows.length+' providers shown';document.getElementById('terms-empty').hidden=n>0}}q.addEventListener('input',filter);s.addEventListener('change',filter);document.getElementById('terms-clear').addEventListener('click',()=>{{q.value='';s.value='';filter();q.focus();window.watchtowerRefresh?.save()}});filter()}})();</script>'''
    return intro + notice + cards + table


def render_terms(config: dict) -> str:
    cache = config.get("_terms_cache")
    body = render_terms_body(cache.snapshot() if cache is not None else None)
    return dashboard._layout(page_title("Provider terms"), '<p><a href="/">← Watchtower overview</a></p>' + body,
                             active_section="terms", csrf_token=str(config.get("_csrf_token") or ""))


__all__ = ["render_terms", "render_terms_body"]
