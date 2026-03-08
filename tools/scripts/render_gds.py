import argparse, os, glob, subprocess, sys

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-root", default=".")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)

    # Find a final GDS from LibreLane output structure
    candidates = glob.glob(os.path.join(args.run_root, "runs", "**", "final", "gds", "*.gds"), recursive=True)
    if not candidates:
        print("No GDS found to render.")
        return

    gds = sorted(candidates)[-1]
    out_png = os.path.join(args.out, os.path.basename(gds).replace(".gds", ".png"))

    # Use KLayout in batch mode to export a screenshot
    # This relies on klayout being installed (pip 'klayout' provides it).
    script = os.path.join("tools", "scripts", "klayout_render.py")
    if not os.path.exists(script):
        raise SystemExit("Missing tools/scripts/klayout_render.py")

    cmd = ["klayout", "-b", "-r", script, "-rd", f"INPUT={gds}", "-rd", f"OUTPUT={out_png}"]
    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd)
    print("Wrote:", out_png)

if __name__ == "__main__":
    main()