"""Private per-run evidence for triage and alert delivery. Disabled by default.

After a cloud-job run, ``record_run_evidence`` can append an execution receipt
(worker, execution id, start/end, process exit code and a minimized copy of the
original worker report) to a bounded private object through the existing
version-conditional storage backends. When a private delivery configuration is
also supplied it runs :func:`alert_delivery.deliver_alerts` over those receipts.

Nothing here polls a provider, changes a schedule or alters the job's exit
code. Failures are reported as one structured log line and otherwise ignored,
so evidence handling can never mask or change the provider run's outcome.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import uuid

from . import strict_json
from .alert_delivery import TRANSPORTS, AlertLedger, deliver_alerts
from .operations_triage import triage_executions
from .storage import StorageBackend, StorageConflictError

RECEIPTS_OBJECT = "runs/receipts.json"
RECEIPTS_SCHEMA_VERSION = 1
DEFAULT_KEEP = 30
MAX_RUN = timedelta(hours=12)
CLOCK_SKEW = timedelta(minutes=2)
_SOURCE_FIELDS = ("status", "checked_at", "rate_limited", "worker")


class ReceiptError(ValueError):
    """The stored receipt log is malformed; fail closed."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _time(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else None


def _plausible(row, not_after) -> tuple:
    """(start, end) for a receipt with sane times, else (None, None)."""
    s, e = _time(row.get("started_at")), _time(row.get("completed_at"))
    if s is None or e is None or s > e or e - s > MAX_RUN:
        return None, None
    if not_after is not None and e > not_after + CLOCK_SKEW:
        return None, None  # a future end would hold every later run
    return s, e


def forward_history(rows: list, not_after=None) -> list:
    """Receipts in recording order that each start after the previous one ends.

    ``not_after`` is the real clock; receipts ending after it (plus skew) or
    with implausible durations are ignored like malformed ones.
    """
    chosen, last_end = [], None
    for row in rows:  # recording order
        s, e = _plausible(row, not_after)
        if s is None:
            continue
        if last_end is not None and s <= last_end:
            continue  # overlaps or precedes a run recorded before it
        chosen.append(row)
        last_end = e
    return chosen


def select_history(rows: list, current_id: str, not_after=None) -> tuple[list, int, bool]:
    """Return ``(history, excluded, out_of_order)`` ending at ``current_id``.

    Triage refuses overlapping executions and receipts that end after the
    cutoff, and incident keys depend on which receipt opened an incident. The
    history therefore only moves forward in recording order: a receipt is used
    only if it starts after every receipt recorded before it ends. A run that
    overlaps, or was recorded after a newer run (a manual run, an extra task,
    a late append), is excluded permanently, so keys never shift.
    ``out_of_order`` reports that the current run itself is such a run;
    delivery is then held. Malformed receipts are excluded too; all exclusions
    are counted for the log line.
    """
    current = next((r for r in rows if r.get("execution_id") == current_id), None)
    start, end = _plausible(current, not_after) if current else (None, None)
    if current is None or start is None:
        return [], len(rows), False
    chosen = forward_history([r for r in rows if r is not current], not_after)
    last_end = _time(chosen[-1]["completed_at"]) if chosen else None
    out_of_order = last_end is not None and start <= last_end
    history = ([] if out_of_order else chosen) + [current]
    return history, len(rows) - len(history), out_of_order


def _incident_starts(history: list) -> dict:
    """Map execution id -> source ids whose unresolved incident it opened."""
    if not history:
        return {}
    try:
        triage = triage_executions(history, as_of=history[-1]["completed_at"])
    except ValueError:
        return {}
    starts = {}
    for event in triage["events"]:
        pair = (event["worker"], event["source_id"])
        starts.setdefault(pair, event["execution_id"])
        if event["type"] == "recovered":
            starts.pop(pair)
    by_execution = {}
    for (_, source_id), execution_id in starts.items():
        by_execution.setdefault(execution_id, set()).add(source_id)
    return by_execution


def _pin(receipt: dict, source_ids: set) -> None:
    """Reduce a retained old receipt to the sources whose incident it opened.

    Its other sources' history is gone from the window, so keeping them would
    let triage stitch unrelated old states onto recent runs.
    """
    report = receipt.get("report")
    if not isinstance(report, dict) or not isinstance(report.get("sources"), dict):
        return
    sources = {sid: row for sid, row in report["sources"].items() if sid in source_ids}
    counts = {s: sum(isinstance(r, dict) and r.get("status") == s for r in sources.values())
              for s in ("ok", "warn", "error")}
    overall = "error" if counts["error"] else "warn" if counts["warn"] else "ok"
    receipt.setdefault("original_exit_code", receipt.get("exit_code"))
    receipt["exit_code"] = {"ok": 0, "warn": 1, "error": 2}[overall]
    receipt["pinned_sources"] = sorted(sources)
    report.update({"sources": sources, "counts": counts, "overall": overall})


