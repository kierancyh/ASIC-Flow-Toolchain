#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, Optional


def load_json(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def first(metrics: Dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in metrics and metrics[k] not in (None, ""):
            return metrics[k]
    return None


def parse_openroad_power_rpt(p: Path) -> Optional[Dict[str, float]]:
    lines = p.read_text(errors="ignore").splitlines()
    for line in lines:
        s = line.strip()
        if s.startswith("Total"):
            parts = s.split()
            if len(parts) >= 5:
                try:
                    return {
                        "internal_W": float(parts[1]),
                        "switching_W": float(parts[2]),
                        "leakage_W": float(parts[3]),
                        "total_W": float(parts[4]),
                    }
                except Exception:
                    return None
    return None


def status_from_row(row: Dict[str, Any]) -> str:
    drc = row.get("drc_errors")
    lvs = row.get("lvs_errors")
    ant = row.get("antenna_violations")
    swns = row.get("setup_wns_ns")
    stns = row.get("setup_tns_ns")

    def nonneg(x: Any) -> bool:
        try:
            return float(x) >= 0.0
        except Exception:
            return False

    def zero_or_missing(x: Any) -> bool:
        if x in (None, "", "None"):
            return True
        try:
            return float(x) == 0.0
        except Exception:
            return False

    clean_signoff = zero_or_missing(drc) and zero_or_missing(lvs) and zero_or_missing(ant)
    timing_ok = nonneg(swns) and nonneg(stns)

    if clean_signoff and timing_ok:
        return "PASS"
    if clean_signoff:
        return "SIGNOFF_CLEAN_TIMING_FAIL"
    return "INCOMPLETE"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path, help="Run folder containing final/metrics.json")
    ap.add_argument("--out", type=Path, required=True, help="Output directory")
    ap.add_argument("--clock-ns", type=float, default=None, help="Requested clock period from workflow")
    args = ap.parse_args()

    run = args.run
    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    metrics_path = run / "final" / "metrics.json"
    power_rpt = run / "power" / "power.rpt"
    fair_rpt = run / "power" / "power_fair_sta.rpt"

    metrics: Dict[str, Any] = {}
    if metrics_path.exists():
        metrics = load_json(metrics_path)

    clock_from_metrics = first(
        metrics,
        "clock__period",
        "clock__period__corner:nom_tt_025C_1v80",
    )

    drc_klayout = first(metrics, "klayout__drc_error__count")
    drc_magic = first(metrics, "magic__drc_error__count")
    antenna_nets = first(metrics, "antenna__violating__nets")
    antenna_pins = first(metrics, "antenna__violating__pins")

    row: Dict[str, Any] = {
        "clock_ns": args.clock_ns if args.clock_ns is not None else clock_from_metrics,
        "clock_ns_reported": clock_from_metrics,
        "setup_wns_ns": first(
            metrics,
            "timing__setup__wns__corner:nom_tt_025C_1v80",
            "timing__setup__wns",
        ),
        "setup_tns_ns": first(
            metrics,
            "timing__setup__tns__corner:nom_tt_025C_1v80",
            "timing__setup__tns",
        ),
        "hold_wns_ns": first(
            metrics,
            "timing__hold__wns__corner:nom_tt_025C_1v80",
            "timing__hold__wns",
        ),
        "hold_tns_ns": first(
            metrics,
            "timing__hold__tns__corner:nom_tt_025C_1v80",
            "timing__hold__tns",
        ),
        "core_area_um2": first(metrics, "design__core__area", "floorplan__core__area"),
        "die_area_um2": first(metrics, "design__die__area", "floorplan__die__area"),
        "instance_count": first(metrics, "design__instance__count"),
        "utilization_pct": first(
            metrics,
            "design__instance__utilization",
            "design__utilization",
            "floorplan__utilization",
        ),
        "wire_length_um": first(
            metrics,
            "route__wirelength",
            "detailedroute__wirelength",
            "globalroute__wirelength",
        ),
        "vias_count": first(
            metrics,
            "route__vias",
            "detailedroute__via__count",
            "globalroute__via__count",
        ),
        "drc_errors": first(metrics, "klayout__drc_error__count", "magic__drc_error__count"),
        "drc_errors_klayout": drc_klayout,
        "drc_errors_magic": drc_magic,
        "lvs_errors": first(metrics, "design__lvs_error__count", "netgen__lvs_error__count"),
        "antenna_violations": first(metrics, "antenna__violating__nets", "antenna__violating__pins"),
        "antenna_violating_nets": antenna_nets,
        "antenna_violating_pins": antenna_pins,
        "ir_drop_worst_V": first(metrics, "ir__drop__worst"),
    }

    p = parse_openroad_power_rpt(power_rpt) if power_rpt.exists() else None
    if p:
        row["power_total_W"] = p["total_W"]
        row["power_internal_W"] = p["internal_W"]
        row["power_switching_W"] = p["switching_W"]
        row["power_leakage_W"] = p["leakage_W"]
        row["power_source"] = str(power_rpt)
    else:
        row["power_total_W"] = first(metrics, "power__total")
        row["power_internal_W"] = None
        row["power_switching_W"] = None
        row["power_leakage_W"] = None
        row["power_source"] = "metrics.json" if metrics else None

    row["power_fair_sta_rpt"] = str(fair_rpt) if fair_rpt.exists() else None
    row["status"] = status_from_row(row)

    field_order = [
        "clock_ns",
        "clock_ns_reported",
        "setup_wns_ns",
        "setup_tns_ns",
        "hold_wns_ns",
        "hold_tns_ns",
        "core_area_um2",
        "die_area_um2",
        "instance_count",
        "utilization_pct",
        "wire_length_um",
        "vias_count",
        "power_total_W",
        "power_internal_W",
        "power_switching_W",
        "power_leakage_W",
        "power_source",
        "drc_errors",
        "drc_errors_klayout",
        "drc_errors_magic",
        "lvs_errors",
        "antenna_violations",
        "antenna_violating_nets",
        "antenna_violating_pins",
        "ir_drop_worst_V",
        "power_fair_sta_rpt",
        "status",
    ]

    csv_path = out / "metrics.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=field_order)
        w.writeheader()
        w.writerow({k: row.get(k) for k in field_order})

    def fmt(v: Any) -> str:
        return "" if v is None else str(v)

    md_lines = [
        "| " + " | ".join(field_order) + " |",
        "|" + "|".join(["---"] * len(field_order)) + "|",
        "| " + " | ".join(fmt(row.get(k)) for k in field_order) + " |",
        "",
    ]
    (out / "metrics.md").write_text("\n".join(md_lines), encoding="utf-8")

    prov = [
        f"run={run}",
        f"metrics={metrics_path if metrics_path.exists() else '(missing)'}",
        f"power_rpt={power_rpt if power_rpt.exists() else '(missing)'}",
        f"fair_sta={fair_rpt if fair_rpt.exists() else '(none)'}",
        f"clock_ns_requested={args.clock_ns}",
    ]
    (out / "provenance.txt").write_text("\n".join(prov) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()