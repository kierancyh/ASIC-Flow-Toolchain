# ASIC-Flow-Toolchain

A variant-driven ASIC flow for **Sky130 + OpenLane2 / LibreLane**, built for **research, reproducibility, and dissertation-facing evidence**.

This repository is designed around **named design variants**, not around arbitrary ad hoc uploads. Each design lives under `designs/<variant_name>/`, is described by its own `variant.yaml`, and is selected through `manifest.yaml` for CI execution and comparison.

The flow performs staged, matrix-based timing exploration, preserves rich run artifacts, publishes a GitHub Pages **Run Explorer**, and keeps the distinction between **real design/timing failures** and **tool/config/runtime failures** as honest as possible.

This repository is intended to be a:

- **Variant-driven ASIC research workflow**
- **Repeatable GitHub Actions pipeline** for OpenLane2 / LibreLane on Sky130
- **Run-comparison framework** that keeps all tested timing points visible
- **Documentation-friendly evidence generator** for metrics, artifacts, failure diagnostics, and GitHub Pages summaries

---

## Core Design Philosophy

Each variant is a self-contained design definition. The workflow resolves the enabled variant from `manifest.yaml`, reads its timing cap and flow settings, performs matrix sweeps, then compares all collected runs into a single explorer.

```text
manifest.yaml
  -> selects a variant
  -> maps to designs/<variant_name>/
       -> variant.yaml
       -> src/**/*.v
```
---

## Repository Structure

```text
.
├─ .github/
│  └─ workflows/
│     └─ aisc_flow.yml
├─ designs/
│  ├─ _shared/
│  │  └─ ll_policy/
│  │     ├─ constraints.sdc
│  │     └─ ...
│  ├─ rns_crt/
│  │  ├─ variant.yaml
│  │  └─ src/
│  │     └─ ... .v files
│  └─ <your_new_variant>/
│     ├─ variant.yaml
│     └─ src/
│        └─ ... .v files
├─ docs/
├─ tools/
│  └─ scripts/
│     ├─ autoflow.py
│     ├─ compare_runs.py
│     ├─ gen_config.py
│     ├─ make_clock_matrix.py
│     ├─ read_start_clock.py
│     └─ select_clock_bracket.py
├─ manifest.yaml
├─ requirements.txt
└─ README.md
```

---

## How the system works

The workflow is staged so that every important timing point remains visible as a separate matrix job and artifact.

### 1. Variant resolution

The `plan` job resolves the active variant from `manifest.yaml`.

If you manually dispatch the workflow, you may supply a specific safe variant name. Otherwise the first enabled manifest entry is used.

### 2. Clock policy

The timing search is driven from the variant’s `clock` section.

Current intended structure:

```yaml
clock:
  port: clk
  mode: auto
  max_ns_cap: 200
```

Restrictions:
- `max_ns_cap` is the real search ceiling
- coarse sweep starts from a floor, usually `0 ns`
- the old idea of using `start_ns` as a search bound is no longer the intended policy
- matrix sweeps are preferred over a hidden serial controller

### 3. Coarse sweep

The first sweep spans the full range:
- minimum floor: usually `0 ns`
- maximum: `clock.max_ns_cap`
- default step: `20 ns`

Each coarse point runs as its own matrix job.

### 4. Bracket selection

After coarse results are collected, the bracket is chosen using:
- **upper_pass** = lowest clock period that passes
- **lower_fail** = highest failing point below `upper_pass`

This bracket is written out as summary artifacts for traceability.

### 5. Mid refine stage

The next stage performs a **downward-only** matrix sweep from `upper_pass` toward `lower_fail`.
Default step: `5 ns`

### 6. Further refinement

The same bracket-and-refine method continues at smaller steps:
- `1.0 ns`
- `0.5 ns`
- `0.125 ns`

At each stage the bracket is recalculated from all available results, then the next matrix is generated.

### 7. Comparison and publishing

After the final refinement stage, the workflow:
- Downloads all run artifacts
- Builds summary markdown and CSV outputs
- Selects the best run according to the explorer logic
- Packages the best layout bundle
- Builds the static Run Explorer site
- Publishes that site to GitHub Pages

---

## Workflow stages

```text
plan
-> Coarse-sweep
-> Select-coarse-bracket
-> Mid-refine-sweep
-> Select-mid-bracket
-> Refine-sweep-1
-> Select-refine-1
-> Refine-sweep-2
-> Select-refine-2
-> Refine-sweep-3
-> Compare-runs
-> Deploy-run-explorer
```

---

## GitHub Pages 

