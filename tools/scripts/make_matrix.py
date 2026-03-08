import argparse
import json
import os
import yaml


def load_yaml(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_sweep_ns(vcfg: dict) -> list[float]:
    clock = vcfg.get("clock", {}) or {}

    sweep = None
    if isinstance(clock, dict):
        # Your current schema:
        sweep = clock.get("sweep_ns")
        # Backwards/alternate schema:
        if sweep is None:
            sweep = (clock.get("search") or {}).get("sweep_ns")

    if sweep is None:
        sweep = [101]

    if isinstance(sweep, (int, float)):
        return [float(sweep)]

    if isinstance(sweep, list):
        out = []
        for x in sweep:
            try:
                out.append(float(x))
            except Exception:
                pass
        return out if out else [101.0]

    return [101.0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=int, default=3, help="Max sweep points per variant (CI-safe)")
    args = ap.parse_args()

    manifest = load_yaml("manifest.yaml")
    include = []

    for exp in manifest.get("experiments", []):
        if not exp.get("enabled", False):
            continue

        variant_path = exp["variant"]  # e.g. designs/rns_crt
        vcfg = load_yaml(os.path.join(variant_path, "variant.yaml"))

        sweep_ns = get_sweep_ns(vcfg)
        sweep_ns = sweep_ns[: max(1, args.cap)]

        for ns in sweep_ns:
            include.append(
                {
                    # Safe identifier used in workflow + docs path
                    "variant": variant_path.replace("/", "_"),
                    "variant_path": variant_path,
                    "clock_ns": float(ns),
                }
            )

    print(json.dumps(include))


if __name__ == "__main__":
    main()