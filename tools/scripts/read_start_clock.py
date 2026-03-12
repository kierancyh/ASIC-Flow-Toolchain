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


def read_clock_field(cfg: Dict[str, Any], field: str) -> Any:
    clock_cfg = cfg.get("clock", {}) or {}

    if field == "max_ns_cap":
        candidates = [
            clock_cfg.get("max_ns_cap"),
            clock_cfg.get("max_clock_ns"),
            cfg.get("max_clock_ns_cap"),
            cfg.get("max_clock_ns"),
        ]
    else:
        raise SystemExit(f"Unsupported field '{field}'")

    for candidate in candidates:
        if candidate not in (None, ""):
            return candidate
    return None


def emit_numeric(value: Any, source: Path, field: str) -> None:
    if value in (None, ""):
        raise SystemExit(f"No {field} found in {source}")

    try:
        numeric = float(value)
    except Exception as exc:
        raise SystemExit(f"Invalid {field} '{value}' in {source}") from exc

    if numeric <= 0:
        raise SystemExit(f"{field} must be > 0 in {source}")

    if numeric.is_integer():
        print(int(numeric))
    else:
        print(round(numeric, 6))


def main() -> None:
    ap = argparse.ArgumentParser(description="Read clock-related fields from variant.yaml")
    ap.add_argument("--variant", required=True)
    ap.add_argument("--field", default="max_ns_cap", choices=["max_ns_cap"])
    args = ap.parse_args()

    variant_dir = resolve_variant_path(args.variant)
    cfg = load_yaml(variant_dir / "variant.yaml")
    value = read_clock_field(cfg, args.field)
    emit_numeric(value, variant_dir / "variant.yaml", args.field)


if __name__ == "__main__":
    main()