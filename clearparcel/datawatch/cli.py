from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from clearparcel.datawatch.dashboard import build_static_site, serve
from clearparcel.datawatch.watch import check_sources, load_config, load_history, load_state


def _default_config() -> Path:
    env = __import__("os").environ.get("CLEARPARCEL_WATCHTOWER_CONFIG")
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parents[2] / "config" / "example_sources.json"


def _render(report: dict) -> str:
    counts = report.get("counts") or {}
    lines = [
        f'GIS Data Watchtower - {str(report.get("overall", "unknown")).upper()}',
        f'Checks: ok={counts.get("ok", 0)}, warn={counts.get("warn", 0)}, error={counts.get("error", 0)}',
    ]
    for source in (report.get("sources") or {}).values():
        line = f'[{str(source.get("status", "unknown")).upper()}] {source.get("name") or source.get("id")}'
        if source.get("feature_count") is not None:
            line += f' - records={source["feature_count"]}'
        if source.get("elapsed_ms") is not None:
            line += f' - {source["elapsed_ms"]} ms'
        if source.get("error"):
            line += f' - {source["error"]}'
        lines.append(line)
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="watchtower", description="GIS Data Watchtower")
    parser.add_argument("--config", type=Path, default=_default_config())
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("check", help="Check GIS data sources")
    p.add_argument("--source")
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-save", action="store_true")
    p.add_argument("--execution-profile", choices=["cloud","local","any"])

    p = sub.add_parser("status", help="Show the latest saved state")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("history", help="Show bounded check history")
    p.add_argument("--source")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("dashboard", help="Serve the private dashboard")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)

    p = sub.add_parser("cloud-job", help="Run one check using configured cloud storage")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("dashboard-build", help="Build a sanitized static dashboard")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        config = load_config(args.config)
        if args.command == "check":
            result = check_sources(config, source_filter=args.source, save=not args.no_save, execution_profile=args.execution_profile)
            if args.source and args.json:
                result["scope"] = {"type": "source_filter", "filter": args.source, "note": "counts and active_alerts in this response cover only the checked source(s); saved state retains fleet-wide status"}
            print(json.dumps(result, indent=2) if args.json else _render(result), end="" if not args.json else "\n")
            return 2 if result.get("overall") == "error" else 1 if result.get("overall") == "warn" else 0
        if args.command == "status":
            result = load_state(config["state_file"])
            print(json.dumps(result, indent=2) if args.json else _render(result), end="" if not args.json else "\n")
            return 2 if result.get("overall") == "error" else 1 if result.get("overall") == "warn" else 0
        if args.command == "history":
            result = load_history(config, source_filter=args.source, limit=args.limit)
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(f'Watchtower history: {result.get("entry_count", 0)} entries')
                for row in result.get("entries", []):
                    print(f'{row.get("generated_at") or "-"} - {row.get("overall") or row.get("status") or "unknown"}')
            return 0
        if args.command == "dashboard":
            serve(config, host=args.host, port=args.port)
            return 0
        if args.command == "cloud-job":
            from clearparcel.datawatch.cloud_job import run_cloud_job
            result = run_cloud_job(args.config)
            print(json.dumps(result, indent=2) if args.json else _render(result), end="" if not args.json else "\n")
            return 2 if result.get("overall") == "error" else 1 if result.get("overall") == "warn" else 0
        if args.command == "dashboard-build":
            result = build_static_site(config, args.output)
            print(json.dumps(result, indent=2) if args.json else f'Watchtower static dashboard: {result["output_dir"]}')
            return 0
        return 2
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
