"""Weekly digest: county-side staleness and Watchtower check gaps in one email.

Stale publisher data is not an outage, so it never sends an alert. Instead,
``watchtower weekly-digest`` (scheduled Monday mornings) reads the private
aggregate and history, and writes one structured log line,
``watchtower_weekly_digest``, that a log-based alert policy routes to the
existing email channel. It never contacts a provider and never claims a
provider-run slot.

The body is plain text kept under ``MAX_BODY`` characters so it fits the
policy's extracted label. The summary lines (data freshness, overdue checks
and, when the CRM link is configured, provider terms follow-ups) always come
first; long lists are cut with "and N more", shrinking further until the body
fits. Terms status is read from the private CRM's read-only endpoint (#185); if
the CRM cannot be read the digest still sends and says so.
"""
from __future__ import annotations

import datetime as dt
import json
import tempfile
from pathlib import Path

from clearparcel.datawatch.aggregate import with_freshness
from clearparcel.datawatch.data_freshness import HISTORY_LIMIT, data_freshness, summarize

LOG_KEY = "watchtower_weekly_digest"
MAX_BODY = 900
MAX_LISTED = 8
CENTRAL = "America/Chicago"


def _name(sid: str, src: dict) -> str:
    return str(src.get("name") or sid)


def _listed(lines: list[str], limit: int = MAX_LISTED) -> list[str]:
    if len(lines) <= limit:
        return lines
    return lines[:limit] + [f"  {'and ' if limit else ''}{len(lines) - limit} more"]


def _fit(headline: list[str], sections: list[tuple[str, list[str]]]) -> str:
    """Headline lines always survive; each list shrinks until the body fits."""
    for limit in (MAX_LISTED, 5, 3, 1, 0):
        lines = list(headline)
        for title, items in sections:
            if items:
                lines += [title] + _listed(items, limit)
        body = "\n".join(lines)
        if len(body) <= MAX_BODY:
            return body
    return body[:MAX_BODY - 1] + "…"


def _terms_lines(terms: dict | None, now: dt.datetime) -> tuple[list[str], list[tuple[str, list[str]]], int]:
    """Headline, sections and overdue count for provider terms; nothing when not configured."""
    from clearparcel.datawatch.provider_terms import (
        WAITING_DAYS, days_waiting, is_due_this_week, is_overdue, sort_for_attention, summarize,
    )
    if terms is None:
        return [], [], 0
    status = terms.get("status")
    if not status:
        return [f"Provider terms: CRM not reachable ({terms.get('last_error') or 'unknown error'})."], [], 0
    providers = [p for p in status.get("providers") or [] if not p.get("archived")]
    counts = summarize(providers, now)
    ordered = sort_for_attention(providers, now)
    headline = [f"Provider terms: {counts['overdue']} follow-up(s) overdue, {counts['due_this_week']} due this week, "
                f"{counts['waiting']} with no reply in {WAITING_DAYS}+ days, {counts['open']} open."]
    sections = [
        ("Terms follow-ups overdue:", [f"  {p['name']}: due {p['open_inquiry']['follow_up_due_on']}"
                                        for p in ordered if is_overdue(p, now)]),
        ("Terms follow-ups this week:", [f"  {p['name']}: {p['open_inquiry']['follow_up_due_on']}"
                                         for p in ordered if is_due_this_week(p, now)]),
        (f"No reply in {WAITING_DAYS}+ days:", [f"  {p['name']}: {days_waiting(p, now)} days"
                                                for p in ordered if (days_waiting(p, now) or 0) >= WAITING_DAYS]),
    ]
    return headline, sections, counts["overdue"]


