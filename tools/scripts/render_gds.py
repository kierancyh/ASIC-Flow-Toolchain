#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import List, Tuple


def find_gds(run_root: Path) -> Path | None:
    candidates = sorted((run_root / "final" / "gds").glob("*.gds"))
    if not candidates:
        candidates = sorted(run_root.glob("**/final/gds/*.gds"))
    if not candidates:
        return None
    return candidates[-1]


def render_one(script: Path, gds: Path, out_png: Path, size: Tuple[int, int]) -> None:
    out_png.parent.mkdir(parents=True, exist_ok=True)
    w, h = size
    cmd = [
        "klayout",
        "-b",
        "-r",
        str(script),
        "-rd",
        f"INPUT={gds}",
        "-rd",
        f"OUTPUT={out_png}",
        "-rd",
        f"WIDTH={w}",
        "-rd",
        f"HEIGHT={h}",
    ]
    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd)
    print("Wrote:", out_png)



def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-root", required=True, help="Run directory, e.g. runs/RUN_...")
    ap.add_argument("--out", required=True, help="Output directory for rendered PNGs")
    args = ap.parse_args()

    run_root = Path(args.run_root)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    gds = find_gds(run_root)
    manifest = {
        "gds": str(gds) if gds else "",
        "renderer": "klayout" if shutil.which("klayout") else "unavailable",
        "renders": [],
        "status": "SKIPPED",
    }

    if gds is None:
        manifest["reason"] = f"No GDS found under run root: {run_root}"
        (out_dir / "renders_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(manifest["reason"])
        return

    script = Path("tools/scripts/klayout_render.py")
    if not script.exists():
        manifest["reason"] = "Missing tools/scripts/klayout_render.py"
        (out_dir / "renders_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(manifest["reason"])
        return

    if shutil.which("klayout") is None:
        manifest["reason"] = "klayout executable not found; render step skipped by design"
        (out_dir / "renders_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(manifest["reason"])
        return

    stem = gds.stem
    views: List[Tuple[str, Tuple[int, int]]] = [
        ("layout_top", (1600, 1200)),
        ("layout_hires", (2400, 1800)),
        ("layout_square", (1800, 1800)),
    ]

    written = []
    for suffix, size in views:
        out_png = out_dir / f"{stem}__{suffix}.png"
        try:
            render_one(script, gds, out_png, size)
            written.append(
                {
                    "file": out_png.name,
                    "width": size[0],
                    "height": size[1],
                    "kind": suffix,
                }
            )
        except subprocess.CalledProcessError as e:
            print(f"Render failed for {suffix}: {e}")

    manifest["status"] = "OK" if written else "FAILED"
    manifest["renders"] = written
    (out_dir / "renders_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Wrote:", out_dir / "renders_manifest.json")


if __name__ == "__main__":
    main()
