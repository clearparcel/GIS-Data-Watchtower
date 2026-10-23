"""Dashboard history uses exact source identity and one history read per render."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from clearparcel.datawatch import dashboard, watch
from clearparcel.datawatch.watch import load_history, load_history_index


def _run(day: int, sources: dict, *, wall_ms: int | None = None) -> dict:
    run = {"generated_at": f"2026-10-{day:02}T10:00:00+00:00", "overall": "ok",
           "counts": {"ok": len(sources), "warn": 0, "error": 0}, "sources": sources}
    if wall_ms is not None:
        run["telemetry"] = {"wall_ms": wall_ms}
    return run


def _src(status: str, count: int, *, name: str = "", changes=None) -> dict:
    return {"name": name, "status": status, "feature_count": count, "changes": changes or []}


class HistoryIdentityTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.history = self.root / "history.jsonl"
        # Rotated file first, then the active file; partial reports interleave.
        rotated = [
            _run(1, {"feed": _src("ok", 100, name="Feed"), "feed-extra": _src("error", 200, name="Feed extra")}),
            _run(2, {"feed-extra": _src("error", 201, name="Feed extra")}),
        ]
        active = [
            _run(3, {"feed": _src("ok", 101, name="Feed", changes=[{"type": "feature_count"}])}, wall_ms=1500),
            _run(4, {"other": _src("warn", 5, name="Mentions feed in its name"),
                     "feed-extra": _src("error", 202, name="Feed extra")}),
            _run(5, {"feed": _src("ok", 102, name="Feed"), "other": _src("ok", 6, name="Mentions feed in its name")},
                 wall_ms=900),
        ]
        (self.root / "history.jsonl.1").write_text("".join(json.dumps(r) + "\n" for r in rotated), encoding="utf-8")
        self.history.write_text("".join(json.dumps(r) + "\n" for r in active) + "not json\n", encoding="utf-8")
        self.config = {"history_file": str(self.history)}

    def tearDown(self):
        self._tmp.cleanup()

    def test_exact_filter_excludes_overlapping_ids_and_names(self):
        exact = load_history(self.config, source_filter="feed", exact=True, limit=60)["entries"]
        self.assertEqual([e["source"] for e in exact], ["feed", "feed", "feed"])
        self.assertEqual([e["feature_count"] for e in exact], [100, 101, 102])
        self.assertEqual({e["status"] for e in exact}, {"ok"})

    def test_cli_fuzzy_search_is_unchanged(self):
        fuzzy = load_history(self.config, source_filter="feed", limit=60)["entries"]
        self.assertEqual({e["source"] for e in fuzzy}, {"feed", "feed-extra", "other"})

    def test_index_matches_per_source_loads_and_run_history(self):
        runs, by_source = load_history_index(self.config, ["feed", "feed-extra", "other", "absent"], limit=2)
        self.assertEqual(runs, load_history(self.config, limit=2)["entries"])
        for sid in ("feed", "feed-extra", "other", "absent"):
            self.assertEqual(by_source[sid],
                             load_history(self.config, source_filter=sid, exact=True, limit=2)["entries"], sid)
        self.assertEqual([e["feature_count"] for e in by_source["feed"]], [101, 102])
        self.assertEqual(by_source["absent"], [])

    def test_source_metrics_stay_source_specific(self):
        _, by_source = load_history_index(self.config, ["feed"], limit=60)
        stats = dashboard._history_stats(by_source["feed"])
        self.assertEqual(stats["success_rate"], 100.0)
        self.assertEqual(stats["consecutive_ok"], 3)
        self.assertEqual(stats["last_change"], "2026-10-03T10:00:00+00:00")

    def _state(self) -> Path:
        state = self.root / "state.json"
        state.write_text(json.dumps({"schema_version": 2, "generated_at": "2026-10-05T10:00:00+00:00",
                                     "overall": "error", "counts": {"ok": 1, "warn": 0, "error": 1},
                                     "sources": {"feed": {"id": "feed", "name": "Feed", "status": "ok",
                                                          "feature_count": 103},
                                                 "feed-extra": {"id": "feed-extra", "name": "Feed extra",
                                                                "status": "error", "feature_count": 203}}}),
                         encoding="utf-8")
        return state

    def test_overview_reads_history_once_and_shows_exact_metrics(self):
        config = {**self.config, "state_file": str(self._state()), "sources": []}
        real = watch._history_rows
        with patch.object(watch, "_history_rows", side_effect=real) as reads:
            page = dashboard.render_dashboard(config)
        self.assertEqual(reads.call_count, 1)
        # feed: prior comparable count is 101 (not feed-extra's 202), 100% reliable.
        row = page.split('data-name="feed"', 1)[1].split("</tr>", 1)[0]
        self.assertIn(">+2<", row)
        self.assertIn("100.0%", row)
        self.assertIn("3 consecutive", row)
        extra = page.split('data-name="feed extra"', 1)[1].split("</tr>", 1)[0]
        self.assertIn(">+2<", extra)
        self.assertIn(">0.0%<", extra)

    def test_source_page_history_is_exact(self):
        config = {**self.config, "state_file": str(self._state()), "sources": []}
        page = dashboard.render_source(config, "feed")
        for other in (">200<", ">201<", ">202<"):
            self.assertNotIn(other, page)
        for own in (">100<", ">101<", ">102<"):
            self.assertIn(own, page)
        self.assertIn(">100.0%", page)

    def test_large_history_render_is_one_pass(self):
        sources = {f"src-{i:02}": _src("ok", i) for i in range(33)}
        with self.history.open("w", encoding="utf-8") as fh:
            for day in range(1, 29):
                for _ in range(50):
                    fh.write(json.dumps(_run(day, sources)) + "\n")
        state = self.root / "state.json"
        state.write_text(json.dumps({"schema_version": 2, "overall": "ok", "counts": {"ok": 33},
                                     "sources": {sid: {"id": sid, "name": sid, "status": "ok"} for sid in sources}}),
                         encoding="utf-8")
        config = {**self.config, "state_file": str(state), "sources": []}
        real = watch._history_rows
        started = time.perf_counter()
        with patch.object(watch, "_history_rows", side_effect=real) as reads:
            dashboard.render_dashboard(config)
        elapsed = time.perf_counter() - started
        self.assertEqual(reads.call_count, 1)
        # Deterministic work count above; timing is informational only.
        self.assertLess(elapsed, 60)


if __name__ == "__main__":
    unittest.main()
