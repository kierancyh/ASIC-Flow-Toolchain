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
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


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
        lines.append(f"- Why selected: {md_escape(best.get('selection_reason'))}")
        lines.append("")
    else:
        lines.append("No runs collected.")
        lines.append("")

    lines.append("## All runs")
    lines.append("")
    lines.append("| Variant | Run | Clock (ns) | Setup WNS | Setup TNS | DRC | LVS | Antenna | Status | Why not best / why selected |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---|---|")

    for idx, row in enumerate(sorted(rows, key=best_sort_key)):
        why = row.get("selection_reason", "")
        if idx == 0:
            why = f"SELECTED — {why}"
        lines.append(
            f"| {md_escape(row.get('_variant'))} | {md_escape(row.get('_run_dir'))} | {md_escape(row.get('clock_ns'))} | "
            f"{md_escape(row.get('setup_wns_ns'))} | {md_escape(row.get('setup_tns_ns'))} | {md_escape(row.get('drc_errors'))} | "
            f"{md_escape(row.get('lvs_errors'))} | {md_escape(row.get('antenna_violations'))} | {md_escape(row.get('status'))} | {md_escape(why)} |"
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
  --bg:#0b1020;
  --panel:#131a2e;
  --panel-2:#18223b;
  --border:#2a3558;
  --text:#eaf0ff;
  --muted:#a9b6d3;
  --accent:#7aa2ff;
  --accent-2:#4de2c5;
  --pass:#1f9d63;
  --timing:#d29b19;
  --signoff:#d15b5b;
  --mixed:#c26ce5;
  --flow:#6b7280;
  --shadow:0 18px 45px rgba(0,0,0,.28);
  --radius:18px;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:linear-gradient(180deg,#09101f 0%,#0b1020 100%);color:var(--text);font:15px/1.55 Inter,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:1440px;margin:0 auto;padding:28px 20px 40px}
.hero{
  background:linear-gradient(135deg,rgba(122,162,255,.18),rgba(77,226,197,.10));
  border:1px solid rgba(122,162,255,.2);
  border-radius:28px;
  padding:28px;
  box-shadow:var(--shadow);
  margin-bottom:22px;
}
.hero h1{margin:0 0 10px;font-size:34px;line-height:1.1}
.hero p{margin:0;color:var(--muted);max-width:920px}
.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:18px}
.card{
  background:rgba(19,26,46,.92);
  border:1px solid var(--border);
  border-radius:var(--radius);
  padding:20px;
  box-shadow:var(--shadow);
}
.card h2,.card h3{margin:0 0 12px}
.card p{margin:0 0 10px}
.rules{grid-column:span 5}
.best{grid-column:span 7}
.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-top:14px}
.stat{
  background:rgba(255,255,255,.03);
  border:1px solid rgba(255,255,255,.06);
  border-radius:14px;
  padding:14px
}
.stat .label{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.08em}
.stat .value{font-size:26px;font-weight:700;margin-top:4px}
.list-clean{margin:0;padding-left:20px}
.list-clean li{margin:8px 0}
.table-card{margin-top:18px;padding:0;overflow:hidden}
.table-head{
  display:flex;justify-content:space-between;align-items:center;
  padding:18px 20px;border-bottom:1px solid var(--border)
}
.table-head h2{margin:0;font-size:20px}
.table-wrap{overflow:auto}
table{width:100%;border-collapse:collapse;min-width:1320px}
th,td{padding:14px 16px;border-bottom:1px solid rgba(255,255,255,.06);vertical-align:top}
th{
  position:sticky;top:0;background:#17213a;color:#dce6ff;
  text-align:left;font-size:13px;letter-spacing:.03em
}
tr:hover td{background:rgba(255,255,255,.025)}
.selected-row td{background:rgba(122,162,255,.08)}
.badge{
  display:inline-flex;align-items:center;justify-content:center;
  min-width:92px;padding:6px 10px;border-radius:999px;font-size:12px;
  font-weight:700;letter-spacing:.02em;border:1px solid transparent
}
.badge.pass{background:rgba(31,157,99,.18);color:#88f0bc;border-color:rgba(31,157,99,.35)}
.badge.timing{background:rgba(210,155,25,.18);color:#ffd66b;border-color:rgba(210,155,25,.35)}
.badge.signoff{background:rgba(209,91,91,.18);color:#ffadad;border-color:rgba(209,91,91,.35)}
.badge.mixed{background:rgba(194,108,229,.18);color:#ebb0ff;border-color:rgba(194,108,229,.35)}
.badge.flow{background:rgba(107,114,128,.18);color:#c8cfdb;border-color:rgba(107,114,128,.35)}
.tag{
  display:inline-block;padding:4px 10px;border-radius:999px;
  background:rgba(77,226,197,.14);border:1px solid rgba(77,226,197,.28);
  color:#8ff2de;font-size:12px;font-weight:700
}
.actions{display:flex;gap:8px;flex-wrap:wrap}
.btn{
  display:inline-flex;align-items:center;justify-content:center;
  padding:8px 12px;border-radius:10px;border:1px solid rgba(122,162,255,.28);
  background:rgba(122,162,255,.10);color:#dfe7ff;font-weight:600;font-size:13px
}
.btn.secondary{
  border-color:rgba(255,255,255,.10);background:rgba(255,255,255,.04);color:#d5def5
}
.muted{color:var(--muted)}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.small{font-size:13px}
@media (max-width:1000px){
  .rules,.best{grid-column:1 / -1}
  .stats{grid-template-columns:repeat(2,minmax(0,1fr))}
  .hero h1{font-size:28px}
}
@media (max-width:640px){
  .stats{grid-template-columns:1fr}
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
        reason = html.escape(row.get("selection_reason", ""))
        gds_link = f'<a class="btn" href="{html.escape(gds_name)}">Download GDS</a>' if gds_name else '<span class="muted">No GDS copied</span>'
        viewer_link = f'<a class="btn secondary" href="{TT_GDS_VIEWER_URL}" target="_blank" rel="noopener noreferrer">Open GDS Viewer (TinyTapeout)</a>'

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
      <h1>{title}</h1>
      <p>Per-run detail page with timing, area, power, signoff, downloadable layout data, and viewer access.</p>
    </div>

    <div class="grid">
      <section class="card rules">
        <h2>Run status</h2>
        <p>{badge_html(row.get('status',''))}</p>
        <p><strong>Selection rationale:</strong> {reason}</p>
        <p><a class="btn secondary" href="../../index.html">Back to ASIC Flow Run Explorer</a></p>
      </section>

      <section class="card best">
        <h2>Downloads and tools</h2>
        <div class="actions">
          {gds_link}
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
</body>
</html>
"""
        (run_dir / "index.html").write_text(run_html, encoding="utf-8")

    total_runs = len(sorted_rows)
    pass_count = sum(1 for row in sorted_rows if row.get("status") == "PASS")
    fail_count = total_runs - pass_count
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
          <p><strong>Why selected:</strong> {html.escape(str(best.get('selection_reason','')))}</p>
        </section>
        """

    rows_html: List[str] = []
    for idx, row in enumerate(sorted_rows):
        run_page = f"runs/{html.escape(row['_site_slug'])}/index.html"
        gds_page = ""
        if row.get("_site_gds"):
            gds_page = f'runs/{html.escape(row["_site_slug"])}/{html.escape(row["_site_gds"])}'

        selected_marker = '<span class="tag">Selected</span>' if idx == 0 else ""
        gds_link = f'<a class="btn" href="{gds_page}">GDS</a>' if gds_page else '<span class="muted small">No GDS</span>'
        tt_viewer_link = f'<a class="btn secondary" href="{TT_GDS_VIEWER_URL}" target="_blank" rel="noopener noreferrer">Open View</a>'
        row_class = "selected-row" if idx == 0 else ""

        rows_html.append(
            "<tr class=\"%s\">"
            "<td>%s</td>"
            "<td><a href=\"%s\"><strong>%s / %s</strong></a><div class=\"muted small mono\">%s</div></td>"
            "<td>%s</td>"
            "<td>%s</td>"
            "<td>%s</td>"
            "<td>%s</td>"
            "<td>%s</td>"
            "<td>%s</td>"
            "<td>%s</td>"
            "<td>%s</td>"
            "<td>%s</td>"
            "<td>%s</td>"
            "</tr>"
            % (
                row_class,
                selected_marker,
                run_page,
                html.escape(str(row.get("_variant", ""))),
                html.escape(str(row.get("_run_dir", ""))),
                html.escape(str(row.get("_artifact", ""))),
                html.escape(str(row.get("clock_ns", ""))),
                html.escape(str(row.get("setup_wns_ns", ""))),
                html.escape(str(row.get("setup_tns_ns", ""))),
                html.escape(str(row.get("drc_errors", ""))),
                html.escape(str(row.get("lvs_errors", ""))),
                html.escape(str(row.get("antenna_violations", ""))),
                badge_html(row.get("status", "")),
                html.escape(str(row.get("selection_reason", ""))),
                gds_link,
                tt_viewer_link,
            )
        )

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
      <h1>ASIC Flow Run Explorer</h1>
      <p>Published summary of all collected runs, how the best run was selected, and direct access to per-run pages and downloadable GDS files.</p>
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
          <div class="value">{html.escape(str(sorted_rows[0].get('clock_ns','') if sorted_rows else ''))}</div>
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
              <th>Selection rationale</th>
              <th>GDS</th>
              <th>GDS Viewer (TinyTapeout)</th>
            </tr>
          </thead>
          <tbody>
            {''.join(rows_html)}
          </tbody>
        </table>
      </div>
    </section>
  </div>
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