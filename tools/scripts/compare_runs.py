#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

TT_VIEWER_URL = "https://gds-viewer.tinytapeout.com/"


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
            row["_metrics_raw"] = str((base_dir / "metrics_raw.json").relative_to(artifacts_root)) if (base_dir / "metrics_raw.json").exists() else ""
            row["_gds_dir"] = str((base_dir / "final" / "gds").relative_to(artifacts_root)) if (base_dir / "final" / "gds").exists() else ""
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


def build_site(site_root: Path, rows: List[Dict[str, str]]) -> None:
    site_root.mkdir(parents=True, exist_ok=True)
    runs_root = site_root / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)

    sorted_rows = sorted(rows, key=best_sort_key)

    for row in sorted_rows:
        slug = f"{row.get('_variant', 'variant').replace('/', '_')}__{row.get('_run_dir', 'run')}"
        row["_site_slug"] = slug
        run_dir = runs_root / slug
        run_dir.mkdir(parents=True, exist_ok=True)

        gds_name = ""
        gds_src = Path(row["_gds_path"]) if row.get("_gds_path") else None
        if gds_src and gds_src.exists():
            gds_name = copy_named_gds(gds_src, run_dir, row.get("_run_dir", "layout"))
        row["_site_gds"] = gds_name

        metrics_src = Path(row["_base_dir"]) / "metrics.csv"
        if metrics_src.exists():
            shutil.copy2(metrics_src, run_dir / "metrics.csv")
        metrics_raw_src = Path(row["_base_dir"]) / "metrics_raw.json"
        if metrics_raw_src.exists():
            shutil.copy2(metrics_raw_src, run_dir / "metrics_raw.json")
        run_meta_src = Path(row["_base_dir"]) / "run_meta.json"
        if run_meta_src.exists():
            shutil.copy2(run_meta_src, run_dir / "run_meta.json")

        title = html.escape(f"{row.get('_variant','')} — {row.get('_run_dir','')}")
        reason = html.escape(row.get("selection_reason", ""))
        gds_link = f'<a href="{html.escape(gds_name)}">Download {html.escape(gds_name)}</a>' if gds_name else "No GDS copied"

        run_html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body{{font-family:Arial,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;line-height:1.5}}