The published explorer is intended to provide:
- A landing page with all collected runs
- Sorting/filtering/search across runs
- Stage filtering and status filtering
- Automatic best-run highlighting
- Settings used for the flow
- Links to per-run pages
- Downloadable GDS and metrics files
- Manual external GDS viewer link

The explorer settings section is intended to show:
- Synthesis strategy (Set as Default)
- Antenna repair
- Heuristic diode insertion
- Post-GRT design repair
- Post-GRT resizer timing

---

## Best-Run Selection Logic

The explorer is designed to prefer runs in this general order:
1. Clean signoff plus non-negative setup timing
2. If no full pass exists, clean signoff ahead of signoff-violating runs
3. Lower requested clock period among otherwise comparable runs
4. Setup WNS/TNS as tie-breakers

This means the selected run is not just “lowest requested clock at any cost”; it prioritises integrity of signoff and timing evidence.

---

## Run Status Definitions

The key status classes are:
**`PASS`** - The design completed cleanly and timing/signoff evidence supports acceptance.
**`TIMING_FAIL`** - Timing evidence exists, but the design does not meet timing.
**`SIGNOFF_FAIL`** - Timing may be acceptable, but signoff checks still fail.
**`SIGNOFF_AND_TIMING_FAIL`** - Both timing and signoff problems are present.
**`FLOW_FAIL`** - Reserved for tool/runtime/config/path failures (i.e. No usable run directory, Missing `metrics.csv`, Incomplete run evidence. OpenLane exited non-zero and no valid timing metrics were produced)

This distinction matters because a runtime/configuration problem should not be misreported as a real design timing failure.

---

## Artifact Philosophy

Artifacts are intentionally rich and debug-friendly, including:
- `metrics.csv`
- `metrics.md`
- `metrics_raw.json`
- `run_meta.json`
- `attempt_started.txt`
- `attempt_manifest.json`
- `renders/`
- `final/gds/`
- copied full `openlane_run/` if available

For `FLOW_FAIL` cases, bundles may be smaller if no usable run directory exists, but the intent is still to preserve useful diagnostics.

---

## Failure Diagnostics

For `FLOW_FAIL` attempts, the flow is intended to generate:
- `failure_summary.md`
- `failure_summary.json`

These summarise likely failure phase and important checkpoints such as:
- whether config generation succeeded
- whether OpenLane was invoked
- whether a run directory existed
- whether timing metrics were present
- whether GDS or renders were produced

On the per-run explorer page, these should appear in a **Failure diagnostic** section.

---

## Bracket Summary Artifacts

When a bracket is selected between stages, the flow is intended to emit:
- `bracket_summary.md`
- `bracket_summary.json`

These typically document:
- `upper_pass`
- `lower_fail`
- failure kind below the bracket
- bracket width
- next stage label
- next step size
- planned next clocks

This helps explain how the next refinement matrix was chosen.

---

## How to: Add a New Design

To test a new design, add a new variant directory under `designs/`.

### Step 1: Create a Variant Folder

Example:

```text
designs/my_alu/
├─ variant.yaml
└─ src/
   ├─ top.v
   ├─ submodule_a.v
   └─ submodule_b.v
```

### Step 2: Place all Verilog Sources under `src/`

Use a clean source tree and include all RTL files needed by the selected top module.

### Step 3: Write `variant.yaml`

An example of a filled template is:

```yaml
name: my_alu
pdk: sky130A

top_module: my_alu_top

clock:
  port: clk
  mode: auto
  max_ns_cap: 200

sources:
  - src/**/*.v

ll_policy:
  sdc: ../_shared/ll_policy/constraints.sdc
  # synth_strategy: AREA 2
  # run_antenna_repair: true
  # run_heuristic_diode_insertion: true
  # run_post_grt_design_repair: true
  # run_post_grt_resizer_timing: false

fp:
  core_util: 10
```

### Step 4: Register it in `manifest.yaml`

Example:

```yaml
project:
  title: "ASIC Flow Toolchain"
  author: "Kieran"
  notes: "Variant-driven Sky130/OpenLane2 research workflow"

experiments:
  - variant: designs/my_alu
    enabled: true
```

If more than one experiment is listed, only enable the one you currently want as the default, unless you are intentionally changing manifest selection behavior.

### Step 5: Commit and Push

Pushing to `main` triggers the workflow. You can also use **workflow_dispatch** from GitHub Actions and optionally provide a specific variant plus timing-step overrides.

---

## How to: Fill in `variant.yaml`

This section is the main user guide for preparing a design variant.

### Required fields

#### `name`
A human-readable name for the design variant.

Example:

```yaml
name: my_alu
```

#### `pdk`
The target PDK. For this repo, that is typically:

```yaml
pdk: sky130A
```

#### `top_module`
The exact top-level Verilog module name to harden.

