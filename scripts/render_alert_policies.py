"""Render the provider-run alert policies into a private folder; never apply them.

The output holds deployment identifiers (project, job names, notification
channel), so it must stay outside this public repository. Apply each file with
``gcloud monitoring policies create --policy-from-file=<file>`` only after the
owner approves the exact policies (see docs/provider-run-alerting-proposal.md).
"""
import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from clearparcel.datawatch.alert_policies import build_policies  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-job", required=True, help="Cloud Run job name of the provider run")
    parser.add_argument("--publisher-job", required=True, help="Cloud Run job name of the public publisher")
    parser.add_argument("--digest-job", help="Cloud Run job name that runs weekly-digest (default: the provider job)")
    parser.add_argument("--channel", required=True,
                        help="projects/<project>/notificationChannels/<id> of the existing alert channel")
    parser.add_argument("--output-dir", type=Path, required=True, help="New private folder outside the repo")
    args = parser.parse_args(argv)
    try:
        policies = build_policies(provider_job=args.provider_job, publisher_job=args.publisher_job,
                                  channel=args.channel, digest_job=args.digest_job)
        out = args.output_dir.resolve()
        if out == REPO or REPO in out.parents:
            raise ValueError("output folder must be outside the public repository")
        out.mkdir(parents=True, exist_ok=True)
        written = []
        for stem, policy in policies.items():
            path = out / f"{stem}.json"
            with path.open("x", encoding="utf-8") as handle:
                json.dump(policy, handle, indent=2, allow_nan=False)
                handle.write("\n")
            written.append(path)
    except (OSError, ValueError) as exc:
        print(f"Render failed: {exc}", file=sys.stderr)
        return 2
    print("Rendered policies (not applied):")
    for path in written:
        print(f"  gcloud monitoring policies create --policy-from-file={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
