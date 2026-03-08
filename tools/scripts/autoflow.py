#!/usr/bin/env python3
"""Self-hosted LibreLane auto-clock runner (v1 scaffold).

This is intentionally lightweight for v1:
- reads designs/<variant>/variant.yaml
- for mode=fixed: runs once at fixed_ns
- for mode=auto:
    - binary search between min_ns..max_ns OR sweep list
    - predicate = setup slack >= 0 AND signoff clean (heuristic: DRC/LVS/Antenna counts == 0 if present)

You will point it at your local dockerized LibreLane + $HOME/.ciel PDK root.
"""
from __future__ import annotations
import argparse, json, subprocess, time
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]

def sh(cmd, cwd=None):
    print(">", " ".join(cmd))
    return subprocess.run(cmd, cwd=cwd, check=False)

def load_yaml(p: Path):
    return yaml.safe_load(p.read_text())

def load_metrics(run_dir: Path):
    p = run_dir / "final" / "metrics.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text())

def pass_pred(metrics: dict) -> bool:
    # setup slack at nom_tt corner
    wns = metrics.get("timing__setup__wns__corner:nom_tt_025C_1v80")
    vio = metrics.get("timing__setup_vio__count__corner:nom_tt_025C_1v80") or metrics.get("timing__setup_vio__count")
    if wns is None:
        return False
    if float(wns) < 0:
        return False
    if vio is not None and float(vio) > 0:
        return False
    # signoff counts if present
    for k in ["drc__error__count", "lvs__error__count", "antenna__violations"]:
        if k in metrics and float(metrics[k]) > 0:
            return False
    return True

def run_once(design_dir: Path, cfg_json: Path, pdk_root: Path) -> Path:
    # run librelane
    sh(["python3","-m","librelane","--dockerized","--pdk-root",str(pdk_root), str(cfg_json)], cwd=design_dir)
    # newest RUN_*
    runs = sorted((design_dir/"runs").glob("RUN_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not runs:
        raise SystemExit("No runs produced")
    return runs[0]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run"])
    ap.add_argument("--variant", required=True, help="e.g. designs/crt")
    ap.add_argument("--pdk-root", default=str(Path.home()/".ciel"))
    ap.add_argument("--mode", default="auto", choices=["auto","fixed"])
    args = ap.parse_args()

    vdir = ROOT / args.variant
    v = load_yaml(vdir/"variant.yaml")
    clk = v.get("clock", {})
    port = clk.get("port","clk")
    pdk_root = Path(args.pdk_root)

    # NOTE: v1 assumes you maintain a LibreLane design dir elsewhere OR you create one in-repo.
    # Easiest migration pattern: keep your current ll_designs/<name> layout and point variant.yaml to it.
    # For v2 we can generate a full config+design dir inside the repo.
    ll_design_dir = v.get("ll_design_dir")
    cfg_json = v.get("ll_config_json")
    if not ll_design_dir or not cfg_json:
        raise SystemExit("v1 expects variant.yaml to include ll_design_dir and ll_config_json (path to your known-good config).")

    design_dir = Path(ll_design_dir).expanduser()
    cfg_json = design_dir / cfg_json

    if args.mode == "fixed" or clk.get("mode") == "fixed":
        run_dir = run_once(design_dir, cfg_json, pdk_root)
        print("run_dir=", run_dir)
        return

    # auto mode: sweep first (v1), binary search in v2
    sweep = clk.get("search", {}).get("sweep_ns") or [101.0]
    best = None
    for period in sweep:
        # TODO: patch CLOCK_PERIOD inside config JSON safely (v2)
        # v1: user provides per-period configs; or keep fixed config and only do hosted TT.
        print(f"[v1] Would run at {period}ns (TODO: implement config patching)")
    print("v1 scaffold complete")

if __name__ == "__main__":
    main()
