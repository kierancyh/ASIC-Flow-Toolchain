#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import yaml


ROOT = Path(__file__).resolve().parents[2]


def load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def normpath(value: str) -> str:
    return value.replace("\\", "/")


def repo_rel(path: Path) -> str:
    return normpath(os.path.relpath(path, ROOT))


def resolve_path(variant_path: Path, value: str) -> str:
    if not value:
        return value

    value = normpath(value)

    # Repo-root style paths stay repo-root relative.
    if value.startswith(("designs/", ".github/", "tools/", "docs/")):
        return value

    # Absolute paths are converted back into repo-relative if they live inside the repo.
    p = Path(value)
    if p.is_absolute():
        try:
            return repo_rel(p.resolve())
        except Exception:
            return normpath(str(p))

    # Otherwise resolve relative to the variant folder, then convert to repo-relative.
    return repo_rel((variant_path / value).resolve())


def map_safe_variant_to_path(safe_variant: str) -> Path:
    manifest = load_yaml(ROOT / "manifest.yaml")
    for exp in manifest.get("experiments", []) or []:
        variant = str(exp.get("variant", "")).strip()
        if variant and variant.replace("/", "_") == safe_variant:
            return ROOT / variant
    raise SystemExit(f"Cannot map variant '{safe_variant}' back to a designs/ path.")


def as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value

    s = str(value).strip().lower()
    if s in {"1", "true", "yes", "on"}:
        return True
    if s in {"0", "false", "no", "off", ""}:
        return False
    return default


def resolve_variant_path(variant_arg: str) -> Path:
    candidate = Path(variant_arg)
    if candidate.is_dir() and (candidate / "variant.yaml").exists():
        return candidate.resolve()
    return map_safe_variant_to_path(variant_arg).resolve()


def resolve_sources(variant_path: Path, source_patterns: List[str]) -> List[str]:
    sources: List[str] = []
    for pattern in source_patterns:
        sources.extend(glob.glob(str(variant_path / pattern), recursive=True))

    resolved = sorted(
        set(repo_rel(Path(path).resolve()) for path in sources if Path(path).exists())
    )

    if not resolved:
        raise SystemExit("No Verilog sources found. Check variant.yaml 'sources' globs.")

    return resolved


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", required=True)
    ap.add_argument("--clock_ns", required=True)
    ap.add_argument("--pdk-root", required=True)
    ap.add_argument("--out", default="config.json")
    ap.add_argument("--synth-strategy", default="")
    ap.add_argument("--run-antenna-repair", default="")
    ap.add_argument("--run-heuristic-diode-insertion", default="")
    ap.add_argument("--run-post-grt-design-repair", default="")
    ap.add_argument("--run-post-grt-resizer-timing", default="")
    args = ap.parse_args()

    variant_path = resolve_variant_path(args.variant)
    variant_cfg = load_yaml(variant_path / "variant.yaml")

    top_module = variant_cfg["top_module"]
    clock_cfg = variant_cfg.get("clock", {}) or {}
    clock_port = clock_cfg.get("port", "clk")
    clock_ns = float(args.clock_ns)

    sources = resolve_sources(variant_path, list(variant_cfg.get("sources", []) or []))

    ll_policy = variant_cfg.get("ll_policy", {}) or {}
    shared = variant_cfg.get("shared", {}) or {}
    fp = variant_cfg.get("fp", {}) or {}

    pnr_sdc = ll_policy.get("sdc") or shared.get("pnr_sdc") or "designs/_shared/ll_policy/constraints.sdc"
    signoff_sdc = shared.get("signoff_sdc") or pnr_sdc

    pnr_sdc = resolve_path(variant_path, str(pnr_sdc))
    signoff_sdc = resolve_path(variant_path, str(signoff_sdc))

    core_util = fp.get("core_util", 10)

    explicit_synth = str(args.synth_strategy or "").strip()
    variant_synth = str(ll_policy.get("synth_strategy") or "").strip()
    synth_strategy = explicit_synth or variant_synth

    run_heuristic_diode_insertion = as_bool(
        args.run_heuristic_diode_insertion,
        as_bool(ll_policy.get("run_heuristic_diode_insertion"), True),
    )
    run_antenna_repair = as_bool(
        args.run_antenna_repair,
        as_bool(ll_policy.get("run_antenna_repair"), True),
    )
    run_post_grt_design_repair = as_bool(
        args.run_post_grt_design_repair,
        as_bool(ll_policy.get("run_post_grt_design_repair"), True),
    )
    run_post_grt_resizer_timing = as_bool(
        args.run_post_grt_resizer_timing,
        as_bool(ll_policy.get("run_post_grt_resizer_timing"), False),
    )

    cfg: Dict[str, Any] = {
        "DESIGN_NAME": top_module,
        "VERILOG_FILES": sources,
        "CLOCK_PORT": clock_port,
        "CLOCK_PERIOD": clock_ns,
        "FP_CORE_UTIL": core_util,
        "SYNTH_ABC_DFF": False,
        "RUN_ANTENNA_REPAIR": run_antenna_repair,
        "RUN_HEURISTIC_DIODE_INSERTION": run_heuristic_diode_insertion,
        "RUN_POST_GRT_DESIGN_REPAIR": run_post_grt_design_repair,
        "RUN_POST_GRT_RESIZER_TIMING": run_post_grt_resizer_timing,
        "PNR_SDC_FILE": pnr_sdc,
        "SIGNOFF_SDC_FILE": signoff_sdc,
        "RUN_LINTER": False,
        "RUN_VERILATOR": False,
    }

    if synth_strategy:
        cfg["SYNTH_STRATEGY"] = synth_strategy

    out_path = Path(args.out)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

    synth_label = synth_strategy if synth_strategy else "OpenLane default (not overridden)"
    print(
        f"Wrote {out_path} for {repo_rel(variant_path)} @ {clock_ns}ns "
        f"(top={top_module}, clk={clock_port}, synth={synth_label}, "
        f"antenna_repair={run_antenna_repair}, diode_insertion={run_heuristic_diode_insertion}, "
        f"post_grt_repair={run_post_grt_design_repair}, post_grt_resizer_timing={run_post_grt_resizer_timing})"
    )
    print(f"Resolved VERILOG_FILES={sources}")
    print(f"Resolved PNR_SDC_FILE={pnr_sdc}")
    print(f"Resolved SIGNOFF_SDC_FILE={signoff_sdc}")


if __name__ == "__main__":
    main()