#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def to_float(value: Any) -> Optional[float]:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def fmt_num(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return str(round(value, 6))


def read_csv_row(path: Path) -> Optional[Dict[str, str]]:
    if not path.exists():
        return None
    with path.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows[0] if rows else None


def signoff_clean(row: Dict[str, str]) -> bool:
    for key in ("drc_errors", "lvs_errors", "antenna_violations"):
        v = to_float(row.get(key))
        if v is not None and v != 0.0:
            return False
    return True


def timing_ok(row: Dict[str, str]) -> bool:
    swns = to_float(row.get("setup_wns_ns"))
    stns = to_float(row.get("setup_tns_ns"))
    return swns is not None and stns is not None and swns >= 0.0 and stns >= 0.0


def classify_status(row: Dict[str, str]) -> str:
    raw_status = str(row.get("status", "")).strip().upper()
    if raw_status in {"FLOW_FAIL", "INCOMPLETE"}:
        return "FLOW_FAIL"

    swns = to_float(row.get("setup_wns_ns"))
    stns = to_float(row.get("setup_tns_ns"))
    if swns is None or stns is None:
        return "FLOW_FAIL"

    if signoff_clean(row) and timing_ok(row):
        return "PASS"
    return "USABLE_FAIL"


def status_rank(status: str) -> int:
    if status == "PASS":
        return 0
    if status == "USABLE_FAIL":
        return 1
    return 2


def collect_by_clock(artifacts_root: Path) -> Dict[float, str]:
    best_by_clock: Dict[float, str] = {}

    for csv_path in sorted(artifacts_root.glob("**/metrics.csv")):
        row = read_csv_row(csv_path)
        if not row:
            continue

        clock_ns = to_float(row.get("clock_ns"))
        if clock_ns is None:
            continue

        status = classify_status(row)
        key = round(clock_ns, 6)
        current = best_by_clock.get(key)
        if current is None or status_rank(status) < status_rank(current):
            best_by_clock[key] = status

    return best_by_clock


def compute_bracket(best_by_clock: Dict[float, str]) -> Tuple[Optional[float], Optional[float], str]:
    pass_clocks = sorted(clock for clock, status in best_by_clock.items() if status == "PASS")
    if not pass_clocks:
        return None, None, "NONE"

    upper_pass = min(pass_clocks)

    usable_fails = sorted(
        clock for clock, status in best_by_clock.items()
        if status == "USABLE_FAIL" and clock < upper_pass
    )
    if usable_fails:
        return upper_pass, max(usable_fails), "USABLE_FAIL"

    flow_fails = sorted(
        clock for clock, status in best_by_clock.items()
        if status == "FLOW_FAIL" and clock < upper_pass
    )
    if flow_fails:
        return upper_pass, max(flow_fails), "FLOW_FAIL"

    return upper_pass, None, "NONE"


def build_downward_matrix(
    upper_pass: float,
    lower_fail: float,
    step_ns: float,
    best_by_clock: Dict[float, str],
) -> List[float]:
    tested = {round(clock, 6) for clock in best_by_clock.keys()}
    values: List[float] = []
    candidate = round(upper_pass - step_ns, 6)

    while candidate > round(lower_fail, 6):
        if candidate not in tested:
            values.append(candidate)
        candidate = round(candidate - step_ns, 6)

    return values


def write_outputs(
    github_output: Path,
    *,
    upper_pass: Optional[float],
    lower_fail: Optional[float],
    lower_fail_kind: str,
    matrix: List[float],
    reason: str,
) -> None:
    payload = [
        int(v) if float(v).is_integer() else round(v, 6)
        for v in matrix
    ]

    with github_output.open("a", encoding="utf-8") as f:
        print(f"upper_pass_clock_ns={fmt_num(upper_pass) if upper_pass is not None else ''}", file=f)
        print(f"lower_fail_clock_ns={fmt_num(lower_fail) if lower_fail is not None else ''}", file=f)
        print(f"lower_fail_kind={lower_fail_kind}", file=f)
        print(f"matrix_json={json.dumps(payload)}", file=f)
        print(f"reason={reason}", file=f)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Select the current fastest PASS and highest FAIL-below-PASS bracket from downloaded artifacts."
    )
    ap.add_argument("--artifacts-root", type=Path, required=True)
    ap.add_argument("--next-step-ns", type=float, default=None, help="If provided, emit a downward matrix between the bracket endpoints.")
    ap.add_argument("--github-output", type=Path, required=True)
    args = ap.parse_args()

    best_by_clock = collect_by_clock(args.artifacts_root)
    if not best_by_clock:
        raise SystemExit("No metrics.csv files with a valid clock_ns were found under the artifacts root.")

    upper_pass, lower_fail, lower_fail_kind = compute_bracket(best_by_clock)

    if upper_pass is None:
        raise SystemExit("No PASS result was found. The sweep has no usable upper pass anchor.")

    if lower_fail is None:
        raise SystemExit(
            f"No failing point was found below the fastest PASS {fmt_num(upper_pass)} ns. "
            f"Increase the coarse reach or lower the floor."
        )

    matrix: List[float] = []
    if args.next_step_ns is not None:
        if args.next_step_ns <= 0:
            raise SystemExit("--next-step-ns must be > 0 when provided")
        matrix = build_downward_matrix(upper_pass, lower_fail, args.next_step_ns, best_by_clock)

    reason = (
        f"Using upper_pass={fmt_num(upper_pass)} ns and lower_fail={fmt_num(lower_fail)} ns "
        f"({lower_fail_kind}) from collected results."
    )

    write_outputs(
        args.github_output,
        upper_pass=upper_pass,
        lower_fail=lower_fail,
        lower_fail_kind=lower_fail_kind,
        matrix=matrix,
        reason=reason,
    )


if __name__ == "__main__":
    main()