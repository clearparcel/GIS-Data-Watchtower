"""Hosted private dashboard: the repository's dashboard server, read-only, on Cloud Run.

This replaces the out-of-repo hosted wrapper. It serves the ordinary private
dashboard (same routes, security headers, CSP and connection limits as
``watchtower dashboard``) with three differences:

- **Read-only.** No refresh form, every POST returns 405, and no provider is
  ever contacted.
- **Synced state.** The unified aggregate and the cloud worker's history
  (``history.jsonl`` and its rotated ``history.jsonl.1``) are read from
  Watchtower storage, at most every ``WATCHTOWER_PRIVATE_SYNC_SECONDS`` (30 by
  default), on request and in the background. A failed sync keeps serving the
  last good copy; the first sync must succeed or the server does not start.
- **Upstream authentication.** Identity-Aware Proxy enforced on the Cloud Run
  service authenticates every request, so the server binds all interfaces
  without Basic auth. That trust is accepted only inside a Cloud Run service.

Environment: ``WATCHTOWER_GCS_BUCKET`` (required), ``WATCHTOWER_GCS_PREFIX``,
``WATCHTOWER_AGGREGATE_OBJECT`` (default ``aggregate-state.json``),
``WATCHTOWER_CONFIG`` (default ``/secrets/data_sources.json``), ``PORT``
(default 8080) and ``WATCHTOWER_PRIVATE_SYNC_SECONDS``. The Provider terms view
also reads ``WATCHTOWER_CRM_ACCESS_CLIENT_ID`` and
``WATCHTOWER_CRM_ACCESS_CLIENT_SECRET`` (see ``provider_terms``).
"""
from __future__ import annotations

import os
import tempfile
import threading
import time
from pathlib import Path

HISTORY_OBJECT = "history.jsonl"
HISTORY_ARCHIVE_OBJECT = "history.jsonl.1"  # read by the history loader beside history.jsonl
DEFAULT_SYNC_SECONDS = 30


class StateSync:
    """Copy hosted objects to local files, rate-limited and thread-safe.

    Each object is downloaded to a temporary file and moved into place, so a
    reader never sees a partial file and a failed download never replaces the
    last good copy.
    """

    def __init__(self, storage, objects: dict[str, Path], *, interval: float = DEFAULT_SYNC_SECONDS,
                 required: tuple[str, ...] = (), clock=time.monotonic):
        self.storage = storage
        self.objects = dict(objects)
        self.interval = max(1.0, float(interval))
        self.required = tuple(required)
        self._clock = clock
        self._lock = threading.Lock()
        self._last = None

    def sync(self) -> dict[str, bool]:
        """Copy every object; the interval restarts even when a copy fails.

        Restarting on failure keeps an outage (or a missing permission) from
        turning every request into another storage read.
        """
        try:
            return self._sync_all()
        finally:
            self._last = self._clock()

    def _sync_all(self) -> dict[str, bool]:
        results = {}
        for name, destination in self.objects.items():
            destination.parent.mkdir(parents=True, exist_ok=True)
            fd, temp = tempfile.mkstemp(prefix=destination.name + ".", dir=destination.parent)
            os.close(fd)
            temp_path = Path(temp)
            try:
                found = self.storage.download(name, temp_path)
                if found:
                    os.replace(temp_path, destination)
                elif name in self.required:
                    raise FileNotFoundError(f"required hosted object not found: {name}")
                results[name] = bool(found)
            finally:
                temp_path.unlink(missing_ok=True)
        return results

    def maybe_sync(self) -> None:
        """Sync if the interval has passed; never blocks behind another sync."""
        if self._last is not None and self._clock() - self._last < self.interval:
            return
        if not self._lock.acquire(blocking=False):
            return
        try:
            if self._last is None or self._clock() - self._last >= self.interval:
                self.sync()
        finally:
            self._lock.release()


def _sync_seconds(environ) -> float:
    try:
        value = float(environ.get("WATCHTOWER_PRIVATE_SYNC_SECONDS", DEFAULT_SYNC_SECONDS))
    except (TypeError, ValueError):
        return DEFAULT_SYNC_SECONDS
    return min(max(value, 5.0), 3600.0)


def prepare_private_dashboard(environ=None, *, storage=None, workdir: Path | None = None):
    """Build (config, StateSync, port) from the environment; performs the first sync."""
    from clearparcel.datawatch.watch import load_config
    environ = os.environ if environ is None else environ
    bucket = str(environ.get("WATCHTOWER_GCS_BUCKET", "")).strip()
    if storage is None:
        if not bucket:
            raise RuntimeError("WATCHTOWER_GCS_BUCKET is required")
        from clearparcel.datawatch.storage import GCSStorage
        storage = GCSStorage(bucket, str(environ.get("WATCHTOWER_GCS_PREFIX", "")))
    aggregate_object = str(environ.get("WATCHTOWER_AGGREGATE_OBJECT", "aggregate-state.json")).strip()
    root = Path(workdir) if workdir is not None else Path(tempfile.mkdtemp(prefix="watchtower-private-"))
    aggregate_path = root / "aggregate-state.json"
    history_path = root / HISTORY_OBJECT
    sync = StateSync(storage, {aggregate_object: aggregate_path, HISTORY_OBJECT: history_path,
                               HISTORY_ARCHIVE_OBJECT: root / HISTORY_ARCHIVE_OBJECT},
                     interval=_sync_seconds(environ), required=(aggregate_object,))
    sync.sync()
    config = load_config(Path(environ.get("WATCHTOWER_CONFIG", "/secrets/data_sources.json")))
    config["aggregate_state_file"] = str(aggregate_path)
    config["history_file"] = str(history_path)
    # Never let a registry path point the hosted server at another local state file.
    config["state_file"] = str(root / "unused-state.json")
    # CRM terms status (#185): read-only, cached locally, refreshed in the background.
    from clearparcel.datawatch.provider_terms import cache_from_env
    config["_terms_cache"] = cache_from_env(environ, cache_path=root / "provider-terms.json")
    port = int(environ.get("PORT", "8080"))
    return config, sync, port


def serve_private_from_env() -> None:
    from clearparcel.datawatch.dashboard import serve
    config, sync, port = prepare_private_dashboard()

    def background():
        while True:
            time.sleep(sync.interval)
            try:
                sync.maybe_sync()
            except Exception:  # noqa: BLE001 - keep serving the last good copy
                pass

    threading.Thread(target=background, name="watchtower-private-sync", daemon=True).start()
    terms = config.get("_terms_cache")
    if terms is not None:
        def terms_background():
            # The CRM is fetched off the request path, so a slow or down CRM never delays a page.
            while True:
                try:
                    terms.maybe_refresh()
                except Exception:  # noqa: BLE001 - keep the last good copy
                    pass
                time.sleep(60)

        threading.Thread(target=terms_background, name="watchtower-terms-sync", daemon=True).start()
    serve(config, host="0.0.0.0", port=port, read_only=True, before_request=sync.maybe_sync,
          trusted_frontend="cloud-run-iap")


__all__ = ["StateSync", "prepare_private_dashboard", "serve_private_from_env"]
