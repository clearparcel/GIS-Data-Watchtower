"""Replay an already sanitized public snapshot locally without provider access."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from clearparcel.datawatch.aggregate import _parse_time, save_json
from clearparcel.datawatch.public_projection import sanitize_public_render_state
from clearparcel.datawatch.public_publish import validate_public_state
from scripts.prepare_cloud_development import prepare


def prepare_snapshot(source: Path, output: Path) -> Path:
    """Create a new offline fixture, preserving all accepted observation clocks."""
    with source.open('rb') as handle:
        raw = handle.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError('public snapshot exceeds 8 MiB')
    state = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(state, dict) or not isinstance(state.get('sources'), dict):
        raise ValueError('public snapshot must contain a source map')
    validate_public_state(state)
    public = sanitize_public_render_state(state)
    if not public['sources'] or _parse_time(public.get('generated_at')) is None:
        raise ValueError('public snapshot requires sources and a valid observation clock')
    # Preparation supplies empty polling configuration and local paths only.
    # Replace synthetic observations without renewing any imported timestamp.
    output = prepare(output)
    save_json(output / 'objects/aggregate-state.json', public)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        output = prepare_snapshot(args.input, args.output)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(2, f'Public snapshot replay refused: {exc}\n')
    print(f'Offline public snapshot fixture ready: {output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
