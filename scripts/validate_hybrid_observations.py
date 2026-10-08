"""Prepare a private candidate manifest or validate already captured snapshots."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clearparcel.datawatch.hybrid_validation import candidate_manifest, validation_receipt
from clearparcel.datawatch.watch import load_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--prepare", action="store_true")
    for name in ("cloud", "local", "aggregate", "public"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="Private receipt/manifest destination; never commit it")
    args = parser.parse_args()
    manifest = candidate_manifest(load_config(args.config))
    result = manifest
    if not args.prepare:
        active = [profile for profile, ids in manifest['expected_sources'].items() if ids]
        required = active + ['aggregate', 'public']
        if any(getattr(args, name) is None for name in required):
            parser.error("validation requires captured snapshots: " + ', '.join('--' + name for name in required))
        read = lambda path: json.loads(path.read_text(encoding="utf-8"))
        result = validation_receipt(manifest, {p: read(getattr(args, p)) for p in ("cloud", "local") if getattr(args, p)},
                                    read(args.aggregate), read(args.public))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("Prepared private candidate manifest" if args.prepare else "Receipt passed" if result["passed"] else "Receipt failed")
    return 0 if args.prepare or result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
