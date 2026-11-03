"""Weekly digest: county-side staleness and Watchtower check gaps in one email.

Stale publisher data is not an outage, so it never sends an alert. Instead,
``watchtower weekly-digest`` (scheduled Monday mornings) reads the private
aggregate and history, and writes one structured log line,
``watchtower_weekly_digest``, that a log-based alert policy routes to the
existing email channel. It never contacts a provider and never claims a
provider-run slot.

The body is plain text kept under ``MAX_BODY`` characters so it fits the
policy's extracted label; long lists are cut with "and N more".
"""
from __future__ import annotations

import datetime as dt
import json
import tempfile
from pathlib import Path

from clearparcel.datawatch.aggregate import with_freshness
from clearparcel.datawatch.data_freshness import data_freshness, summarize

LOG_KEY = "watchtower_weekly_digest"
MAX_BODY = 900
MAX_LISTED = 8
CENTRAL = "America/Chicago"


def _name(sid: str, src: dict) -> str:
    return str(src.get("name") or sid)


def _listed(lines: list[str], limit: int = MAX_LISTED) -> list[str]:
    if len(lines) <= limit:
        return lines
    return lines[:limit] + [f"  and {len(lines) - limit} more"]


def build_digest(state: dict, config: dict, histories: dict, *, now: dt.datetime | None = None) -> dict:
    """Return ``{digest_id, subject, body, counts}`` for the week containing ``now``."""
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

    lines = [f"Data freshness: {counts['current']} current, {counts['stale']} stale, "
             f"{counts['unknown']} unknown of {len(rows)} sources."]
    if stale:
        lines.append("Stale publisher data (oldest first):")
        lines += _listed([f"  {_name(sid, sources[sid])}: {row['age_days']} days since update "
                          f"(expected within {row['expected_days']})" for sid, row in stale])
    if unknown:
        lines.append("No publisher update time:")
        lines += _listed([f"  {_name(sid, sources[sid])}" for sid in unknown])
    lines.append(f"Watchtower checks: {len(overdue_checks)} source(s) and {len(overdue_workers)} worker(s) "
                 "past the check window.")
    if overdue_workers:
        lines += _listed([f"  {name} worker" for name in overdue_workers])
    body = "\n".join(lines)
    if len(body) > MAX_BODY:
        body = body[:MAX_BODY - 20].rsplit("\n", 1)[0] + "\n  (list shortened)"
    subject = (f"Watchtower weekly digest {digest_id}: {counts['stale']} stale, "
               f"{counts['unknown']} unknown")
    return {"digest_id": digest_id, "subject": subject, "body": body, "counts": counts,
            "overdue_checks": len(overdue_checks), "overdue_workers": len(overdue_workers)}


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
        _, histories = load_history_index(history_config, (state.get("sources") or {}).keys(), limit=1000)
    digest = build_digest(state, config, histories, now=now)
    emit_digest(digest, stream)
    return digest
