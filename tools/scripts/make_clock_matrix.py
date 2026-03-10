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
        description="Generate the initial coarse auto-sweep clock matrix centered on the baseline and capped at 0."
    )
    ap.add_argument("--start-clock-ns", type=float, required=True)
    ap.add_argument("--min-clock-ns", type=float, required=True)
    ap.add_argument("--max-clock-ns", type=float, required=True)
    ap.add_argument("--step-ns", type=float, required=True)
    args = ap.parse_args()

    start_clock = float(args.start_clock_ns)
    min_clock = max(0.0, float(args.min_clock_ns))
    max_clock = float(args.max_clock_ns)
    step = float(args.step_ns)

    if step <= 0:
        raise SystemExit("--step-ns must be > 0")
    if min_clock > max_clock:
        raise SystemExit("--min-clock-ns must be <= --max-clock-ns")

    ordered: List[float] = []
    seen = set()

    def add(value: float) -> None:
        key = round(value, 6)
        if key in seen:
            return
        if min_clock <= key <= max_clock:
            seen.add(key)
            ordered.append(key)

    k = 0
    while True:
        added_any = False

        if k == 0:
            if min_clock <= start_clock <= max_clock:
                add(start_clock)
                added_any = True
        else:
            down = start_clock - (k * step)
            up = start_clock + (k * step)

            if down < min_clock:
                down = min_clock

            if min_clock <= down <= max_clock:
                before = len(ordered)
                add(down)
                added_any = added_any or (len(ordered) > before)

            if min_clock <= up <= max_clock:
                before = len(ordered)
                add(up)
                added_any = added_any or (len(ordered) > before)

        lower_edge = start_clock - (k * step)
        upper_edge = start_clock + (k * step)

        if not added_any and lower_edge < min_clock and upper_edge > max_clock:
            break

        if min_clock in seen and upper_edge > max_clock:
            break

        k += 1

    print(json.dumps([format_json_number(v) for v in ordered]))


if __name__ == "__main__":
    main()