# LibreLane-Sky130-ASIC-Toolchain — Technical Documentation

## 1. Introduction

This repository is a **variant-driven GitHub ASIC flow and run explorer** built for **Sky130 + OpenLane2 / LibreLane**. 

This repository is designed so that a user can:

- Place ASIC RTL inside a named design variant
- Select the active experiment through `manifest.yaml`
- Let CI run backend sweeps automatically
- Review the results through a lightweight static dashboard

---

## 2. Purpose of Repository

This repository is intended to be:

- **Variant-driven ASIC research workflow**
- **Repeatable GitHub Actions pipeline** for OpenLane2 / LibreLane on Sky130
- **Matrix-based timing exploration framework**
- **Run Explorer generator** for comparing results across timing points
- **Documentation-friendly evidence system** 


## 3. Design Philosophy

The underlying philosophy of the repo can be summarised in four ideas.

### 3.1 Variant-driven by design

Every design lives under its own folder in `designs/<variant_name>/` and is configured by its own `variant.yaml`. The repository is therefore organised around **named experiments**, not around ad hoc uploads.

### 3.2 User contract is simple and stable

The intended user-facing contract is:

- Put ASIC RTL into `src/`
- Edit `variant.yaml`
- Select the active design in `manifest.yaml`
- Let CI do the rest

This keeps the repo clean and makes it easier to reuse across multiple designs.

### 3.3 Matrix sweeps should remain visible

Timing exploration is deliberately kept **matrix-based and explicit**. Rather than using a hidden serial controller that silently mutates one run into the next, the flow preserves individual timing points as separate jobs and artifacts. That is far better for traceability and dissertation evidence.

### 3.4 Pages should be lightweight and honest

GitHub Pages is used for the **Run Explorer**, not as a dumping ground for the full backend implementation tree. The published site is intentionally lightweight, while large and detailed backend outputs remain in GitHub Actions artifacts.

---

## 4. Repository Structure

A typical structure is expected to look like this:

```text
.
├─ .github/
│  └─ workflows/
│     └─ aisc_flow.yml
├─ designs/
│  ├─ _shared/
│  │  └─ ll_policy/
│  │     ├─ constraints.sdc
│  │     ├─ power_fair.tcl
│  │     └─ power_activity.tcl
│  ├─ <variant_name>/
│  │  ├─ variant.yaml
│  │  └─ src/
│  │     └─ ... RTL files ...
├─ tools/
│  └─ scripts/
│     ├─ autoflow.py
│     ├─ compare_runs.py
│     ├─ gen_config.py
│     ├─ make_clock_matrix.py
│     ├─ read_start_clock.py
│     ├─ select_clock_bracket.py
│     └─ select_refine_matrix.py
├─ manifest.yaml
├─ README.md
├─ TECHNICAL DOCUMENTATION.md
└─ requirements.txt
```

Notes:

- `designs/<variant>/src/` is for **ASIC RTL only**
- `_shared/ll_policy/` is the natural place for shared SDC or power-policy files
- `manifest.yaml` is the switchboard that selects the active experiment

---

## 5. Core Architecture and File Responsibilities

The repository can be separated into three layers.

### 5.1 Configuration layer

Defines **what design is active** and **how it should be treated**.

- `manifest.yaml` chooses the active experiment
- `designs/<variant>/variant.yaml` defines design-specific behaviour

### 5.2 Execution layer

Decides **what CI does**.

- `.github/workflows/aisc_flow.yml` orchestrates the entire pipeline
- `autoflow.py` remains the backend ASIC attempt engine

### 5.3 Presentation layer

Decides **how results are surfaced**.

- `compare_runs.py` downloads artifacts, classifies runs, builds summary tables, writes per-run pages, and generates the static Run Explorer site
- GitHub Pages publishes a lightweight snapshot for the current run and a `latest/` shortcut

---

## 6. Variant Contract

Each design variant is defined inside `designs/<variant_name>/variant.yaml`.

A representative example is:

```yaml
name: my_variant
pdk: sky130A

top_module: my_top

clock:
  port: clk
  mode: auto
  max_ns_cap: 200

sources:
  - src/**/*.v

ll_policy:
  sdc: ../_shared/ll_policy/constraints.sdc
  power_fair_tcl: ../_shared/ll_policy/power_fair.tcl
  power_activity_tcl: ../_shared/ll_policy/power_activity.tcl
```

### 6.1 Required fields

#### `name`
A human-readable label for the variant.

#### `pdk`
The target PDK. For this flow, that is typically `sky130A`.

#### `top_module`
The exact top-level module to synthesise and harden.

#### `clock.port`
The clock input port name used by the RTL.

#### `clock.mode`
For this workflow, the intended setting is `auto`, meaning the clock period is explored by staged sweeps.

#### `clock.max_ns_cap`
The real upper search ceiling for timing exploration.

#### `sources`
A list of RTL globs relative to the variant directory. These must describe **ASIC synthesis RTL only**.

### 6.2 LibreLane / OpenLane policy fields