Example:

```yaml
top_module: my_alu_top
```

This must match the RTL exactly.

#### `clock.port`
The clock input port name used by the design.

Example:

```yaml
clock:
  port: clk
```

If your design uses a different name, change it accordingly.

#### `clock.mode`
For this workflow, use:

```yaml
mode: auto
```

This indicates the clock period will be searched by the staged sweep process.

#### `clock.max_ns_cap`
The maximum clock period the sweep is allowed to test.

Example:

```yaml
max_ns_cap: 200
```

Choose this realistically:
**Too Low** - Coarse sweep may never find a passing point
**Too High** - Spend extra CI time exploring obviously slow periods

#### `sources`
A list of source globs relative to the variant directory.

Example:

```yaml
sources:
  - src/**/*.v
```

This should include all required Verilog files for the top module.

---

## How to: Run the Workflow

This repository supports two normal ways to run the flow:
- **Automatic run on push**
- **Manual run from GitHub Actions**

In both cases, the workflow:
- Selects a design variant
- Runs the staged clock search
- Uploads per-run artifacts
- Compares all collected runs
- Publishes the Run Explorer if the compare stage succeeds

### Option 1: Automatic run on push

This is the normal way to use the repository:
1. Create the new design under `designs/<variant_name>/`
2. Fill in `variant.yaml`
3. Register it in `manifest.yaml`
4. Commit and push to `main` and the workflow starts automatically.

Use this when:
- Repository to use its normal default behavior
- Testing the currently enabled manifest design
- Do not need to override any workflow inputs manually

### Option 2: Manual run from GitHub Actions

Use manual dispatch when you want to:
- Rerun the flow without making a new commit
- Test a specific registered variant
- Change the timing search step sizes for an experiment
- Temporarily override synthesis or repair options

To run it manually:
1. Open the repository on GitHub
2. Click **Actions**
3. Select **ASIC Flow**
4. Click **Run workflow**
5. Choose the branch, usually `main`
6. Fill in any inputs you want to override
7. Click **Run workflow**

### Typical manual test settings

For a normal first test, use:
```
variant: designs_my_alu
min_clock_ns: 0
initial_step_ns: 20
mid_refine_step_ns: 5.0
refine1_step_ns: 1.0
refine2_step_ns: 0.5
refine3_step_ns: 0.125
tolerance_ns: 0.125
synth_strategy: leave blank
run_antenna_repair: true
run_heuristic_diode_insertion: true
run_post_grt_design_repair: true
run_post_grt_resizer_timing: false
```

---

## Recommended `variant.yaml` Sections

### `ll_policy`
Use this section for OpenLane/LibreLane policy controls that should belong to the variant.

Common examples:

```yaml
ll_policy:
  sdc: ../_shared/ll_policy/constraints.sdc
  synth_strategy: AREA 2
  run_antenna_repair: true
  run_heuristic_diode_insertion: true
  run_post_grt_design_repair: true
  run_post_grt_resizer_timing: false
```

#### `ll_policy.sdc`
Path to the SDC used for PnR/signoff constraints.

A shared repo-relative pattern is common:

```yaml
sdc: ../_shared/ll_policy/constraints.sdc
```

#### `ll_policy.synth_strategy`
Optional synthesis override.

Leave it blank or omit it to use the OpenLane/LibreLane default honestly. Only set it when you intentionally want an **explicit override**

#### Repair switches
These optional booleans let you steer common OpenLane behaviour:
- `run_antenna_repair`
- `run_heuristic_diode_insertion`
- `run_post_grt_design_repair`
- `run_post_grt_resizer_timing`

### `fp`
Use this section for floorplanning-oriented settings.

Common example:

```yaml
fp:
  core_util: 10
```

**`core_util`** controls the requested core utilisation target.

---

## Practical Guidance for Choosing `max_ns_cap`

`max_ns_cap` should be chosen as a realistic upper search ceiling for your design.

Examples:
- Very small sequential test design may only need `50` to `100 ns`
- More complex arithmetic block may justify `150` to `250 ns`
- New and uncharacterised design may start with a generous cap and be tightened later

A safe rule is to pick a ceiling high enough that the coarse sweep can find at least one passing region but **do not make it absurdly large** without reason

---

## Manifest Usage

`manifest.yaml` controls which design the workflow resolves.

Minimal example:

```yaml
project:
  title: "ASIC Flow Toolchain"
  author: "Kieran"
  notes: "Variant-driven Sky130/OpenLane2 research workflow"

experiments:
  - variant: designs/my_alu
    enabled: true
```

### Important Notes

- `variant` should point to the design directory, not directly to files
- Workflow converts this into a safe name for CI use when needed
- If no explicit variant is provided at dispatch time, the first enabled manifest experiment is used

