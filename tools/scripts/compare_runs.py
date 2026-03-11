#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


TT_GDS_VIEWER_URL = "https://gds-viewer.tinytapeout.com/"


def build_theme_widget(button_id: str, panel_id: str) -> str:
    return f"""
<div class="theme-control">
  <button class="theme-launch" id="{button_id}" type="button" aria-expanded="false" aria-controls="{panel_id}">
    Appearance ⚙️
  </button>

  <div class="theme-widget" id="{panel_id}" hidden>
    <div class="theme-widget-body">
      <h3>Page appearance</h3>

      <div class="theme-row">
        <label for="{panel_id}_preset">Theme preset</label>
        <select id="{panel_id}_preset">
          <option value="canvas">Canvas Beige</option>
          <option value="darkwood">Dark Wood</option>
          <option value="forest">Forest</option>
          <option value="slate">Slate</option>
        </select>
      </div>

      <div class="theme-inline">
        <div class="theme-row">
          <label for="{panel_id}_bg">Base background</label>
          <input type="color" id="{panel_id}_bg" value="#f4ecdf">
        </div>
        <div class="theme-row">
          <label for="{panel_id}_accent">Accent</label>
          <input type="color" id="{panel_id}_accent" value="#8b5e3c">
        </div>
      </div>

      <div class="theme-inline">
        <div class="theme-row">
          <label for="{panel_id}_grad1">Gradient 1</label>
          <input type="color" id="{panel_id}_grad1" value="#f8f1e7">
        </div>
        <div class="theme-row">
          <label for="{panel_id}_grad2">Gradient 2</label>
          <input type="color" id="{panel_id}_grad2" value="#efe4d3">
        </div>
      </div>

      <div class="theme-btn-row">
        <button id="{panel_id}_save" type="button">Save</button>
        <button id="{panel_id}_reset" type="button">Reset</button>
      </div>
    </div>
  </div>
</div>
"""


