"""Rehearse synthetic aggregate restore and concurrent writes in temporary local storage."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clearparcel.datawatch.restore_rehearsal import run_rehearsal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New receipt file; existing files are preserved")
    args = parser.parse_args()
    try:
        result = run_rehearsal()
        with args.output.open("x", encoding="utf-8") as output:
            json.dump(result, output, indent=2, allow_nan=False)
            output.write("\n")
    except Exception as exc:
        print(f"Synthetic rehearsal failed ({type(exc).__name__}); completion is not confirmed.", file=sys.stderr)
        return 2
    print("Synthetic local restore/CAS rehearsal passed. Production and GCS remain unverified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
