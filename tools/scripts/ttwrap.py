#!/usr/bin/env python3
"""TT compatibility + manifest helpers.

Commands:
  - validate
  - matrix --out github
  - gen-tt --variant designs/crt --clock_ns 101 --out tt_submission

This keeps your repo's native `variant.yaml` but generates a TT-style `info.yaml`
+ `src/` folder as input to `tt-gds-action`.
"""
from __future__ import annotations
import argparse, glob, os, sys, shutil
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]

def load_yaml(p: Path):
    return yaml.safe_load(p.read_text())

def expand_sources(base: Path, patterns):
    files = []
    for pat in patterns:
        hits = sorted((base / pat).glob("**/*") if "**" in pat else base.glob(pat))
        # above is conservative; easiest is glob.glob:
    # use glob.glob for reliability
    for pat in patterns:
        files += sorted([Path(x) for x in glob.glob(str(base / pat), recursive=True)])
    # keep only files
    files = [f for f in files if f.is_file()]
    # de-dup
    out=[]
    seen=set()
    for f in files:
        s=str(f.resolve())
        if s not in seen:
            seen.add(s); out.append(f)
    return out

def cmd_validate():
    manifest = load_yaml(ROOT / "manifest.yaml")
    for exp in manifest.get("experiments", []):
        if not exp.get("enabled", True):
            continue
        vdir = ROOT / exp["variant"]
        vy = vdir / "variant.yaml"
        if not vy.exists():
            raise SystemExit(f"Missing {vy}")
        v = load_yaml(vy)
        if "top_module" not in v:
            raise SystemExit(f"variant.yaml missing top_module: {vy}")
        srcs = expand_sources(vdir, v.get("sources", []))
        if not srcs:
            print(f"WARN: no source files found for {vdir} (patterns={v.get('sources')})")
    print("OK: manifests look sane")

def cmd_matrix(outfmt: str):
    manifest = load_yaml(ROOT / "manifest.yaml")
    variants=[]
    for exp in manifest.get("experiments", []):
        if exp.get("enabled", True):
            variants.append(Path(exp["variant"]).as_posix())
    if outfmt == "github":
        import json
        print(json.dumps({"variant": variants}))
    else:
        print("\n".join(variants))

def cmd_gen_tt(variant: str, clock_ns: float, outdir: Path):
    vdir = ROOT / variant
    v = load_yaml(vdir / "variant.yaml")
    srcs = expand_sources(vdir, v.get("sources", []))
    if outdir.exists():
        shutil.rmtree(outdir)
    (outdir / "src").mkdir(parents=True, exist_ok=True)
    # copy sources into tt_submission/src
    for f in srcs:
        rel = f.relative_to(vdir)
        dst = outdir / "src" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)
    # TT info.yaml
    info = {
        "project": v.get("name", Path(variant).name),
        "top_module": v["top_module"],
        "source_files": sorted([str(p.as_posix()) for p in (outdir/"src").rglob("*.v")]),
        "clock_hz": int(round(1e9 / float(clock_ns))),
    }
    (outdir / "info.yaml").write_text(yaml.safe_dump(info, sort_keys=False))
    print(f"Wrote {outdir}/info.yaml with clock_hz={info['clock_hz']}")
    print(f"Copied {len(srcs)} source files")

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate")
    mx = sub.add_parser("matrix")
    mx.add_argument("--out", default="github", choices=["github","plain"])
    gt = sub.add_parser("gen-tt")
    gt.add_argument("--variant", required=True)
    gt.add_argument("--clock_ns", type=float, required=True)
    gt.add_argument("--out", default="tt_submission")
    args = ap.parse_args()

    if args.cmd == "validate": cmd_validate()
    elif args.cmd == "matrix": cmd_matrix(args.out)
    elif args.cmd == "gen-tt": cmd_gen_tt(args.variant, args.clock_ns, ROOT/args.out)

if __name__ == "__main__":
    main()
