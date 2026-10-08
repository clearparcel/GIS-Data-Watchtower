"""Create synthetic local dashboard data without reading operational configuration."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path


def prepare(output: Path, *, now: dt.datetime | None = None) -> Path:
    now = now or dt.datetime.now(dt.timezone.utc)
    current = now.isoformat()
    old = (now - dt.timedelta(days=3)).isoformat()
    output = output.resolve()
    # Fail closed instead of overwriting an existing development or private tree.
    output.mkdir(parents=True, exist_ok=False)
    objects = output / "objects"
    objects.mkdir()
    sources = {}
    for source_id, worker, status, timestamp, count in (
        ("synthetic-cloud", "cloud", "ok", current, 120),
        ("synthetic-local", "local", "ok", old, 75),
        ("synthetic-warning", "cloud", "warn", current, 0),
    ):
        sources[source_id] = {
            "id": source_id, "name": f"Synthetic development: {source_id}",
            "provider": "Invented development provider", "category": "Parcels",
            "worker": worker, "status": status, "feature_count": count,
            "checked_at": timestamp, "last_report_at": timestamp,
            "last_success_at": timestamp, "field_count": 4,
        }
    state = {
        "schema_version": 3, "generated_at": current,
        "public_published_at": current, "overall": "warn",
        "counts": {"ok": 2, "warn": 1, "error": 0}, "sources": sources,
        "workers": {
            "cloud": {"last_report_at": current, "last_success_at": current,
                      "overall": "warn", "source_count": 2},
            "local": {"last_report_at": old, "last_success_at": old,
                      "overall": "ok", "source_count": 1},
        },
    }
    aggregate = objects / "aggregate-state.json"
    aggregate.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    config = {
        "sources": [], "state_file": str(aggregate),
        "aggregate_state_file": str(aggregate),
        "history_file": str(output / "history.jsonl"),
        "alerts_file": str(output / "alerts.json"),
        "alerts_text_file": str(output / "alerts.txt"),
        "public_dashboard": {"internet_exposure": False},
    }
    (output / "history.jsonl").write_text("", encoding="utf-8")
    (output / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "datawatch/cloud-development")
    args = parser.parse_args()
    try:
        output = prepare(args.output)
    except FileExistsError:
        parser.exit(2, "Refusing to overwrite existing fixture directory; choose a new --output.\n")
    print(f"Synthetic Watchtower fixture ready: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
