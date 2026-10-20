"""Alert delivery ledger operations. Disabled configurations never send."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clearparcel.datawatch import strict_json
from clearparcel.datawatch.alert_delivery import (
    DEFAULT_LEDGER_NAME, TRANSPORTS, AlertLedger, LedgerError, acknowledge,
    deliver_alerts, ledger_status, normalize_config, reconcile)
from clearparcel.datawatch.storage import LocalStorage, StorageConflictError, backend_from_env



def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _ledger(args):
    if os.environ.get("WATCHTOWER_STORAGE", "local").strip().lower() == "local":
        if not args.ledger_root:
            raise ValueError("--ledger-root is required for local ledger storage")
        # Use the named directory exactly; never fall back to another root.
        return AlertLedger(LocalStorage(args.ledger_root), args.ledger_name)
    return AlertLedger(backend_from_env("."), args.ledger_name)


def _write(path, payload):
    with path.open("x", encoding="utf-8") as output:
        json.dump(payload, output, indent=2, allow_nan=False)
        output.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger-root", help="Private local ledger directory (local storage)")
    parser.add_argument("--ledger-name", default=DEFAULT_LEDGER_NAME)
    commands = parser.add_subparsers(dest="command", required=True)

    deliver = commands.add_parser("deliver", help="Queue current alerts; send only when enabled")
    deliver.add_argument("--input", type=Path, required=True,
                         help="Private object containing executions, expected_sources and routing")
    deliver.add_argument("--config", type=Path,
                         help="Private delivery configuration; omitted means disabled")
    deliver.add_argument("--output", type=Path, required=True, help="New private receipt file")
    deliver.add_argument("--as-of", required=True)

    ack = commands.add_parser("acknowledge", help="Record operator acknowledgement")
    ack.add_argument("--event-key", action="append", required=True)
    ack.add_argument("--by", required=True)

    fix = commands.add_parser("reconcile", help="Resolve an ambiguous or exhausted record")
    fix.add_argument("--event-key", required=True)
    fix.add_argument("--resolution", choices=("sent", "requeue", "abandon"), required=True)
    fix.add_argument("--by", required=True)

    commands.add_parser("status", help="Summarize ledger states")
    args = parser.parse_args()
    try:
        ledger = _ledger(args)
        if args.command == "deliver":
            data = strict_json.loads(args.input.read_text(encoding="utf-8-sig"))
            if not isinstance(data, dict):
                raise ValueError("input must be an object")
            config = (strict_json.loads(args.config.read_text(encoding="utf-8-sig"))
                      if args.config else None)
            settings = normalize_config(config)
            transport = None
            if settings["enabled"]:
                factory = TRANSPORTS.get(settings["transport"])
                if factory is None:
                    raise ValueError("unsupported transport")
                transport = factory()
            if args.output.exists():
                raise ValueError("receipt output must not exist")
            result = deliver_alerts(
                data.get("executions"), expected_sources=data.get("expected_sources"),
                routing=data.get("routing"), as_of=args.as_of, now=_now(),
                config=config, transport=transport, ledger=ledger)
            _write(args.output, result)
            print(f"Private receipt written; mode {result['mode']}, "
                  f"delivery {result['notification_delivery']}.", file=sys.stderr)
            attention = (result["routing_gaps"] or result["source_evidence_gaps"]
                         or result["notification_delivery"] in ("ambiguous", "rejected",
                                                                "blocked_routing_incomplete",
                                                                "blocked_transport_backoff")
                         or result.get("ledger", {}).get("needs_operator_attention"))
            return 1 if attention else 0
        if args.command == "acknowledge":
            result = acknowledge(ledger, args.event_key, by=args.by, at=_now())
        elif args.command == "reconcile":
            result = reconcile(ledger, args.event_key, resolution=args.resolution,
                               by=args.by, at=_now())
        else:
            result = ledger_status(ledger)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, TypeError, RuntimeError, ArithmeticError,
            StorageConflictError) as exc:
        detail = str(exc) if isinstance(exc, (LedgerError, ValueError)) else type(exc).__name__
        print(f"Alert delivery failed: {detail}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
