"""Produce a private offline parcel-monitoring evidence receipt; never poll or activate."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clearparcel.datawatch.monitoring_authority import reconciliation_receipt
from clearparcel.datawatch.parcel_access import load_parcel_access


def _read(path):
    # Ambiguous keys must not silently replace a hold/revocation with a grant.
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON field")
            result[key] = value
        return result
    # Reject nonstandard non-finite JSON, including overflowed numeric exponents.
    def reject(_value):
        raise ValueError("non-finite JSON")
    result = json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=reject,
                        object_pairs_hook=unique)
    json.dumps(result, allow_nan=False)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--approvals", type=Path, help="Private reviewed records; absent means none")
    parser.add_argument("--cadences", type=Path, help="Private combined cadence evidence; absent means none")
    parser.add_argument("--as-of", required=True, help="YYYY-MM-DD evidence evaluation date")
    parser.add_argument("--output", required=True, type=Path, help="New private receipt; never commit")
    args = parser.parse_args()
    try:
        registry = _read(args.registry)
        if not isinstance(registry, dict) or not isinstance(registry.get("sources"), list):
            raise ValueError("registry requires sources")
        research_by_name = load_parcel_access()
        counties = _read(Path(__file__).resolve().parents[1] /
                         "clearparcel/datawatch/minnesota_counties.json")["counties"]
        research = {c["slug"]: research_by_name[c["name"]] for c in counties}
        result = reconciliation_receipt(
            registry["sources"], research,
            _read(args.approvals) if args.approvals else [],
            _read(args.cadences) if args.cadences else [], as_of=args.as_of)
        with args.output.open("x", encoding="utf-8") as output:
            json.dump(result, output, indent=2, allow_nan=False)
            output.write("\n")
    except (OSError, ValueError, TypeError, KeyError):
        print("Reconciliation failed; check private input/output.", file=sys.stderr)
        return 2
    print("Private evidence receipt written; no monitoring permission granted.")
    return 0 if result["reconciliation_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
