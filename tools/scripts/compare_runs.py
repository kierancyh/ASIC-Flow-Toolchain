#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


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
    if signoff_clean(row) and timing_ok(row):
        return "PASS"
    if signoff_clean(row):
        return "SIGNOFF_CLEAN_TIMING_FAIL"
    return "INCOMPLETE"


def best_sort_key(row: Dict[str, str]):
    clean = signoff_clean(row)
    timing = timing_ok(row)
    clk = to_float(row.get("clock_ns"))
    swns = to_float(row.get("setup_wns_ns"))
    stns = to_float(row.get("setup_tns_ns"))

    return (
        0 if clean and timing else 1,
        0 if clean else 1,
        clk if clk is not None else 1e12,
        -(swns if swns is not None else -1e12),
        -(stns if stns is not None else -1e12),
    )


def collect_rows(artifacts_root: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []

    for csv_path in sorted(artifacts_root.glob("**/metrics.csv")):
        row = read_csv_row(csv_path)
        if not row:
            continue

        rel = csv_path.relative_to(artifacts_root)
        parts = rel.parts

        artifact_name = parts[0] if len(parts) > 0 else ""
        variant = parts[2] if len(parts) > 2 else ""
        run_dir = parts[3] if len(parts) > 3 else ""

        row["_artifact"] = artifact_name
        row["_variant"] = variant
        row["_run_dir"] = run_dir
        row["_metrics_csv"] = str(rel)

        base_dir = csv_path.parent
        row["_viewer"] = str((base_dir / "viewer.html").relative_to(artifacts_root)) if (base_dir / "viewer.html").exists() else ""
        row["_metrics_raw"] = str((base_dir / "metrics_raw.json").relative_to(artifacts_root)) if (base_dir / "metrics_raw.json").exists() else ""
        row["_gds_dir"] = str((base_dir / "final" / "gds").relative_to(artifacts_root)) if (base_dir / "final" / "gds").exists() else ""
        row["status"] = classify_status(row)

        rows.append(row)

    return rows


def write_summary_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    fieldnames = [
        "_variant",
        "_run_dir",
        "_artifact",
        "clock_ns",
        "setup_wns_ns",
        "setup_tns_ns",
        "hold_wns_ns",
        "hold_tns_ns",
        "core_area_um2",
        "die_area_um2",
        "instance_count",
        "utilization_pct",
        "power_total_W",
        "drc_errors",
        "lvs_errors",
        "antenna_violations",
        "status",
        "_viewer",
        "_metrics_csv",
        "_metrics_raw",
        "_gds_dir",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def write_summary_md(path: Path, rows: List[Dict[str, str]]) -> None:
    lines: List[str] = []
    lines.append("## Best run")
    lines.append("")

    if rows:
        best = sorted(rows, key=best_sort_key)[0]
        lines.append("| Variant | Run | Clock (ns) | Setup WNS | Setup TNS | DRC | LVS | Antenna | Status | Artifact |")
        lines.append("|---|---|---:|---:|---:|---:|---:|---:|---|---|")
        lines.append(
            f"| {best.get('_variant','')} | {best.get('_run_dir','')} | "
            f"{best.get('clock_ns','')} | {best.get('setup_wns_ns','')} | {best.get('setup_tns_ns','')} | "
            f"{best.get('drc_errors','')} | {best.get('lvs_errors','')} | {best.get('antenna_violations','')} | "
            f"{best.get('status','')} | {best.get('_artifact','')} |"
        )
    else:
        lines.append("No runs collected.")
    lines.append("")

    lines.append("## All runs")
    lines.append("")
    lines.append("| Variant | Run | Clock (ns) | Setup WNS | Setup TNS | Hold WNS | Core Area | Die Area | Inst | Util (%) | Power (W) | DRC | LVS | Antenna | Status | Artifact |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|")

    for row in sorted(rows, key=best_sort_key):
        lines.append(
            f"| {row.get('_variant','')} | {row.get('_run_dir','')} | "
            f"{row.get('clock_ns','')} | {row.get('setup_wns_ns','')} | {row.get('setup_tns_ns','')} | "
            f"{row.get('hold_wns_ns','')} | {row.get('core_area_um2','')} | {row.get('die_area_um2','')} | "
            f"{row.get('instance_count','')} | {row.get('utilization_pct','')} | {row.get('power_total_W','')} | "
            f"{row.get('drc_errors','')} | {row.get('lvs_errors','')} | {row.get('antenna_violations','')} | "
            f"{row.get('status','')} | {row.get('_artifact','')} |"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_best_json(path: Path, rows: List[Dict[str, str]]) -> None:
    best = sorted(rows, key=best_sort_key)[0] if rows else {}
    path.write_text(json.dumps(best, indent=2), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifacts-root", type=Path, required=True)
    ap.add_argument("--summary-md", type=Path, required=True)
    ap.add_argument("--summary-csv", type=Path, required=True)
    ap.add_argument("--best-json", type=Path, required=True)
    args = ap.parse_args()

    rows = collect_rows(args.artifacts_root)
    write_summary_csv(args.summary_csv, rows)
    write_summary_md(args.summary_md, rows)
    write_best_json(args.best_json, rows)


if __name__ == "__main__":
    main()