code{{background:#f4f4f4;padding:.15rem .35rem;border-radius:4px}}
table{{border-collapse:collapse;width:100%;margin-bottom:1rem}}
th,td{{border:1px solid #ddd;padding:.55rem;text-align:left}}
th{{background:#f7f7f7}}
.pill{{display:inline-block;padding:.2rem .5rem;border-radius:999px;background:#efefef}}
</style></head><body>
<h1>{title}</h1>
<p><a href="../../index.html">Back to ASIC Flow Run Explorer</a></p>
<p><strong>Status:</strong> <span class="pill">{html.escape(row.get('status', ''))}</span></p>
<p><strong>Selection rationale:</strong> {reason}</p>
<ul>
<li>{gds_link}</li>
<li><a href="{TT_VIEWER_URL}" target="_blank" rel="noopener noreferrer">Open TinyTapeout Viewer</a></li>
</ul>

<h2>Timing</h2>
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

<h2>Area and power</h2>
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
<tr><td>power_source</td><td>{html.escape(str(row.get('power_source', '')))}</td></tr>
</table>

<h2>Signoff and physical</h2>
<table>
<tr><th>Metric</th><th>Value</th></tr>
<tr><td>drc_errors</td><td>{html.escape(str(row.get('drc_errors', '')))}</td></tr>
<tr><td>drc_errors_klayout</td><td>{html.escape(str(row.get('drc_errors_klayout', '')))}</td></tr>
<tr><td>drc_errors_magic</td><td>{html.escape(str(row.get('drc_errors_magic', '')))}</td></tr>
<tr><td>lvs_errors</td><td>{html.escape(str(row.get('lvs_errors', '')))}</td></tr>
<tr><td>antenna_violations</td><td>{html.escape(str(row.get('antenna_violations', '')))}</td></tr>
<tr><td>antenna_violating_nets</td><td>{html.escape(str(row.get('antenna_violating_nets', '')))}</td></tr>
<tr><td>antenna_violating_pins</td><td>{html.escape(str(row.get('antenna_violating_pins', '')))}</td></tr>
<tr><td>ir_drop_worst_V</td><td>{html.escape(str(row.get('ir_drop_worst_V', '')))}</td></tr>
</table>
</body></html>"""
        (run_dir / "index.html").write_text(run_html, encoding="utf-8")

    rows_html = []
    for idx, row in enumerate(sorted_rows):
        run_page = f"runs/{html.escape(row['_site_slug'])}/index.html"
        gds_html = html.escape(row.get("_site_gds", ""))
        if row.get("_site_gds"):
            gds_html = f'<a href="runs/{html.escape(row["_site_slug"])}/{html.escape(row["_site_gds"])}">{html.escape(row["_site_gds"])}</a>'
        selected = "SELECTED" if idx == 0 else ""
        rows_html.append(
            "<tr>"
            f"<td>{html.escape(selected)}</td>"
            f"<td><a href=\"{run_page}\">{html.escape(str(row.get('_variant','')))} / {html.escape(str(row.get('_run_dir','')))}</a></td>"
            f"<td>{html.escape(str(row.get('clock_ns','')))}</td>"
            f"<td>{html.escape(str(row.get('setup_wns_ns','')))}</td>"
            f"<td>{html.escape(str(row.get('setup_tns_ns','')))}</td>"
            f"<td>{html.escape(str(row.get('drc_errors','')))}</td>"
            f"<td>{html.escape(str(row.get('lvs_errors','')))}</td>"
            f"<td>{html.escape(str(row.get('antenna_violations','')))}</td>"
            f"<td>{html.escape(str(row.get('status','')))}</td>"
            f"<td>{html.escape(str(row.get('selection_reason','')))}</td>"
            f"<td>{gds_html}</td>"
            f"<td><a href=\"{TT_VIEWER_URL}\" target=\"_blank\" rel=\"noopener noreferrer\">Open viewer</a></td>"
            "</tr>"
        )

    best_text = ""
    if sorted_rows:
        best = sorted_rows[0]
        best_text = (
            f"<p><strong>Best run:</strong> {html.escape(str(best.get('_variant','')))} / {html.escape(str(best.get('_run_dir','')))} "
            f"at {html.escape(str(best.get('clock_ns','')))} ns.</p>"
            f"<p><strong>Why this run won:</strong> {html.escape(str(best.get('selection_reason','')))}</p>"
        )

    index_html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>ASIC Flow Run Explorer</title>
<style>
body{{font-family:Arial,sans-serif;max-width:1400px;margin:2rem auto;padding:0 1rem;line-height:1.5}}
table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ddd;padding:.55rem;text-align:left;vertical-align:top}}th{{background:#f7f7f7}}code{{background:#f4f4f4;padding:.15rem .35rem;border-radius:4px}}
</style></head><body>
<h1>ASIC Flow Run Explorer</h1>
<p>This published site is a quick-access summary for all collected runs. It explains why the best run was selected and why the other runs were not selected.</p>
<p><strong>Best-run selection order:</strong> clean signoff plus non-negative setup timing first, then clean signoff over signoff failures, then lower requested clock period, then better setup WNS/TNS tie-breakers.</p>
{best_text}
<table>
<thead><tr><th>Best</th><th>Run</th><th>Clock (ns)</th><th>Setup WNS</th><th>Setup TNS</th><th>DRC</th><th>LVS</th><th>Antenna</th><th>Status</th><th>Why selected / why not best</th><th>Named GDS</th><th>TinyTapeout viewer</th></tr></thead>
<tbody>
{''.join(rows_html)}
</tbody></table>
</body></html>"""
    (site_root / "index.html").write_text(index_html, encoding="utf-8")


def package_best_bundle(best_bundle_dir: Path, best: Dict[str, Any]) -> None:
    best_bundle_dir.mkdir(parents=True, exist_ok=True)
    if not best:
        return

    base_dir = Path(best["_base_dir"])
    for name in ("metrics.csv", "metrics_raw.json", "run_meta.json"):
        src = base_dir / name
        if src.exists():
            shutil.copy2(src, best_bundle_dir / name)

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