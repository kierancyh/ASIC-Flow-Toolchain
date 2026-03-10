#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def resolve_variant_path(value: str) -> Path:
    candidate = ROOT / value
    if candidate.is_dir() and (candidate / "variant.yaml").exists():
        return candidate

    manifest = load_yaml(ROOT / "manifest.yaml")
    for exp in manifest.get("experiments", []) or []:
        variant = str(exp.get("variant", "")).strip()
        safe = variant.replace("/", "_")
        if value in (variant, safe):
            path = ROOT / variant
            if path.is_dir() and (path / "variant.yaml").exists():
                return path

    raise SystemExit(f"Cannot map variant '{value}' to a directory containing variant.yaml")


def main() -> None:
    ap = argparse.ArgumentParser(description="Read the auto start clock from variant.yaml")
    ap.add_argument("--variant", required=True)
    args = ap.parse_args()

    variant_dir = resolve_variant_path(args.variant)
    cfg = load_yaml(variant_dir / "variant.yaml")

    clock_cfg = cfg.get("clock", {}) or {}

    candidates = [
        clock_cfg.get("start_ns"),
        cfg.get("start_clock_ns"),
        clock_cfg.get("period"),
        clock_cfg.get("period_ns"),
    ]

    value = None
    for candidate in candidates:
        if candidate not in (None, ""):
          value = candidate
          break

    if value in (None, ""):
        raise SystemExit(f"No start clock found in {variant_dir / 'variant.yaml'}")

    try:
        numeric = float(value)
    except Exception as exc:
        raise SystemExit(f"Invalid start clock '{value}' in {variant_dir / 'variant.yaml'}") from exc

    if numeric.is_integer():
        print(int(numeric))
    else:
        print(round(numeric, 6))


if __name__ == "__main__":
    main()