The `ll_policy` section is where variant-level backend policy belongs.

Typical examples include:

- `sdc`
- `power_fair_tcl`
- `power_activity_tcl`
- `synth_strategy`
- repair-related toggles when intentionally overridden

The guiding principle is simple: use variant-level policy when it genuinely belongs to the design, but do not overcomplicate the user contract.

### 6.3 Floorplanning fields

The `fp` section may be used for floorplanning settings such as:

```yaml
fp:
  core_util: 10
```

---

## 7. Manifest Contract

`manifest.yaml` selects the active design for CI.

A minimal example looks like this:

```yaml
project:
  title: "LibreLane Sky130 ASIC Toolchain"
  author: "Kieran"
  notes: "Variant-driven Sky130/OpenLane2 research workflow"

experiments:
  - variant: designs/my_variant
    enabled: true
```

### Important rules

- `variant` points to the **design directory**, not to individual files.
- Workflow resolves the first enabled experiment if no manual override is supplied,
- Workflow converts the path into a safe CI-friendly variant name when needed.

In practice, this means the manifest acts as the **front door** to the whole flow.

---

## 8. End-to-End CI Flow

The intended high-level flow is:

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

### 8.1 `plan`

This stage resolves the active variant, loads its metadata, builds the initial coarse matrix, and captures summary labels for the explorer.

The key outputs include:

- Safe variant name
- Actual variant path
- Top module
- Clock cap
- Coarse matrix JSON

### 8.2 `coarse-sweep`

The first backend sweep spans the whole timing search space explicitly as a matrix.

Current policy:

- minimum floor: `0 ns`
- maximum: `clock.max_ns_cap`
- default step: `20 ns`

Every point is kept visible as an individual run.

### 8.3 `select-coarse-bracket`

This stage analyses the coarse results and picks a bracket using:

- `upper_pass`: the lowest passing clock period
- `lower_fail`: the highest failing point below that pass

### 8.4 `mid-refine-sweep`

This stage performs a downward-only matrix sweep across the coarse bracket using a default step of `5 ns`.

### 8.5 `select-mid-bracket`

This stage narrows the bracket further in preparation for the finer `1 ns` exploration.

### 8.6 `refine-sweep-1`

This stage sweeps the narrowed region at `1.0 ns` granularity.

### 8.7 `select-refine-1`

This stage selects the next matrix for the `0.5 ns` refinement stage.

### 8.8 `refine-sweep-2`

This stage sweeps the narrowed region at `0.5 ns` granularity.

### 8.9 `select-refine-2`

This stage selects the final matrix for the `0.125 ns` stage.

### 8.10 `refine-sweep-3`

This stage performs the finest intended sweep at `0.125 ns` resolution.

### 8.11 `compare-runs`

This stage downloads all artifacts, classifies the runs, builds summary outputs, chooses the best run according to explorer logic, and generates the static Run Explorer site.

### 8.12 `deploy-run-explorer`

This stage publishes the generated site to `gh-pages`, keeps a per-run snapshot under `runs/<run_id>/`, and updates `latest/` so the newest explorer is easy to access.

---

## 9. Script Responsibilities

The repository works best when each script keeps a clear, limited role.

### `make_clock_matrix.py`
Generates the explicit matrix of clock values for a sweep stage.

### `select_clock_bracket.py`
Chooses a pass/fail bracket from completed runs and emits summary artifacts.

### `select_refine_matrix.py`
Generates the next refine matrix for the smaller-step stages.

### `autoflow.py`
Remains the actual ASIC attempt engine. It should stay focused on backend execution.

### `compare_runs.py`
Builds the summary CSV/Markdown outputs, classifies results, chooses the best run, builds the static site, writes per-run pages, and prepares the bundle used by Pages.

That separation of responsibilities is one of the reasons the repo remains maintainable.

---

## 10. Timing Search Strategy

The timing search strategy is one of the central ideas of the repository.

### 10.1 Why matrix sweeps are used

A matrix sweep has two big advantages:

1. Each tested timing point is visible as its own job and artifact,
2. Refinement logic remains explainable in reports and writeups.

### 10.2 Coarse to fine structure

The intended schedule is:

- coarse sweep: `20 ns`
- mid refine: `5 ns`
- refine 1: `1.0 ns`
- refine 2: `0.5 ns`
- refine 3: `0.125 ns`

### 10.3 Why a cap is necessary

`clock.max_ns_cap` is not cosmetic. It prevents the search from drifting into unrealistic or wasteful timing regions.

A good cap should be:

- High enough to find a passing region,
- Not so high that CI spends time exploring obviously uninteresting points.

### 10.4 Why refinement is bracket-based

Refinement is driven by observed pass/fail evidence. That is more honest than simply tightening around a guess, and it produces a paper trail that is useful in both debugging and dissertation writing.

---

## 11. Run Classification and Status Model

The explorer uses status classes that are intended to be academically honest.

### `PASS`
The run completed cleanly and timing/signoff evidence supports acceptance.

### `TIMING_FAIL`
Timing evidence exists, but setup timing is not met.

