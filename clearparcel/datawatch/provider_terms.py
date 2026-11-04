"""Read-only data-provider terms status from the private CRM (#185).

Watchtower shows, never changes, where each county and state agency stands on
data-use terms. The CRM owns that record; Watchtower reads one route,
``GET /api/terms/status``, with its own Cloudflare Access service token. That
token is separate from the CRM's CI token and the CRM allows it nothing else.

Boundaries kept here:

- **No correspondence crosses over.** Each provider row is reduced to an
  allow-list of fields (stage, purposes, follow-up date, outcome, dates and
  links). Anything else the CRM might add later is dropped, never stored.
- **Not a GIS provider.** The CRM is the owner's own system, so this is not a
  provider poll: it never claims a provider-run slot and is not rate-limited by
  the provider-run guard. It is still bounded: one request at most every
  ``REFRESH_SECONDS``, a short timeout and a size cap.
- **Cached.** The last good response is kept in memory and, when a cache path
  is given, on local disk, so the dashboard still renders it (marked with its
  age) while the CRM is unreachable. A failed fetch, of any kind, never
  replaces it and never raises out of ``refresh``.

Environment: ``WATCHTOWER_CRM_TERMS_URL`` (the private CRM's HTTPS terms status
URL; deployment configuration, not kept in this public repository),
``WATCHTOWER_CRM_ACCESS_CLIENT_ID`` and ``WATCHTOWER_CRM_ACCESS_CLIENT_SECRET``
(from Secret Manager). All three turn it on.
"""
from __future__ import annotations

import datetime as dt
import http.client
import json
import os
import re
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

URL_ENV = "WATCHTOWER_CRM_TERMS_URL"
CLIENT_ID_ENV = "WATCHTOWER_CRM_ACCESS_CLIENT_ID"
CLIENT_SECRET_ENV = "WATCHTOWER_CRM_ACCESS_CLIENT_SECRET"
REFRESH_SECONDS = 900
TIMEOUT_SECONDS = 10
MAX_BYTES = 1_000_000
WAITING_DAYS = 14
CENTRAL = "America/Chicago"

STAGES = {
    "not-contacted": "Not contacted", "inquiry-sent": "Inquiry sent", "awaiting-reply": "Awaiting reply",
    "in-discussion": "In discussion", "terms-received": "Terms received", "no-response": "No response",
    "decided": "Decided",
}
PURPOSES = {"watchtower-monitoring": "Watchtower monitoring", "clearparcel-minnesota": "ClearParcel Minnesota",
            "other": "Other"}
OUTCOMES = {"full": "Full", "details-and-count": "Details and count only", "none": "None",
            "hold-for-terms": "Hold for terms", "stop-requested": "Stop requested"}

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_GATE_PREFIX = "https://github.com/clearparcel/GIS-Data-Watchtower/"


class TermsStatusError(Exception):
    """The CRM could not be read; the message never carries response content."""


def _text(value, limit: int = 200) -> str | None:
    return value[:limit] if isinstance(value, str) and value else None


def _timestamp(value) -> str | None:
    """An instant with a time zone, as sent; anything else (dates, naive times) is dropped."""
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if parsed.tzinfo is not None and "T" in value else None


def _date(value) -> str | None:
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        return None
    try:
        dt.date.fromisoformat(value)
    except ValueError:
        return None
    return value


def _choice(value, allowed: dict) -> str | None:
    return value if isinstance(value, str) and value in allowed else None


def _url(value, prefix: str) -> str | None:
    return value if isinstance(value, str) and value.startswith(prefix) and len(value) <= 300 else None


def _provider(row, crm_origin: str | None) -> dict | None:
    """One provider row reduced to the allow-listed fields; None if unusable."""
    if not isinstance(row, dict) or not _text(row.get("organizationId")) or not _text(row.get("name")):
        return None
    inquiry = row.get("openInquiry")
    open_inquiry = None
    if isinstance(inquiry, dict):
        purposes = inquiry.get("purposes")
        open_inquiry = {
            "stage": _choice(inquiry.get("stage"), STAGES),
            "purposes": [p for p in purposes if _choice(p, PURPOSES)][:3] if isinstance(purposes, list) else [],
            "follow_up_due_on": _date(inquiry.get("followUpDueOn")),
            "opened_at": _timestamp(inquiry.get("openedAt")),
            "updated_at": _timestamp(inquiry.get("updatedAt")),
        }
    return {
        "organization_id": _text(row["organizationId"], 64),
        "name": _text(row["name"]),
        "organization_type": _choice(row.get("organizationType"), {"county": 1, "agency": 1}),
        "archived": row.get("archived") is True,
        "crm_url": _url(row.get("crmUrl"), f"{crm_origin}/organizations/") if crm_origin else None,
        "terms_stopped": row.get("termsStopped") is True,
        "open_inquiry": open_inquiry,
        "latest_outcome": _choice(row.get("latestOutcome"), OUTCOMES),
        "latest_decided_at": _timestamp(row.get("latestDecidedAt")),
        "watchtower_gate_url": _url(row.get("watchtowerGateUrl"), _GATE_PREFIX),
        "last_email_at": _timestamp(row.get("lastEmailAt")),
        "last_reply_at": _timestamp(row.get("lastReplyAt")),
    }