def minimize_report(report) -> dict | None:
    """Keep only the fields triage validates; drop URLs, diagnostics and values."""
    if not isinstance(report, dict):
        return None
    sources = report.get("sources")
    minimized_sources = None
    if isinstance(sources, dict):
        minimized_sources = {}
        for sid, source in sources.items():
            if not isinstance(source, dict):
                minimized_sources[str(sid)] = None
                continue
            row = {k: source[k] for k in _SOURCE_FIELDS if k in source}
            if source.get("deferred"):
                row["deferred"] = True
            minimized_sources[str(sid)] = row
    scope = report.get("scope")
    out = {
        "generated_at": report.get("generated_at"),
        "scope": {"type": scope.get("type")} if isinstance(scope, dict) else None,
        "overall": report.get("overall"),
        "counts": report.get("counts"),
        "sources": minimized_sources,
    }
    if isinstance(report.get("worker"), str):
        out["worker"] = report["worker"]
    return out


def build_receipt(*, worker: str, execution_id: str, started_at: str, completed_at: str,
                  exit_code: int | None, report) -> dict:
    return {"execution_id": execution_id, "worker": worker, "started_at": started_at,
            "completed_at": completed_at, "exit_code": exit_code,
            "report": minimize_report(report)}


def _validate(data) -> dict:
    if (not isinstance(data, dict) or data.get("schema_version") != RECEIPTS_SCHEMA_VERSION
            or not isinstance(data.get("executions"), list)):
        raise ReceiptError("unsupported or malformed run receipt log")
    for row in data["executions"]:
        if (not isinstance(row, dict) or not isinstance(row.get("execution_id"), str)
                or not isinstance(row.get("worker"), str)):
            raise ReceiptError("malformed run receipt")
    return data


class ReceiptLog:
    """A bounded, compare-and-swap receipt list per storage backend."""

    def __init__(self, storage: StorageBackend, name: str = RECEIPTS_OBJECT, *, keep: int = DEFAULT_KEEP):
        if type(keep) is not int or not 1 <= keep <= 365:
            raise ValueError("keep must be an integer from 1 to 365")
        self.storage, self.name, self.keep = storage, name, keep

    def read(self):
        with tempfile.TemporaryDirectory(prefix="watchtower-receipts-") as scratch:
            path = Path(scratch) / "receipts.json"
            exists, token = self.storage.download_versioned(self.name, path)
            if not exists:
                return {"schema_version": RECEIPTS_SCHEMA_VERSION, "private_evidence": True,
                        "executions": []}, None
            try:
                data = strict_json.loads(path.read_text(encoding="utf-8"))
            except ValueError as exc:
                raise ReceiptError("run receipt log is not valid JSON") from exc
        return _validate(data), token

    def append(self, receipt: dict, *, attempts: int = 8, now=None) -> bool:
        """Add one receipt. Returns False when this execution is already recorded."""
        clock = _time(now) if now is not None else _time(receipt.get("completed_at"))
        for attempt in range(attempts):
            data, token = self.read()
            identity = (receipt["worker"], receipt["execution_id"])
            if any((r["worker"], r["execution_id"]) == identity for r in data["executions"]):
                return False
            data["executions"].append(receipt)
            # Retain the newest receipts per worker, plus the receipt that opened
            # each unresolved incident so its event key stays stable.
            for worker in {r["worker"] for r in data["executions"]}:
                rows = [r for r in data["executions"] if r["worker"] == worker]
                if len(rows) <= self.keep:
                    continue
                # Protection follows the forward chain, so a late out-of-order
                # append cannot hide an unresolved incident's opening receipt.
                protected = _incident_starts(forward_history(rows, clock))
                for stale in rows[:-self.keep]:
                    pinned = protected.get(stale["execution_id"])
                    if pinned:
                        _pin(stale, pinned)
                    else:
                        data["executions"].remove(stale)
            with tempfile.TemporaryDirectory(prefix="watchtower-receipts-") as scratch:
                path = Path(scratch) / "receipts.json"
                path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")
                try:
                    self.storage.upload_if_version(self.name, path, token)
                    return True
                except StorageConflictError:
                    if attempt + 1 >= attempts:
                        raise
        return False

    def executions(self, worker: str) -> list:
        data, _ = self.read()
        return [r for r in data["executions"] if r["worker"] == worker]


def expected_sources(config: dict, profile: str | None) -> list:
    """Sources this worker is expected to report, derived from the registry.

    Disabled, other-profile and hold-for-terms sources are excluded with the
    same rules the worker uses before polling.
    """
    from .watch import _held_county_slugs, _hold_skip_reason, _profile_skip_reason
    held = _held_county_slugs()
    rows = []
    for source in config.get("sources") or []:
        sid = source.get("id")
        if not isinstance(sid, str) or not sid:
            continue
        if _profile_skip_reason(source, profile) or _hold_skip_reason(source, held):
            continue
        rows.append({"worker": profile or "unassigned", "source_id": sid})
    return rows


