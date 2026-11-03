"""Data freshness: has the publisher updated its data recently?

This is deliberately separate from check freshness (``with_freshness``), which
asks whether Watchtower checked a source recently. A source can be checked
every day and still publish data that is months old.

The publisher time comes from what a check already observes: an ArcGIS
``editingInfo.lastEditDate``, an HTTP ``Last-Modified`` header, or (for the
MnGeo county catalog) the newest county acquisition date. When the latest check
observed none (for example, it failed), the newest time in the source's history
is used. Each source's expected update interval is, in order:

1. ``expected_update_days`` in the source registry (owner override);
2. learned from the source's own history once at least three distinct publisher
   times have been seen (the median gap, with 50% headroom);
3. a 90-day default.

States: ``current``, ``stale`` (older than the expected interval) and
``unknown`` (no publisher time, or one in the future). Unknown is never shown as
current. Stale data is not an outage, so it never becomes an active alert.
"""
from __future__ import annotations

import datetime as dt
import math
import statistics

from clearparcel.datawatch.public_values import _metadata_date, provider_edit_timestamp

DEFAULT_EXPECTED_DAYS = 90
MIN_DISTINCT_UPDATES = 3
LEARNED_HEADROOM = 1.5
MAX_EXPECTED_DAYS = 3650
# History rows read per source for learning an interval. The dashboard and the
# weekly digest share it so both classify a source the same way.
HISTORY_LIMIT = 1000
FUTURE_TOLERANCE = dt.timedelta(days=1)


def publisher_updated_at(record: object) -> str | None:
    """Normalized UTC ISO time the publisher last changed this source's data."""
    if not isinstance(record, dict):
        return None
    editing = record.get("editing_info")
    if isinstance(editing, dict):
        stamp = provider_edit_timestamp(editing.get("lastEditDate"))
        if stamp:
            return stamp
    tracked = record.get("tracked_values")
    if isinstance(tracked, dict) and tracked.get("last_modified"):
        stamp = _metadata_date(tracked.get("last_modified"), http=True)
        if stamp:
            return stamp
    catalog = record.get("county_records")
    if isinstance(catalog, dict):
        # MnGeo's county catalog: the newest county acquisition date is when
        # the statewide data last took in a county update.
        stamps = [provider_edit_timestamp(row.get("acqdate")) for row in catalog.values() if isinstance(row, dict)]
        stamps = [stamp for stamp in stamps if stamp]
        if stamps:
            return max(stamps, key=_parse)
    stamp = record.get("data_updated_at")  # already normalized (history rows)
    return _metadata_date(stamp) if isinstance(stamp, str) else None


def valid_expected_days(value: object) -> bool:
    return type(value) is int and 1 <= value <= MAX_EXPECTED_DAYS


def expected_interval(source_config: object, history: object = ()) -> tuple[int, str]:
    """``(days, basis)`` where basis is ``configured``, ``observed`` or ``default``."""
    configured = source_config.get("expected_update_days") if isinstance(source_config, dict) else None
    if valid_expected_days(configured):
        return configured, "configured"
    times = sorted({_parse(row.get("data_updated_at")) for row in (history or ()) if isinstance(row, dict)} - {None})
    if len(times) >= MIN_DISTINCT_UPDATES:
        gaps = [(b - a).total_seconds() / 86400 for a, b in zip(times, times[1:])]
        days = math.ceil(statistics.median(gaps) * LEARNED_HEADROOM)
        return min(max(days, 1), MAX_EXPECTED_DAYS), "observed"
    return DEFAULT_EXPECTED_DAYS, "default"


def data_freshness(record: object, *, source_config: object = None, history: object = (),
                   now: dt.datetime | None = None) -> dict:
    """Classify one source's data age."""
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    days, basis = expected_interval(source_config, history)
    stamp = publisher_updated_at(record) or _latest_in_history(history)
    seen = _parse(stamp)
    result = {"data_updated_at": stamp, "expected_days": days, "basis": basis, "age_days": None}
    if seen is None or seen - now > FUTURE_TOLERANCE:
        return {**result, "state": "unknown"}
    age = max(0.0, (now - seen).total_seconds() / 86400)
    return {**result, "age_days": int(age), "state": "stale" if age > days else "current"}


def summarize(states: object) -> dict:
    counts = {"current": 0, "stale": 0, "unknown": 0}
    for row in states or ():
        state = row.get("state") if isinstance(row, dict) else None
        counts[state if state in counts else "unknown"] += 1
    return counts


def _latest_in_history(history: object) -> str | None:
    times = [(parsed, row["data_updated_at"]) for row in (history or ()) if isinstance(row, dict)
             for parsed in [_parse(row.get("data_updated_at"))] if parsed]
    return max(times)[1] if times else None


def _parse(value: object) -> dt.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)
