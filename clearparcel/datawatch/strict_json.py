"""JSON parsing that never produces NaN or Infinity.

Python's json module accepts ``NaN``/``Infinity`` and turns ``1e400`` into
``inf``; Watchtower writes standard JSON (``allow_nan=False``). Non-finite
numbers are read as ``None`` — a missing observation, never zero — so a
provider quirk or an older state file cannot make later writes fail.
"""
from __future__ import annotations

import json
import math


def _missing(_constant: str) -> None:
    return None


def _finite_float(text: str) -> float | None:
    value = float(text)
    return value if math.isfinite(value) else None


def loads(text: str):
    return json.loads(text, parse_constant=_missing, parse_float=_finite_float)
