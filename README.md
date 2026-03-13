# ASIC-Flow-Toolchain

A variant-driven GitHub ASIC flow for **Sky130 + OpenLane2 / LibreLane**, built for **research, reproducibility, and dissertation-facing evidence**.

This repository is designed around **named design variants**, not around arbitrary ad hoc uploads. Each design lives under `designs/<variant_name>/`, is described by its own `variant.yaml`, and is selected through `manifest.yaml` for CI execution and comparison.

The flow performs staged, matrix-based timing exploration, preserves rich run artifacts, publishes a GitHub Pages **Run Explorer**, and keeps the distinction between **real design/timing failures** and **tool/config/runtime failures** as honest as possible.

---

## What this repository is

This repo is intended to be:

- a **variant-driven ASIC research workflow**
- a **repeatable GitHub Actions pipeline** for OpenLane2 / LibreLane on Sky130
- a **run-comparison framework** that keeps all tested timing points visible
- a **documentation-friendly evidence generator** for metrics, artifacts, failure diagnostics, and GitHub Pages summaries

It is especially suited to projects where you want to:

- compare multiple design variants under a common flow
- sweep timing constraints systematically
- keep each timing point as a separate CI artifact
- publish a clean browser-based summary of results
- support academic reporting with traceable run outputs

---

## What this repository is not

This repo is **not** intended to be:

- a generic “throw any Verilog into CI” template
- a TinyTapeout hardening flow
- a TinyTapeout GitHub viewer action wrapper
- a single long opaque adaptive controller that hides intermediate timing points

TinyTapeout is used only as a **manual external GDS viewer homepage link** from the published explorer. The actual ASIC flow here is your own GitHub/OpenLane2/LibreLane research workflow.

---

## Core design philosophy

The non-negotiable architecture is:

```text
manifest.yaml
  -> selects a variant
  -> maps to designs/<variant_name>/
       -> variant.yaml
       -> src/**/*.v
```

Each variant is a self-contained design definition. The workflow resolves the enabled variant from `manifest.yaml`, reads its timing cap and flow settings, performs matrix sweeps, then compares all collected runs into a single explorer.

This keeps the repo:

- structured
- reproducible
- auditable
- easy to explain in reports and dissertation chapters

---

## Repository structure

A typical repository layout looks like this:

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

Important rules:

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

Default step:

- `5 ns`

### 6. Further refinement

The same bracket-and-refine method continues at smaller steps:

- `1.0 ns`
- `0.5 ns`
- `0.125 ns`

At each stage the bracket is recalculated from all available results, then the next matrix is generated.

### 7. Comparison and publishing

After the final refinement stage, the workflow:

- downloads all run artifacts
- builds summary markdown and CSV outputs
- selects the best run according to the explorer logic
- packages the best layout bundle
- builds the static Run Explorer site
- publishes that site to GitHub Pages

---

## Current workflow stages

The intended staged flow is:

```text
plan
-> coarse-sweep
-> select-coarse-bracket
-> mid-refine-sweep
-> select-mid-bracket
-> refine-sweep-1
-> select-refine-1
-> refine-sweep-2
-> select-refine-2
-> refine-sweep-3
-> compare-runs
-> deploy-run-explorer
```

Why this structure is preferred:

- every tested timing point is visible in GitHub UI
- every timing point has its own artifact bundle
- debugging is easier than with a hidden monolithic adaptive loop
- screenshots and results are dissertation-friendly

---

## What GitHub Pages publishes

The published explorer is intended to provide:

- a landing page with all collected runs
- sorting/filtering/search across runs
- stage filtering and status filtering
- automatic best-run highlighting
- settings used for the flow
- links to per-run pages
- downloadable GDS and metrics files
- a manual external GDS viewer link

The explorer settings section is intended to show:

- Synthesis strategy
- Antenna repair
- Heuristic diode insertion
- Post-GRT design repair
- Post-GRT resizer timing

If synthesis strategy is not overridden, the explorer should show:

- `Default`

not a misleading explicit strategy.

---

## Best-run selection logic

The explorer is designed to prefer runs in this general order:

1. clean signoff plus non-negative setup timing
2. if no full pass exists, clean signoff ahead of signoff-violating runs
3. lower requested clock period among otherwise comparable runs
4. setup WNS/TNS as tie-breakers