---

## Workflow Dispatch Inputs

The workflow supports manual overrides for the search schedule and a few OpenLane controls.

Typical dispatch controls include:

- `variant`
- `min_clock_ns`
- `initial_step_ns`
- `mid_refine_step_ns`
- `refine1_step_ns`
- `refine2_step_ns`
- `refine3_step_ns`
- `tolerance_ns`
- `synth_strategy`
- `run_antenna_repair`
- `run_heuristic_diode_insertion`
- `run_post_grt_design_repair`
- `run_post_grt_resizer_timing`
- `openlane_image`
- `open_pdks_rev`

In most normal use, you should keep the defaults unless you are deliberately running an experiment.

---

## Explorer pages and per-run pages

Each successful compare stage builds a landing page across all runs and per-run detail pages

Per-run pages are intended to show:
- Clean metadata
- Metrics by category
  - Timing
  - Physical
  - Power
  - Signoff
- Additional raw metrics if relevant
- Failure diagnostic section for `FLOW_FAIL`

The per-run `Download & Tools` area typically keeps the useful actions, such as:
- `Download GDS`
- `Open GDS Viewer`
- `Open metrics.csv`
- `Open metrics_raw.json`

---

## How to interpret results

### Timing metrics
Common timing fields include:
- Requested clock period
- Reported clock period
- Setup WNS / TNS
- Hold WNS / TNS

Note:
- **Non-negative setup WNS** - Generally what you want for a timing-clean result
- **Large negative WNS or TNS** - Indicates the chosen clock is too aggressive

### Physical Metrics
Typical fields include:
- Core area
- Die area
- Instance count
- Utilisation
- Wire length
- Via count

These help compare how different timing points or synthesis options affect implementation cost.

### Power Metrics
Typical fields include:

- Total power
- Internal power
- Switching power
- Leakage power

These matter when you are comparing efficiency trade-offs across otherwise similar runs. Power is given in watts (W)

### Signoff Metrics
Typical signoff fields include:
- DRC count
- KLayout DRC
- Magic DRC
- LVS
- Antenna violations
- Worst IR drop

These usually decide whether a run is truly publishable or only interesting as an intermediate datapoint.

---

## Recommended process for adding a new design

Before pushing a new design, check the following:

### Design checklist

- Top module name is correct
- All RTL files are inside `src/`
- Source globs match your actual files
- Clock port name is correct
- `max_ns_cap` is sensible
- Shared SDC path exists
- No machine-specific absolute paths are used
- Manifest points to the correct variant
- Exactly the intended variant is enabled by default

### First-run strategy

For a first test of a new design:
- Keep synthesis strategy blank unless you intentionally want an override
- Use the default matrix step sizes
- Choose a generous but sensible `max_ns_cap`
- Expect the first pass to validate structure more than to immediately produce an optimal timing point

---

## Troubleshooting

### The flow says no sources were found

Check:
- `sources:` glob in `variant.yaml`
- Files are under the variant directory
- File extensions match the glob

### The flow never finds a PASS

Check:
- `clock.max_ns_cap` may be too small
- RTL may truly be too slow at the explored range
- Constraints or clock port naming may be wrong

### The run is marked `FLOW_FAIL`

This usually points to infrastructure or configuration problems rather than true design timing failure.

Check:
- Config. generation
- Path resolution
- Whether `metrics.csv` was produced
- Whether the OpenLane run directory exists
- Failure summary files on the artifact/per-run page

### The explorer settings show an unexpected synthesis strategy

Check:
- Workflow dispatch override
- `ll_policy.synth_strategy` in the variant
- Whether a blank/default case has been handled honestly in the scripts

---

## Minimal example for a new user

If you only want the shortest path to trying a new design, do this:
1. Create `designs/my_design/src/` and put all Verilog there.
2. Create `designs/my_design/variant.yaml` using the template above.
3. Add `designs/my_design` to `manifest.yaml` and enable it.
4. Commit and push.
5. Open the GitHub Actions run.
6. After completion, inspect:
   - Matrix jobs
   - Uploaded artifacts
   - Compare summary
   - Best-layout bundle
   - Published Run Explorer

---

## Suggested starting template

Copy this and edit the marked fields:

```yaml
name: my_design
pdk: sky130A

top_module: my_top_module

clock:
  port: clk
  mode: auto
  max_ns_cap: 200

sources:
  - src/**/*.v

ll_policy:
  sdc: ../_shared/ll_policy/constraints.sdc

fp:
  core_util: 10
```

Then add this to `manifest.yaml`:

```yaml
experiments:
  - variant: designs/my_design
    enabled: true
```