### `SIGNOFF_FAIL`
Timing may be acceptable, but signoff checks such as DRC, LVS, or antenna still fail.

### `SIGNOFF_AND_TIMING_FAIL`
Both timing and signoff problems are present.

### `FLOW_FAIL`
Reserved for runtime, tooling, configuration, or evidence-integrity failures such as:

- Missing usable run directory
- Missing timing metrics
- Incomplete artifact state
- Backend failure before valid evidence is produced

This model matters. A configuration/runtime failure should not be misreported as though the design simply “failed timing”.

---

## 12. Best-Run Selection Logic

The selected best run is **not** just the lowest requested clock period.

The intended preference order is:

1. Clean signoff with non-negative setup timing
2. If no full pass exists, signoff-clean runs ahead of signoff-violating ones
3. Lower requested clock period among otherwise comparable runs
4. Setup WNS/TNS as tie-breakers

This is important because it keeps the selected result aligned with engineering integrity rather than chasing the most aggressive clock value at any cost.

---

## 13. Artifact Philosophy

Artifacts are intentionally rich. The point is to preserve enough evidence to support debugging, comparison, and writeup.

### 13.1 Attempt artifacts

Typical backend artifacts may include:

- `metrics.csv`
- `metrics.md`
- `metrics_raw.json`
- `run_meta.json`
- `attempt_started.txt`
- `attempt_manifest.json`
- `renders/`
- `final/gds/`
- backend run trees where available

### 13.2 Bracket summary artifacts

Bracket selection stages may emit:

- `bracket_summary.md`
- `bracket_summary.json`

These help explain why a new refine matrix was chosen.

### 13.3 Failure diagnostics

When a run lands in `FLOW_FAIL`, the flow is intended to preserve a useful diagnostic summary rather than simply collapsing into a vague failure state.

That is especially valuable during development, because it helps distinguish:

- Script/configuration failure
- Backend tool failure
- Missing outputs
- Design or timing issues

---

## 14. GitHub Pages and Site Publishing Policy

GitHub Pages is used for the **Run Explorer**.

### What gets published

The published site is intended to include:

- Homepage overview
- Run comparison table
- Per-run detail pages
- Lightweight copies of selected outputs
- Run snapshots under `runs/<run_id>/`

### What does not get published

Large backend trees and bulky implementation outputs should stay in GitHub Actions artifacts rather than being mirrored in full to Pages.

This keeps the published site faster, lighter, and easier to maintain.

---

## 15. Run Explorer Design

The explorer is meant to be a practical engineering dashboard rather than a decorative landing page.

### Homepage responsibilities

The homepage is intended to present:

- Run overview
- Summary settings
- All-runs comparison table

The comparison table is where timing points are compared clearly across status, timing, physical, power, and artifact availability.

### Per-run page responsibilities

Each run page is intended to show:

- Clean run metadata
- Grouped metrics by category
- Useful buttons and output links
- Failure diagnostic section when needed

### External tools

The explorer may link outward to:

- External GDS viewer homepage (TinyTapeout GDS Viewer)

---

## 16. Metrics and Units

The Run Explorer should use explicit units consistently.

### Timing

- **WNS** = `ns` = nanoseconds
- **TNS** = `ns` = nanoseconds
- requested clock period = `ns`
- reported clock period = `ns`

### Physical

- **Core Area** = `μm²` = square micrometres
- die area = typically `μm²`
- utilisation = percentage or ratio depending on source metric

### Power

- **Total Power** = `W` = watts

### Signoff and integrity

- **IR Drop** = `V` = volts
- DRC/LVS/Antenna counts = count-based integrity metrics

Being explicit about units is not a minor formatting issue. It improves clarity for engineering review and for dissertation screenshots.

---

## 17. How to Add a New Design

### Step 1: Create a new variant folder

Example:

```text
designs/my_alu/
├─ variant.yaml
└─ src/
   ├─ top.v
   ├─ datapath.v
   └─ control.v
```

### Step 2: Place synthesis RTL under `src/`

Only real ASIC RTL should go here.

### Step 3: Fill in `variant.yaml`

At minimum, make sure these are correct:

- `top_module`
- `clock.port`
- `clock.max_ns_cap`
- `sources`

### Step 4: Register the variant in `manifest.yaml`

Enable the new experiment.

### Step 5: Commit and push

The normal usage model is to push to `main` and let the workflow run automatically.

---

## 18. How to Run the Flow

### Automatic run on push

This is the normal mode:

1. Edit the design files
2. Update `variant.yaml`
3. Select the variant in `manifest.yaml`
4. Push to `main`

### Manual run from GitHub Actions

Manual dispatch is useful when you want to rerun the flow without creating a new commit.

---

## 19. How to Interpret Results

### If backend fails

That usually means the design is at least selected correctly, but the ASIC flow still encountered implementation, timing, or backend issues.

### If timing fails but signoff is clean

It is a real timing result, not a repo failure. It means the clock is probably too aggressive for the design at that point.
