from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from clearparcel.datawatch.dashboard import build_static_site, serve
from clearparcel.datawatch.watch import _EXECUTION_PROFILES, _resolve_execution_profile, _safe_diagnostic, check_sources, load_config, load_history, load_state


def _default_config() -> Path | None:
    env = os.environ.get("CLEARPARCEL_WATCHTOWER_CONFIG")
    if env:
        return Path(env).expanduser()
    repository_example = Path(__file__).resolve().parents[2] / "config" / "example_sources.json"
    return repository_example if repository_example.is_file() else None


def _render(report: dict) -> str:
    counts = report.get("counts") or {}
    lines = [
        f'GIS Data Watchtower - {str(report.get("overall", "unknown")).upper()}',
        f'Checks: ok={counts.get("ok", 0)}, warn={counts.get("warn", 0)}, error={counts.get("error", 0)}',
    ]
    if report.get("error"):
        lines.append(f'Run error: {_safe_diagnostic(report["error"])}')
    for source in (report.get("sources") or {}).values():
        line = f'[{str(source.get("status", "unknown")).upper()}] {source.get("name") or source.get("id")}'
        if source.get("feature_count") is not None:
            line += f' - records={source["feature_count"]}'
        if source.get("elapsed_ms") is not None:
            line += f' - {source["elapsed_ms"]} ms'
        if source.get("error"):
            line += f' - {_safe_diagnostic(source["error"])}'
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
    p.add_argument("--source"); p.add_argument("--limit", type=int, default=50); p.add_argument("--json", action="store_true")
    p = sub.add_parser("aggregate", help="Merge a partial worker result into an authoritative state")
    p.add_argument("--base", type=Path, required=True); p.add_argument("--partial", type=Path, required=True); p.add_argument("--worker", required=True, choices=sorted(_EXECUTION_PROFILES)); p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser('worker-retire', help='Prepare an offline inactive-worker retirement snapshot')
    p.add_argument('--base', type=Path, required=True)
    p.add_argument('--worker', required=True)
    p.add_argument('--at', required=True)
    p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser("dashboard", help="Serve the private dashboard")
    p.add_argument("--host", default="127.0.0.1"); p.add_argument("--port", type=int, default=8765)
    p = sub.add_parser("public-dashboard", help="Serve the read-only sanitized public dashboard")
    p.add_argument("--host", default="0.0.0.0"); p.add_argument("--port", type=int, default=8080)
    p = sub.add_parser("public-publish", help="Publish a sanitized public aggregate to production storage")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("cloud-job", help="Run one check using configured cloud storage")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("dashboard-build", help="Build a sanitized static dashboard")
    p.add_argument("--output", type=Path, required=True); p.add_argument("--json", action="store_true")
    return parser


# Exit codes: 0 ok, 1 warnings, 2 a source (or the run's scope) reported an
# error, 3 Watchtower itself failed (bad config, storage or an unexpected
# exception). Warnings are an expected non-zero exit for scheduled runs.
EXIT_OK, EXIT_WARN, EXIT_SOURCE_ERROR, EXIT_TOOL_FAILURE = 0, 1, 2, 3


def _exit_code(result: dict) -> int:
    overall = result.get("overall")
    return EXIT_SOURCE_ERROR if overall == "error" else EXIT_WARN if overall == "warn" else EXIT_OK


def _utc_now() -> str:
    from clearparcel.datawatch.run_evidence import utc_now
    return utc_now()


