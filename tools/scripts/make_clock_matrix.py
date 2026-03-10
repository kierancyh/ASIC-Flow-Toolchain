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
        description="Generate the initial coarse auto-sweep clock matrix."
    )
    ap.add_argument("--start-clock-ns", type=float, required=True)
    ap.add_argument("--min-clock-ns", type=float, required=True)
    ap.add_argument("--max-clock-ns", type=float, required=True)
    ap.add_argument("--step-ns", type=float, required=True)
    args = ap.parse_args()

    start_clock = float(args.start_clock_ns)
    min_clock = float(args.min_clock_ns)
    max_clock = float(args.max_clock_ns)
    step = float(args.step_ns)

    if step <= 0:
        raise SystemExit("--step-ns must be > 0")
    if min_clock > max_clock:
        raise SystemExit("--min-clock-ns must be <= --max-clock-ns")

    values = set()
    k = 0

    while True:
        added = False

        upper = start_clock + (k * step)
        lower = start_clock - (k * step)

        if min_clock <= upper <= max_clock:
            values.add(round(upper, 6))
            added = True

        if min_clock <= lower <= max_clock:
            values.add(round(lower, 6))
            added = True

        if not added and upper > max_clock and lower < min_clock:
            break

        k += 1

    ordered: List[float] = sorted(values, reverse=True)
    print(json.dumps([format_json_number(v) for v in ordered]))


if __name__ == "__main__":
    main()