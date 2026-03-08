# ASIC Flow Template (TT-style viewer + research dashboards)

This repo is a **general template**: you can drop **any multi-file Verilog design** under `designs/<design>/src/`,
set `top_module` in `designs/<design>/variant.yaml`, push to GitHub, and get:
- **Harden runs** (GDS + reports)
- **A Pages layout viewer** (TinyTapeout-style)
- A **dashboard** with tables for area/timing/power + comparisons across variants and clock sweeps

## Quick start (add your own design)
1. Create a new folder:
   - `designs/my_design/src/`  (put your `.v` files here)
2. Create `designs/my_design/variant.yaml`:
   - set `top_module`
   - set `clock.port` (or keep `clk`)
   - set a small `clock.sweep_ns` list
3. Add it to `manifest.yaml` under `experiments` and set `enabled: true`
4. Commit + push.

## Running locally (optional)
- You can run the heavy flow on a self-hosted runner (your PC/WSL2) later.
- Do **not** commit `runs/` or other large outputs: GitHub Actions will upload artifacts and publish Pages.

## Included examples
- `designs/example_counter` (tiny demo design)
- `designs/rns_crt` and `designs/rns_mrc` (your RNS ALU examples)
