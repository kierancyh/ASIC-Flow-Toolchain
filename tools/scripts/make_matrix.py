#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def load_yaml(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def parse_clock_list(text: str):
    vals = []
    for part in text.split(","):
        s = part.strip()
        if not s:
            continue
        vals.append(float(s) if "." in s else int(s))
    return vals


def clocks_from_variant(vcfg: dict, exp: dict):
    clock_cfg = vcfg.get("clock", {}) or {}

    clocks = (
        vcfg.get("clocks_ns")
        or clock_cfg.get("sweep_ns")
        or exp.get("clocks_ns")
        or []
    )

    return clocks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="", help="Optional safe variant name, e.g. designs_rns_crt")
    ap.add_argument("--clock-list", default="", help="Optional comma-separated clock list")
    ap.add_argument("--matrix-cap", default="", help="Optional limit on emitted sweep points")
    args = ap.parse_args()

    manifest = load_yaml("manifest.yaml")
    experiments = manifest.get("experiments", [])

    if args.variant:
        experiments = [e for e in experiments if e.get("variant", "").replace("/", "_") == args.variant]

    include = []
    cap = int(args.matrix_cap) if str(args.matrix_cap).strip() else None

    for exp in experiments:
        if not exp.get("enabled", True):
            continue

        variant_path = exp["variant"]
        safe_variant = variant_path.replace("/", "_")
        variant_yaml = Path(variant_path) / "variant.yaml"
        vcfg = load_yaml(str(variant_yaml))

        if args.clock_list.strip():
            clocks = parse_clock_list(args.clock_list)
        else:
            clocks = clocks_from_variant(vcfg, exp)

        if cap is not None:
            clocks = clocks[:cap]

        for clk in clocks:
            include.append(
                {
                    "variant": safe_variant,
                    "clock_ns": clk,
                }
            )

    print(json.dumps(include))


if __name__ == "__main__":
    main()