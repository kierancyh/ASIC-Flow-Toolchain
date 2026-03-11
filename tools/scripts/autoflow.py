#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import yaml

ROOT = Path(__file__).resolve().parents[2]

CSV_FIELDS = [
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

HISTORY_FIELDS = [
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
    "openlane_rc",
    "run_dir",
    "attempt_dir",
]


def load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def sh(
    cmd: Sequence[str],
    *,
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
) -> int:
    printable = " ".join(str(x) for x in cmd)
    print(f"> {printable}", flush=True)
    rc = subprocess.run(
        [str(x) for x in cmd],
        cwd=str(cwd) if cwd else None,
        env=env,
        check=False,
    )
    if check and rc.returncode != 0:
        raise SystemExit(rc.returncode)
    return rc.returncode


def resolve_variant(value: str) -> str:
    manifest = load_yaml(ROOT / "manifest.yaml")
    experiments = manifest.get("experiments", []) or []

    if value:
        for exp in experiments:
            variant = str(exp.get("variant", ""))
            safe = variant.replace("/", "_")
            if value in (variant, safe):
                return safe
        return value

    enabled = [
        str(exp.get("variant", "")).replace("/", "_")
        for exp in experiments
        if exp.get("enabled", True) and exp.get("variant")
    ]
    if not enabled:
        raise SystemExit("No enabled variants found in manifest.yaml")
    return enabled[0]


def safe_variant_to_path(safe_variant: str) -> Path:
    candidate = ROOT / safe_variant
    if candidate.is_dir() and (candidate / "variant.yaml").exists():
        return candidate

    manifest = load_yaml(ROOT / "manifest.yaml")
    for exp in manifest.get("experiments", []) or []:
        variant = str(exp.get("variant", ""))
        safe = variant.replace("/", "_")
        if safe_variant in (variant, safe):
            return ROOT / variant

    raise SystemExit(f"Cannot map variant '{safe_variant}' to a designs/<name> path")


def to_float(value: Any) -> Optional[float]:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def clock_label(clock_ns: float) -> str:
    as_float = float(clock_ns)
    if as_float.is_integer():
        return str(int(as_float))
    return str(as_float).replace(".", "p")


def append_summary(summary_path: Optional[Path], line: str) -> None:
    if summary_path is None:
        return
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("a", encoding="utf-8") as f:
        f.write(line)
        if not line.endswith("\n"):
            f.write("\n")


def gh_group_start(title: str) -> None:
    print(f"::group::{title}", flush=True)


def gh_group_end() -> None:
    print("::endgroup::", flush=True)


def gh_debug(message: str) -> None:
    print(f"::debug::{message}", flush=True)


def read_csv_row(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    with path.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows[0] if rows else {}


def write_placeholder_metrics(
    attempt_dir: Path,
    *,
    clock_ns: float,
    status: str = "FLOW_FAIL",
) -> None:
    attempt_dir.mkdir(parents=True, exist_ok=True)

    row: Dict[str, Any] = {key: "" for key in CSV_FIELDS}
    row["clock_ns"] = clock_ns
    row["clock_ns_reported"] = ""
    row["status"] = status

    with (attempt_dir / "metrics.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in CSV_FIELDS})

    md_lines = [
        "| " + " | ".join(CSV_FIELDS) + " |",
        "|" + "|".join(["---"] * len(CSV_FIELDS)) + "|",
        "| " + " | ".join(str(row.get(k, "")) for k in CSV_FIELDS) + " |",
        "",
    ]
    (attempt_dir / "metrics.md").write_text("\n".join(md_lines), encoding="utf-8")


def write_run_meta(
    attempt_dir: Path,
    *,
    variant: str,
    clock_ns: float,
    synth_strategy_override: str = "",
) -> None:
    meta = {
        "variant": variant,
        "clock_ns_requested": clock_ns,
        "github_run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "synth_strategy_override": synth_strategy_override or "",
        "artifact_name": f"autoflow-{variant}",
    }
    (attempt_dir / "run_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def find_latest_run_dir(since_ts: float) -> Optional[Path]:
    runs_dir = ROOT / "runs"
    if not runs_dir.exists():
        return None

    candidates: List[Tuple[float, Path]] = []

    for path in runs_dir.rglob("RUN_*"):
        if not path.is_dir():
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime >= since_ts - 5.0:
            candidates.append((mtime, path))

    if not candidates:
        for metrics in runs_dir.glob("**/final/metrics.json"):
            try:
                candidates.append((metrics.stat().st_mtime, metrics.parent.parent))
            except OSError:
                pass

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def maybe_copy_metrics_raw(run_dir: Path, attempt_dir: Path) -> None:
    metrics_json = run_dir / "final" / "metrics.json"
    if metrics_json.exists():
        shutil.copy2(metrics_json, attempt_dir / "metrics_raw.json")


def maybe_copy_gds(run_dir: Path, attempt_dir: Path) -> None:
    gds_dir = run_dir / "final" / "gds"
    if not gds_dir.exists():
        return

    dst_gds = attempt_dir / "final" / "gds"
    dst_gds.mkdir(parents=True, exist_ok=True)
    for gds in sorted(gds_dir.glob("*")):
        if gds.is_file():
            shutil.copy2(gds, dst_gds / gds.name)


def has_valid_timing_metrics(metrics_row: Dict[str, str]) -> bool:
    swns = to_float(metrics_row.get("setup_wns_ns"))
    stns = to_float(metrics_row.get("setup_tns_ns"))
    return swns is not None and stns is not None


def classify_metrics_row(metrics_row: Dict[str, str]) -> Tuple[str, str]:
    reasons: List[str] = []

    swns = to_float(metrics_row.get("setup_wns_ns"))
    stns = to_float(metrics_row.get("setup_tns_ns"))
    drc = to_float(metrics_row.get("drc_errors"))
    lvs = to_float(metrics_row.get("lvs_errors"))
    ant = to_float(metrics_row.get("antenna_violations"))

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


def classify_attempt(
    *,
    run_dir: Optional[Path],
    metrics_row: Dict[str, str],
    openlane_rc: int,
) -> Tuple[str, str]:
    if run_dir is None:
        return "FLOW_FAIL", f"No OpenLane run directory found (rc={openlane_rc})."

    if not metrics_row:
        return "FLOW_FAIL", f"No metrics.csv was produced for discovered run dir {run_dir} (rc={openlane_rc})."

    raw_status = str(metrics_row.get("status", "")).strip().upper()
    timing_present = has_valid_timing_metrics(metrics_row)

    if openlane_rc != 0 and not timing_present:
        return "FLOW_FAIL", f"OpenLane exited with code {openlane_rc} and no valid timing metrics were produced."

    if raw_status in {"INCOMPLETE", "FLOW_FAIL"}:
        return "FLOW_FAIL", f"Metrics were incomplete for run dir {run_dir} (rc={openlane_rc})."

    status, reason = classify_metrics_row(metrics_row)

    if status == "PASS" and not timing_present:
        return "FLOW_FAIL", "Run was marked PASS-like but valid setup timing metrics are missing."

    if openlane_rc != 0:
        return status, f"{reason}; OpenLane rc={openlane_rc}"

    return status, reason


def write_history_files(out_root: Path, history: List[Dict[str, Any]]) -> None:
    out_root.mkdir(parents=True, exist_ok=True)

    with (out_root / "autoflow_history.json").open("w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

    with (out_root / "autoflow_history.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HISTORY_FIELDS)
        writer.writeheader()
        for row in history:
            writer.writerow({k: row.get(k, "") for k in HISTORY_FIELDS})

    lines = [
        "## Autoflow attempts",
        "",
        "| Attempt | Clock (ns) | Status | Setup WNS | Setup TNS | DRC | LVS | Antenna | RC | Remarks |",
        "|---:|---:|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in history:
        lines.append(
            f"| {row.get('attempt','')} | {row.get('clock_ns','')} | {row.get('status','')} | "
            f"{row.get('setup_wns_ns','')} | {row.get('setup_tns_ns','')} | {row.get('drc_errors','')} | "
            f"{row.get('lvs_errors','')} | {row.get('antenna_violations','')} | {row.get('openlane_rc','')} | "
            f"{row.get('selection_reason','')} |"
        )

    (out_root / "autoflow_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def compute_bounds(pass_clocks: Sequence[float], fail_clocks: Sequence[float]) -> Tuple[Optional[float], Optional[float]]:
    pass_bound = min(pass_clocks) if pass_clocks else None
    if pass_bound is None:
        return None, None

    lower_fails = [f for f in fail_clocks if f < pass_bound]
    fail_bound = max(lower_fails) if lower_fails else None
    return pass_bound, fail_bound


def parse_refine_steps(refine_steps_ns: str, initial_step_ns: float, tolerance_ns: float) -> List[float]:
    steps: List[float] = [round(max(float(initial_step_ns), float(tolerance_ns)), 6)]
    raw = (refine_steps_ns or "").strip()
    if raw:
        for token in raw.replace(";", ",").split(","):
            piece = token.strip()
            if not piece:
                continue
            value = float(piece)
            if value <= 0:
                raise SystemExit("refine-steps-ns values must be > 0")
            rounded = round(max(value, float(tolerance_ns)), 6)
            if rounded not in steps:
                steps.append(rounded)

    for idx in range(1, len(steps)):
        if steps[idx] > steps[idx - 1]:
            raise SystemExit("refine-steps-ns must be in non-increasing order after the coarse step")

    return steps


def next_downward_candidate_no_fail(
    *,
    pass_bound: float,
    step: float,
    min_clock_ns: float,
    tested: Set[float],
) -> Optional[float]:
    candidate = round(pass_bound - step, 6)
    while candidate >= round(min_clock_ns, 6):
        if candidate not in tested:
            return candidate
        candidate = round(candidate - step, 6)
    return None


def next_downward_candidate_within_bracket(
    *,
    pass_bound: float,
    fail_bound: float,
    step: float,
    tested: Set[float],
) -> Optional[float]:
    candidate = round(pass_bound - step, 6)
    while candidate > round(fail_bound, 6):
        if candidate not in tested:
            return candidate
        candidate = round(candidate - step, 6)
    return None


def next_upward_candidate(
    *,
    anchor_clock: float,
    step: float,
    max_clock_ns: float,
    tested: Set[float],
) -> Optional[float]:
    candidate = round(anchor_clock + step, 6)
    while candidate <= round(max_clock_ns, 6):
        if candidate not in tested:
            return candidate
        candidate = round(candidate + step, 6)
    return None


def choose_next_clock(
    *,
    tested_clocks: Sequence[float],
    pass_clocks: Sequence[float],
    usable_fail_clocks: Sequence[float],
    flow_fail_clocks: Sequence[float],
    step_sequence: Sequence[float],
    step_index: int,
    min_clock_ns: float,
    max_clock_ns: float,
    tolerance_ns: float,
) -> Tuple[Optional[float], int, str]:
    tested = {round(v, 6) for v in tested_clocks}
    pass_bound, fail_bound = compute_bounds(pass_clocks, usable_fail_clocks)

    provisional_flow_fail_bound: Optional[float] = None
    if pass_bound is not None:
        lower_flow_fails = [f for f in flow_fail_clocks if f < pass_bound]
        provisional_flow_fail_bound = max(lower_flow_fails) if lower_flow_fails else None

    while True:
        current_step = step_sequence[step_index]

        if pass_bound is None:
            anchor_clock = max(tested) if tested else round(min_clock_ns, 6)
            candidate = next_upward_candidate(
                anchor_clock=anchor_clock,
                step=current_step,
                max_clock_ns=max_clock_ns,
                tested=tested,
            )
            if candidate is None:
                return None, step_index, f"Stopping because no passing point was found before the max clock cap {max_clock_ns} ns."
            return candidate, step_index, f"No pass found yet, so search upward at the current {current_step} ns step."

        effective_fail_bound = fail_bound
        effective_fail_kind = "usable"
        if effective_fail_bound is None and provisional_flow_fail_bound is not None:
            effective_fail_bound = provisional_flow_fail_bound
            effective_fail_kind = "flow"

        if effective_fail_bound is None:
            candidate = next_downward_candidate_no_fail(
                pass_bound=pass_bound,
                step=current_step,
                min_clock_ns=min_clock_ns,
                tested=tested,
            )
            if candidate is None:
                return None, step_index, f"Reached the minimum clock floor {min_clock_ns} ns with no failure below the current best pass {pass_bound} ns."
            return candidate, step_index, f"No failure below the current best pass {pass_bound} ns, so keep searching downward at {current_step} ns step."

        interval = round(pass_bound - effective_fail_bound, 6)
        if interval <= tolerance_ns:
            if effective_fail_kind == "flow":
                return None, step_index, f"Stopping because the provisional pass/FLOW_FAIL bracket [{effective_fail_bound}, {pass_bound}] ns is within tolerance {tolerance_ns} ns."
            return None, step_index, f"Stopping because the pass/fail bracket [{effective_fail_bound}, {pass_bound}] ns is within tolerance {tolerance_ns} ns."

        candidate = next_downward_candidate_within_bracket(
            pass_bound=pass_bound,
            fail_bound=effective_fail_bound,
            step=current_step,
            tested=tested,
        )
        if candidate is not None:
            if effective_fail_kind == "flow":
                return candidate, step_index, f"Using provisional FLOW_FAIL boundary [{effective_fail_bound}, {pass_bound}] ns and refining at the current {current_step} ns step."
            return candidate, step_index, f"Refining inside bracket [{effective_fail_bound}, {pass_bound}] ns at the current {current_step} ns step."

        if step_index + 1 >= len(step_sequence):
            if effective_fail_kind == "flow":
                return None, step_index, f"Stopping because no further untested candidates remain inside provisional FLOW_FAIL bracket [{effective_fail_bound}, {pass_bound}] ns at the finest configured step {current_step} ns."
            return None, step_index, f"Stopping because no further untested candidates remain inside bracket [{effective_fail_bound}, {pass_bound}] ns at the finest configured step {current_step} ns."

        step_index += 1


def resolve_summary_path() -> Optional[Path]:
    if os.environ.get("GITHUB_STEP_SUMMARY_PATH"):
        return Path(os.environ["GITHUB_STEP_SUMMARY_PATH"])
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        return Path(os.environ["GITHUB_STEP_SUMMARY"])
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="")
    ap.add_argument("--pdk-root", required=True)
    ap.add_argument("--openlane-image", required=True)
    ap.add_argument("--start-clock-ns", type=float, required=True)
    ap.add_argument("--min-clock-ns", type=float, default=5.0)
    ap.add_argument("--max-clock-ns", type=float, default=200.0)
    ap.add_argument("--initial-step-ns", type=float, default=20.0)
    ap.add_argument("--refine-steps-ns", default="5.0,1.0,0.5,0.125")
    ap.add_argument("--tolerance-ns", type=float, default=1.0)
    ap.add_argument("--max-iters", type=int, default=8)
    ap.add_argument("--synth-strategy", default="")
    ap.add_argument("--run-antenna-repair", default="true")
    ap.add_argument("--run-heuristic-diode-insertion", default="true")
    ap.add_argument("--run-post-grt-design-repair", default="true")
    ap.add_argument("--run-post-grt-resizer-timing", default="false")
    ap.add_argument("--out-root", default="ci_out/designs_rns_crt")
    args = ap.parse_args()

    safe_variant = resolve_variant(args.variant)
    _variant_path = safe_variant_to_path(safe_variant)

    out_root = (ROOT / args.out_root).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / ".autoflow_started").write_text("started\n", encoding="utf-8")

    session_meta = {
        "variant": safe_variant,
        "start_clock_ns": args.start_clock_ns,
        "min_clock_ns": args.min_clock_ns,
        "max_clock_ns": args.max_clock_ns,
        "initial_step_ns": args.initial_step_ns,
        "refine_steps_ns": args.refine_steps_ns,
        "tolerance_ns": args.tolerance_ns,
        "max_iters": args.max_iters,
        "openlane_image": args.openlane_image,
        "pdk_root": args.pdk_root,
        "github_run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "synth_strategy_override": args.synth_strategy or "",
    }
    (out_root / "_autoflow_session.json").write_text(json.dumps(session_meta, indent=2), encoding="utf-8")

    summary_path = resolve_summary_path()
    append_summary(summary_path, f"## Autoflow: {safe_variant}")
    append_summary(summary_path, "")
    append_summary(summary_path, f"Adaptive steps: {parse_refine_steps(args.refine_steps_ns, args.initial_step_ns, args.tolerance_ns)}")
    append_summary(summary_path, "")
    append_summary(summary_path, "| Attempt | Clock (ns) | Status | Setup WNS | Setup TNS | DRC | LVS | Antenna | RC | Remarks |")
    append_summary(summary_path, "|---:|---:|---|---:|---:|---:|---:|---:|---:|---|")

    history: List[Dict[str, Any]] = []
    pass_clocks: List[float] = []
    usable_fail_clocks: List[float] = []
    flow_fail_clocks: List[float] = []

    current = max(args.min_clock_ns, min(args.max_clock_ns, args.start_clock_ns))
    step_sequence = parse_refine_steps(args.refine_steps_ns, args.initial_step_ns, args.tolerance_ns)
    step_index = 0
    tried: Set[float] = set()

    for attempt in range(1, args.max_iters + 1):
        rounded_current = round(current, 6)
        if rounded_current in tried:
            print(f"Stopping: clock {rounded_current} ns already tried.", flush=True)
            break
        tried.add(rounded_current)

        current_step = step_sequence[step_index]
        group_title = f"Attempt {attempt} - {rounded_current} ns"
        gh_group_start(group_title)
        try:
            print(f"\n=== Attempt {attempt}: trying {rounded_current} ns (step {current_step} ns) ===", flush=True)
            gh_debug(f"variant={safe_variant}")
            gh_debug(f"clock_ns={rounded_current}")
            gh_debug(f"current_step_ns={current_step}")
            gh_debug(f"step_index={step_index}")
            gh_debug(f"min_clock_ns={args.min_clock_ns}")
            gh_debug(f"max_clock_ns={args.max_clock_ns}")
            gh_debug(f"out_root={out_root}")

            attempt_dir = out_root / f"clk_{clock_label(rounded_current)}ns_attempt_{attempt:02d}"
            attempt_dir.mkdir(parents=True, exist_ok=True)
            write_run_meta(
                attempt_dir,
                variant=safe_variant,
                clock_ns=rounded_current,
                synth_strategy_override=args.synth_strategy,
            )
            (attempt_dir / "attempt_started.txt").write_text(
                f"attempt={attempt}\nclock_ns={rounded_current}\nstarted_at={int(time.time())}\n",
                encoding="utf-8",
            )

            cfg_path = ROOT / "config.json"
            gh_debug(f"config_path={cfg_path}")
            sh(
                [
                    sys.executable,
                    str(ROOT / "tools/scripts/gen_config.py"),
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
                check=True,
            )

            start_ts = time.time()
            openlane_rc = sh(
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
                check=False,
            )
            print(f"OpenLane return code: {openlane_rc}", flush=True)
            gh_debug(f"openlane_rc={openlane_rc}")

            run_dir = find_latest_run_dir(start_ts)
            if run_dir is None:
                print("No run directory detected after attempt.", flush=True)
                gh_debug("run_dir=(missing)")
                (attempt_dir / "run_dir_used.txt").write_text("(missing)\n", encoding="utf-8")
                write_placeholder_metrics(attempt_dir, clock_ns=rounded_current, status="FLOW_FAIL")
            else:
                print(f"Using run directory: {run_dir}", flush=True)
                gh_debug(f"run_dir={run_dir}")
                (attempt_dir / "run_dir_used.txt").write_text(f"{run_dir}\n", encoding="utf-8")

                extract_rc = sh(
                    [
                        sys.executable,
                        str(ROOT / "tools/scripts/extract_metrics.py"),
                        str(run_dir),
                        "--out",
                        str(attempt_dir),
                        "--clock-ns",
                        str(rounded_current),
                    ],
                    cwd=ROOT,
                    check=False,
                )
                print(f"extract_metrics return code: {extract_rc}", flush=True)
                gh_debug(f"extract_metrics_rc={extract_rc}")

                render_rc = sh(
                    [
                        sys.executable,
                        str(ROOT / "tools/scripts/render_gds.py"),
                        "--run-root",
                        str(run_dir),
                        "--out",
                        str(attempt_dir / "renders"),
                    ],
                    cwd=ROOT,
                    check=False,
                )
                gh_debug(f"render_gds_rc={render_rc}")

                viewer_rc = sh(
                    [
                        sys.executable,
                        str(ROOT / "tools/scripts/build_layout_viewer.py"),
                        "--out-dir",
                        str(attempt_dir),
                    ],
                    cwd=ROOT,
                    check=False,
                )
                gh_debug(f"build_layout_viewer_rc={viewer_rc}")

                maybe_copy_metrics_raw(run_dir, attempt_dir)
                maybe_copy_gds(run_dir, attempt_dir)

                if not (attempt_dir / "metrics.csv").exists():
                    write_placeholder_metrics(attempt_dir, clock_ns=rounded_current, status="FLOW_FAIL")

            metrics_row = read_csv_row(attempt_dir / "metrics.csv")
            status, reason = classify_attempt(run_dir=run_dir, metrics_row=metrics_row, openlane_rc=openlane_rc)

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
                "openlane_rc": openlane_rc,
                "run_dir": str(run_dir) if run_dir else "",
                "attempt_dir": str(attempt_dir.relative_to(ROOT)),
            }
            history.append(history_row)
            write_history_files(out_root, history)

            print(
                f"Attempt {attempt} | {rounded_current} ns | {status} | "
                f"WNS={history_row['setup_wns_ns']} | TNS={history_row['setup_tns_ns']} | "
                f"DRC={history_row['drc_errors']} | LVS={history_row['lvs_errors']} | "
                f"ANT={history_row['antenna_violations']} | RC={openlane_rc} | {reason}",
                flush=True,
            )
            append_summary(
                summary_path,
                f"| {attempt} | {rounded_current} | {status} | {history_row['setup_wns_ns']} | "
                f"{history_row['setup_tns_ns']} | {history_row['drc_errors']} | {history_row['lvs_errors']} | "
                f"{history_row['antenna_violations']} | {openlane_rc} | {reason} |",
            )

            if status == "PASS":
                pass_clocks.append(rounded_current)
            elif status == "FLOW_FAIL":
                flow_fail_clocks.append(rounded_current)
            else:
                usable_fail_clocks.append(rounded_current)

            gh_debug(f"pass_clocks={pass_clocks}")
            gh_debug(f"usable_fail_clocks={usable_fail_clocks}")
            gh_debug(f"flow_fail_clocks={flow_fail_clocks}")

            next_clock, step_index, next_reason = choose_next_clock(
                tested_clocks=sorted(tried),
                pass_clocks=pass_clocks,
                usable_fail_clocks=usable_fail_clocks,
                flow_fail_clocks=flow_fail_clocks,
                step_sequence=step_sequence,
                step_index=step_index,
                min_clock_ns=args.min_clock_ns,
                max_clock_ns=args.max_clock_ns,
                tolerance_ns=args.tolerance_ns,
            )

            gh_debug(f"next_clock={next_clock}")
            gh_debug(f"next_step_index={step_index}")
            gh_debug(f"next_reason={next_reason}")

            if next_clock is None:
                print(next_reason, flush=True)
                append_summary(summary_path, "")
                append_summary(summary_path, f"Adaptive controller: {next_reason}")
                break

            print(f"Adaptive controller: next clock = {next_clock} ns | {next_reason}", flush=True)
            append_summary(summary_path, f"Adaptive controller: next clock = {next_clock} ns | {next_reason}")
            current = next_clock
        finally:
            gh_group_end()

    write_history_files(out_root, history)

    if not history:
        raise SystemExit("Autoflow produced no attempts")

    passing = [row for row in history if row["status"] == "PASS"]
    best = min(passing, key=lambda row: float(row["clock_ns"])) if passing else history[-1]

    (out_root / "_autoflow_best.json").write_text(json.dumps(best, indent=2), encoding="utf-8")
    status_payload = {
        "variant": safe_variant,
        "attempt_count": len(history),
        "pass_count": len(passing),
        "fail_count": len(history) - len(passing),
        "best_clock_ns": best.get("clock_ns"),
        "best_status": best.get("status"),
        "best_attempt_dir": best.get("attempt_dir"),
    }
    (out_root / "_autoflow_status.json").write_text(json.dumps(status_payload, indent=2), encoding="utf-8")
    (out_root / ".autoflow_completed").write_text("completed\n", encoding="utf-8")


if __name__ == "__main__":
    main()