#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def sh(cmd: List[str], cwd: Optional[Path] = None, env: Optional[Dict[str, str]] = None) -> None:
    print(">", " ".join(cmd))
    rc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env, check=False)
    if rc.returncode != 0:
        raise SystemExit(rc.returncode)


def resolve_variant(value: str) -> str:
    manifest = load_yaml(ROOT / "manifest.yaml")
    experiments = manifest.get("experiments", [])

    if value:
      for exp in experiments:
        variant = exp.get("variant", "")
        if variant.replace("/", "_") == value:
            return value
      return value

    enabled = [exp.get("variant", "").replace("/", "_") for exp in experiments if exp.get("enabled", True)]
    if not enabled:
        raise SystemExit("No enabled variants found in manifest.yaml")
    return enabled[0]


def safe_variant_to_path(safe_variant: str) -> Path:
    manifest = load_yaml(ROOT / "manifest.yaml")
    for exp in manifest.get("experiments", []):
        variant = exp.get("variant", "")
        if variant.replace("/", "_") == safe_variant:
            return ROOT / variant
    raise SystemExit(f"Cannot map safe variant '{safe_variant}' to designs/<x>")


def latest_run_dir(since_ts: float) -> Path:
    candidates: List[Tuple[float, Path]] = []
    runs_dir = ROOT / "runs"
    if not runs_dir.exists():
        raise SystemExit("No runs/ directory found after OpenLane invocation")

    for metrics in runs_dir.glob("**/final/metrics.json"):
        try:
            mtime = metrics.stat().st_mtime
        except OSError:
            continue
        if mtime >= since_ts - 1.0:
            candidates.append((mtime, metrics.parent.parent))

    if not candidates:
        all_candidates = []
        for metrics in runs_dir.glob("**/final/metrics.json"):
            try:
                all_candidates.append((metrics.stat().st_mtime, metrics.parent.parent))
            except OSError:
                pass
        if not all_candidates:
            raise SystemExit("No runs/**/final/metrics.json found")
        candidates = all_candidates

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def read_csv_row(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    with path.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows[0] if rows else {}


def to_float(v: Any) -> Optional[float]:
    try:
        if v in (None, "", "None"):
            return None
        return float(v)
    except Exception:
        return None


def classify_status(row: Dict[str, str]) -> Tuple[str, str]:
    reasons: List[str] = []

    swns = to_float(row.get("setup_wns_ns"))
    stns = to_float(row.get("setup_tns_ns"))
    drc = to_float(row.get("drc_errors"))
    lvs = to_float(row.get("lvs_errors"))
    ant = to_float(row.get("antenna_violations"))

    timing_ok = swns is not None and stns is not None and swns >= 0.0 and stns >= 0.0
    signoff_ok = all(v in (None, 0.0) for v in (drc, lvs, ant))

    if drc not in (None, 0.0):
        reasons.append(f"DRC={int(drc) if drc.is_integer() else drc}")
    if lvs not in (None, 0.0):
        reasons.append(f"LVS={int(lvs) if lvs.is_integer() else lvs}")
    if ant not in (None, 0.0):
        reasons.append(f"Antenna={int(ant) if ant.is_integer() else ant}")
    if swns is None or swns < 0.0:
        reasons.append(f"setup WNS={swns}")
    if stns is None or stns < 0.0:
        reasons.append(f"setup TNS={stns}")

    if signoff_ok and timing_ok:
        return "PASS", "Clean signoff and non-negative setup timing."
    if signoff_ok and not timing_ok:
        return "TIMING_FAIL", "; ".join(reasons) if reasons else "Timing failed."
    if (not signoff_ok) and timing_ok:
        return "SIGNOFF_FAIL", "; ".join(reasons) if reasons else "Signoff failed."
    return "SIGNOFF_AND_TIMING_FAIL", "; ".join(reasons) if reasons else "Timing and signoff failed."


def clock_label(clock_ns: float) -> str:
    if float(clock_ns).is_integer():
        return str(int(clock_ns))
    return str(clock_ns).replace(".", "p")


def append_summary(summary_path: Optional[Path], line: str) -> None:
    if not summary_path:
        return
    with summary_path.open("a", encoding="utf-8") as f:
        f.write(line)
        if not line.endswith("\n"):
            f.write("\n")


def write_history_files(out_root: Path, history: List[Dict[str, Any]]) -> None:
    out_root.mkdir(parents=True, exist_ok=True)

    with (out_root / "autoflow_history.json").open("w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

    fieldnames = [
        "attempt",
        "clock_ns",
        "status",
        "selection_reason",
        "setup_wns_ns",
        "setup_tns_ns",
        "hold_wns_ns",
        "hold_tns_ns",
        "drc_errors",
        "lvs_errors",
        "antenna_violations",
        "attempt_dir",
    ]
    with (out_root / "autoflow_history.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in history:
            w.writerow({k: row.get(k, "") for k in fieldnames})

    lines = []
    lines.append("## Autoflow attempts")
    lines.append("")
    lines.append("| Attempt | Clock (ns) | Status | Setup WNS | Setup TNS | DRC | LVS | Antenna | Why |")
    lines.append("|---:|---:|---|---:|---:|---:|---:|---:|---|")
    for row in history:
        lines.append(
            f"| {row.get('attempt','')} | {row.get('clock_ns','')} | {row.get('status','')} | "
            f"{row.get('setup_wns_ns','')} | {row.get('setup_tns_ns','')} | {row.get('drc_errors','')} | "
            f"{row.get('lvs_errors','')} | {row.get('antenna_violations','')} | {row.get('selection_reason','')} |"
        )
    (out_root / "autoflow_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="")
    ap.add_argument("--pdk-root", required=True)
    ap.add_argument("--openlane-image", required=True)
    ap.add_argument("--start-clock-ns", type=float, required=True)
    ap.add_argument("--min-clock-ns", type=float, default=5.0)
    ap.add_argument("--max-clock-ns", type=float, default=200.0)
    ap.add_argument("--initial-step-ns", type=float, default=20.0)
    ap.add_argument("--tolerance-ns", type=float, default=1.0)
    ap.add_argument("--max-iters", type=int, default=8)
    ap.add_argument("--synth-strategy", default="AREA 3")
    ap.add_argument("--run-antenna-repair", default="true")
    ap.add_argument("--run-heuristic-diode-insertion", default="true")
    ap.add_argument("--run-post-grt-design-repair", default="true")
    ap.add_argument("--run-post-grt-resizer-timing", default="false")
    ap.add_argument("--out-root", default="ci_out/designs_rns_crt")
    args = ap.parse_args()

    safe_variant = resolve_variant(args.variant)
    variant_path = safe_variant_to_path(safe_variant)
    out_root = ROOT / args.out_root
    out_root.mkdir(parents=True, exist_ok=True)

    summary_path_env = None
    if "GITHUB_STEP_SUMMARY_PATH" in dict(**subprocess.os.environ):
        summary_path_env = Path(subprocess.os.environ["GITHUB_STEP_SUMMARY_PATH"])
    elif "GITHUB_STEP_SUMMARY" in dict(**subprocess.os.environ):
        summary_path_env = Path(subprocess.os.environ["GITHUB_STEP_SUMMARY"])

    append_summary(summary_path_env, f"## Autoflow: {safe_variant}")
    append_summary(summary_path_env, "")
    append_summary(summary_path_env, "| Attempt | Clock (ns) | Status | Setup WNS | Setup TNS | DRC | LVS | Antenna | Why |")
    append_summary(summary_path_env, "|---:|---:|---|---:|---:|---:|---:|---:|---|")

    history: List[Dict[str, Any]] = []

    lower_fail: Optional[float] = None
    upper_pass: Optional[float] = None
    current = max(args.min_clock_ns, min(args.max_clock_ns, args.start_clock_ns))
    step = max(args.initial_step_ns, args.tolerance_ns)

    tried = set()

    for attempt in range(1, args.max_iters + 1):
        rounded_current = round(current, 6)
        if rounded_current in tried:
            break
        tried.add(rounded_current)

        attempt_dir = out_root / f"clk_{clock_label(rounded_current)}ns_attempt_{attempt:02d}"
        attempt_dir.mkdir(parents=True, exist_ok=True)

        cfg_path = ROOT / "config.json"
        sh(
            [
                "python",
                "tools/scripts/gen_config.py",
                "--variant",
                safe_variant,
                "--clock_ns",
                str(rounded_current),
                "--pdk-root",
                args.pdk_root,
                "--synth-strategy",
                args.synth_strategy,
                "--run-antenna-repair",
                args.run_antenna_repair,
                "--run-heuristic-diode-insertion",
                args.run_heuristic_diode_insertion,
                "--run-post-grt-design-repair",
                args.run_post_grt_design_repair,
                "--run-post-grt-resizer-timing",
                args.run_post_grt_resizer_timing,
                "--out",
                str(cfg_path),
            ],
            cwd=ROOT,
        )

        start_ts = time.time()
        sh(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{ROOT}:/work",
                "-v",
                f"{args.pdk_root}:/pdk",
                "-w",
                "/work",
                args.openlane_image,
                "bash",
                "-lc",
                "python3 -m openlane --pdk-root /pdk config.json",
            ],
            cwd=ROOT,
        )

        run_dir = latest_run_dir(start_ts)

        with (attempt_dir / "run_meta.json").open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "variant": safe_variant,
                    "clock_ns_requested": rounded_current,
                    "github_run_id": subprocess.os.environ.get("GITHUB_RUN_ID", ""),
                    "artifact_name": f"autoflow-{safe_variant}",
                },
                f,
                indent=2,
            )

        (attempt_dir / "run_dir_used.txt").write_text(f"RUN_DIR used: {run_dir}\n", encoding="utf-8")

        sh(
            [
                "python",
                "tools/scripts/extract_metrics.py",
                str(run_dir),
                "--out",
                str(attempt_dir),
                "--clock-ns",
                str(rounded_current),
            ],
            cwd=ROOT,
        )

        try:
            sh(
                [
                    "python",
                    "tools/scripts/render_gds.py",
                    "--run-root",
                    str(run_dir),
                    "--out",
                    str(attempt_dir / "renders"),
                ],
                cwd=ROOT,
            )
        except SystemExit:
            pass

        try:
            sh(
                [
                    "python",
                    "tools/scripts/build_layout_viewer.py",
                    "--out-dir",
                    str(attempt_dir),
                ],
                cwd=ROOT,
            )
        except SystemExit:
            pass

        metrics_json = run_dir / "final" / "metrics.json"
        if metrics_json.exists():
            shutil.copy2(metrics_json, attempt_dir / "metrics_raw.json")

        gds_dir = run_dir / "final" / "gds"
        if gds_dir.exists():
            dst_gds = attempt_dir / "final" / "gds"
            dst_gds.mkdir(parents=True, exist_ok=True)
            for g in gds_dir.glob("*"):
                if g.is_file():
                    shutil.copy2(g, dst_gds / g.name)

        metrics_row = read_csv_row(attempt_dir / "metrics.csv")
        status, reason = classify_status(metrics_row)

        history_row: Dict[str, Any] = {
            "attempt": attempt,
            "clock_ns": rounded_current,
            "status": status,
            "selection_reason": reason,
            "setup_wns_ns": metrics_row.get("setup_wns_ns", ""),
            "setup_tns_ns": metrics_row.get("setup_tns_ns", ""),
            "hold_wns_ns": metrics_row.get("hold_wns_ns", ""),
            "hold_tns_ns": metrics_row.get("hold_tns_ns", ""),
            "drc_errors": metrics_row.get("drc_errors", ""),
            "lvs_errors": metrics_row.get("lvs_errors", ""),
            "antenna_violations": metrics_row.get("antenna_violations", ""),
            "attempt_dir": str(attempt_dir.relative_to(ROOT)),
        }
        history.append(history_row)

        append_summary(
            summary_path_env,
            f"| {attempt} | {rounded_current} | {status} | {history_row['setup_wns_ns']} | {history_row['setup_tns_ns']} | {history_row['drc_errors']} | {history_row['lvs_errors']} | {history_row['antenna_violations']} | {reason} |",
        )

        passed = status == "PASS"

        if passed:
            upper_pass = rounded_current if upper_pass is None else min(upper_pass, rounded_current)
            next_candidate = rounded_current - step
            if lower_fail is not None:
                interval = upper_pass - lower_fail
                if interval <= args.tolerance_ns:
                    break
                next_candidate = (upper_pass + lower_fail) / 2.0
        else:
            lower_fail = rounded_current if lower_fail is None else max(lower_fail, rounded_current)
            if upper_pass is None:
                next_candidate = rounded_current + step
            else:
                interval = upper_pass - lower_fail
                if interval <= args.tolerance_ns:
                    break
                next_candidate = (upper_pass + lower_fail) / 2.0

        if upper_pass is not None and lower_fail is not None:
            step = max(args.tolerance_ns, abs(upper_pass - lower_fail) / 2.0)

        current = max(args.min_clock_ns, min(args.max_clock_ns, next_candidate))

    write_history_files(out_root, history)

    passing = [h for h in history if h["status"] == "PASS"]
    best = min(passing, key=lambda x: float(x["clock_ns"])) if passing else (history[-1] if history else {})
    with (out_root / "_autoflow_best.json").open("w", encoding="utf-8") as f:
        json.dump(best, f, indent=2)

    append_summary(summary_path_env, "")
    if best:
        append_summary(summary_path_env, f"**Best selected clock:** `{best.get('clock_ns', '')}` ns")
        append_summary(summary_path_env, f"**Best status:** `{best.get('status', '')}`")


if __name__ == "__main__":
    main()