import argparse
import glob
import json
import os
import yaml


def load_yaml(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def normpath(p: str) -> str:
    return p.replace("\\", "/")


def resolve_path(variant_path: str, p: str) -> str:
    if not p:
        return p
    p = normpath(p)

    if p.startswith("/") or (len(p) > 2 and p[1] == ":" and p[2] in ("/", "\\")):
        return p

    if p.startswith(("designs/", ".github/", "tools/", "docs/")):
        return p

    return normpath(os.path.normpath(os.path.join(variant_path, p)))


def map_safe_variant_to_path(safe: str) -> str:
    manifest = load_yaml("manifest.yaml")
    for exp in manifest.get("experiments", []):
        vp = exp.get("variant")
        if vp and vp.replace("/", "_") == safe:
            return vp
    raise SystemExit(f"Cannot map variant '{safe}' back to a designs/<x> path.")


def as_bool(value, default: bool) -> bool:
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


def main():
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

    if os.path.isdir(args.variant) and os.path.exists(os.path.join(args.variant, "variant.yaml")):
        variant_path = args.variant
    else:
        variant_path = map_safe_variant_to_path(args.variant)

    vcfg = load_yaml(os.path.join(variant_path, "variant.yaml"))

    top = vcfg["top_module"]
    clk_port = (vcfg.get("clock") or {}).get("port", "clk")
    clk_ns = float(args.clock_ns)

    sources = []
    for pat in vcfg.get("sources", []):
        sources += glob.glob(os.path.join(variant_path, pat), recursive=True)
    sources = sorted(set(normpath(s) for s in sources))
    if not sources:
        raise SystemExit("No Verilog sources found. Check variant.yaml 'sources' globs.")

    llp = vcfg.get("ll_policy", {}) or {}
    shared = vcfg.get("shared", {}) or {}

    pnr_sdc = llp.get("sdc") or shared.get("pnr_sdc") or "designs/_shared/ll_policy/constraints.sdc"
    signoff_sdc = shared.get("signoff_sdc") or pnr_sdc

    pnr_sdc = resolve_path(variant_path, pnr_sdc)
    signoff_sdc = resolve_path(variant_path, signoff_sdc)

    fp = vcfg.get("fp", {}) or {}
    core_util = fp.get("core_util", 10)

    synth_strategy = args.synth_strategy or llp.get("synth_strategy", "AREA 3")
    run_heuristic_diode_insertion = as_bool(args.run_heuristic_diode_insertion, as_bool(llp.get("run_heuristic_diode_insertion"), True))
    run_antenna_repair = as_bool(args.run_antenna_repair, as_bool(llp.get("run_antenna_repair"), True))
    run_post_grt_design_repair = as_bool(args.run_post_grt_design_repair, as_bool(llp.get("run_post_grt_design_repair"), True))
    run_post_grt_resizer_timing = as_bool(args.run_post_grt_resizer_timing, as_bool(llp.get("run_post_grt_resizer_timing"), False))

    cfg = {
        "DESIGN_NAME": top,
        "VERILOG_FILES": sources,
        "CLOCK_PORT": clk_port,
        "CLOCK_PERIOD": clk_ns,
        "FP_CORE_UTIL": core_util,

        "SYNTH_STRATEGY": synth_strategy,
        "SYNTH_ABC_DFF": False,

        "RUN_ANTENNA_REPAIR": run_antenna_repair,
        "RUN_HEURISTIC_DIODE_INSERTION": run_heuristic_diode_insertion,
        "RUN_POST_GRT_DESIGN_REPAIR": run_post_grt_design_repair,
        "RUN_POST_GRT_RESIZER_TIMING": run_post_grt_resizer_timing,

        "PNR_SDC_FILE": pnr_sdc,
        "SIGNOFF_SDC_FILE": signoff_sdc,
        "RUN_LINTER": False,
        "RUN_VERILATOR": False,
        "QUIT_ON_LINTER_ERRORS": False,
        "QUIT_ON_VERILATOR_ERRORS": False,
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

    print(
        f"Wrote {args.out} for {variant_path} @ {clk_ns}ns "
        f"(top={top}, clk={clk_port}, synth={synth_strategy}, "
        f"antenna_repair={run_antenna_repair}, diode_insertion={run_heuristic_diode_insertion}, "
        f"post_grt_repair={run_post_grt_design_repair}, post_grt_resizer_timing={run_post_grt_resizer_timing})"
    )


if __name__ == "__main__":
    main()