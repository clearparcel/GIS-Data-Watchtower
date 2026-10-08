#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$root"
install_target='.'
if [[ "${1:-}" == '--gcs' ]]; then
    install_target='.[gcs]'
    shift
fi
if (( $# )); then
    echo 'Usage: bash setup_watchtower_env.sh [--gcs]' >&2
    exit 2
fi
python_bin="${WATCHTOWER_DEV_PYTHON:-python3.13}"
"$python_bin" -c 'import sys; assert sys.version_info >= (3, 12), "Python 3.12+ required"'
node -e 'if (Number(process.versions.node.split(".")[0]) < 24) throw new Error("Node 24+ required for regression tests")'
"$python_bin" -m venv .venv-watchtower
.venv-watchtower/bin/python -m pip install --disable-pip-version-check --constraint constraints.txt -e "$install_target"
.venv-watchtower/bin/python -m pip check
.venv-watchtower/bin/python -m clearparcel.datawatch --help >/dev/null
echo "Watchtower environment ready: $root/.venv-watchtower"
echo 'Activate with: source .venv-watchtower/bin/activate'
