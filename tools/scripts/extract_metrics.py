#!/usr/bin/env python3
"""Extract dissertation-friendly tables from a run directory.

Inputs (expected):
  - final/metrics.json
  - power/power.rpt (OpenROAD report_power, prefer post-PnR nom_tt_025C_1v80)
  - power/power_fair_sta.rpt (optional)

Outputs:
  - metrics.csv
  - metrics.md
  - provenance.txt (paths used)

This script is intentionally close to your local extract_ll_metrics/compare_ll_metrics behavior.
"""
from __future__ import annotations
import argparse, json, re
from pathlib import Path
from typing import Optional, Dict, Any

SCI = re.compile(r"[-+]?\d+\.\d+e[+-]\d+")

def load_json(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text())

def parse_openroad_power_rpt(p: Path) -> Optional[Dict[str,float]]:
    lines = p.read_text(errors="ignore").splitlines()
    for line in lines:
        if line.strip().startswith("Total"):
            parts = line.split()
            if len(parts) >= 5:
                return {
                    "internal_W": float(parts[1]),
                    "switching_W": float(parts[2]),
                    "leakage_W": float(parts[3]),
                    "total_W": float(parts[4]),
                }
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path, help="Run folder containing final/metrics.json")
    ap.add_argument("--out", type=Path, default=Path("out"), help="Output folder")
    args = ap.parse_args()

    run = args.run
    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    metrics_path = run / "final" / "metrics.json"
    metrics = load_json(metrics_path) if metrics_path.exists() else {}
    # pick key fields (nom_tt corner preferred)
    def g(k): return metrics.get(k)

    row = {
      "clock_ns": g("clock__period") or g("clock__period__corner:nom_tt_025C_1v80"),
      "setup_wns_ns": g("timing__setup__wns__corner:nom_tt_025C_1v80") or g("timing__setup__wns"),
      "setup_tns_ns": g("timing__setup__tns__corner:nom_tt_025C_1v80") or g("timing__setup__tns"),
      "core_area_um2": g("design__core__area") or g("floorplan__core__area"),
      "die_area_um2": g("design__die__area") or g("floorplan__die__area"),
      "instance_count": g("design__instance__count"),
      "utilization": g("design__utilization") or g("floorplan__utilization"),
    }

    # power (post-pnr report first, else metrics.json power__total)
    power_rpt = run / "power" / "power.rpt"
    p = parse_openroad_power_rpt(power_rpt) if power_rpt.exists() else None
    if p:
        row.update({"power_total_W": p["total_W"], "power_internal_W": p["internal_W"], "power_switching_W": p["switching_W"], "power_leakage_W": p["leakage_W"]})
        row["power_source"] = str(power_rpt)
    else:
        row["power_total_W"] = g("power__total")
        row["power_source"] = "metrics.json"

    fair = run / "power" / "power_fair_sta.rpt"
    row["power_fair_sta_W"] = None
    if fair.exists():
        # keep as raw text path; you can extend parsing later
        row["power_fair_sta_rpt"] = str(fair)

    # write CSV/MD
    import pandas as pd
    df = pd.DataFrame([row])
    df.to_csv(out / "metrics.csv", index=False)
    try:
        (out / "metrics.md").write_text(df.to_markdown(index=False, floatfmt=".6g")+"\n")
    except Exception:
        (out / "metrics.md").write_text(df.to_csv(index=False)+"\n")

    prov = [f"run={run}", f"metrics={metrics_path if metrics_path.exists() else '(missing)'}", f"power_rpt={power_rpt if power_rpt.exists() else '(missing)'}", f"fair_sta={fair if fair.exists() else '(none)'}"]
    (out / "provenance.txt").write_text("\n".join(prov)+"\n")

if __name__ == "__main__":
    main()