def build_theme_script(button_id: str, panel_id: str, storage_key: str) -> str:
    return f"""
<script>
(function () {{
  const root = document.documentElement;
  const button = document.getElementById("{button_id}");
  const panel = document.getElementById("{panel_id}");
  if (!root || !button || !panel) return;
  document.body.appendChild(panel);

  const presetTheme = document.getElementById("{panel_id}_preset");
  const bgColor = document.getElementById("{panel_id}_bg");
  const accentColor = document.getElementById("{panel_id}_accent");
  const grad1 = document.getElementById("{panel_id}_grad1");
  const grad2 = document.getElementById("{panel_id}_grad2");
  const saveTheme = document.getElementById("{panel_id}_save");
  const resetTheme = document.getElementById("{panel_id}_reset");

  const presets = {{
    canvas: {{
      "--bg": "#f4ecdf",
      "--bg-grad-1": "#f8f1e7",
      "--bg-grad-2": "#efe4d3",
      "--panel": "rgba(255, 250, 243, 0.82)",
      "--panel-strong": "rgba(255, 248, 238, 0.94)",
      "--text": "#2f2418",
      "--muted": "#716250",
      "--accent": "#8b5e3c",
      "--accent-2": "#b6845e"
    }},
    darkwood: {{
      "--bg": "#1b1712",
      "--bg-grad-1": "#241c14",
      "--bg-grad-2": "#34281d",
      "--panel": "rgba(44, 35, 26, 0.86)",
      "--panel-strong": "rgba(50, 40, 30, 0.94)",
      "--text": "#f3e7d6",
      "--muted": "#c1b09a",
      "--accent": "#e1b78a",
      "--accent-2": "#d39f68"
    }},
    forest: {{
      "--bg": "#e9efe7",
      "--bg-grad-1": "#f3f7f1",
      "--bg-grad-2": "#d9e7d5",
      "--panel": "rgba(248, 252, 247, 0.86)",
      "--panel-strong": "rgba(252, 255, 251, 0.94)",
      "--text": "#203025",
      "--muted": "#557060",
      "--accent": "#4f7a5c",
      "--accent-2": "#789d83"
    }},
    slate: {{
      "--bg": "#e7ebf0",
      "--bg-grad-1": "#f3f6fa",
      "--bg-grad-2": "#d7dde6",
      "--panel": "rgba(250, 252, 255, 0.84)",
      "--panel-strong": "rgba(255, 255, 255, 0.94)",
      "--text": "#1d2732",
      "--muted": "#5c6d7d",
      "--accent": "#496a8a",
      "--accent-2": "#7292b0"
    }}
  }};

  function applyVars(vars) {{
    Object.entries(vars).forEach(([key, value]) => {{
      root.style.setProperty(key, value);
    }});
  }}

  function toHex(color) {{
    if (!color) return null;
    if (color.startsWith("#")) return color;

    const m = color.match(/^rgb\\((\\d+),\\s*(\\d+),\\s*(\\d+)\\)$/);
    if (!m) return null;

    return "#" + [m[1], m[2], m[3]]
      .map(x => Number(x).toString(16).padStart(2, "0"))
      .join("");
  }}

  function syncInputsFromComputed() {{
    const styles = getComputedStyle(root);
    bgColor.value = toHex(styles.getPropertyValue("--bg").trim()) || "#f4ecdf";
    grad1.value = toHex(styles.getPropertyValue("--bg-grad-1").trim()) || "#f8f1e7";
    grad2.value = toHex(styles.getPropertyValue("--bg-grad-2").trim()) || "#efe4d3";
    accentColor.value = toHex(styles.getPropertyValue("--accent").trim()) || "#8b5e3c";
  }}

  function applyCustomTheme() {{
    applyVars({{
      "--bg": bgColor.value,
      "--bg-grad-1": grad1.value,
      "--bg-grad-2": grad2.value,
      "--accent": accentColor.value,
      "--accent-2": accentColor.value
    }});
  }}

  function saveSettings() {{
    const settings = {{
      preset: presetTheme.value,
      bg: bgColor.value,
      grad1: grad1.value,
      grad2: grad2.value,
      accent: accentColor.value
    }};
    localStorage.setItem("{storage_key}", JSON.stringify(settings));
  }}

  function loadSettings() {{
    const raw = localStorage.getItem("{storage_key}");
    if (!raw) return;

    try {{
      const s = JSON.parse(raw);

      if (s.preset && presets[s.preset]) {{
        presetTheme.value = s.preset;
        applyVars(presets[s.preset]);
      }}

      if (s.bg) bgColor.value = s.bg;
      if (s.grad1) grad1.value = s.grad1;
      if (s.grad2) grad2.value = s.grad2;
      if (s.accent) accentColor.value = s.accent;

      applyCustomTheme();
    }} catch (e) {{
      console.warn("Failed to load saved theme settings", e);
    }}
  }}

  function positionPanel() {{
    if (panel.hidden) return;

    const rect = button.getBoundingClientRect();
    const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 0;
    const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
    const margin = 12;
    const panelWidth = Math.min(320, Math.max(260, viewportWidth - (margin * 2)));

    panel.style.width = panelWidth + "px";
    panel.style.maxWidth = panelWidth + "px";

    const panelHeight = panel.offsetHeight || 320;
    let left = rect.right - panelWidth;
    left = Math.max(margin, Math.min(left, viewportWidth - panelWidth - margin));

    let top = rect.bottom + 12;
    if (top + panelHeight > viewportHeight - margin) {{
      top = Math.max(margin, rect.top - panelHeight - 12);
    }}

    panel.style.left = left + "px";
    panel.style.top = top + "px";
  }}

  function openPanel() {{
    panel.hidden = false;
    panel.classList.add("open");
    button.setAttribute("aria-expanded", "true");
    positionPanel();
  }}

  function closePanel() {{
    panel.hidden = true;
    panel.classList.remove("open");
    button.setAttribute("aria-expanded", "false");
  }}

  function togglePanel() {{
    if (panel.hidden) {{
      openPanel();
    }} else {{
      closePanel();
    }}
  }}

  button.addEventListener("click", function (event) {{
    event.stopPropagation();
    togglePanel();
  }});

  panel.addEventListener("click", function (event) {{
    event.stopPropagation();
  }});

  document.addEventListener("click", function () {{
    closePanel();
  }});

  document.addEventListener("keydown", function (event) {{
    if (event.key === "Escape") {{
      closePanel();
    }}
  }});

  window.addEventListener("resize", function () {{
    if (!panel.hidden) positionPanel();
  }});

  window.addEventListener("scroll", function () {{
    if (!panel.hidden) positionPanel();
  }}, true);

  presetTheme.addEventListener("change", () => {{
    const preset = presets[presetTheme.value];
    applyVars(preset);
    syncInputsFromComputed();
    saveSettings();
  }});

  [bgColor, grad1, grad2, accentColor].forEach(el => {{
    el.addEventListener("input", () => {{
      applyCustomTheme();
      saveSettings();
    }});
  }});

  saveTheme.addEventListener("click", saveSettings);

  resetTheme.addEventListener("click", () => {{
    localStorage.removeItem("{storage_key}");
    location.reload();
  }});

  syncInputsFromComputed();
  loadSettings();
  closePanel();
}})();
</script>
"""


def to_float(v: Any) -> Optional[float]:
    try:
        if v in (None, "", "None"):
            return None
        return float(v)
    except Exception:
        return None


def fmt_num(v: Any, digits: int = 3) -> str:
    f = to_float(v)
    if f is None:
        return ""
    return f"{f:.{digits}f}"


def read_csv_row(path: Path) -> Optional[Dict[str, str]]:
    if not path.exists():
        return None
    with path.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows[0] if rows else None


def signoff_clean(row: Dict[str, str]) -> bool:
    for key in ("drc_errors", "lvs_errors", "antenna_violations"):
        v = to_float(row.get(key))
        if v is not None and v != 0.0:
            return False
    return True


def timing_ok(row: Dict[str, str]) -> bool:
    swns = to_float(row.get("setup_wns_ns"))
    stns = to_float(row.get("setup_tns_ns"))
    return swns is not None and stns is not None and swns >= 0.0 and stns >= 0.0


def classify_status(row: Dict[str, str]) -> str:
    raw_status = str(row.get("status", "")).strip().upper()
    if raw_status in {"FLOW_FAIL", "INCOMPLETE"}:
        return "FLOW_FAIL"

    swns = to_float(row.get("setup_wns_ns"))
    stns = to_float(row.get("setup_tns_ns"))
    timing_present = swns is not None and stns is not None
    if not timing_present:
        return "FLOW_FAIL"

    clean = signoff_clean(row)
    ok = timing_ok(row)

    if clean and ok:
        return "PASS"
    if clean and not ok:
        return "TIMING_FAIL"
    if (not clean) and ok:
        return "SIGNOFF_FAIL"
    return "SIGNOFF_AND_TIMING_FAIL"