def _record_run_evidence(config: dict, config_path, started_at: str, exit_code: int, report) -> None:
    """Optional private run receipt and alert stage; never changes the exit code."""
    if os.environ.get("WATCHTOWER_RUN_RECEIPTS") != "1":
        return
    try:
        from clearparcel.datawatch.cloud_job import job_profile, job_storage
        from clearparcel.datawatch.run_evidence import record_run_evidence
        record_run_evidence(config, storage=job_storage(config, config_path), profile=job_profile(),
                            started_at=started_at, completed_at=_utc_now(),
                            exit_code=exit_code, report=report)
    except Exception as exc:  # noqa: BLE001 - evidence must not mask the run outcome
        print(json.dumps({"severity": "ERROR", "message": "Watchtower run evidence stage failed",
                          "watchtower_alert_pipeline_error": {"stage": "setup",
                                                              "error": type(exc).__name__}}),
              file=sys.stderr)


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "public-dashboard":
            from clearparcel.datawatch.public_dashboard import serve_public
            serve_public(host=args.host, port=args.port); return 0
        if args.command == "public-publish":
            from clearparcel.datawatch.public_publish import publish_public_snapshot_from_env
            result = publish_public_snapshot_from_env()
            message = (f'Published {result["source_count"]} public Watchtower sources' if result["published"]
                       else 'Skipped superseded public Watchtower snapshot')
            print(json.dumps(result, indent=2) if args.json else message)
            return 0
        if args.command == 'worker-retire':
            from clearparcel.datawatch.aggregate import load_json, retire_worker, save_json
            result = retire_worker(load_json(args.base), args.worker, args.at)
            save_json(args.output, result)
            print(f'Prepared retirement snapshot for {args.worker}')
            return 0
        if args.config is None:
            raise FileNotFoundError(
                "No default Watchtower config is available in this installation. "
                "Pass --config PATH or set CLEARPARCEL_WATCHTOWER_CONFIG."
            )
        config = load_config(args.config)
        if args.command == "check":
            # Resolve once so the polled profile and the published worker agree.
            profile = _resolve_execution_profile(args.execution_profile)
            if profile and not args.no_save:
                from clearparcel.datawatch.cloud_job import require_publishable_profile
                require_publishable_profile(config, profile)
            result = check_sources(config, source_filter=args.source, save=not args.no_save, execution_profile=profile)
            if profile and not args.no_save:
                from clearparcel.datawatch.cloud_job import publish_worker_result
                publish_worker_result(config, result, profile)
            if args.source and args.json:
                result["scope"] = {"type": "source_filter", "filter": args.source, "note": "counts and active_alerts in this response cover only the checked source(s); saved state retains fleet-wide status"}
            print(json.dumps(result, indent=2) if args.json else _render(result), end="" if not args.json else "\n")
            return _exit_code(result)
        if args.command == "status":
            result = load_state(config.get("aggregate_state_file") or config["state_file"])
            print(json.dumps(result, indent=2) if args.json else _render(result), end="" if not args.json else "\n")
            return _exit_code(result)
        if args.command == "history":
            result = load_history(config, source_filter=args.source, limit=args.limit)
            if args.json: print(json.dumps(result, indent=2))
            else:
                print(f'Watchtower history: {result.get("entry_count", 0)} entries')
                for row in result.get("entries", []): print(f'{row.get("generated_at") or "-"} - {row.get("overall") or row.get("status") or "unknown"}')
            return 0
        if args.command == "aggregate":
            from clearparcel.datawatch.aggregate import load_json, merge_states, save_json
            merged = merge_states(load_json(args.base), load_json(args.partial), args.worker)
            save_json(args.output, merged); print(json.dumps(merged, indent=2)); return 0
        if args.command == "dashboard":
            serve(config, host=args.host, port=args.port); return 0
        if args.command == "cloud-job":
            from clearparcel.datawatch.cloud_job import run_cloud_job
            started_at = _utc_now()
            try:
                result = run_cloud_job(args.config)
            except Exception:
                _record_run_evidence(config, args.config, started_at, EXIT_TOOL_FAILURE, None)
                raise
            code = _exit_code(result)
            _record_run_evidence(config, args.config, started_at, code, result)
            print(json.dumps(result, indent=2) if args.json else _render(result), end="" if not args.json else "\n")
            return code
        if args.command == "dashboard-build":
            result = build_static_site(config, args.output)
            print(json.dumps(result, indent=2) if args.json else f'Watchtower static dashboard: {result["output_dir"]}'); return 0
        return EXIT_TOOL_FAILURE
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"ERROR: {_safe_diagnostic(type(exc).__name__ + ': ' + str(exc))}", file=sys.stderr); return EXIT_TOOL_FAILURE


if __name__ == "__main__":
    raise SystemExit(main())
