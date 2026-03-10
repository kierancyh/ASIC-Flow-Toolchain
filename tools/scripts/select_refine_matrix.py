#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


def to_float(v: Any) -> Optional[float]:
    try:
        if v in (None, "", "None"):
            return None
        return float(v)
    except Exception:
        return None


def read_csv_row(path: Path) -> Optional[Dict[str, str]]:
    if not path.exists():
        return None
    with path.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows[0] if rows else None


def classify_status(row: Dict[str, str]) -> str:
    raw_status = str(row.get("status", "")).strip().upper()
    if raw_status in {"FLOW_FAIL", "INCOMPLETE"}:
        return "FLOW_FAIL"

    swns = to_float(row.get("setup_wns_ns"))
    stns = to_float(row.get("setup_tns_ns"))
    drc = to_float(row.get("drc_errors"))
    lvs = to_float(row.get("lvs_errors"))
    ant = to_float(row.get("antenna_violations"))

    timing_ok = swns is not None and stns is not None and swns >= 0.0 and stns >= 0.0
    signoff_ok = all(v in (None, 0.0) for v in (drc, lvs, ant))

    if signoff_ok and timing_ok:
        return "PASS"
    if signoff_ok and not timing_ok:
        return "TIMING_FAIL"
    if (not signoff_ok) and timing_ok:
        return "SIGNOFF_FAIL"
    return "SIGNOFF_AND_TIMING_FAIL"


def collect_rows(artifacts_root: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen: Set[Path] = set()

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
                    "status": classify_status(row),
                    "raw_status": str(row.get("status", "")).strip().upper(),
                    "path": str(csv_path),
                }
            )

    return rows


def unique_sorted_desc(values: List[float]) -> List[float]:
    return sorted(set(round(v, 6) for v in values), reverse=True)


def unique_sorted_asc(values: List[float]) -> List[float]:
    return sorted(set(round(v, 6) for v in values))


def build_between(
    lower_fail: float,
    upper_pass: float,
    step_ns: float,
    *,
    existing: Set[float],
    min_clock_ns: float,
    batch_size: int,
) -> List[float]:
    candidates: List[float] = []
    current = upper_pass - step_ns
    while current > lower_fail and len(candidates) < batch_size:
        c = round(current, 6)
        if c >= min_clock_ns and c not in existing:
            candidates.append(c)
        current -= step_ns
    return unique_sorted_desc(candidates)


def build_extend_downward(
    anchor_clock: float,
    step_ns: float,
    *,
    existing: Set[float],
    min_clock_ns: float,
    batch_size: int,
) -> List[float]:
    candidates: List[float] = []
    current = anchor_clock - step_ns
    while current >= min_clock_ns and len(candidates) < batch_size:
        c = round(current, 6)
        if c not in existing:
            candidates.append(c)
        current -= step_ns
    return unique_sorted_desc(candidates)


def build_extend_upward(
    anchor_clock: float,
    step_ns: float,
    *,
    existing: Set[float],
    max_clock_ns: float,
    batch_size: int,
) -> List[float]:
    candidates: List[float] = []
    current = anchor_clock + step_ns
    while current <= max_clock_ns and len(candidates) < batch_size:
        c = round(current, 6)
        if c not in existing:
            candidates.append(c)
        current += step_ns
    return unique_sorted_asc(candidates)


def write_output(matrix: List[float], github_output: Optional[Path], reason: str) -> None:
    payload = [int(v) if float(v).is_integer() else round(v, 6) for v in matrix]
    matrix_json = json.dumps(payload)
    print(matrix_json)
    print(f"reason={reason}")
    if github_output is not None:
        with github_output.open("a", encoding="utf-8") as f:
            print(f"matrix_json={matrix_json}", file=f)
            print(f"reason={reason}", file=f)


def main() -> None:
    ap = argparse.ArgumentParser(description="Select the next clock matrix for staged refinement.")
    ap.add_argument("--artifacts-root", type=Path, required=True)
    ap.add_argument("--mode", choices=["extend", "refine"], required=True)
    ap.add_argument("--step-ns", type=float, required=True)
    ap.add_argument("--min-clock-ns", type=float, required=True)
    ap.add_argument("--max-clock-ns", type=float, required=True)
    ap.add_argument("--tolerance-ns", type=float, required=True)
    ap.add_argument("--batch-size", type=int, default=4)
    ap.add_argument("--github-output", type=Path, default=None)
    args = ap.parse_args()

    if args.step_ns <= 0:
        raise SystemExit("--step-ns must be > 0")
    if args.batch_size <= 0:
        raise SystemExit("--batch-size must be > 0")

    rows = collect_rows(args.artifacts_root)
    if not rows:
        write_output([], args.github_output, "No metrics.csv files were found in downloaded artifacts.")
        return

    non_flow_results = [row for row in rows if row["status"] != "FLOW_FAIL"]
    if not non_flow_results:
        write_output([], args.github_output, "All discovered runs are FLOW_FAIL, so refinement stops.")
        return

    existing = {row["clock_ns"] for row in rows}
    passes = sorted(row["clock_ns"] for row in non_flow_results if row["status"] == "PASS")

    if not passes:
        highest_tested = max(row["clock_ns"] for row in non_flow_results)
        if args.mode == "refine":
            write_output([], args.github_output, "No PASS result exists yet, so a finer refine stage is not started.")
            return
        if highest_tested >= args.max_clock_ns:
            write_output([], args.github_output, "No PASS result exists and the upward clock cap is already reached.")
            return
        matrix = build_extend_upward(
            highest_tested,
            args.step_ns,
            existing=existing,
            max_clock_ns=args.max_clock_ns,
            batch_size=args.batch_size,
        )
        write_output(matrix, args.github_output, "No PASS result exists yet, so the same step is extended upward.")
        return

    lowest_pass = min(passes)
    fails_below = sorted(
        row["clock_ns"] for row in non_flow_results if row["status"] != "PASS" and row["clock_ns"] < lowest_pass
    )
    highest_fail_below_pass = max(fails_below) if fails_below else None

    if args.mode == "refine":
        if highest_fail_below_pass is None:
            write_output([], args.github_output, "A pass/fail bracket does not exist yet, so finer refinement is deferred.")
            return
        interval = lowest_pass - highest_fail_below_pass
        if interval <= args.tolerance_ns:
            write_output([], args.github_output, "The pass/fail bracket is already within tolerance, so refinement stops.")
            return
        matrix = build_between(
            highest_fail_below_pass,
            lowest_pass,
            args.step_ns,
            existing=existing,
            min_clock_ns=args.min_clock_ns,
            batch_size=args.batch_size,
        )
        write_output(matrix, args.github_output, "A pass/fail bracket exists, so a finer stage is inserted between them.")
        return

    if highest_fail_below_pass is not None:
        matrix = build_between(
            highest_fail_below_pass,
            lowest_pass,
            args.step_ns,
            existing=existing,
            min_clock_ns=args.min_clock_ns,
            batch_size=args.batch_size,
        )
        write_output(matrix, args.github_output, "A pass/fail bracket exists, so the same step continues filling that bracket.")
        return

    matrix = build_extend_downward(
        lowest_pass,
        args.step_ns,
        existing=existing,
        min_clock_ns=args.min_clock_ns,
        batch_size=args.batch_size,
    )
    if matrix:
        write_output(matrix, args.github_output, "All usable results still pass, so the same step is extended downward first.")
        return

    write_output([], args.github_output, "All usable results pass, but the minimum clock floor has already been reached.")


if __name__ == "__main__":
    main()
