#!/usr/bin/env python3
import argparse
import glob
import os
import subprocess
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-root", required=True, help="Run directory, e.g. runs/RUN_...")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    run_root = Path(args.run_root)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    candidates = sorted((run_root / "final" / "gds").glob("*.gds"))
    if not candidates:
        candidates = sorted(run_root.glob("**/final/gds/*.gds"))

    if not candidates:
        print(f"No GDS found under run root: {run_root}")
        return

    gds = candidates[-1]
    out_png = out_dir / (gds.stem + ".png")

    script = Path("tools/scripts/klayout_render.py")
    if not script.exists():
        raise SystemExit("Missing tools/scripts/klayout_render.py")

    cmd = [
        "klayout",
        "-b",
        "-r",
        str(script),
        "-rd",
        f"INPUT={gds}",
        "-rd",
        f"OUTPUT={out_png}",
    ]
    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd)
    print("Wrote:", out_png)


if __name__ == "__main__":
    main()