"""Create a private offline receipt from operator-correlated execution/report evidence."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clearparcel.datawatch.operations_triage import triage_executions
from clearparcel.datawatch import strict_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Private JSON executions list")
    parser.add_argument("--output", required=True, type=Path, help="New private receipt; never commit")
    parser.add_argument("--as-of", required=True, help="Explicit timezone-aware evidence cutoff")
    parser.add_argument("--max-age-hours", type=float, default=36)
    args = parser.parse_args()
    try:
        result = triage_executions(
            strict_json.loads(args.input.read_text(encoding="utf-8-sig")),
            as_of=args.as_of, max_age_hours=args.max_age_hours)
        # Exclusive creation preserves input evidence and any earlier receipt.
        with args.output.open("x", encoding="utf-8") as output:
            json.dump(result, output, indent=2, allow_nan=False)
            output.write("\n")
    except (OSError, ValueError, TypeError) as exc:
        print(f"Triage failed: {type(exc).__name__}; check local input/output.", file=sys.stderr)
        return 2
    print("Private offline receipt written; notifications not attempted.")
    return 0 if result["evidence_complete"] and not result["unresolved_sources"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
