#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from typing import List


def format_json_number(value: float):
    if float(value).is_integer():
        return int(value)
    return round(value, 6)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Generate a full coarse sweep matrix from the minimum floor to the maximum cap at a fixed step."
    )
    ap.add_argument("--min-clock-ns", type=float, required=True)
    ap.add_argument("--max-clock-ns", type=float, required=True)
    ap.add_argument("--step-ns", type=float, required=True)
    ap.add_argument("--coarse-steps", type=int, required=False, default=0, help="Accepted for compatibility; not used in full-span coarse mode.")
    args = ap.parse_args()

    min_clock = max(0.0, float(args.min_clock_ns))
    max_clock = float(args.max_clock_ns)
    step = float(args.step_ns)

    if max_clock < min_clock:
        raise SystemExit("--max-clock-ns must be >= --min-clock-ns")
    if step <= 0:
        raise SystemExit("--step-ns must be > 0")

    values: List[float] = []
    current = round(min_clock, 6)
    max_rounded = round(max_clock, 6)

    while current <= max_rounded:
        values.append(current)
        current = round(current + step, 6)

    if not values or values[-1] != max_rounded:
        values.append(max_rounded)

    seen = set()
    ordered: List[float] = []
    for value in values:
        key = round(value, 6)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(key)

    print(json.dumps([format_json_number(v) for v in ordered]))


if __name__ == "__main__":
    main()
