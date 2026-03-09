#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import yaml


ROOT = Path(__file__).resolve().parents[2]


def load_yaml(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def safe_variant_to_path(safe_variant: str) -> Path:
    manifest = load_yaml(ROOT / "manifest.yaml")
    for exp in manifest.get("experiments", []):
        variant = exp.get("variant", "")
        if variant.replace("/", "_") == safe_variant:
            return ROOT / variant
    raise SystemExit(f"Cannot map safe variant '{safe_variant}' to designs/<x>")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", required=True)
    args = ap.parse_args()

    variant_path = safe_variant_to_path(args.variant)
    vcfg = load_yaml(variant_path / "variant.yaml")

    clock_cfg = vcfg.get("clock", {}) or {}

    start_clock = (
        clock_cfg.get("start_ns")
        or vcfg.get("start_clock_ns")
        or clock_cfg.get("period")
        or clock_cfg.get("period_ns")
    )

    if start_clock in (None, ""):
        raise SystemExit(
            f"No auto-sweep starting clock found in {variant_path / 'variant.yaml'}; "
            f"use clock.start_ns: <value>"
        )

    print(start_clock)


if __name__ == "__main__":
    main()