This means the selected run is not just “lowest requested clock at any cost”; it prioritises integrity of signoff and timing evidence.

---

## Run status meanings

The key status classes are:

- `PASS`
- `TIMING_FAIL`
- `SIGNOFF_FAIL`
- `SIGNOFF_AND_TIMING_FAIL`
- `FLOW_FAIL`

### PASS
The design completed cleanly and timing/signoff evidence supports acceptance.

### TIMING_FAIL
Timing evidence exists, but the design does not meet timing.

### SIGNOFF_FAIL
Timing may be acceptable, but signoff checks still fail.

### SIGNOFF_AND_TIMING_FAIL
Both timing and signoff problems are present.

### FLOW_FAIL
This is reserved for tool/runtime/config/path failures, for example:

- no usable run directory
- missing `metrics.csv`
- incomplete run evidence
- OpenLane exited non-zero and no valid timing metrics were produced

This distinction matters because a runtime/configuration problem should not be misreported as a real design timing failure.

---

## Artifact philosophy

Artifacts are intentionally rich and debug-friendly.

A normal run bundle should preserve as much as possible, including:

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

This repository favours:

- reproducibility
- auditability
- debug convenience
- dissertation evidence

more than aggressively slimming artifacts.

---

## Failure diagnostics

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

## Bracket summary artifacts

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

## How to add a new design

To test a new design, add a new variant directory under `designs/`.

### Step 1: create a variant folder

Example:

```text
designs/my_alu/
├─ variant.yaml
└─ src/
   ├─ top.v
   ├─ submodule_a.v
   └─ submodule_b.v
```

### Step 2: place all Verilog sources under `src/`

Use a clean source tree and include all RTL files needed by the selected top module.

### Step 3: write `variant.yaml`

A good starting template is:

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

### Step 4: register it in `manifest.yaml`

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

### Step 5: commit and push

Pushing to `main` triggers the workflow. You can also use **workflow_dispatch** from GitHub Actions and optionally provide a specific variant plus timing-step overrides.

---

## How to fill in `variant.yaml`

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

- too low, and the coarse sweep may never find a passing point
- too high, and you spend extra CI time exploring obviously slow periods

#### `sources`
A list of source globs relative to the variant directory.

Example:

```yaml
sources:
  - src/**/*.v
```

This should include all required Verilog files for the top module.

---

## Recommended `variant.yaml` sections

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

Important rule:

- leave it blank or omit it to use the OpenLane/LibreLane default honestly
- only set it when you intentionally want an explicit override

This is important because the flow should not pretend a blank value means a specific strategy.

#### Repair switches
These optional booleans let you steer common OpenLane behaviour:

- `run_antenna_repair`
- `run_heuristic_diode_insertion`
- `run_post_grt_design_repair`
- `run_post_grt_resizer_timing`

If omitted, the workflow and scripts fall back to their own defaults.

### `fp`
Use this section for floorplanning-oriented settings.

Common example:

```yaml
fp:
  core_util: 10
```

`core_util` controls the requested core utilisation target.

---

## Practical guidance for choosing `max_ns_cap`

`max_ns_cap` should be chosen as a realistic upper search ceiling for your design.

Examples:

- a very small sequential test design may only need `50` to `100 ns`
- a more complex arithmetic block may justify `150` to `250 ns`
- a new and uncharacterised design may start with a generous cap and be tightened later

A safe rule is:

- pick a ceiling high enough that the coarse sweep can find at least one passing region
- do not make it absurdly large without reason

---

## Manifest usage

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

### Important notes

- `variant` should point to the design directory, not directly to files
- the workflow converts this into a safe name for CI use when needed
- if no explicit variant is provided at dispatch time, the first enabled manifest experiment is used

---

## Workflow dispatch inputs

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

## Honest synthesis handling

This repository aims to be explicit and honest about synthesis strategy.

The intended rule is:

- only write `SYNTH_STRATEGY` into generated OpenLane config when a real override exists
- if the value is blank, that means **use the tool default**
- the explorer should display `Default`, not invent a specific strategy label

This avoids one of the most common research-workflow mistakes: silently pretending a blank value meant an explicit synthesis choice.

---

## Path handling rules

Generated OpenLane config should use **repo-relative POSIX paths**, not host absolute runner paths.

Why this matters:

- it makes configs portable
- it avoids GitHub runner path leakage
- it improves reproducibility across local and CI environments