def crm_origin(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def parse_status(payload, crm_origin: str | None = None) -> dict:
    """Validate the CRM response and keep only allow-listed fields.

    Record links are kept only when they point at the CRM the status came from.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("providers"), list):
        raise TermsStatusError("CRM terms status had an unexpected shape")
    providers = [p for p in (_provider(row, crm_origin) for row in payload["providers"][:500]) if p is not None]
    return {"generated_at": _timestamp(payload.get("generatedAt")), "providers": providers}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Access answers an unauthenticated call with a redirect to sign-in; treat it as a failure."""

    def redirect_request(self, *args, **kwargs):  # noqa: D401
        return None


def fetch_status(url: str, client_id: str, client_secret: str, *, opener=None,
                 timeout: float = TIMEOUT_SECONDS) -> dict:
    """GET the CRM terms status with the Access service token; raises TermsStatusError."""
    if not url.startswith("https://") or not urllib.parse.urlsplit(url).netloc:
        raise TermsStatusError("CRM terms URL must be an HTTPS URL")
    request = urllib.request.Request(url, headers={
        "CF-Access-Client-Id": client_id, "CF-Access-Client-Secret": client_secret,
        "Accept": "application/json", "User-Agent": "GIS-Data-Watchtower/terms-status",
    })
    opener = opener or urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            content_type = response.headers.get("Content-Type", "")
            raw = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise TermsStatusError(f"CRM terms status returned HTTP {exc.code}") from None
    except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError, ValueError) as exc:
        raise TermsStatusError(f"CRM terms status unreachable ({type(exc).__name__})") from None
    if status != 200:
        raise TermsStatusError(f"CRM terms status returned HTTP {status}")
    if "json" not in content_type:
        raise TermsStatusError("CRM terms status was not JSON (is the Access token valid?)")
    if len(raw) > MAX_BYTES:
        raise TermsStatusError("CRM terms status response was too large")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise TermsStatusError("CRM terms status was not valid JSON") from None
    try:
        return parse_status(payload, crm_origin(url))
    except TermsStatusError:
        raise
    except Exception as exc:  # noqa: BLE001 - a malformed response is a failed read, never a crash
        raise TermsStatusError(f"CRM terms status could not be read ({type(exc).__name__})") from None


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class TermsCache:
    """The last good terms status, refreshed at most every ``interval`` seconds."""

    def __init__(self, fetch, *, interval: float = REFRESH_SECONDS, cache_path: Path | None = None,
                 clock=time.monotonic, now=_now):
        self._fetch = fetch
        self.interval = max(60.0, float(interval))
        self.cache_path = Path(cache_path) if cache_path else None
        self._clock = clock
        self._now = now
        self._lock = threading.Lock()
        self._last_attempt = None
        self.status: dict | None = None
        self.fetched_at: str | None = None
        self.last_error: str | None = None
        self.last_attempt_at: str | None = None
        self._load_disk()

    def _load_disk(self) -> None:
        if not self.cache_path or not self.cache_path.exists():
            return
        try:
            saved = json.loads(self.cache_path.read_text(encoding="utf-8"))
            status = saved["status"]
            if not isinstance(status, dict) or not isinstance(status.get("providers"), list):
                raise ValueError("cached terms status has an unexpected shape")
            self.status, self.fetched_at = status, _timestamp(saved.get("fetched_at"))
        except (OSError, ValueError, KeyError, TypeError):
            self.status, self.fetched_at = None, None

    def _save_disk(self) -> None:
        if not self.cache_path:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix=self.cache_path.name + ".", dir=self.cache_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"status": self.status, "fetched_at": self.fetched_at}, handle)
            os.replace(temp, self.cache_path)
        finally:
            Path(temp).unlink(missing_ok=True)

    def refresh(self) -> bool:
        """One fetch now; on failure keep the last good copy and record the error."""
        self._last_attempt = self._clock()
        self.last_attempt_at = self._now().isoformat()
        try:
            status = self._fetch()
        except TermsStatusError as exc:
            self.last_error = str(exc)
            return False
        except Exception as exc:  # noqa: BLE001 - record any failure; never the response content
            self.last_error = f"CRM terms status failed ({type(exc).__name__})"
            return False
        self.status, self.fetched_at, self.last_error = status, self.last_attempt_at, None
        try:
            self._save_disk()
        except OSError:
            pass
        return True

    def maybe_refresh(self) -> None:
        """Refresh if due; never blocks behind another refresh."""
        if self._last_attempt is not None and self._clock() - self._last_attempt < self.interval:
            return
        if not self._lock.acquire(blocking=False):
            return
        try:
            if self._last_attempt is None or self._clock() - self._last_attempt >= self.interval:
                self.refresh()
        finally:
            self._lock.release()

    def snapshot(self) -> dict:
        return {"status": self.status, "fetched_at": self.fetched_at, "last_error": self.last_error,
                "last_attempt_at": self.last_attempt_at}


