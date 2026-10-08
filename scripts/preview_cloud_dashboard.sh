#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
if (( $# )); then
    echo 'Usage: bash scripts/preview_cloud_dashboard.sh' >&2
    exit 2
fi
fixture="$root/datawatch/cloud-development"
if [[ ! -f "$fixture/objects/aggregate-state.json" ]]; then
    echo 'First run: python scripts/prepare_cloud_development.py' >&2
    exit 2
fi
export WATCHTOWER_STORAGE=local
export WATCHTOWER_STORAGE_ROOT="$fixture/objects"
export WATCHTOWER_PUBLIC_WORKDIR="$fixture/cache"
export WATCHTOWER_AGGREGATE_OBJECT=aggregate-state.json
# Prevent inherited operational configuration from changing the synthetic view.
unset CLEARPARCEL_WATCHTOWER_ROOT CLEARPARCEL_WATCHTOWER_STATE_FILE
unset CLEARPARCEL_WATCHTOWER_AGGREGATE_STATE_FILE CLEARPARCEL_WATCHTOWER_HISTORY_FILE
unset WATCHTOWER_GCS_BUCKET WATCHTOWER_GCS_PREFIX
unset WATCHTOWER_POSTHOG_PROJECT_TOKEN WATCHTOWER_POSTHOG_IP_DISCARD_CONFIRMED
unset WATCHTOWER_POSTHOG_HOST WATCHTOWER_POSTHOG_SCRIPT_URL
export WATCHTOWER_WORKER_STALE_MINUTES=1560
export WATCHTOWER_SOURCE_STALE_MINUTES=1560
exec .venv-watchtower/bin/python -m clearparcel.datawatch public-dashboard --host 127.0.0.1 --port 8080