def explain_row(row: Dict[str, str]) -> str:
    raw_status = str(row.get("status", "")).strip().upper()
    if raw_status in {"FLOW_FAIL", "INCOMPLETE"}:
        return "Flow failed before valid timing metrics were produced."

    reasons: List[str] = []

    swns = to_float(row.get("setup_wns_ns"))
    stns = to_float(row.get("setup_tns_ns"))
    drc = to_float(row.get("drc_errors"))
    lvs = to_float(row.get("lvs_errors"))
    ant = to_float(row.get("antenna_violations"))

    if drc not in (None, 0.0):
        reasons.append(f"DRC errors = {int(drc) if drc.is_integer() else drc}")
    if lvs not in (None, 0.0):
        reasons.append(f"LVS errors = {int(lvs) if lvs.is_integer() else lvs}")
    if ant not in (None, 0.0):
        reasons.append(f"antenna violations = {int(ant) if ant.is_integer() else ant}")
    if swns is None or swns < 0.0:
        reasons.append(f"setup WNS = {fmt_num(swns)} ns")
    if stns is None or stns < 0.0:
        reasons.append(f"setup TNS = {fmt_num(stns)} ns")

    if not reasons:
        return "Clean signoff and non-negative setup timing."
    return "; ".join(reasons)


def best_sort_key(row: Dict[str, str]) -> Tuple[Any, ...]:
    clean = signoff_clean(row)
    timing = timing_ok(row)
    clk = to_float(row.get("clock_ns"))
    swns = to_float(row.get("setup_wns_ns"))
    stns = to_float(row.get("setup_tns_ns"))
    ant = to_float(row.get("antenna_violations"))
    drc = to_float(row.get("drc_errors"))
    lvs = to_float(row.get("lvs_errors"))
    penalty = sum(v or 0.0 for v in (ant, drc, lvs))

    return (
        0 if clean and timing else 1,
        0 if clean else 1,
        penalty,
        clk if clk is not None else 1e12,
        -(swns if swns is not None else -1e12),
        -(stns if stns is not None else -1e12),
    )


def first_gds_path(base_dir: Path) -> Optional[Path]:
    gds_dir = base_dir / "final" / "gds"
    if not gds_dir.exists():
        return None
    candidates = sorted(gds_dir.glob("*.gds"))
    return candidates[0] if candidates else None


def copy_tree_if_exists(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    if src.is_dir():
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def collect_rows(artifacts_root: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    seen: set[Path] = set()

    patterns = [
        "**/ci_out/*/clk_*ns_*/metrics.csv",
        "**/*/clk_*ns_*/metrics.csv",
    ]

    for pattern in patterns:
        for csv_path in sorted(artifacts_root.glob(pattern)):
            if csv_path in seen:
                continue
            seen.add(csv_path)

            row = read_csv_row(csv_path)
            if not row:
                continue

            base_dir = csv_path.parent
            meta_path = base_dir / "run_meta.json"
            meta: Dict[str, Any] = {}
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))

            row["_artifact"] = meta.get("artifact_name", "")
            row["_variant"] = meta.get("variant", base_dir.parent.name)
            row["_run_dir"] = base_dir.name
            row["_base_dir"] = str(base_dir)
            row["_metrics_csv"] = str(csv_path.relative_to(artifacts_root))
            row["_metrics_raw"] = (
                str((base_dir / "metrics_raw.json").relative_to(artifacts_root))
                if (base_dir / "metrics_raw.json").exists()
                else ""
            )
            row["_gds_dir"] = (
                str((base_dir / "final" / "gds").relative_to(artifacts_root))
                if (base_dir / "final" / "gds").exists()
                else ""
            )
            row["status"] = classify_status(row)
            row["selection_reason"] = explain_row(row)

            gds_path = first_gds_path(base_dir)
            row["_gds_path"] = str(gds_path) if gds_path else ""
            row["_gds_name"] = gds_path.name if gds_path else ""
            rows.append(row)

    return rows