def build_digest(state: dict, config: dict, histories: dict, *, now: dt.datetime | None = None,
                 terms: dict | None = None) -> dict:
    """Return ``{digest_id, subject, body, counts}`` for the week containing ``now``.

    ``terms`` is a provider-terms snapshot (``TermsCache.snapshot()``), or None
    when the CRM link is not configured.
    """
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    state = with_freshness(state or {}, now=now,
                           worker_stale_minutes=int(config.get("worker_stale_minutes", 1560)),
                           source_stale_minutes=int(config.get("source_stale_minutes", 1560)))
    sources = state.get("sources") or {}
    config_map = {s.get("id"): s for s in config.get("sources", []) if isinstance(s, dict)}
    rows = {sid: data_freshness(src, source_config=config_map.get(sid), history=histories.get(sid, ()), now=now)
            for sid, src in sources.items()}
    counts = summarize(rows.values())
    stale = sorted(((sid, row) for sid, row in rows.items() if row["state"] == "stale"),
                   key=lambda item: -(item[1]["age_days"] or 0))
    unknown = sorted(sid for sid, row in rows.items() if row["state"] == "unknown")
    overdue_checks = sorted(sid for sid, src in sources.items() if src.get("stale"))
    overdue_workers = sorted(name for name, w in (state.get("workers") or {}).items() if w.get("stale"))
    try:
        from zoneinfo import ZoneInfo
        local = now.astimezone(ZoneInfo(CENTRAL))
    except Exception:  # noqa: BLE001 - tzdata missing: fall back to UTC wording
        local = now
    year, week, _ = local.isocalendar()
    digest_id = f"{year}-W{week:02d}"

    headline = [f"Data freshness: {counts['current']} current, {counts['stale']} stale, "
                f"{counts['unknown']} unknown of {len(rows)} sources.",
                f"Watchtower checks: {len(overdue_checks)} source(s) and {len(overdue_workers)} worker(s) "
                "past the check window."]
    sections = [
        ("Stale publisher data (oldest first):",
         [f"  {_name(sid, sources[sid])}: {row['age_days']} days since update "
          f"(expected within {row['expected_days']})" for sid, row in stale]),
        ("No publisher update time:", [f"  {_name(sid, sources[sid])}" for sid in unknown]),
        ("Checks overdue:", [f"  {name} worker" for name in overdue_workers]
         + [f"  {_name(sid, sources[sid])}" for sid in overdue_checks]),
    ]
    terms_headline, terms_sections, terms_overdue = _terms_lines(terms, now)
    # Terms follow-ups come before the long freshness lists: they are the owner's actions.
    body = _fit(headline + terms_headline, terms_sections + sections)
    subject = (f"Watchtower weekly digest {digest_id}: {counts['stale']} stale, "
               f"{counts['unknown']} unknown")
    if overdue_checks or overdue_workers:
        subject += f", {len(overdue_checks) + len(overdue_workers)} overdue"
    if terms_overdue:
        subject += f", {terms_overdue} terms follow-up(s) overdue"
    return {"digest_id": digest_id, "subject": subject, "body": body, "counts": counts,
            "overdue_checks": len(overdue_checks), "overdue_workers": len(overdue_workers),
            "terms_overdue": terms_overdue}


def emit_digest(digest: dict, stream) -> None:
    """One structured log line; ``message`` carries the subject for the policy."""
    payload = {"severity": "NOTICE", "message": digest["subject"],
               LOG_KEY: {"schema_version": 1, "digest_id": digest["digest_id"], "body": digest["body"],
                         "counts": digest["counts"]}}
    stream.write(json.dumps(payload, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n")
    stream.flush()


def run_weekly_digest(config: dict, storage, stream, *, aggregate_object: str = "aggregate-state.json",
                      now: dt.datetime | None = None) -> dict:
    """Read the aggregate and history from storage, build the digest and log it."""
    from clearparcel.datawatch.cloud_job import ARTIFACTS, HISTORY_ARCHIVE
    from clearparcel.datawatch.watch import load_history_index, load_state
    with tempfile.TemporaryDirectory(prefix="watchtower-digest-") as scratch:
        root = Path(scratch)
        aggregate_path = root / "aggregate-state.json"
        if not storage.download(aggregate_object, aggregate_path):
            raise FileNotFoundError(f"aggregate not found: {aggregate_object}")
        history = ARTIFACTS["history_file"]
        history_config = {"history_file": str(root / history)}
        storage.download(history, root / history)
        storage.download(HISTORY_ARCHIVE, root / HISTORY_ARCHIVE)
        state = load_state(str(aggregate_path))
        _, histories = load_history_index(history_config, (state.get("sources") or {}).keys(),
                                          limit=HISTORY_LIMIT)
    digest = build_digest(state, config, histories, now=now, terms=_terms_snapshot())
    emit_digest(digest, stream)
    return digest


def _terms_snapshot(environ=None) -> dict | None:
    """One read of the CRM terms status for this digest; None when not configured."""
    from clearparcel.datawatch.provider_terms import cache_from_env
    cache = cache_from_env(environ)
    if cache is None:
        return None
    cache.refresh()  # never raises: a failure becomes the snapshot's last_error
    return cache.snapshot()
