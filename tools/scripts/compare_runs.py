#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

TT_GDS_VIEWER_URL = "https://gds-viewer.tinytapeout.com/"


def to_float(v: Any) -> Optional[float]:
    try:
        if v in (None, "", "None"):
            return None
        return float(v)
    except Exception:
        return None


def read_csv_row(path: Path) -> Optional[Dict[str, str]]:
    if not path.exists():
        return None
    with path.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows[0] if rows else None


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def flatten_scalar_metrics(value: Any, prefix: str = "", out: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if out is None:
        out = {}

    if isinstance(value, dict):
        for key, child in value.items():
            next_prefix = f"{prefix}__{key}" if prefix else str(key)
            flatten_scalar_metrics(child, next_prefix, out)
        return out

    if isinstance(value, list):
        for idx, child in enumerate(value):
            if isinstance(child, (dict, list)):
                continue
            if child in (None, ""):
                continue
            next_prefix = f"{prefix}__{idx}" if prefix else str(idx)
            out[next_prefix] = child
        return out

    if prefix and value not in (None, ""):
        out[prefix] = value
    return out


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
    if not (
        to_float(row.get("setup_wns_ns")) is not None
        and to_float(row.get("setup_tns_ns")) is not None
    ):
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
    if classify_status(row) == "FLOW_FAIL":
        return "Flow failed before valid timing metrics were produced."
    reasons: List[str] = []
    for k, label in (
        ("drc_errors", "DRC"),
        ("lvs_errors", "LVS"),
        ("antenna_violations", "Antenna"),
    ):
        v = to_float(row.get(k))
        if v not in (None, 0.0):
            reasons.append(f"{label}={int(v) if float(v).is_integer() else v}")
    swns = to_float(row.get("setup_wns_ns"))
    stns = to_float(row.get("setup_tns_ns"))
    if swns is None or swns < 0.0:
        reasons.append(f"setup WNS={row.get('setup_wns_ns', '')}")
    if stns is None or stns < 0.0:
        reasons.append(f"setup TNS={row.get('setup_tns_ns', '')}")
    return "; ".join(reasons) if reasons else "Clean signoff and non-negative setup timing."


def best_sort_key(row: Dict[str, str]) -> Tuple[Any, ...]:
    clean = signoff_clean(row)
    ok = timing_ok(row)
    clk = to_float(row.get("clock_ns"))
    swns = to_float(row.get("setup_wns_ns"))
    stns = to_float(row.get("setup_tns_ns"))
    penalty = sum(
        (to_float(row.get(k)) or 0.0)
        for k in ("antenna_violations", "drc_errors", "lvs_errors")
    )
    return (
        0 if clean and ok else 1,
        0 if clean else 1,
        penalty,
        clk if clk is not None else 1e12,
        -(swns if swns is not None else -1e12),
        -(stns if stns is not None else -1e12),
    )


def first_matching(base: Path, rel: Path) -> Optional[Path]:
    p = base / rel
    return p if p.exists() else None


def first_gds_path(base_dir: Path) -> Optional[Path]:
    gds_dir = base_dir / "final" / "gds"
    if not gds_dir.exists():
        return None
    files = sorted(gds_dir.glob("*.gds"))
    return files[0] if files else None


def first_render_path(base_dir: Path) -> Optional[Path]:
    renders_dir = base_dir / "renders"
    if not renders_dir.exists():
        return None
    for pattern in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
        files = sorted(renders_dir.glob(pattern))
        if files:
            return files[0]
    return None


def parse_attempt_started(path: Path) -> Dict[str, str]:
    data: Dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip()
    return data


def infer_stage_label(row: Dict[str, str]) -> str:
    haystack = " ".join(
        [
            str(row.get("_artifact", "")),
            str(row.get("_run_dir", "")),
            str(row.get("_variant", "")),
        ]
    ).lower()

    if "coarse" in haystack:
        return "coarse"
    if "mid" in haystack or "5ns" in haystack or "5 ns" in haystack or "step5" in haystack:
        return "5 ns"
    if "0.125" in haystack or "125ps" in haystack or "refine3" in haystack or "refine_3" in haystack:
        return "0.125 ns"
    if "0.5" in haystack or "500ps" in haystack or "refine2" in haystack or "refine_2" in haystack:
        return "0.5 ns"
    if "1.0" in haystack or "1ns" in haystack or "1 ns" in haystack or "refine1" in haystack or "refine_1" in haystack:
        return "1.0 ns"

    match = re.search(r"step[_\s-]?([0-9]+(?:\.[0-9]+)?)", haystack)
    if match:
        return f"{match.group(1)} ns"

    return ""


def raw_row_key(raw_key: str) -> str:
    return f"_raw__{raw_key}"


def raw_metric_value(row: Dict[str, Any], raw_key: str) -> Any:
    return row.get(raw_row_key(raw_key), "")


def pretty_raw_metric_label(raw_key: str) -> str:
    pieces = [piece.replace("_", " ").strip() for piece in raw_key.split("__") if piece.strip()]
    return " / ".join(piece.title() for piece in pieces)


def raw_metric_sort_priority(raw_key: str) -> Tuple[int, str]:
    priorities = [
        ("clock__", 0),
        ("timing__", 0),
        ("power__", 1),
        ("design__", 2),
        ("floorplan__", 2),
        ("place__", 3),
        ("route__", 4),
        ("cts__", 5),
        ("drc__", 6),
        ("klayout__", 6),
        ("magic__", 6),
        ("lvs__", 6),
        ("antenna__", 6),
        ("ir__", 6),
    ]
    for prefix, rank in priorities:
        if raw_key.startswith(prefix):
            return (rank, raw_key)
    return (99, raw_key)


def iter_raw_metrics(row: Dict[str, Any]) -> List[Tuple[str, Any]]:
    items: List[Tuple[str, Any]] = []
    for key, value in row.items():
        if not key.startswith("_raw__"):
            continue
        if value in ("", None, "None"):
            continue
        raw_key = key[len("_raw__") :]
        items.append((raw_key, value))
    items.sort(key=lambda item: raw_metric_sort_priority(item[0]))
    return items


def pick_raw_metric_items(
    row: Dict[str, Any],
    prefixes: Tuple[str, ...],
    consumed: Set[str],
    *,
    limit: int = 8,
    catch_all: bool = False,
) -> List[Tuple[str, Any]]:
    selected: List[Tuple[str, Any]] = []
    for raw_key, value in iter_raw_metrics(row):
        if raw_key in consumed:
            continue
        matches = True if catch_all else any(raw_key.startswith(prefix) for prefix in prefixes)
        if not matches:
            continue
        consumed.add(raw_key)
        selected.append((pretty_raw_metric_label(raw_key), value))
        if len(selected) >= limit:
            break
    return selected


def collect_rows(artifacts_root: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    seen: set[Path] = set()
    for pattern in ("**/ci_out/*/clk_*ns_*/metrics.csv", "**/*/clk_*ns_*/metrics.csv"):
        for csv_path in sorted(artifacts_root.glob(pattern)):
            if csv_path in seen:
                continue
            seen.add(csv_path)
            row = read_csv_row(csv_path)
            if not row:
                continue
            base_dir = csv_path.parent
            meta_path = base_dir / "run_meta.json"
            meta: Dict[str, Any] = (
                json.loads(meta_path.read_text(encoding="utf-8"))
                if meta_path.exists()
                else {}
            )
            started = parse_attempt_started(base_dir / "attempt_started.txt")

            raw_metrics = load_json(base_dir / "metrics_raw.json")
            raw_flat = flatten_scalar_metrics(raw_metrics)
            failure_summary = load_json(base_dir / "failure_summary.json")

            row["_variant"] = str(meta.get("variant", base_dir.parent.name))
            row["_artifact"] = str(meta.get("artifact_name", ""))
            row["_run_dir"] = base_dir.name
            row["_base_dir"] = str(base_dir)
            row["_clock_requested"] = str(
                meta.get("clock_ns_requested", row.get("clock_ns", ""))
            )
            row["_github_run_id"] = str(meta.get("github_run_id", ""))
            row["_synth_strategy_override"] = str(meta.get("synth_strategy_override", ""))
            row["_attempt_number"] = started.get("attempt", "")
            row["_attempt_started_at"] = started.get("started_at", "")
            row["_metrics_raw_present"] = "yes" if raw_metrics else "no"
            row["_raw_metric_count"] = str(len(raw_flat))
            row["status"] = classify_status(row)
            row["selection_reason"] = explain_row(row)

            meta_stage = str(meta.get("stage_label", "")).strip()
            started_stage = str(started.get("stage_label", "")).strip()
            row["_stage_label"] = meta_stage or started_stage or infer_stage_label(row)

            row["_failure_summary_present"] = "yes" if failure_summary else "no"
            row["_failure_reason"] = str(failure_summary.get("reason", ""))
            row["_failure_phase"] = str(failure_summary.get("likely_failure_phase", ""))
            row["_failure_openlane_rc"] = str(failure_summary.get("openlane_rc", ""))
            row["_failure_config_rc"] = str(failure_summary.get("config_generation_rc", ""))
            row["_failure_summary"] = failure_summary

            for raw_key, raw_value in raw_flat.items():
                row[raw_row_key(raw_key)] = raw_value

            gds = first_gds_path(base_dir)
            rnd = first_render_path(base_dir)
            row["_gds_path"] = str(gds) if gds else ""
            row["_render_path"] = str(rnd) if rnd else ""
            row["_openlane_run_present"] = (
                "yes" if (base_dir / "openlane_run").exists() else "no"
            )
            rows.append(row)
    return rows


def write_summary_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    base_keys = [
        "_variant",
        "_run_dir",
        "_artifact",
        "_clock_requested",
        "_stage_label",
        "_metrics_raw_present",
        "_raw_metric_count",
        "_failure_summary_present",
        "_failure_reason",
        "_failure_phase",
        "_failure_openlane_rc",
        "_failure_config_rc",
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
        "wire_length_um",
        "vias_count",
        "power_total_W",
        "power_internal_W",
        "power_switching_W",
        "power_leakage_W",
        "power_source",
        "power_fair_sta_rpt",
        "drc_errors",
        "drc_errors_klayout",
        "drc_errors_magic",
        "lvs_errors",
        "antenna_violations",
        "antenna_violating_nets",
        "antenna_violating_pins",
        "ir_drop_worst_V",
        "status",
        "selection_reason",
        "_openlane_run_present",
        "_attempt_number",
        "_github_run_id",
        "_synth_strategy_override",
    ]
    raw_keys = sorted(
        {
            key
            for row in rows
            for key in row.keys()
            if key.startswith("_raw__")
        }
    )
    keys = base_keys + raw_keys
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in keys})


