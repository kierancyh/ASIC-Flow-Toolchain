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
    """
    If p is relative (e.g. ../_shared/...), resolve it relative to variant_path.
    If p is already repo-relative (designs/_shared/...) or absolute, keep it.
    """
    if not p:
        return p
    p = normpath(p)

    if p.startswith("/") or (len(p) > 2 and p[1] == ":" and p[2] in ("/", "\\")):  # linux or windows abs
        return p

    # Repo-relative already
    if p.startswith("designs/") or p.startswith(".github/") or p.startswith("tools/") or p.startswith("docs/"):
        return p

    # Otherwise treat it as relative to the variant folder
    return normpath(os.path.normpath(os.path.join(variant_path, p)))


def map_safe_variant_to_path(safe: str) -> str:
    """
    Map designs_rns_crt -> designs/rns_crt by checking manifest.yaml.
    """
    manifest = load_yaml("manifest.yaml")
    for exp in manifest.get("experiments", []):
        vp = exp.get("variant")
        if vp and vp.replace("/", "_") == safe:
            return vp
    raise SystemExit(f"Cannot map variant '{safe}' back to a designs/<x> path.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", required=True, help="safe name designs_rns_crt OR direct path designs/rns_crt")
    ap.add_argument("--clock_ns", required=True)
    ap.add_argument("--pdk-root", required=True)  # kept for provenance/debug
    ap.add_argument("--out", default="config.json")
    args = ap.parse_args()

    # Accept either safe name or path
    if os.path.isdir(args.variant) and os.path.exists(os.path.join(args.variant, "variant.yaml")):
        variant_path = args.variant
    else:
        variant_path = map_safe_variant_to_path(args.variant)

    vcfg = load_yaml(os.path.join(variant_path, "variant.yaml"))

    top = vcfg["top_module"]
    clk_port = (vcfg.get("clock") or {}).get("port", "clk")
    clk_ns = float(args.clock_ns)

    # Expand sources
    sources = []
    for pat in vcfg.get("sources", []):
        sources += glob.glob(os.path.join(variant_path, pat), recursive=True)
    sources = sorted(set([normpath(s) for s in sources]))
    if not sources:
        raise SystemExit("No Verilog sources found. Check variant.yaml 'sources' globs.")

    # Policy paths (your schema + fallback)
    llp = vcfg.get("ll_policy", {}) or {}
    shared = vcfg.get("shared", {}) or {}

    pnr_sdc = llp.get("sdc") or shared.get("pnr_sdc") or "designs/_shared/ll_policy/constraints.sdc"
    signoff_sdc = shared.get("signoff_sdc") or pnr_sdc

    pnr_sdc = resolve_path(variant_path, pnr_sdc)
    signoff_sdc = resolve_path(variant_path, signoff_sdc)

    # Optional floorplan overrides
    fp = vcfg.get("fp", {}) or {}
    core_util = fp.get("core_util", 10)

    cfg = {
        "DESIGN_NAME": top,
        "VERILOG_FILES": sources,
        "CLOCK_PORT": clk_port,
        "CLOCK_PERIOD": clk_ns,
        "FP_CORE_UTIL": core_util,
        "SYNTH_STRATEGY": "AREA 3",
        "SYNTH_ABC_DFF": False,
        "PNR_SDC_FILE": pnr_sdc,
        "SIGNOFF_SDC_FILE": signoff_sdc,
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

    print(f"Wrote {args.out} for {variant_path} @ {clk_ns}ns (top={top}, clk={clk_port})")


if __name__ == "__main__":
    main()