def cache_from_env(environ=None, *, cache_path: Path | None = None, opener=None) -> TermsCache | None:
    """A TermsCache when the URL, client ID and secret are set; otherwise None (view shows "not connected")."""
    environ = os.environ if environ is None else environ
    url = str(environ.get(URL_ENV, "")).strip()
    client_id = str(environ.get(CLIENT_ID_ENV, "")).strip()
    secret = str(environ.get(CLIENT_SECRET_ENV, "")).strip()
    if not url or not client_id or not secret:
        return None
    return TermsCache(lambda: fetch_status(url, client_id, secret, opener=opener), cache_path=cache_path)


# --- Derived views (US Central calendar dates) -------------------------------------------

def central_date(at: dt.datetime) -> str:
    try:
        from zoneinfo import ZoneInfo
        return at.astimezone(ZoneInfo(CENTRAL)).date().isoformat()
    except Exception:  # noqa: BLE001 - tzdata missing: fall back to UTC dates
        return at.astimezone(dt.timezone.utc).date().isoformat()


def _parse(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def is_overdue(provider: dict, now: dt.datetime) -> bool:
    due = (provider.get("open_inquiry") or {}).get("follow_up_due_on")
    return bool(due and due < central_date(now))


def is_due_this_week(provider: dict, now: dt.datetime) -> bool:
    due = (provider.get("open_inquiry") or {}).get("follow_up_due_on")
    today = central_date(now)
    week_end = (dt.date.fromisoformat(today) + dt.timedelta(days=6)).isoformat()
    return bool(due and today <= due <= week_end)


def days_waiting(provider: dict, now: dt.datetime) -> int | None:
    """Calendar days since our last email when it is newer than their last reply."""
    sent, reply = provider.get("last_email_at"), provider.get("last_reply_at")
    if not provider.get("open_inquiry") or not sent:
        return None
    if reply and _parse(reply) >= _parse(sent):
        return None
    return (dt.date.fromisoformat(central_date(now)) - dt.date.fromisoformat(central_date(_parse(sent)))).days


def summarize(providers: list[dict], now: dt.datetime) -> dict:
    open_rows = [p for p in providers if not p.get("archived") and p.get("open_inquiry")]
    return {
        "open": len(open_rows),
        "overdue": sum(1 for p in open_rows if is_overdue(p, now)),
        "due_this_week": sum(1 for p in open_rows if is_due_this_week(p, now)),
        "no_follow_up": sum(1 for p in open_rows if not p["open_inquiry"].get("follow_up_due_on")),
        "waiting": sum(1 for p in open_rows if (days_waiting(p, now) or 0) >= WAITING_DAYS),
        "stopped": sum(1 for p in providers if p.get("terms_stopped")),
    }


def sort_for_attention(providers: list[dict], now: dt.datetime) -> list[dict]:
    """Overdue follow-ups first, then the soonest, then the longest wait, then name."""
    def key(p: dict):
        inquiry = p.get("open_inquiry")
        rank = 3 if not inquiry else 0 if is_overdue(p, now) else 1 if inquiry.get("follow_up_due_on") else 2
        return (rank, (inquiry or {}).get("follow_up_due_on") or "", -(days_waiting(p, now) or -1), p.get("name") or "")
    return sorted(providers, key=key)


__all__ = ["TermsCache", "TermsStatusError", "cache_from_env", "days_waiting", "fetch_status", "is_due_this_week",
           "is_overdue", "parse_status", "sort_for_attention", "summarize"]
