#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List


def clock_label(clock_ns: float) -> str:
    return str(int(clock_ns)) if float(clock_ns).is_integer() else str(round(clock_ns, 6)).rstrip("0").rstrip(".")


def main() -> None:
    ap = argparse.ArgumentParser(description="Lightweight artifact enricher for one fixed-clock autoflow attempt")
    ap.add_argument("--base-dir", type=Path, required=True)
    ap.add_argument("--clock-ns", type=float, required=True)
    args = ap.parse_args()

    base_dir = args.base_dir
    base_dir.mkdir(parents=True, exist_ok=True)

    label = clock_label(args.clock_ns)
    pattern = f"clk_{label}ns_attempt_*"
    attempts: List[Path] = sorted(base_dir.glob(pattern))

    manifest = {
        "base_dir": str(base_dir),
        "clock_ns": args.clock_ns,
        "clock_label": label,
        "matched_attempt_dirs": [p.name for p in attempts],
        "latest_attempt_dir": attempts[-1].name if attempts else None,
    }

    (base_dir / f"artifact_manifest_{label}ns.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()