def _emit(stream, severity: str, payload: dict) -> None:
    try:
        stream.write(json.dumps({"severity": severity, **payload}, ensure_ascii=True,
                                allow_nan=False, separators=(",", ":")) + "\n")
        stream.flush()
    except Exception:  # noqa: BLE001 - observability must not fail the job
        pass


def _execution_id(environ) -> str:
    execution = environ.get("CLOUD_RUN_EXECUTION")
    if execution:
        # A retried task attempt is a distinct run with its own report.
        return (f"{execution}:{environ.get('CLOUD_RUN_TASK_INDEX', '0')}"
                f":{environ.get('CLOUD_RUN_TASK_ATTEMPT', '0')}")
    return "manual-" + uuid.uuid4().hex


def record_run_evidence(config: dict, *, storage: StorageBackend, profile: str | None,
                        started_at: str, completed_at: str, exit_code: int | None, report,
                        environ=None, stream=None, transports=None, keep: int = DEFAULT_KEEP,
                        now: str | None = None) -> dict:
    """Record this run's receipt and optionally deliver alerts. Never raises.

    Enabled only when ``WATCHTOWER_RUN_RECEIPTS=1``. Delivery additionally needs
    ``WATCHTOWER_ALERT_DELIVERY_CONFIG`` (private JSON with ``delivery`` and
    ``routing`` objects); its own ``enabled`` flag still defaults to false.
    """
    env = os.environ if environ is None else environ
    out = sys.stderr if stream is None else stream
    summary = {"receipts": "disabled", "delivery": "not_configured"}
    if env.get("WATCHTOWER_RUN_RECEIPTS") != "1":
        return summary
    worker = profile or "unassigned"
    clock = now or utc_now()
    try:
        log = ReceiptLog(storage, keep=keep)
        start, end = _plausible({"started_at": started_at, "completed_at": completed_at},
                                _time(clock))
        if start is None:
            summary["receipts"] = "rejected_invalid_times"
            _emit(out, "ERROR", {"message": "Watchtower run evidence refused: implausible times",
                                 "watchtower_alert_pipeline_error": {"stage": "receipt",
                                                                     "error": "invalid_times"}})
            return summary
        receipt = build_receipt(worker=worker, execution_id=_execution_id(env),
                                started_at=started_at, completed_at=completed_at,
                                exit_code=exit_code, report=report)
        summary["receipts"] = ("recorded" if log.append(receipt, now=clock)
                               else "already_recorded")
        summary["execution_id"] = receipt["execution_id"]
    except Exception as exc:  # noqa: BLE001 - never change the provider run's outcome
        summary["receipts"] = "failed"
        _emit(out, "ERROR", {"message": "Watchtower run evidence was not recorded",
                             "watchtower_alert_pipeline_error": {"stage": "receipt",
                                                                 "error": type(exc).__name__}})
        return summary

    raw = env.get("WATCHTOWER_ALERT_DELIVERY_CONFIG")
    if not raw:
        return summary
    try:
        private = strict_json.loads(raw)
        if not isinstance(private, dict):
            raise ValueError("delivery configuration must be an object")
        settings = private.get("delivery") or {}
        expected = expected_sources(config, profile)
        if not expected:
            summary["delivery"] = "no_expected_sources"
            return summary
        history, excluded, out_of_order = select_history(log.executions(worker),
                                                         summary["execution_id"], _time(clock))
        if out_of_order:
            summary["delivery"] = "held_out_of_order_run"
            _emit(out, "WARNING", {"message": "Watchtower alert delivery held: run overlaps or "
                                              "precedes a recorded run",
                                   "watchtower_alert_delivery": {"mode": "held",
                                                                 "receipts_excluded": excluded}})
            return summary
        transport = None
        if settings.get("enabled") is True:
            factory = (transports or TRANSPORTS).get(settings.get("transport"))
            if factory is None:
                raise ValueError("unsupported transport")
            transport = factory()
        result = deliver_alerts(history, expected_sources=expected,
                                routing=private.get("routing"), as_of=completed_at,
                                now=completed_at, ledger=AlertLedger(storage),
                                config=settings, transport=transport)
        summary["delivery"] = result["notification_delivery"]
        summary["mode"] = result["mode"]
        _emit(out, "INFO", {"message": "Watchtower alert delivery stage",
                            "watchtower_alert_delivery": {
                                "mode": result["mode"],
                                "delivery": result["notification_delivery"],
                                "preview_messages": result["preview_messages"],
                                "new_events": len(result["new_event_keys"]),
                                "routing_gaps": len(result["routing_gaps"]),
                                "source_evidence_gaps": len(result["source_evidence_gaps"]),
                                "receipts_excluded": excluded,
                                "needs_operator_attention": len(
                                    (result.get("ledger") or {}).get("needs_operator_attention") or [])}})
    except Exception as exc:  # noqa: BLE001 - never change the provider run's outcome
        summary["delivery"] = "failed"
        _emit(out, "ERROR", {"message": "Watchtower alert delivery stage failed",
                             "watchtower_alert_pipeline_error": {"stage": "delivery",
                                                                 "error": type(exc).__name__}})
    return summary
