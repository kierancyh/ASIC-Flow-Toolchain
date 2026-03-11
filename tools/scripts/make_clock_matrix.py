#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from typing import List, Optional


def format_json_number(value: float):
    if float(value).is_integer():
        return int(value)
    return round(value, 6)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Generate a coarse auto-sweep matrix centered on the baseline with a limited number of step levels."
    )
    ap.add_argument("--start-clock-ns", type=float, required=True)
    ap.add_argument("--min-clock-ns", type=float, required=True)
    ap.add_argument("--max-clock-ns", type=float, default=None)
    ap.add_argument("--step-ns", type=float, required=True)
    ap.add_argument("--coarse-steps", type=int, required=True)
    args = ap.parse_args()

    start_clock = float(args.start_clock_ns)
    min_clock = max(0.0, float(args.min_clock_ns))
    max_clock: Optional[float] = float(args.max_clock_ns) if args.max_clock_ns is not None else None
    step = float(args.step_ns)
    coarse_steps = int(args.coarse_steps)

    if max_clock is not None and max_clock < min_clock:
        raise SystemExit("--max-clock-ns must be >= --min-clock-ns")
    if step <= 0:
        raise SystemExit("--step-ns must be > 0")
    if coarse_steps < 0:
        raise SystemExit("--coarse-steps must be >= 0")

    ordered: List[float] = []
    seen = set()

    def add(value: float) -> None:
        key = round(value, 6)
        if key in seen:
            return
        if key < min_clock:
            return
        if max_clock is not None and key > round(max_clock, 6):
            return
        seen.add(key)
        ordered.append(key)

    add(start_clock)

    for k in range(1, coarse_steps + 1):
        down = start_clock - (k * step)
        up = start_clock + (k * step)

        if down < min_clock:
            down = min_clock
        if max_clock is not None and up > max_clock:
            up = max_clock

        add(down)
        add(up)

    print(json.dumps([format_json_number(v) for v in ordered]))


if __name__ == "__main__":
    main()