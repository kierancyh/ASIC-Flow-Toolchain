#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def to_float(value: Any) -> Optional[float]:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def fmt(value: Optional[float]) -> str:
    if value is None:
        return ""
    if float(value).is_integer():
        return str(int(value))
    return str(round(value, 6))


def json_number(value: float):
    if float(value).is_integer():
        return int(value)
    return round(value, 6)


def read_csv_row(path: Path) -> Optional[Dict[str, str]]:
    if not path.exists():
        return None
    with path.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows[0] if rows else None


def signoff_clean(row: Dict[str, str]) -> bool:
    for key in ("drc_errors", "lvs_errors", "antenna_violations"):
        value = to_float(row.get(key))
        if value is not None and value != 0.0:
            return False
    return True


def timing_ok(row: Dict[str, str]) -> bool:
    setup_wns = to_float(row.get("setup_wns_ns"))
    setup_tns = to_float(row.get("setup_tns_ns"))
    return (
        setup_wns is not None
        and setup_tns is not None
        and setup_wns >= 0.0
        and setup_tns >= 0.0
    )


def classify(row: Dict[str, str]) -> str:
    clean = signoff_clean(row)
    ok = timing_ok(row)
    if clean and ok:
        return "PASS"
    if clean and not ok:
        return "TIMING_FAIL"
    if (not clean) and ok:
        return "SIGNOFF_FAIL"
    return "SIGNOFF_AND_TIMING_FAIL"


def collect_rows(artifacts_root: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen: set[Path] = set()

    patterns = [
        "**/ci_out/*/clk_*ns_*/metrics.csv",
        "**/*/clk_*ns_*/metrics.csv",
    ]

    for pattern in patterns:
        for csv_path in sorted(artifacts_root.glob(pattern)):
            if csv_path in seen:
                continue
            seen.add(csv_path)

            row = read_csv_row(csv_path)
            if not row:
                continue

            clock_ns = to_float(row.get("clock_ns"))
            if clock_ns is None:
                continue

            rows.append(
                {
                    "clock_ns": round(clock_ns, 6),
                    "status": classify(row),
                    "path": str(csv_path),
                }
            )

    return rows


def unique_desc(values: List[float]) -> List[float]:
    seen = set()
    ordered: List[float] = []
    for value in sorted(values, reverse=True):
        key = round(value, 6)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return ordered


def write_output(path: Optional[Path], payload: Dict[str, str]) -> None:
    if path is None:
        for key, value in payload.items():
            print(f"{key}={value}")
        return

    with path.open("a", encoding="utf-8") as f:
        for key, value in payload.items():
            print(f"{key}={value}", file=f)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Select the next automated refine matrix from downloaded artifacts."
    )
    ap.add_argument("--artifacts-root", required=True)
    ap.add_argument("--expand-step-ns", type=float, required=True)
    ap.add_argument("--refine-step-ns", type=float, required=True)
    ap.add_argument("--min-clock-ns", type=float, required=True)
    ap.add_argument("--max-clock-ns", type=float, required=True)
    ap.add_argument("--tolerance-ns", type=float, required=True)
    ap.add_argument("--batch-size", type=int, default=4)
    ap.add_argument("--github-output", default="")
    args = ap.parse_args()

    if args.expand_step_ns <= 0:
        raise SystemExit("--expand-step-ns must be > 0")
    if args.refine_step_ns <= 0:
        raise SystemExit("--refine-step-ns must be > 0")
    if args.min_clock_ns > args.max_clock_ns:
        raise SystemExit("--min-clock-ns must be <= --max-clock-ns")
    if args.tolerance_ns <= 0:
        raise SystemExit("--tolerance-ns must be > 0")
    if args.batch_size <= 0:
        raise SystemExit("--batch-size must be > 0")

    rows = collect_rows(Path(args.artifacts_root))
    tried = {round(row["clock_ns"], 6) for row in rows}
    passing = sorted({row["clock_ns"] for row in rows if row["status"] == "PASS"})
    failing = sorted({row["clock_ns"] for row in rows if row["status"] != "PASS"})

    lowest_pass = min(passing) if passing else None
    highest_fail_below_pass = None

    if lowest_pass is not None:
        fails_below = [value for value in failing if value < lowest_pass]
        if fails_below:
            highest_fail_below_pass = max(fails_below)

    next_clocks: List[float] = []
    done = False
    reason = ""

    if lowest_pass is None:
        reason = "No passing clocks found yet; moving upward to easier clock periods."
        top_tried = max(tried) if tried else args.min_clock_ns

        for i in range(1, args.batch_size + 1):
            candidate = round(top_tried + (i * args.expand_step_ns), 6)
            if candidate > args.max_clock_ns + 1e-9:
                break
            if candidate not in tried:
                next_clocks.append(candidate)

        if not next_clocks:
            done = True
            reason = "No passing clocks found and no larger untried clock periods remain."

    elif highest_fail_below_pass is None:
        reason = "Passes exist but no failing point below the lowest pass yet; probing downward."

        for i in range(1, args.batch_size + 1):
            candidate = round(lowest_pass - (i * args.expand_step_ns), 6)
            if candidate < args.min_clock_ns - 1e-9:
                break
            if candidate not in tried:
                next_clocks.append(candidate)

        if not next_clocks:
            done = True
            reason = "Passes exist but no lower failing point remains untried within bounds."

    else:
        bracket_width = lowest_pass - highest_fail_below_pass

        if bracket_width <= args.tolerance_ns + 1e-9:
            done = True
            reason = "Bracket width is already within tolerance."
        else:
            reason = (
                f"Refining downward from lowest pass {fmt(lowest_pass)} ns toward "
                f"highest fail below pass {fmt(highest_fail_below_pass)} ns."
            )

            cursor = round(lowest_pass - args.refine_step_ns, 6)
            while cursor > highest_fail_below_pass + 1e-9:
                if cursor >= args.min_clock_ns - 1e-9 and cursor not in tried:
                    next_clocks.append(cursor)
                if len(next_clocks) >= args.batch_size:
                    break
                cursor = round(cursor - args.refine_step_ns, 6)

            if not next_clocks:
                done = True
                reason = "Bracket exists, but no new refine points remain between pass and fail bounds."

    next_clocks = unique_desc(next_clocks)

    payload = {
        "matrix_json": json.dumps([json_number(value) for value in next_clocks]),
        "done": "true" if done else "false",
        "lowest_pass_ns": fmt(lowest_pass),
        "highest_fail_below_pass_ns": fmt(highest_fail_below_pass),
        "reason": reason,
        "run_count": str(len(rows)),
        "pass_count": str(len(passing)),
        "fail_count": str(len(failing)),
    }

    output_path = Path(args.github_output) if args.github_output else None
    write_output(output_path, payload)


if __name__ == "__main__":
    main()