As a user, the practical implication is simple:

- keep all design sources inside the repo
- use variant-relative or repo-relative paths in `variant.yaml`
- avoid hardcoding machine-specific absolute paths

---

## Explorer pages and per-run pages

Each successful compare stage builds:

- a landing page across all runs
- per-run detail pages

Per-run pages are intended to show:

- clean metadata
- metrics by category
  - Timing
  - Physical
  - Power
  - Signoff
- additional raw metrics if relevant
- a failure diagnostic section for `FLOW_FAIL`
- a useful download/tools area

The per-run tools area typically keeps the useful actions, such as:

- `Download GDS`
- `Open GDS Viewer`
- `Open metrics.csv`
- `Open metrics_raw.json`

---

## How to interpret results

### Timing metrics
Common timing fields include:

- requested clock period
- reported clock period
- setup WNS / TNS
- hold WNS / TNS

As a rough guide:

- non-negative setup WNS is generally what you want for a timing-clean result
- large negative WNS or TNS indicates the chosen clock is too aggressive

### Physical metrics
Typical fields include:

- core area
- die area
- instance count
- utilisation
- wire length
- via count

These help compare how different timing points or synthesis options affect implementation cost.

### Power metrics
Typical fields include:

- total power
- internal power
- switching power
- leakage power

These matter when you are comparing efficiency trade-offs across otherwise similar runs.

### Signoff metrics
Typical signoff fields include:

- DRC count
- KLayout DRC
- Magic DRC
- LVS
- antenna violations
- worst IR drop

These usually decide whether a run is truly publishable or only interesting as an intermediate datapoint.

---

## Recommended process for adding a new design

Before pushing a new design, check the following:

### Design checklist

- top module name is correct
- all RTL files are inside `src/`
- source globs match your actual files
- the clock port name is correct
- `max_ns_cap` is sensible
- shared SDC path exists
- no machine-specific absolute paths are used
- manifest points to the correct variant
- exactly the intended variant is enabled by default

### First-run strategy

For a first test of a new design:

- keep synthesis strategy blank unless you intentionally want an override
- use the default matrix step sizes
- choose a generous but sensible `max_ns_cap`
- expect the first pass to validate structure more than to immediately produce an optimal timing point

---

## Troubleshooting

### The flow says no sources were found

Check:

- your `sources:` glob in `variant.yaml`
- that files are under the variant directory
- that your file extensions match the glob

### The flow never finds a PASS

Check:

- `clock.max_ns_cap` may be too small
- your RTL may truly be too slow at the explored range
- constraints or clock port naming may be wrong

### The run is marked `FLOW_FAIL`

This usually points to infrastructure or configuration problems rather than true design timing failure.

Check:

- config generation
- path resolution
- whether `metrics.csv` was produced
- whether the OpenLane run directory exists
- failure summary files on the artifact/per-run page

### The explorer settings show an unexpected synthesis strategy

Check:

- workflow dispatch override
- `ll_policy.synth_strategy` in the variant
- whether a blank/default case has been handled honestly in the scripts

---

## Dissertation/reporting benefits

This repo is especially useful for academic hardware implementation work because it preserves:

- every matrix timing point as a separate run
- comparison-ready metrics
- traceable stage labels
- bracket summaries for timing-search narrative
- failure diagnostics for debugging sections
- static web pages suitable for screenshots and appendix references

In other words, it supports not just “getting a GDS,” but also explaining **how** you arrived there.

---

## Minimal example for a new user

If you only want the shortest path to trying a new design, do this:

1. Create `designs/my_design/src/` and put all Verilog there.
2. Create `designs/my_design/variant.yaml` using the template above.
3. Add `designs/my_design` to `manifest.yaml` and enable it.
4. Commit and push.
5. Open the GitHub Actions run.
6. After completion, inspect:
   - matrix jobs
   - uploaded artifacts
   - compare summary
   - best-layout bundle
   - published Run Explorer

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

---

## Final note

The most important thing to remember is that this repository is a **variant-driven research flow**, not a generic upload bucket.

Treat each `designs/<variant_name>/` directory as a documented experiment:

- clearly named
- reproducibly configured
- safely selected from the manifest
- explored through staged matrix timing sweeps
- preserved with rich artifacts and publishable summaries

That is what makes the repo useful not just for implementation, but also for engineering analysis and dissertation evidence.
