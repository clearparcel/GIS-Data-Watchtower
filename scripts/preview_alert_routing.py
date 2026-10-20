"""Write a private offline alert preview; never deliver or enable notifications."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clearparcel.datawatch import strict_json
from clearparcel.datawatch.alert_routing import prepare_alert_preview


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True,
                        help="Private object containing executions, expected_sources and routing")
    parser.add_argument("--output", type=Path, required=True, help="New private preview file")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--max-age-hours", type=float, default=36)
    args = parser.parse_args()
    try:
        data = strict_json.loads(args.input.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            raise ValueError("input must be an object")
        result = prepare_alert_preview(
            data.get("executions"), expected_sources=data.get("expected_sources"),
            routing=data.get("routing"), as_of=args.as_of,
            max_age_hours=args.max_age_hours)
        with args.output.open("x", encoding="utf-8") as output:
            json.dump(result, output, indent=2, allow_nan=False)
            output.write("\n")
    except (OSError, ValueError, TypeError) as exc:
        print(f"Preview failed: {type(exc).__name__}; check private input/output.", file=sys.stderr)
        return 2
    print("Private offline preview written; no notifications sent or enabled.")
    return 1 if (result["routing_gaps"] or result["source_evidence_gaps"]
                 or not result["input_evidence_complete"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