def write_summary_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    fieldnames = [
        "_variant",
        "_run_dir",
        "_artifact",
        "clock_ns",
        "clock_ns_reported",
        "setup_wns_ns",
        "setup_tns_ns",
        "hold_wns_ns",
        "hold_tns_ns",
        "core_area_um2",
        "die_area_um2",
        "instance_count",
        "utilization_pct",
        "power_total_W",
        "power_internal_W",
        "power_switching_W",
        "power_leakage_W",
        "drc_errors",
        "lvs_errors",
        "antenna_violations",
        "ir_drop_worst_V",
        "status",
        "selection_reason",
        "_metrics_csv",
        "_metrics_raw",
        "_gds_dir",
        "_gds_name",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def md_escape(text: Any) -> str:
    s = "" if text is None else str(text)
    return s.replace("|", "\\|").replace("\n", " ")


def write_summary_md(path: Path, rows: List[Dict[str, str]]) -> None:
    lines: List[str] = []
    lines.append("## Best run selection")
    lines.append("")
    lines.append("Selection order:")
    lines.append("1. Clean signoff plus non-negative setup timing wins.")
    lines.append("2. If no full PASS exists, clean signoff wins over signoff violations.")
    lines.append("3. Among comparable runs, lower requested clock period is preferred.")
    lines.append("4. Setup WNS/TNS are used as tie-breakers.")
    lines.append("")

    if rows:
        best = sorted(rows, key=best_sort_key)[0]
        lines.append("### Chosen best run")
        lines.append("")
        lines.append(f"- Variant: `{md_escape(best.get('_variant'))}`")
        lines.append(f"- Run: `{md_escape(best.get('_run_dir'))}`")
        lines.append(f"- Status: `{md_escape(best.get('status'))}`")
        lines.append("")
    else:
        lines.append("No runs collected.")
        lines.append("")

    lines.append("## All runs")
    lines.append("")
    lines.append("| Variant | Run | Clock (ns) | Setup WNS | Setup TNS | DRC | LVS | Antenna | Status | Remarks |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---|---|")

    for idx, row in enumerate(sorted(rows, key=best_sort_key)):
        remarks = row.get("selection_reason", "")
        if idx == 0:
            remarks = f"SELECTED — {remarks}"
        lines.append(
            f"| {md_escape(row.get('_variant'))} | {md_escape(row.get('_run_dir'))} | {md_escape(row.get('clock_ns'))} | "
            f"{md_escape(row.get('setup_wns_ns'))} | {md_escape(row.get('setup_tns_ns'))} | {md_escape(row.get('drc_errors'))} | "
            f"{md_escape(row.get('lvs_errors'))} | {md_escape(row.get('antenna_violations'))} | {md_escape(row.get('status'))} | {md_escape(remarks)} |"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def copy_named_gds(src: Path, dest_dir: Path, run_dir_name: str) -> str:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dst_name = f"{run_dir_name}.gds"
    shutil.copy2(src, dest_dir / dst_name)
    return dst_name


def write_best_json(path: Path, rows: List[Dict[str, str]]) -> Dict[str, Any]:
    best = sorted(rows, key=best_sort_key)[0] if rows else {}
    path.write_text(json.dumps(best, indent=2), encoding="utf-8")
    return best


def package_best_bundle(best_bundle_dir: Path, best: Dict[str, Any]) -> None:
    best_bundle_dir.mkdir(parents=True, exist_ok=True)
    if not best:
        return

    base_dir = Path(best["_base_dir"])

    for name in ("metrics.csv", "metrics_raw.json", "run_meta.json", "viewer.html", "index.html", "README.txt"):
        src = base_dir / name
        if src.exists():
            shutil.copy2(src, best_bundle_dir / name)

    copy_tree_if_exists(base_dir / "renders", best_bundle_dir / "renders")
    copy_tree_if_exists(base_dir / "final" / "gds", best_bundle_dir / "final" / "gds")
    copy_tree_if_exists(base_dir / "openlane_run", best_bundle_dir / "openlane_run")

    gds_src = Path(best["_gds_path"]) if best.get("_gds_path") else None
    if gds_src and gds_src.exists():
        copy_named_gds(gds_src, best_bundle_dir, best.get("_run_dir", "best_run"))

    manifest = {
        "variant": best.get("_variant"),
        "run_dir": best.get("_run_dir"),
        "clock_ns": best.get("clock_ns"),
        "status": best.get("status"),
        "selection_reason": best.get("selection_reason"),
        "gds_file": f"{best.get('_run_dir', 'best_run')}.gds" if best.get("_gds_path") else "",
    }
    (best_bundle_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def status_class(status: str) -> str:
    s = (status or "").upper()
    if s == "PASS":
        return "pass"
    if s == "TIMING_FAIL":
        return "timing"
    if s == "SIGNOFF_FAIL":
        return "signoff"
    if s == "SIGNOFF_AND_TIMING_FAIL":
        return "mixed"
    return "flow"


def badge_html(status: str) -> str:
    label = html.escape(status or "")
    cls = status_class(status)
    return f'<span class="badge {cls}">{label}</span>'


def build_site(site_root: Path, rows: List[Dict[str, str]]) -> None:
    site_root.mkdir(parents=True, exist_ok=True)
    runs_root = site_root / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)

    sorted_rows = sorted(rows, key=best_sort_key)

    site_css = """
:root{
  color-scheme: light dark;

  --bg: #f4ecdf;
  --bg-grad-1: #f8f1e7;
  --bg-grad-2: #efe4d3;
  --panel: rgba(255, 250, 243, 0.82);
  --panel-strong: rgba(255, 248, 238, 0.94);
  --panel-soft: rgba(255, 255, 255, 0.46);
  --border: rgba(116, 92, 62, 0.16);
  --border-strong: rgba(116, 92, 62, 0.22);
  --text: #2f2418;
  --muted: #716250;
  --accent: #8b5e3c;
  --accent-2: #b6845e;
  --shadow: 0 18px 45px rgba(110, 84, 53, 0.12);

  --pass-bg: rgba(73, 143, 96, 0.14);
  --pass-fg: #285a38;
  --pass-br: rgba(73, 143, 96, 0.28);

  --timing-bg: rgba(190, 143, 45, 0.16);
  --timing-fg: #7d5b13;
  --timing-br: rgba(190, 143, 45, 0.28);

  --signoff-bg: rgba(180, 83, 72, 0.14);
  --signoff-fg: #7b2f28;
  --signoff-br: rgba(180, 83, 72, 0.26);

  --mixed-bg: rgba(135, 96, 166, 0.14);
  --mixed-fg: #5b3f77;
  --mixed-br: rgba(135, 96, 166, 0.24);

  --flow-bg: rgba(120, 115, 108, 0.14);
  --flow-fg: #504a44;
  --flow-br: rgba(120, 115, 108, 0.22);

  --tag-bg: rgba(139, 94, 60, 0.10);
  --tag-fg: #7a5235;
  --tag-br: rgba(139, 94, 60, 0.18);

  --radius-xl: 28px;
  --radius-lg: 20px;
  --radius-md: 14px;
}

@media (prefers-color-scheme: dark) {
  :root{
    --bg: #1b1712;
    --bg-grad-1: #1e1913;
    --bg-grad-2: #2a2219;
    --panel: rgba(44, 35, 26, 0.86);
    --panel-strong: rgba(50, 40, 30, 0.94);
    --panel-soft: rgba(255, 255, 255, 0.04);
    --border: rgba(219, 194, 161, 0.10);
    --border-strong: rgba(219, 194, 161, 0.18);
    --text: #f3e7d6;
    --muted: #c1b09a;
    --accent: #e1b78a;
    --accent-2: #d39f68;
    --shadow: 0 20px 50px rgba(0, 0, 0, 0.34);

    --pass-bg: rgba(84, 160, 109, 0.18);
    --pass-fg: #bfe8c8;
    --pass-br: rgba(84, 160, 109, 0.34);

    --timing-bg: rgba(202, 156, 58, 0.18);
    --timing-fg: #f5d48c;
    --timing-br: rgba(202, 156, 58, 0.34);

    --signoff-bg: rgba(194, 95, 84, 0.18);
    --signoff-fg: #ffb9b0;
    --signoff-br: rgba(194, 95, 84, 0.34);

    --mixed-bg: rgba(153, 113, 187, 0.18);
    --mixed-fg: #e2c2ff;
    --mixed-br: rgba(153, 113, 187, 0.32);

    --flow-bg: rgba(131, 126, 120, 0.18);
    --flow-fg: #d8d1ca;
    --flow-br: rgba(131, 126, 120, 0.28);

    --tag-bg: rgba(225, 183, 138, 0.12);
    --tag-fg: #f0d2b2;
    --tag-br: rgba(225, 183, 138, 0.22);
  }
}

*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{
  background:
    radial-gradient(circle at top left, var(--bg-grad-1) 0%, transparent 36%),
    radial-gradient(circle at top right, var(--bg-grad-2) 0%, transparent 28%),
    linear-gradient(180deg, var(--bg-grad-1) 0%, var(--bg) 100%);
  color:var(--text);
  font:15px/1.6 Inter, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:1480px;margin:0 auto;padding:28px 20px 40px}
.hero{
  position:relative;
  background:
    linear-gradient(135deg, rgba(255,255,255,0.14), rgba(255,255,255,0.02)),
    var(--panel-strong);
  border:1px solid var(--border-strong);
  border-radius:var(--radius-xl);
  padding:30px;
  box-shadow:var(--shadow);
  backdrop-filter: blur(12px);
  margin-bottom:22px;
}
.hero-head{
  display:flex;
  justify-content:space-between;
  align-items:flex-start;
  gap:16px;
}
.hero-copy{
  min-width:0;
}
.hero h1{margin:0 0 12px;font-size:34px;line-height:1.1;letter-spacing:-0.02em}
.hero p{margin:0;color:var(--muted);max-width:980px}
.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:18px}
.card{
  background:var(--panel);
  border:1px solid var(--border);
  border-radius:var(--radius-lg);
  padding:22px;
  box-shadow:var(--shadow);
  backdrop-filter: blur(12px);
}
.card h2,.card h3{margin:0 0 12px;letter-spacing:-0.01em}
.card p{margin:0 0 10px}
.rules{grid-column:span 5}
.best{grid-column:span 7}
.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-top:14px}
.stat{
  background:var(--panel-soft);
  border:1px solid var(--border);
  border-radius:var(--radius-md);
  padding:16px;
}
.stat .label{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.08em}
.stat .value{font-size:28px;font-weight:700;margin-top:4px}
.list-clean{margin:0;padding-left:20px}
.list-clean li{margin:8px 0}
.table-card{margin-top:18px;padding:0;overflow:hidden}
.table-head{
  display:flex;
  justify-content:space-between;
  align-items:center;
  padding:18px 20px;
  border-bottom:1px solid var(--border)
}
.table-head h2{margin:0;font-size:20px}
.table-wrap{overflow:auto}
table{width:100%;border-collapse:collapse;min-width:1380px}
th,td{padding:14px 16px;border-bottom:1px solid var(--border);vertical-align:top}
th{
  position:sticky;
  top:0;
  background:rgba(255,248,240,0.92);
  color:var(--text);
  text-align:left;
  font-size:13px;
  letter-spacing:.03em;
  backdrop-filter: blur(10px);
}
@media (prefers-color-scheme: dark) {
  th{background:rgba(57,45,34,0.94)}
}
tr:hover td{background:rgba(255,255,255,0.06)}
.selected-row td{background:rgba(139,94,60,0.08)}
.badge{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  min-width:100px;
  padding:6px 10px;
  border-radius:999px;
  font-size:12px;
  font-weight:700;
  letter-spacing:.02em;
  border:1px solid transparent
}
.badge.pass{background:var(--pass-bg);color:var(--pass-fg);border-color:var(--pass-br)}
.badge.timing{background:var(--timing-bg);color:var(--timing-fg);border-color:var(--timing-br)}
.badge.signoff{background:var(--signoff-bg);color:var(--signoff-fg);border-color:var(--signoff-br)}
.badge.mixed{background:var(--mixed-bg);color:var(--mixed-fg);border-color:var(--mixed-br)}
.badge.flow{background:var(--flow-bg);color:var(--flow-fg);border-color:var(--flow-br)}
.tag{
  display:inline-block;
  padding:4px 10px;
  border-radius:999px;
  background:var(--tag-bg);
  border:1px solid var(--tag-br);
  color:var(--tag-fg);
  font-size:12px;
  font-weight:700
}
.actions{display:flex;gap:8px;flex-wrap:wrap}
.btn{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  padding:8px 12px;
  border-radius:10px;
  border:1px solid rgba(139,94,60,0.20);
  background:rgba(139,94,60,0.08);
  color:var(--text);
  font-weight:600;
  font-size:13px
}
.btn.secondary{
  border-color:var(--border-strong);
  background:rgba(255,255,255,0.08);
  color:var(--text)
}
.muted{color:var(--muted)}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.small{font-size:13px}
.section-note{
  color:var(--muted);
  font-size:14px;
  margin-top:6px;
}

.theme-control{
  position:relative;
  flex:0 0 auto;
  z-index:40;
}
.theme-launch{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  min-width:148px;
  padding:10px 14px;
  border-radius:12px;
  border:1px solid var(--border-strong);
  background:var(--panel-soft);
  color:var(--text);
  font:600 13px/1.2 Inter, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
  cursor:pointer;
  box-shadow:var(--shadow);
}
.theme-widget{
  position:fixed;
  top:72px;
  right:24px;
  width:320px;
  max-width:min(320px, calc(100vw - 24px));
  z-index:99999;
  pointer-events:auto;
}
.theme-widget[hidden]{display:none !important;}

.theme-widget-body{
  padding:16px;
  border-radius:16px;
  border:1px solid var(--border-strong);
  background:var(--panel-strong);
  backdrop-filter:blur(12px);
  box-shadow:var(--shadow);
}
.theme-widget h3{
  margin:0 0 12px;
  font-size:16px;
}
.theme-row{
  display:grid;
  grid-template-columns:1fr;
  gap:6px;
  margin-bottom:12px;
}
.theme-row label{
  font-size:12px;
  opacity:.85;
  font-weight:600;
}
.theme-row input,
.theme-row select,
.theme-row button{
  width:100%;
  padding:8px 10px;
  border-radius:10px;
  border:1px solid var(--border-strong);
  background:var(--panel-soft);
  color:var(--text);
  font:inherit;
}
.theme-inline{
  display:grid;
  grid-template-columns:1fr 1fr;
  gap:8px;
}
.theme-btn-row{
  display:grid;
  grid-template-columns:1fr 1fr;
  gap:8px;
  margin-top:6px;
}
@media (max-width:1080px){
  .rules,.best{grid-column:1 / -1}
  .stats{grid-template-columns:repeat(2,minmax(0,1fr))}
  .hero h1{font-size:28px}
}
@media (max-width:780px){
  .hero-head{
    flex-direction:column;
    align-items:stretch;
  }
  .theme-control{
    align-self:flex-end;
  }
  .theme-widget{
    width:min(320px, calc(100vw - 24px));
  }
}
@media (max-width:680px){
  .stats{grid-template-columns:1fr}
  .theme-inline{
    grid-template-columns:1fr;
  }
}
"""

    for row in sorted_rows:
        slug = f"{row.get('_variant', 'variant').replace('/', '_')}__{row.get('_run_dir', 'run')}"
        row["_site_slug"] = slug
        run_dir = runs_root / slug
        run_dir.mkdir(parents=True, exist_ok=True)

        base_dir = Path(row["_base_dir"])
        gds_name = ""

        gds_src = Path(row["_gds_path"]) if row.get("_gds_path") else None
        if gds_src and gds_src.exists():
            gds_name = copy_named_gds(gds_src, run_dir, row.get("_run_dir", "layout"))
            row["_site_gds"] = gds_name

        for name in ("metrics.csv", "metrics_raw.json", "run_meta.json", "viewer.html", "README.txt"):
            src = base_dir / name
            if src.exists():
                shutil.copy2(src, run_dir / name)

        copy_tree_if_exists(base_dir / "renders", run_dir / "renders")
        copy_tree_if_exists(base_dir / "final" / "gds", run_dir / "final" / "gds")

        title = html.escape(f"{row.get('_variant','')} — {row.get('_run_dir','')}")
        remarks = html.escape(row.get("selection_reason", ""))
        gds_link = f'<a class="btn" href="{html.escape(gds_name)}">Download GDS</a>' if gds_name else '<span class="muted">No GDS copied</span>'
        metrics_link = f'<a class="btn secondary" href="metrics.csv">Open metrics.csv</a>' if (run_dir / "metrics.csv").exists() else ""
        raw_metrics_link = f'<a class="btn secondary" href="metrics_raw.json">Open metrics_raw.json</a>' if (run_dir / "metrics_raw.json").exists() else ""
        viewer_link = f'<a class="btn secondary" href="{TT_GDS_VIEWER_URL}" target="_blank" rel="noopener noreferrer">Open GDS Viewer</a>'

        theme_widget = build_theme_widget("runAppearanceButton", "runThemeWidget")
        theme_script = build_theme_script("runAppearanceButton", "runThemeWidget", "asic-flow-theme")

        run_html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <style>{site_css}</style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <div class="hero-head">
        <div class="hero-copy">
          <h1>{title}</h1>
          <p>Per-run detail page with timing, area, power, signoff, downloadable layout data, and a manual GDS viewer link.</p>
        </div>
        {theme_widget}
      </div>
    </div>

    <div class="grid">
      <section class="card rules">
        <h2>Run status</h2>
        <p>{badge_html(row.get('status',''))}</p>
        <p><strong>Remarks:</strong> {remarks}</p>
        <p><a class="btn secondary" href="../../index.html">Back to ASIC Flow Run Explorer</a></p>
      </section>

      <section class="card best">
        <h2>Download &amp; Tools</h2>
        <div class="actions">
          {gds_link}
          {metrics_link}
          {raw_metrics_link}
          {viewer_link}
        </div>
      </section>
    </div>

    <section class="card table-card">
      <div class="table-head"><h2>Timing</h2></div>
      <div class="table-wrap">
        <table>
          <tr><th>Metric</th><th>Value</th></tr>
          <tr><td>clock_ns</td><td>{html.escape(str(row.get('clock_ns', '')))}</td></tr>
          <tr><td>clock_ns_reported</td><td>{html.escape(str(row.get('clock_ns_reported', '')))}</td></tr>
          <tr><td>setup_wns_ns</td><td>{html.escape(str(row.get('setup_wns_ns', '')))}</td></tr>
          <tr><td>setup_tns_ns</td><td>{html.escape(str(row.get('setup_tns_ns', '')))}</td></tr>
          <tr><td>hold_wns_ns</td><td>{html.escape(str(row.get('hold_wns_ns', '')))}</td></tr>
          <tr><td>hold_tns_ns</td><td>{html.escape(str(row.get('hold_tns_ns', '')))}</td></tr>
          <tr><td>status</td><td>{html.escape(str(row.get('status', '')))}</td></tr>
        </table>
      </div>
    </section>

    <section class="card table-card">
      <div class="table-head"><h2>Area and power</h2></div>
      <div class="table-wrap">
        <table>
          <tr><th>Metric</th><th>Value</th></tr>
          <tr><td>core_area_um2</td><td>{html.escape(str(row.get('core_area_um2', '')))}</td></tr>
          <tr><td>die_area_um2</td><td>{html.escape(str(row.get('die_area_um2', '')))}</td></tr>
          <tr><td>instance_count</td><td>{html.escape(str(row.get('instance_count', '')))}</td></tr>
          <tr><td>utilization_pct</td><td>{html.escape(str(row.get('utilization_pct', '')))}</td></tr>
          <tr><td>wire_length_um</td><td>{html.escape(str(row.get('wire_length_um', '')))}</td></tr>
          <tr><td>vias_count</td><td>{html.escape(str(row.get('vias_count', '')))}</td></tr>
          <tr><td>power_total_W</td><td>{html.escape(str(row.get('power_total_W', '')))}</td></tr>
          <tr><td>power_internal_W</td><td>{html.escape(str(row.get('power_internal_W', '')))}</td></tr>
          <tr><td>power_switching_W</td><td>{html.escape(str(row.get('power_switching_W', '')))}</td></tr>
          <tr><td>power_leakage_W</td><td>{html.escape(str(row.get('power_leakage_W', '')))}</td></tr>
        </table>
      </div>
    </section>

    <section class="card table-card">
      <div class="table-head"><h2>Signoff and physical</h2></div>
      <div class="table-wrap">
        <table>
          <tr><th>Metric</th><th>Value</th></tr>
          <tr><td>drc_errors</td><td>{html.escape(str(row.get('drc_errors', '')))}</td></tr>
          <tr><td>lvs_errors</td><td>{html.escape(str(row.get('lvs_errors', '')))}</td></tr>
          <tr><td>antenna_violations</td><td>{html.escape(str(row.get('antenna_violations', '')))}</td></tr>
          <tr><td>ir_drop_worst_V</td><td>{html.escape(str(row.get('ir_drop_worst_V', '')))}</td></tr>
        </table>
      </div>
    </section>
  </div>
  {theme_script}
</body>
</html>
"""
        (run_dir / "index.html").write_text(run_html, encoding="utf-8")

    total_runs = len(sorted_rows)
    pass_count = sum(1 for row in sorted_rows if row.get("status") == "PASS")
    fail_count = total_runs - pass_count
    best_clock = str(sorted_rows[0].get("clock_ns", "")) if sorted_rows else ""

    best_text = ""
    if sorted_rows:
        best = sorted_rows[0]
        best_text = f"""
        <section class="card best">
          <h2>Chosen best run</h2>
          <p><span class="tag">Selected</span></p>
          <p><strong>Run:</strong> {html.escape(str(best.get('_variant','')))} / {html.escape(str(best.get('_run_dir','')))}</p>
          <p><strong>Clock:</strong> {html.escape(str(best.get('clock_ns','')))} ns</p>
          <p><strong>Status:</strong> {badge_html(best.get('status',''))}</p>
          <p><strong>Remarks:</strong> {html.escape(str(best.get('selection_reason','')))}</p>
        </section>
        """

    rows_html: List[str] = []
    for idx, row in enumerate(sorted_rows):
        run_page = f"runs/{html.escape(row['_site_slug'])}/index.html"
        gds_page = ""
        if row.get("_site_gds"):
            gds_page = f'runs/{html.escape(row["_site_slug"])}/{html.escape(row["_site_gds"])}'

        selected_marker = '<span class="tag">Selected</span>' if idx == 0 else ""
        gds_link_html = (
            f'<a class="btn" href="{gds_page}">GDS</a>'
            if gds_page
            else '<span class="muted small">No GDS</span>'
        )
        tt_viewer_link = f'<a class="btn secondary" href="{TT_GDS_VIEWER_URL}" target="_blank" rel="noopener noreferrer">Viewer</a>'
        row_class = "selected-row" if idx == 0 else ""

        rows_html.append(
            f"""
            <tr class="{row_class}">
              <td>{selected_marker}</td>
              <td>
                <a href="{run_page}"><strong>{html.escape(str(row.get("_variant", "")))} / {html.escape(str(row.get("_run_dir", "")))}</strong></a>
                <div class="muted small mono">{html.escape(str(row.get("_artifact", "")))}</div>
              </td>
              <td>{html.escape(str(row.get("clock_ns", "")))}</td>
              <td>{html.escape(str(row.get("setup_wns_ns", "")))}</td>
              <td>{html.escape(str(row.get("setup_tns_ns", "")))}</td>
              <td>{html.escape(str(row.get("drc_errors", "")))}</td>
              <td>{html.escape(str(row.get("lvs_errors", "")))}</td>
              <td>{html.escape(str(row.get("antenna_violations", "")))}</td>
              <td>{badge_html(row.get("status", ""))}</td>
              <td>{html.escape(str(row.get("selection_reason", "")))}</td>
              <td>{gds_link_html}</td>
              <td>{tt_viewer_link}</td>
            </tr>
            """
        )

    theme_widget = build_theme_widget("indexAppearanceButton", "indexThemeWidget")
    theme_script = build_theme_script("indexAppearanceButton", "indexThemeWidget", "asic-flow-theme")

    index_html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>ASIC Flow Run Explorer</title>
  <style>{site_css}</style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <div class="hero-head">
        <div class="hero-copy">
          <h1>ASIC Flow Run Explorer</h1>
          <p>Published summary of all collected runs, how the best run was selected, and direct access to per-run pages and downloadable GDS files.</p>
        </div>
        {theme_widget}
      </div>
    </section>

    <div class="grid">
      <section class="card rules">
        <h2>Selection order</h2>
        <ol class="list-clean">
          <li>Clean signoff plus non-negative setup timing wins.</li>
          <li>If no full PASS exists, clean signoff wins over signoff violations.</li>
          <li>Among comparable runs, lower requested clock period is preferred.</li>
          <li>Setup WNS/TNS are used as tie-breakers.</li>
        </ol>
      </section>

      {best_text}
    </div>

    <section class="card" style="margin-top:18px">
      <h2>Run overview</h2>
      <p class="section-note">Top row is the selected best run.</p>
      <div class="stats">
        <div class="stat">
          <div class="label">Total runs</div>
          <div class="value">{total_runs}</div>
        </div>
        <div class="stat">
          <div class="label">PASS runs</div>
          <div class="value">{pass_count}</div>
        </div>
        <div class="stat">
          <div class="label">Non-pass runs</div>
          <div class="value">{fail_count}</div>
        </div>
        <div class="stat">
          <div class="label">Best clock</div>
          <div class="value">{html.escape(best_clock)}</div>
        </div>
      </div>
    </section>

    <section class="card table-card">
      <div class="table-head">
        <h2>All runs</h2>
        <span class="muted small">Top row is the selected best run</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Selected</th>
              <th>Run</th>
              <th>Clock (ns)</th>
              <th>Setup WNS</th>
              <th>Setup TNS</th>
              <th>DRC</th>
              <th>LVS</th>
              <th>Antenna</th>
              <th>Status</th>
              <th>Remarks</th>
              <th>GDS</th>
              <th>GDS Viewer</th>
            </tr>
          </thead>
          <tbody>
            {"".join(rows_html)}
          </tbody>
        </table>
      </div>
    </section>
  </div>
  {theme_script}
</body>
</html>
"""
    (site_root / "index.html").write_text(index_html, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifacts-root", type=Path, required=True)
    ap.add_argument("--summary-md", type=Path, required=True)
    ap.add_argument("--summary-csv", type=Path, required=True)
    ap.add_argument("--best-json", type=Path, required=True)
    ap.add_argument("--best-bundle-dir", type=Path, default=Path("best-layout-bundle"))
    ap.add_argument("--site-dir", type=Path, default=Path("_site"))
    ap.add_argument("--repo-slug", default="")
    ap.add_argument("--run-id", default="")
    args = ap.parse_args()

    rows = collect_rows(args.artifacts_root)
    write_summary_csv(args.summary_csv, rows)
    write_summary_md(args.summary_md, rows)
    best = write_best_json(args.best_json, rows)
    package_best_bundle(args.best_bundle_dir, best)
    build_site(args.site_dir, rows)


if __name__ == "__main__":
    main()