def write_summary_md(path: Path, rows: List[Dict[str, str]]) -> None:
    lines = [
        "## Best run selection",
        "",
        "1. Clean signoff plus non-negative setup timing wins.",
        "2. If no full PASS exists, clean signoff wins over signoff violations.",
        "3. Among comparable runs, lower requested clock period is preferred.",
        "4. Setup WNS/TNS are used as tie-breakers.",
        "",
    ]
    ordered = sorted(rows, key=best_sort_key)
    if ordered:
        best = ordered[0]
        lines += [
            f"- Selected: `{best.get('_variant', '')}` / `{best.get('_run_dir', '')}`",
            f"- Clock: `{best.get('clock_ns', '')} ns`",
            f"- Status: `{best.get('status', '')}`",
            f"- Remarks: {best.get('selection_reason', '')}",
            "",
        ]
    lines += [
        "## All runs",
        "",
        "| Variant | Run | Clock (ns) | Setup WNS | Setup TNS | Core area | Power total | DRC | LVS | Antenna | Status | Remarks |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for idx, row in enumerate(ordered):
        remarks = row.get("selection_reason", "")
        if idx == 0:
            remarks = f"SELECTED — {remarks}"
        lines.append(
            f"| {row.get('_variant', '').replace('|', '/')} | {row.get('_run_dir', '').replace('|', '/')} | "
            f"{row.get('clock_ns', '')} | {row.get('setup_wns_ns', '')} | {row.get('setup_tns_ns', '')} | "
            f"{row.get('core_area_um2', '')} | {row.get('power_total_W', '')} | {row.get('drc_errors', '')} | "
            f"{row.get('lvs_errors', '')} | {row.get('antenna_violations', '')} | {row.get('status', '')} | "
            f"{remarks.replace('|', '/')} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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


def write_best_json(path: Path, rows: List[Dict[str, str]]) -> Dict[str, Any]:
    best = sorted(rows, key=best_sort_key)[0] if rows else {}
    path.write_text(json.dumps(best, indent=2), encoding="utf-8")
    return best


def package_best_bundle(best_bundle_dir: Path, best: Dict[str, Any]) -> None:
    best_bundle_dir.mkdir(parents=True, exist_ok=True)
    if not best:
        return
    base_dir = Path(best["_base_dir"])
    for name in (
        "metrics.csv",
        "metrics.md",
        "metrics_raw.json",
        "run_meta.json",
        "attempt_started.txt",
        "attempt_manifest.json",
        "viewer.html",
        "index.html",
        "README.txt",
        "failure_summary.md",
        "failure_summary.json",
    ):
        src = base_dir / name
        if src.exists():
            shutil.copy2(src, best_bundle_dir / name)
    copy_tree_if_exists(base_dir / "renders", best_bundle_dir / "renders")
    copy_tree_if_exists(base_dir / "final" / "gds", best_bundle_dir / "final" / "gds")
    copy_tree_if_exists(base_dir / "openlane_run", best_bundle_dir / "openlane_run")
    for name in ("autoflow_history.json", "autoflow_history.csv", "autoflow_summary.md"):
        src = base_dir.parent / name
        if src.exists():
            shutil.copy2(src, best_bundle_dir / name)


def build_theme_widget(button_id: str, panel_id: str) -> str:
    return f"""
<div class="theme-control">
  <button class="theme-launch" id="{button_id}" type="button" aria-expanded="false" aria-controls="{panel_id}">Appearance ⚙️</button>
  <div class="theme-widget" id="{panel_id}" hidden>
    <div class="theme-widget-body">
      <h3>Appearance</h3>
      <div class="theme-row"><label for="{panel_id}_preset">Theme preset</label><select id="{panel_id}_preset"><option value="canvas">Canvas Beige</option><option value="forest">Forest</option><option value="slate">Slate</option></select></div>
      <div class="theme-inline">
        <div class="theme-row"><label for="{panel_id}_bg">Base background</label><input type="color" id="{panel_id}_bg" value="#f4ecdf"></div>
        <div class="theme-row"><label for="{panel_id}_accent">Accent</label><input type="color" id="{panel_id}_accent" value="#8b5e3c"></div>
      </div>
      <div class="theme-inline">
        <div class="theme-row"><label for="{panel_id}_grad1">Gradient 1</label><input type="color" id="{panel_id}_grad1" value="#f8f1e7"></div>
        <div class="theme-row"><label for="{panel_id}_grad2">Gradient 2</label><input type="color" id="{panel_id}_grad2" value="#efe4d3"></div>
      </div>
      <div class="theme-btn-row"><button id="{panel_id}_save" type="button">Save</button><button id="{panel_id}_reset" type="button">Reset</button></div>
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
    canvas: {{"--bg":"#f4ecdf","--bg-grad-1":"#f8f1e7","--bg-grad-2":"#efe4d3","--accent":"#8b5e3c","--accent-2":"#b6845e"}},
    forest: {{"--bg":"#e9efe7","--bg-grad-1":"#f3f7f1","--bg-grad-2":"#d9e7d5","--accent":"#4f7a5c","--accent-2":"#789d83"}},
    slate: {{"--bg":"#e7ebf0","--bg-grad-1":"#f3f6fa","--bg-grad-2":"#d7dde6","--accent":"#496a8a","--accent-2":"#7292b0"}}
  }};
  function applyVars(vars) {{ Object.entries(vars).forEach(([k,v]) => root.style.setProperty(k, v)); }}
  function syncInputsFromCurrentTheme() {{
    const styles = getComputedStyle(root);
    bgColor.value = styles.getPropertyValue("--bg").trim() || bgColor.value;
    grad1.value = styles.getPropertyValue("--bg-grad-1").trim() || grad1.value;
    grad2.value = styles.getPropertyValue("--bg-grad-2").trim() || grad2.value;
    accentColor.value = styles.getPropertyValue("--accent").trim() || accentColor.value;
  }}
  function saveSettings() {{ localStorage.setItem("{storage_key}", JSON.stringify({{preset:presetTheme.value,bg:bgColor.value,grad1:grad1.value,grad2:grad2.value,accent:accentColor.value}})); }}
  function loadSettings() {{
    const raw = localStorage.getItem("{storage_key}");
    if (!raw) {{
      presetTheme.value = "canvas";
      applyVars(presets.canvas);
      syncInputsFromCurrentTheme();
      return;
    }}
    try {{
      const s = JSON.parse(raw);
      const preset = (s.preset && presets[s.preset]) ? s.preset : "canvas";
      presetTheme.value = preset;
      applyVars(presets[preset]);
      if (s.bg) bgColor.value = s.bg;
      if (s.grad1) grad1.value = s.grad1;
      if (s.grad2) grad2.value = s.grad2;
      if (s.accent) accentColor.value = s.accent;
      applyVars({{"--bg":bgColor.value,"--bg-grad-1":grad1.value,"--bg-grad-2":grad2.value,"--accent":accentColor.value,"--accent-2":accentColor.value}});
    }} catch (e) {{
      presetTheme.value = "canvas";
      applyVars(presets.canvas);
    }}
    syncInputsFromCurrentTheme();
  }}
  function positionPanel() {{
    if (panel.hidden) return;
    const rect = button.getBoundingClientRect();
    const vw = window.innerWidth || document.documentElement.clientWidth || 0;
    const vh = window.innerHeight || document.documentElement.clientHeight || 0;
    const margin = 12;
    const w = Math.min(340, Math.max(260, vw - (margin * 2)));
    panel.style.width = w + "px";
    panel.style.maxWidth = w + "px";
    const h = panel.offsetHeight || 320;
    let left = rect.right - w;
    left = Math.max(margin, Math.min(left, vw - w - margin));
    let top = rect.bottom + 12;
    if (top + h > vh - margin) top = Math.max(margin, rect.top - h - 12);
    panel.style.left = left + "px";
    panel.style.top = top + "px";
  }}
  function openPanel() {{ panel.hidden = false; button.setAttribute("aria-expanded", "true"); positionPanel(); }}
  function closePanel() {{ panel.hidden = true; button.setAttribute("aria-expanded", "false"); }}
  button.addEventListener("click", function (e) {{ e.stopPropagation(); if (panel.hidden) openPanel(); else closePanel(); }});
  panel.addEventListener("click", function (e) {{ e.stopPropagation(); }});
  document.addEventListener("click", function () {{ closePanel(); }});
  document.addEventListener("keydown", function (e) {{ if (e.key === "Escape") closePanel(); }});
  window.addEventListener("resize", function () {{ if (!panel.hidden) positionPanel(); }});
  window.addEventListener("scroll", function () {{ if (!panel.hidden) positionPanel(); }}, true);
  presetTheme.addEventListener("change", function () {{
    if (presets[presetTheme.value]) {{
      applyVars(presets[presetTheme.value]);
      syncInputsFromCurrentTheme();
      saveSettings();
    }}
  }});
  [bgColor, grad1, grad2, accentColor].forEach(el => el.addEventListener("input", function () {{
    applyVars({{"--bg":bgColor.value,"--bg-grad-1":grad1.value,"--bg-grad-2":grad2.value,"--accent":accentColor.value,"--accent-2":accentColor.value}});
    saveSettings();
  }}));
  saveTheme.addEventListener("click", saveSettings);
  resetTheme.addEventListener("click", function () {{
    localStorage.removeItem("{storage_key}");
    presetTheme.value = "canvas";
    applyVars(presets.canvas);
    syncInputsFromCurrentTheme();
    closePanel();
  }});
  loadSettings();
  closePanel();
}})();
</script>
"""


def value_or_dash(v: Any) -> str:
    if isinstance(v, bool):
        s = "yes" if v else "no"
    else:
        s = "" if v is None else str(v)
    return html.escape(s) if s not in {"", "None"} else "—"


def badge_html(status: str) -> str:
    s = (status or "").upper()
    cls = "flow"
    if s == "PASS":
        cls = "pass"
    elif s == "TIMING_FAIL":
        cls = "timing"
    elif s == "SIGNOFF_FAIL":
        cls = "signoff"
    elif s == "SIGNOFF_AND_TIMING_FAIL":
        cls = "mixed"
    return f'<span class="badge {cls}">{html.escape(status or "")}</span>'


def link_button(href: str, label: str, secondary: bool = False) -> str:
    cls = "btn secondary" if secondary else "btn"
    return f'<a class="{cls}" href="{html.escape(href)}">{html.escape(label)}</a>'


def external_button(href: str, label: str, secondary: bool = False) -> str:
    cls = "btn secondary" if secondary else "btn"
    return (
        f'<a class="{cls}" href="{html.escape(href)}" target="_blank" '
        f'rel="noopener noreferrer">{html.escape(label)}</a>'
    )


def kv_rows(items: List[Tuple[str, Any]]) -> str:
    return "".join(
        f"<tr><td>{html.escape(k)}</td><td>{value_or_dash(v)}</td></tr>"
        for k, v in items
    )


def setting_value(explorer_settings: Dict[str, str], key: str, default: str = "—") -> str:
    value = str(explorer_settings.get(key, "")).strip()
    return value if value else default


def sortable_number_attr(v: Any) -> str:
    n = to_float(v)
    if n is None:
        return ""
    return str(n)


def sortable_text_attr(v: Any) -> str:
    return str(v or "").strip()


def sanitize_site_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())


def normalize_site_subdir(site_subdir: str) -> str:
    raw = str(site_subdir or "").strip().replace("\\", "/")
    parts = [part for part in raw.split("/") if part not in {"", ".", ".."}]
    return "/".join(parts)


def write_redirect_page(path: Path, target_href: str, title: str, description: str) -> None:
    safe_target = html.escape(target_href, quote=True)
    safe_title = html.escape(title)
    safe_description = html.escape(description)
    content = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta http-equiv=\"refresh\" content=\"0; url={safe_target}\">
  <title>{safe_title}</title>
  <style>
    body{{font:16px/1.6 Inter,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0;background:#f4ecdf;color:#2f2418;display:grid;min-height:100vh;place-items:center;padding:24px}}
    .card{{max-width:720px;background:rgba(255,248,238,.94);border:1px solid rgba(116,92,62,.22);border-radius:18px;padding:24px;box-shadow:0 18px 45px rgba(110,84,53,.12)}}
    a{{color:#8b5e3c;text-decoration:none;font-weight:700}}
  </style>
</head>
<body>
  <div class=\"card\">
    <h1>{safe_title}</h1>
    <p>{safe_description}</p>
    <p><a href=\"{safe_target}\">Open the explorer snapshot</a></p>
  </div>
</body>
</html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_site(
    site_root: Path,
    rows: List[Dict[str, str]],
    explorer_settings: Optional[Dict[str, str]] = None,
    *,
    repo_slug: str = "",
    run_id: str = "",
    site_subdir: str = "",
) -> None:
    site_root.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows, key=best_sort_key)
    explorer_settings = explorer_settings or {}

    normalized_site_subdir = normalize_site_subdir(site_subdir)
    snapshot_root = site_root / normalized_site_subdir if normalized_site_subdir else site_root
    snapshot_root.mkdir(parents=True, exist_ok=True)
    runs_root = snapshot_root / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)

    run_id_label = str(run_id or "").strip()
    repo_slug_label = str(repo_slug or "").strip()
    snapshot_label = run_id_label if run_id_label else "current"
    snapshot_prefix = f"/{normalized_site_subdir}" if normalized_site_subdir else "/"
    snapshot_description = (
        f"Static explorer snapshot for GitHub run {run_id_label}." if run_id_label else "Static explorer snapshot."
    )

    if normalized_site_subdir:
        write_redirect_page(
            site_root / "index.html",
            f"{normalized_site_subdir}/index.html",
            "ASIC Flow Run Explorer",
            snapshot_description,
        )
    (site_root / ".nojekyll").write_text("\n", encoding="utf-8")

    css = """
:root{
  color-scheme:light dark;
  --bg:#f4ecdf;
  --bg-grad-1:#f8f1e7;
  --bg-grad-2:#efe4d3;
  --panel:rgba(255,250,243,.82);
  --panel-strong:rgba(255,248,238,.94);
  --panel-soft:rgba(255,255,255,.46);
  --border:rgba(116,92,62,.16);
  --border-strong:rgba(116,92,62,.22);
  --text:#2f2418;
  --muted:#716250;
  --accent:#8b5e3c;
  --accent-2:#b6845e;
  --shadow:0 18px 45px rgba(110,84,53,.12);
  --pass-bg:rgba(73,143,96,.14);
  --pass-fg:#285a38;
  --timing-bg:rgba(190,143,45,.16);
  --timing-fg:#7d5b13;
  --signoff-bg:rgba(180,83,72,.14);
  --signoff-fg:#7b2f28;
  --mixed-bg:rgba(135,96,166,.14);
  --mixed-fg:#5b3f77;
  --flow-bg:rgba(120,115,108,.14);
  --flow-fg:#504a44;
  --radius-xl:28px;
  --radius-lg:20px;
  --radius-md:14px
}
body{
  margin:0;
  background:
    radial-gradient(circle at top left,var(--bg-grad-1)0%,transparent 36%),
    radial-gradient(circle at top right,var(--bg-grad-2)0%,transparent 28%),
    linear-gradient(180deg,var(--bg-grad-1)0%,var(--bg)100%);
  color:var(--text);
  font:15px/1.6 Inter,Segoe UI,Roboto,Helvetica,Arial,sans-serif
}
a{color:var(--accent);text-decoration:none}
.wrap{max-width:1520px;margin:0 auto;padding:28px 20px 40px}
.hero{
  background:var(--panel-strong);
  border:1px solid var(--border-strong);
  border-radius:var(--radius-xl);
  padding:30px;
  box-shadow:var(--shadow);
  margin-bottom:22px
}
.hero-head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px}
.hero-copy{max-width:980px}
.hero-copy p{margin:0}
.settings-list{
  margin:12px 0 0;
  padding:0;
  list-style:none;
  display:grid;
  gap:6px;
  color:var(--muted);
  font-size:14px
}
.settings-list strong{color:var(--text)}
.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:18px}
.card{
  background:var(--panel);
  border:1px solid var(--border);
  border-radius:var(--radius-lg);
  padding:22px;
  box-shadow:var(--shadow)
}
.span-12{grid-column:span 12}
.span-7{grid-column:span 7}
.span-5{grid-column:span 5}
.span-4{grid-column:span 4}
.span-3{grid-column:span 3}
.kpi-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.stat{
  background:var(--panel-soft);
  border:1px solid var(--border);
  border-radius:var(--radius-md);
  padding:16px
}
.stat .label{color:var(--muted);font-size:12px;text-transform:uppercase}
.stat .value{font-size:28px;font-weight:700}
.metrics-strip{display:grid;grid-template-columns:1fr;gap:14px}
.metric-group{
  background:var(--panel);
  border:1px solid var(--border);
  border-radius:var(--radius-lg);
  padding:0;
  overflow:hidden
}
.metric-group h3{margin:0;font-size:15px}
.table-card{padding:0;overflow:hidden}
.table-head{
  display:flex;
  justify-content:space-between;
  align-items:center;
  padding:18px 20px;
  border-bottom:1px solid var(--border)
}
.table-wrap{overflow:auto}
.kv-wrap{overflow:hidden}

.wide-table{
  width:100%;
  border-collapse:collapse;
  min-width:1180px
}
.wide-table th,
.wide-table td{
  padding:14px 16px;
  border-bottom:1px solid var(--border)
}
.wide-table th{
  background:rgba(255,248,240,.92);
  text-align:left;
  font-size:13px;
  white-space:nowrap
}

.kv-table{
  width:100%;
  border-collapse:collapse;
  table-layout:fixed;
  min-width:0
}
.kv-table col.kv-key{width:38%}
.kv-table col.kv-value{width:62%}
.kv-table th,
.kv-table td{
  padding:12px 16px;
  border-bottom:1px solid var(--border);
  vertical-align:top
}
.kv-table th{
  background:rgba(255,248,240,.92);
  text-align:left;
  font-size:13px
}
.kv-table td:first-child,
.kv-table th:first-child{
  white-space:nowrap
}
.kv-table td:last-child,
.kv-table th:last-child{
  word-break:break-word
}

.table-tools{
  display:flex;
  gap:12px;
  flex-wrap:wrap;
  align-items:end;
  padding:16px 20px 0
}
.table-tools label{
  display:grid;
  gap:6px;
  color:var(--muted);
  font-size:12px;
  font-weight:700;
  text-transform:uppercase
}
.table-tools select,
.table-tools input[type="search"]{
  min-width:180px;
  padding:10px 12px;
  border-radius:10px;
  border:1px solid var(--border-strong);
  background:var(--panel-soft);
  color:var(--text);
  font:500 13px/1.2 Inter,Segoe UI,Roboto,Helvetica,Arial,sans-serif
}
.table-tools .inline-check{
  display:flex;
  align-items:center;
  gap:8px;
  font-size:13px;
  font-weight:600;
  text-transform:none;
  color:var(--text);
  padding-bottom:2px
}
.table-tools .summary{
  margin-left:auto;
  font-size:13px;
  color:var(--muted);
  padding-bottom:4px
}
.sort-btn{
  all:unset;
  cursor:pointer;
  font-weight:700;
  color:var(--text);
  display:inline-flex;
  align-items:center;
  gap:6px
}
.sort-btn:hover{
  color:var(--accent)
}
.sort-btn.active{
  color:var(--accent)
}
.sort-indicator{
  font-size:11px;
  color:var(--muted)
}

.badge{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  min-width:112px;
  padding:6px 10px;
  border-radius:999px;
  font-size:12px;
  font-weight:700
}
.badge.pass{background:var(--pass-bg);color:var(--pass-fg)}
.badge.timing{background:var(--timing-bg);color:var(--timing-fg)}
.badge.signoff{background:var(--signoff-bg);color:var(--signoff-fg)}
.badge.mixed{background:var(--mixed-bg);color:var(--mixed-fg)}
.badge.flow{background:var(--flow-bg);color:var(--flow-fg)}
.btn{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  padding:8px 12px;
  border-radius:10px;
  border:1px solid rgba(139,94,60,.20);
  background:rgba(139,94,60,.08);
  color:var(--text);
  font-weight:600;
  font-size:13px
}
.btn.secondary{
  border-color:var(--border-strong);
  background:rgba(255,255,255,.08)
}
.actions{display:flex;gap:8px;flex-wrap:wrap}
.tag{
  display:inline-flex;
  align-items:center;
  padding:4px 10px;
  border-radius:999px;
  font-size:12px;
  font-weight:700;
  background:rgba(139,94,60,.12);
  color:var(--accent)
}

.theme-control{position:relative;z-index:40}
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
  font:600 13px/1.2 Inter,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
  cursor:pointer;
  box-shadow:none
}
.theme-widget{
  position:fixed;
  top:72px;
  right:24px;
  width:320px;
  max-width:min(320px,calc(100vw - 24px));
  z-index:99999;
  pointer-events:auto
}
.theme-widget[hidden]{display:none !important}
.theme-widget-body{
  padding:16px;
  border-radius:16px;
  border:1px solid var(--border-strong);
  background:var(--panel-strong);
  box-shadow:var(--shadow)
}
.theme-widget-body h3{margin:0 0 12px;font-size:16px}
.theme-row{display:grid;gap:6px;margin-bottom:12px}
.theme-row label{
  font-size:12px;
  font-weight:600;
  color:var(--muted);
  text-transform:uppercase
}
.theme-row select,
.theme-row input,
.theme-btn-row button{
  font:500 13px/1.2 Inter,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
  color:var(--text)
}
.theme-row select{
  padding:10px 12px;
  border-radius:10px;
  border:1px solid var(--border-strong);
  background:var(--panel-soft)
}
.theme-row input[type='color']{
  width:100%;
  height:42px;
  padding:4px;
  border-radius:10px;
  border:1px solid var(--border-strong);
  background:var(--panel-soft)
}
.theme-inline{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.theme-btn-row{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.theme-btn-row button{
  padding:10px 12px;
  border-radius:10px;
  border:1px solid var(--border-strong);
  background:var(--panel-soft);
  cursor:pointer
}

@media(max-width:1080px){
  .span-7,.span-5,.span-4,.span-3{grid-column:span 12}
  .kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
  .metrics-strip{grid-template-columns:1fr}
  .table-tools .summary{margin-left:0;width:100%}
}
@media(max-width:720px){
  .kpi-grid{grid-template-columns:1fr}
  .kv-table col.kv-key{width:42%}
  .kv-table col.kv-value{width:58%}
}
"""

    def setting_line(label: str, value: str) -> str:
        return f"<li><strong>{html.escape(label)}:</strong> {html.escape(value)}</li>"

    settings_html = "".join(
        [
            setting_line(
                "Synthesis strategy",
                setting_value(explorer_settings, "synth_strategy", "Default"),
            ),
            setting_line(
                "Antenna repair",
                setting_value(explorer_settings, "antenna_repair", "—"),
            ),
            setting_line(
                "Heuristic diode insertion",
                setting_value(explorer_settings, "heuristic_diode_insertion", "—"),
            ),
            setting_line(
                "Post-GRT design repair",
                setting_value(explorer_settings, "post_grt_design_repair", "—"),
            ),
            setting_line(
                "Post-GRT resizer timing",
                setting_value(explorer_settings, "post_grt_resizer_timing", "—"),
            ),
        ]
    )

    def metric_group_html(title: str, items: List[Tuple[str, Any]]) -> str:
        return (
            f'<section class="metric-group table-card">'
            f'<div class="table-head"><h3>{html.escape(title)}</h3></div>'
            f'<div class="kv-wrap"><table class="kv-table">'
            f'<colgroup><col class="kv-key"><col class="kv-value"></colgroup>'
            f"<tr><th>Field</th><th>Value</th></tr>{kv_rows(items)}</table></div>"
            f"</section>"
        )

    for row in ordered:
        slug = f"{row.get('_variant', 'variant').replace('/', '_')}__{row.get('_run_dir', 'run')}"
        row["_site_slug"] = slug
        run_dir = runs_root / slug
        run_dir.mkdir(parents=True, exist_ok=True)
        base_dir = Path(row["_base_dir"])
        gds_src = Path(row["_gds_path"]) if row.get("_gds_path") else None
        rnd_src = Path(row["_render_path"]) if row.get("_render_path") else None
        gds_name = ""
        rnd_name = ""

        if gds_src and gds_src.exists():
            gds_name = f"{row.get('_run_dir', 'layout')}.gds"
            shutil.copy2(gds_src, run_dir / gds_name)
            row["_site_gds"] = gds_name

        if rnd_src and rnd_src.exists():
            rnd_name = rnd_src.name
            shutil.copy2(rnd_src, run_dir / rnd_name)
            row["_site_render"] = rnd_name

        for name in ("metrics.csv", "metrics_raw.json", "viewer.html", "failure_summary.md", "failure_summary.json"):
            src = base_dir / name
            if src.exists():
                shutil.copy2(src, run_dir / name)

        copy_tree_if_exists(base_dir / "renders", run_dir / "renders")
        copy_tree_if_exists(base_dir / "final" / "gds", run_dir / "final" / "gds")

        title = html.escape(f"{row.get('_variant', '')} — {row.get('_run_dir', '')}")

        actions: List[str] = []
        if gds_name:
            actions.append(link_button(gds_name, "Download GDS"))
            actions.append(external_button(TT_GDS_VIEWER_URL, "Open GDS Viewer", secondary=True))
        else:
            actions.append(external_button(TT_GDS_VIEWER_URL, "Open GDS Viewer", secondary=True))

        for name in ("metrics.csv", "metrics_raw.json"):
            if (run_dir / name).exists():
                actions.append(link_button(name, f"Open {name}", secondary=True))

        preview = ""
        if rnd_name:
            preview = (
                '<section class="card span-12">'
                "<h2>Preview render</h2>"
                f'<img style="width:100%;max-height:520px;object-fit:contain;'
                f'border-radius:14px;border:1px solid var(--border)" '
                f'src="{html.escape(rnd_name)}" alt="Layout render preview">'
                "</section>"
            )

        consumed_raw: Set[str] = set()

        timing_items: List[Tuple[str, Any]] = [
            ("Clock requested", f"{row.get('_clock_requested', '')} ns"),
            ("Clock reported", f"{row.get('clock_ns_reported', '')} ns"),
            ("Setup WNS", f"{row.get('setup_wns_ns', '')} ns"),
            ("Setup TNS", f"{row.get('setup_tns_ns', '')} ns"),
            ("Hold WNS", f"{row.get('hold_wns_ns', '')} ns"),
            ("Hold TNS", f"{row.get('hold_tns_ns', '')} ns"),
        ]
        timing_items.extend(pick_raw_metric_items(row, ("clock__", "timing__"), consumed_raw, limit=10))

        physical_items: List[Tuple[str, Any]] = [
            ("Core area", row.get("core_area_um2", "")),
            ("Die area", row.get("die_area_um2", "")),
            ("Instances", row.get("instance_count", "")),
            ("Utilization", row.get("utilization_pct", "")),
            ("Wire length", row.get("wire_length_um", "")),
            ("Vias", row.get("vias_count", "")),
        ]
        physical_items.extend(
            pick_raw_metric_items(row, ("design__", "floorplan__", "place__", "route__", "cts__"), consumed_raw, limit=12)
        )

        power_items: List[Tuple[str, Any]] = [
            ("Total", row.get("power_total_W", "")),
            ("Internal", row.get("power_internal_W", "")),
            ("Switching", row.get("power_switching_W", "")),
            ("Leakage", row.get("power_leakage_W", "")),
            ("Source", row.get("power_source", "")),
            ("FAIR STA rpt", row.get("power_fair_sta_rpt", "")),
        ]
        power_items.extend(pick_raw_metric_items(row, ("power__",), consumed_raw, limit=10))

        signoff_items: List[Tuple[str, Any]] = [
            ("DRC", row.get("drc_errors", "")),
            ("KLayout DRC", row.get("drc_errors_klayout", "")),
            ("Magic DRC", row.get("drc_errors_magic", "")),
            ("LVS", row.get("lvs_errors", "")),
            ("Antenna", row.get("antenna_violations", "")),
            ("Worst IR drop", row.get("ir_drop_worst_V", "")),
        ]
        signoff_items.extend(
            pick_raw_metric_items(
                row,
                ("drc__", "klayout__", "magic__", "lvs__", "antenna__", "ir__"),
                consumed_raw,
                limit=12,
            )
        )

        additional_raw_items = pick_raw_metric_items(row, tuple(), consumed_raw, limit=24, catch_all=True)

        timing_group = metric_group_html("Timing", timing_items)
        physical_group = metric_group_html("Physical", physical_items)
        power_group = metric_group_html("Power (W)", power_items)
        signoff_group = metric_group_html("Signoff", signoff_items)
        raw_group = (
            metric_group_html("Additional raw metrics", additional_raw_items)
            if additional_raw_items
            else ""
        )

        failure_section = ""
        failure_summary = row.get("_failure_summary", {})
        if row.get("status") == "FLOW_FAIL" and isinstance(failure_summary, dict) and failure_summary:
            checks = failure_summary.get("checks", {}) or {}
            failure_rows: List[Tuple[str, Any]] = [
                ("Primary reason", failure_summary.get("reason", row.get("_failure_reason", ""))),
                ("Likely failing phase", failure_summary.get("likely_failure_phase", row.get("_failure_phase", ""))),
                ("OpenLane return code", failure_summary.get("openlane_rc", row.get("_failure_openlane_rc", ""))),
                ("Config generation return code", failure_summary.get("config_generation_rc", row.get("_failure_config_rc", ""))),
                ("Config generated", checks.get("config_generated", "")),
                ("OpenLane invoked", checks.get("openlane_invoked", "")),
                ("Run directory found", checks.get("run_dir_found", "")),
                ("metrics.csv present", checks.get("metrics_csv_present", "")),
                ("metrics_raw.json present", checks.get("metrics_raw_present", "")),
                ("Valid timing present", checks.get("timing_present", "")),
                ("GDS present", checks.get("gds_present", "")),
                ("Render present", checks.get("render_present", "")),
                ("OpenLane run copied", checks.get("openlane_run_present", "")),
                ("Viewer HTML present", checks.get("viewer_present", "")),
            ]
            failure_section = (
                '<section class="card span-12">'
                '<div class="metrics-strip">'
                f'{metric_group_html("Failure diagnostic", failure_rows)}'
                "</div>"
                "</section>"
            )

        meta_rows = [
            ("Variant", row.get("_variant")),
            ("Snapshot run ID", run_id_label),
            ("Repository", repo_slug_label),
            ("Run folder", row.get("_run_dir")),
            ("Artifact label", row.get("_artifact")),
            ("Stage label", row.get("_stage_label")),
            ("Attempt number", row.get("_attempt_number")),
            ("GitHub run ID", row.get("_github_run_id")),
            ("Synthesis override", row.get("_synth_strategy_override")),
            ("OpenLane run copied", row.get("_openlane_run_present")),
            ("metrics_raw.json present", row.get("_metrics_raw_present")),
            ("Raw metric count", row.get("_raw_metric_count")),
            ("Failure summary present", row.get("_failure_summary_present")),
            ("Likely failure phase", row.get("_failure_phase")),
            ("Status", row.get("status")),
            ("Remarks", row.get("selection_reason")),
        ]

        theme_widget = build_theme_widget("runAppearanceButton", "runThemeWidget")
        theme_script = build_theme_script(
            "runAppearanceButton", "runThemeWidget", "asic-flow-theme"
        )

        run_html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <style>{css}</style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <div class="hero-head">
        <div class="hero-copy">
          <h1>{title}</h1>
          <p>Enriched per-run detail page with timing, physical, power, signoff, and download links.</p>
          <p><strong>Snapshot:</strong> {html.escape(snapshot_label)} · <strong>Path:</strong> {html.escape(snapshot_prefix + '/index.html' if snapshot_prefix != '/' else '/index.html')}</p>
        </div>
        {theme_widget}
      </div>
    </section>

    <div class="grid">
      <section class="card span-5">
        <h2>Run status</h2>
        <p>{badge_html(row.get('status', ''))}</p>
        <p><strong>Remarks:</strong> {html.escape(row.get('selection_reason', ''))}</p>
        <p><a class="btn secondary" href="../../index.html">Back to ASIC Flow Run Explorer</a></p>
      </section>

      <section class="card span-7">
        <h2>Download &amp; Tools</h2>
        <div class="actions">{''.join(actions)}</div>
      </section>

      {failure_section}

      <section class="card span-12">
        <h2>Metrics by category</h2>
        <div class="metrics-strip">
          {timing_group}
          {physical_group}
          {power_group}
          {signoff_group}
          {raw_group}
        </div>
      </section>

      {preview}

      <section class="card span-12 table-card">
        <div class="table-head"><h2>Metadata</h2></div>
        <div class="kv-wrap">
          <table class="kv-table">
            <colgroup><col class="kv-key"><col class="kv-value"></colgroup>
            <tr><th>Field</th><th>Value</th></tr>
            {kv_rows(meta_rows)}
          </table>
        </div>
      </section>
    </div>
  </div>
  {theme_script}
</body>
</html>"""
        (run_dir / "index.html").write_text(run_html, encoding="utf-8")

    best = ordered[0] if ordered else {}
    rows_html: List[str] = []
    stage_values = sorted({str(row.get("_stage_label", "")).strip() for row in ordered if str(row.get("_stage_label", "")).strip()})

    for idx, row in enumerate(ordered):
        run_page = f"runs/{html.escape(row['_site_slug'])}/index.html"
        gds_page = (
            f"runs/{html.escape(row['_site_slug'])}/{html.escape(row.get('_site_gds', ''))}"
            if row.get("_site_gds")
            else ""
        )
        selected_marker = '<span class="tag">Selected</span>' if idx == 0 else ""
        gds_html = link_button(gds_page, "GDS") if gds_page else "<span>No GDS</span>"

        run_text = f"{row.get('_variant', '')} / {row.get('_run_dir', '')}"
        selected_flag = "1" if idx == 0 else "0"

        rows_html.append(
            f'<tr '
            f'data-selected="{selected_flag}" '
            f'data-run="{html.escape(sortable_text_attr(run_text))}" '
            f'data-clock="{html.escape(sortable_number_attr(row.get("clock_ns")))}" '
            f'data-setup_wns="{html.escape(sortable_number_attr(row.get("setup_wns_ns")))}" '
            f'data-setup_tns="{html.escape(sortable_number_attr(row.get("setup_tns_ns")))}" '
            f'data-core_area="{html.escape(sortable_number_attr(row.get("core_area_um2")))}" '
            f'data-power_total="{html.escape(sortable_number_attr(row.get("power_total_W")))}" '
            f'data-drc="{html.escape(sortable_number_attr(row.get("drc_errors")))}" '
            f'data-lvs="{html.escape(sortable_number_attr(row.get("lvs_errors")))}" '
            f'data-antenna="{html.escape(sortable_number_attr(row.get("antenna_violations")))}" '
            f'data-ir_drop="{html.escape(sortable_number_attr(row.get("ir_drop_worst_V")))}" '
            f'data-status="{html.escape(sortable_text_attr(row.get("status")))}" '
            f'data-stage="{html.escape(sortable_text_attr(row.get("_stage_label")))}" '
            f'data-remarks="{html.escape(sortable_text_attr(row.get("selection_reason")))}">'
            f"<td>{selected_marker}</td>"
            f'<td><a href="{run_page}"><strong>{html.escape(str(row.get("_variant", "")))} / '
            f'{html.escape(str(row.get("_run_dir", "")))}</strong></a></td>'
            f"<td>{value_or_dash(row.get('clock_ns'))}</td>"
            f"<td>{value_or_dash(row.get('setup_wns_ns'))}</td>"
            f"<td>{value_or_dash(row.get('setup_tns_ns'))}</td>"
            f"<td>{value_or_dash(row.get('core_area_um2'))}</td>"
            f"<td>{value_or_dash(row.get('power_total_W'))}</td>"
            f"<td>{value_or_dash(row.get('drc_errors'))}</td>"
            f"<td>{value_or_dash(row.get('lvs_errors'))}</td>"
            f"<td>{value_or_dash(row.get('antenna_violations'))}</td>"
            f"<td>{value_or_dash(row.get('ir_drop_worst_V'))}</td>"
            f"<td>{badge_html(row.get('status', ''))}</td>"
            f"<td>{html.escape(str(row.get('selection_reason', '')))}</td>"
            f"<td>{gds_html}</td>"
            f"<td>{external_button(TT_GDS_VIEWER_URL, 'Viewer', True)}</td>"
            f"</tr>"
        )

    stage_options_html = "".join(
        f'<option value="{html.escape(stage)}">{html.escape(stage)}</option>'
        for stage in stage_values
    )

    theme_widget = build_theme_widget("indexAppearanceButton", "indexThemeWidget")
    theme_script = build_theme_script(
        "indexAppearanceButton", "indexThemeWidget", "asic-flow-theme"
    )

    sort_filter_script = """
<script>
(function () {
  const table = document.querySelector(".wide-table");
  if (!table) return;

  const tbody = table.querySelector("tbody");
  const headerButtons = Array.from(document.querySelectorAll(".sort-btn"));
  const statusFilter = document.getElementById("statusFilter");
  const stageFilter = document.getElementById("stageFilter");
  const searchFilter = document.getElementById("searchFilter");
  const pinSelected = document.getElementById("pinSelected");
  const visibleSummary = document.getElementById("visibleRowsSummary");

  const allRows = Array.from(tbody.querySelectorAll("tr"));
  let currentKey = "";
  let currentDir = "asc";

  const statusRank = {
    "PASS": 0,
    "TIMING_FAIL": 1,
    "SIGNOFF_FAIL": 2,
    "SIGNOFF_AND_TIMING_FAIL": 3,
    "FLOW_FAIL": 4
  };

  function getRowValue(row, key, type) {
    const raw = (row.dataset[key] || "").trim();
    if (type === "number") {
      if (raw === "") return Number.POSITIVE_INFINITY;
      const parsed = Number(raw);
      return Number.isFinite(parsed) ? parsed : Number.POSITIVE_INFINITY;
    }
    if (type === "status") {
      return Object.prototype.hasOwnProperty.call(statusRank, raw) ? statusRank[raw] : 999;
    }
    return raw.toLowerCase();
  }

  function updateHeaderState() {
    headerButtons.forEach((btn) => {
      const indicator = btn.querySelector(".sort-indicator");
      const isActive = btn.dataset.key === currentKey;
      btn.classList.toggle("active", isActive);
      btn.setAttribute("aria-sort", isActive ? (currentDir === "asc" ? "ascending" : "descending") : "none");
      if (indicator) {
        indicator.textContent = isActive ? (currentDir === "asc" ? "▲" : "▼") : "↕";
      }
    });
  }

  function applyFilters(rows) {
    const wantedStatus = (statusFilter && statusFilter.value) ? statusFilter.value : "";
    const wantedStage = (stageFilter && stageFilter.value) ? stageFilter.value : "";
    const term = (searchFilter && searchFilter.value) ? searchFilter.value.trim().toLowerCase() : "";

    return rows.filter((row) => {
      const statusOk = !wantedStatus || (row.dataset.status || "") === wantedStatus;
      const stageOk = !wantedStage || (row.dataset.stage || "") === wantedStage;
      const haystack = [
        row.dataset.run || "",
        row.dataset.status || "",
        row.dataset.stage || "",
        row.dataset.remarks || ""
      ].join(" ").toLowerCase();
      const searchOk = !term || haystack.includes(term);
      return statusOk && stageOk && searchOk;
    });
  }

  function render() {
    let rows = applyFilters(allRows.slice());

    if (currentKey) {
      const activeBtn = headerButtons.find((btn) => btn.dataset.key === currentKey);
      const type = activeBtn ? (activeBtn.dataset.type || "text") : "text";

      rows.sort((a, b) => {
        const av = getRowValue(a, currentKey, type);
        const bv = getRowValue(b, currentKey, type);
        if (av < bv) return currentDir === "asc" ? -1 : 1;
        if (av > bv) return currentDir === "asc" ? 1 : -1;
        return 0;
      });
    }

    if (pinSelected && pinSelected.checked) {
      rows.sort((a, b) => Number(b.dataset.selected || "0") - Number(a.dataset.selected || "0"));
    }

    tbody.innerHTML = "";
    rows.forEach((row) => tbody.appendChild(row));

    if (visibleSummary) {
      visibleSummary.textContent = "Showing " + rows.length + " of " + allRows.length + " runs";
    }

    updateHeaderState();
  }

  headerButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const key = btn.dataset.key || "";
      if (!key) return;
      if (currentKey === key) {
        currentDir = currentDir === "asc" ? "desc" : "asc";
      } else {
        currentKey = key;
        currentDir = "asc";
      }
      render();
    });
  });

  [statusFilter, stageFilter, searchFilter, pinSelected].forEach((el) => {
    if (!el) return;
    el.addEventListener("input", render);
    el.addEventListener("change", render);
  });

  render();
})();
</script>
"""

    best_text = ""
    if best:
        best_text = (
            '<section class="card span-7">'
            "<h2>Chosen best run</h2>"
            f"<p><strong>Run:</strong> {html.escape(str(best.get('_variant', '')))} / "
            f"{html.escape(str(best.get('_run_dir', '')))}</p>"
            f"<p><strong>Clock:</strong> {html.escape(str(best.get('clock_ns', '')))} ns</p>"
            f"<p><strong>Status:</strong> {badge_html(best.get('status', ''))}</p>"
            f"<p><strong>Remarks:</strong> {html.escape(str(best.get('selection_reason', '')))}</p>"
            "</section>"
        )

    index_html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>ASIC Flow Run Explorer</title>
  <style>{css}</style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <div class="hero-head">
        <div class="hero-copy">
          <h1>ASIC Flow Run Explorer</h1>
          <p>Published summary of all collected runs, richer per-run metrics, and direct access to downloadable layout data.</p>
          <p><strong>Snapshot run ID:</strong> {html.escape(snapshot_label)} · <strong>Repository:</strong> {html.escape(repo_slug_label or '—')}</p>
          <ul class="settings-list">{settings_html}</ul>
        </div>
        {theme_widget}
      </div>
    </section>

    <div class="grid">
      <section class="card span-5">
        <h2>Selection order</h2>
        <ol>
          <li>Clean signoff plus non-negative setup timing wins.</li>
          <li>If no full PASS exists, clean signoff wins over signoff violations.</li>
          <li>Among comparable runs, lower requested clock period is preferred.</li>
          <li>Setup WNS/TNS are used as tie-breakers.</li>
        </ol>
      </section>

      {best_text}

      <section class="card span-12">
        <h2>Run overview</h2>
        <div class="kpi-grid">
          <div class="stat">
            <div class="label">Total runs</div>
            <div class="value">{len(ordered)}</div>
          </div>
          <div class="stat">
            <div class="label">PASS runs</div>
            <div class="value">{sum(1 for r in ordered if r.get("status") == "PASS")}</div>
          </div>
          <div class="stat">
            <div class="label">Non-pass runs</div>
            <div class="value">{sum(1 for r in ordered if r.get("status") != "PASS")}</div>
          </div>
          <div class="stat">
            <div class="label">Best clock</div>
            <div class="value">{html.escape(str(best.get("clock_ns", "")))}</div>
          </div>
        </div>
      </section>
    </div>

    <section class="card table-card">
      <div class="table-head"><h2>All runs</h2><span>Top row is the selected best run</span></div>
      <div class="table-tools">
        <label>Status
          <select id="statusFilter">
            <option value="">All</option>
            <option value="PASS">PASS</option>
            <option value="TIMING_FAIL">TIMING_FAIL</option>
            <option value="SIGNOFF_FAIL">SIGNOFF_FAIL</option>
            <option value="SIGNOFF_AND_TIMING_FAIL">SIGNOFF_AND_TIMING_FAIL</option>
            <option value="FLOW_FAIL">FLOW_FAIL</option>
          </select>
        </label>

        <label>Stage
          <select id="stageFilter">
            <option value="">All</option>
            {stage_options_html}
          </select>
        </label>

        <label>Search
          <input id="searchFilter" type="search" placeholder="Run, remarks, status...">
        </label>

        <label class="inline-check">
          <input type="checkbox" id="pinSelected" checked>
          Keep selected run on top
        </label>

        <div class="summary" id="visibleRowsSummary"></div>
      </div>
      <div class="table-wrap">
        <table class="wide-table">
          <thead>
            <tr>
              <th><button class="sort-btn" data-key="selected" data-type="number" aria-sort="none">Selected <span class="sort-indicator">↕</span></button></th>
              <th><button class="sort-btn" data-key="run" data-type="text" aria-sort="none">Run <span class="sort-indicator">↕</span></button></th>
              <th><button class="sort-btn" data-key="clock" data-type="number" aria-sort="none">Clock (ns) <span class="sort-indicator">↕</span></button></th>
              <th><button class="sort-btn" data-key="setup_wns" data-type="number" aria-sort="none">Setup WNS <span class="sort-indicator">↕</span></button></th>
              <th><button class="sort-btn" data-key="setup_tns" data-type="number" aria-sort="none">Setup TNS <span class="sort-indicator">↕</span></button></th>
              <th><button class="sort-btn" data-key="core_area" data-type="number" aria-sort="none">Core area <span class="sort-indicator">↕</span></button></th>
              <th><button class="sort-btn" data-key="power_total" data-type="number" aria-sort="none">Total power <span class="sort-indicator">↕</span></button></th>
              <th><button class="sort-btn" data-key="drc" data-type="number" aria-sort="none">DRC <span class="sort-indicator">↕</span></button></th>
              <th><button class="sort-btn" data-key="lvs" data-type="number" aria-sort="none">LVS <span class="sort-indicator">↕</span></button></th>
              <th><button class="sort-btn" data-key="antenna" data-type="number" aria-sort="none">Antenna <span class="sort-indicator">↕</span></button></th>
              <th><button class="sort-btn" data-key="ir_drop" data-type="number" aria-sort="none">IR drop <span class="sort-indicator">↕</span></button></th>
              <th><button class="sort-btn" data-key="status" data-type="status" aria-sort="none">Status <span class="sort-indicator">↕</span></button></th>
              <th><button class="sort-btn" data-key="remarks" data-type="text" aria-sort="none">Remarks <span class="sort-indicator">↕</span></button></th>
              <th>GDS</th>
              <th>GDS Viewer</th>
            </tr>
          </thead>
          <tbody>{''.join(rows_html)}</tbody>
        </table>
      </div>
    </section>
  </div>

  {theme_script}
  {sort_filter_script}
</body>
</html>"""
    (snapshot_root / "index.html").write_text(index_html, encoding="utf-8")

    site_manifest = {
        "repo_slug": repo_slug_label,
        "run_id": run_id_label,
        "site_subdir": normalized_site_subdir,
        "entrypoint": f"{normalized_site_subdir + '/' if normalized_site_subdir else ''}index.html",
        "snapshot_root": str(snapshot_root.relative_to(site_root)) if snapshot_root != site_root else ".",
    }
    (site_root / "site_manifest.json").write_text(json.dumps(site_manifest, indent=2), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifacts-root", type=Path, required=True)
    ap.add_argument("--summary-md", type=Path, required=True)
    ap.add_argument("--summary-csv", type=Path, required=True)
    ap.add_argument("--best-json", type=Path, required=True)
    ap.add_argument("--best-bundle-dir", type=Path, default=Path("best-layout-bundle"))
    ap.add_argument("--site-dir", type=Path, default=Path("_site"))
    ap.add_argument("--site-subdir", default="")
    ap.add_argument("--repo-slug", default="")
    ap.add_argument("--run-id", default="")
    ap.add_argument("--summary-synth-strategy", default="")
    ap.add_argument("--summary-antenna-repair", default="")
    ap.add_argument("--summary-heuristic-diode-insertion", default="")
    ap.add_argument("--summary-post-grt-design-repair", default="")
    ap.add_argument("--summary-post-grt-resizer-timing", default="")
    args = ap.parse_args()

    rows = collect_rows(args.artifacts_root)
    write_summary_csv(args.summary_csv, rows)
    write_summary_md(args.summary_md, rows)
    best = write_best_json(args.best_json, rows)
    package_best_bundle(args.best_bundle_dir, best)
    requested_site_subdir = normalize_site_subdir(args.site_subdir)
    if not requested_site_subdir and str(args.run_id or "").strip():
        requested_site_subdir = normalize_site_subdir(f"runs/{sanitize_site_component(args.run_id)}")

    build_site(
        args.site_dir,
        rows,
        explorer_settings={
            "synth_strategy": args.summary_synth_strategy,
            "antenna_repair": args.summary_antenna_repair,
            "heuristic_diode_insertion": args.summary_heuristic_diode_insertion,
            "post_grt_design_repair": args.summary_post_grt_design_repair,
            "post_grt_resizer_timing": args.summary_post_grt_resizer_timing,
        },
        repo_slug=args.repo_slug,
        run_id=args.run_id,
        site_subdir=requested_site_subdir,
    )


if __name__ == "__main__":
    main()