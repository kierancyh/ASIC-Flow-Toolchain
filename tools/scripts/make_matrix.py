import json
import os
import yaml


def load_yaml(p: str):
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_sweep_ns(vcfg: dict) -> list[float]:
    clock = vcfg.get("clock", {}) or {}

    sweep = None
    if isinstance(clock, dict):
        sweep = clock.get("sweep_ns")
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
    cap_env = os.getenv("MATRIX_CAP", "").strip()
    cap = None
    if cap_env:
        try:
            cap = int(cap_env)
        except Exception:
            cap = None

    manifest = load_yaml("manifest.yaml")
    include = []

    for exp in manifest.get("experiments", []):
        if not exp.get("enabled", False):
            continue

        variant_path = exp["variant"]
        vcfg = load_yaml(os.path.join(variant_path, "variant.yaml"))

        sweep_ns = get_sweep_ns(vcfg)
        if cap is not None and cap > 0:
            sweep_ns = sweep_ns[:cap]

        for ns in sweep_ns:
            include.append(
                {
                    "variant": variant_path.replace("/", "_"),
                    "variant_path": variant_path,
                    "clock_ns": float(ns),
                }
            )

    print(json.dumps(include))


if __name__ == "__main__":
    main()