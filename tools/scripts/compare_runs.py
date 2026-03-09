#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional


SUMMARY_FIELDS = [
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
    "_viewer_rel",
    "_bundle_rel",
    "_metrics_csv",
    "_metrics_raw",
    "_gds_file",
]


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
    if signoff_clean(row) and timing_ok(row):
        return "PASS"
    if signoff_clean(row):
        return "SIGNOFF_CLEAN_TIMING_FAIL"
    return "INCOMPLETE"



def best_sort_key(row: Dict[str, str]):
    clean = signoff_clean(row)
    timing = timing_ok(row)
    clk = to_float(row.get("clock_ns"))
    swns = to_float(row.get("setup_wns_ns"))
    stns = to_float(row.get("setup_tns_ns"))

    return (
        0 if clean and timing else 1,
        0 if clean else 1,
        clk if clk is not None else 1e12,
        -(swns if swns is not None else -1e12),
        -(stns if stns is not None else -1e12),
    )



def slugify(text: str) -> str:
    keep = []
    for ch in str(text):
        if ch.isalnum() or ch in ("-", "_"):
            keep.append(ch)
        else:
            keep.append("-")
    out = "".join(keep).strip("-")
    while "--" in out:
        out = out.replace("--", "-")
    return out or "run"



def first_existing_file(paths: List[Path]) -> Optional[Path]:
    for path in paths:
        if path.exists() and path.is_file():
            return path
    return None



def first_gds(base_dir: Path) -> Optional[Path]:
    gds_dir = base_dir / "final" / "gds"
    if gds_dir.exists():
        files = sorted(gds_dir.glob("*.gds"))
        if files:
            return files[0]
    files = sorted(base_dir.glob("**/final/gds/*.gds"))
    return files[0] if files else None



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
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except Exception:
                    meta = {}

            gds_path = first_gds(base_dir)
            run_id = str(meta.get("github_run_id") or "")
            requested_clock = str(meta.get("clock_ns_requested") or row.get("clock_ns") or "")
            variant = str(meta.get("variant") or base_dir.parent.name)

            row["_artifact"] = str(meta.get("artifact_name") or "")
            row["_variant"] = variant
            row["_run_dir"] = base_dir.name
            row["_metrics_csv"] = str(csv_path.relative_to(artifacts_root))
            row["_metrics_raw"] = str((base_dir / "metrics_raw.json").relative_to(artifacts_root)) if (base_dir / "metrics_raw.json").exists() else ""
            row["_gds_file"] = str(gds_path.relative_to(artifacts_root)) if gds_path else ""
            row["_base_dir"] = str(base_dir)
            row["_github_run_id"] = run_id
            row["_clock_requested"] = requested_clock
            row["_site_slug"] = slugify(f"{variant}-clk-{requested_clock}ns-run-{run_id or base_dir.name}")
            row["status"] = classify_status(row)
            rows.append(row)

    return rows



def write_summary_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in SUMMARY_FIELDS})



def write_summary_md(path: Path, rows: List[Dict[str, str]]) -> None:
    lines: List[str] = []
    lines.append("## Best run")
    lines.append("")

    if rows:
        best = sorted(rows, key=best_sort_key)[0]
        lines.append("| Variant | Run | Clock (ns) | Setup WNS | Setup TNS | Hold WNS | DRC | LVS | Antenna | Status | Bundle | Viewer |")
        lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|")
        lines.append(
            f"| {best.get('_variant','')} | {best.get('_run_dir','')} | "
            f"{best.get('clock_ns','')} | {best.get('setup_wns_ns','')} | {best.get('setup_tns_ns','')} | {best.get('hold_wns_ns','')} | "
            f"{best.get('drc_errors','')} | {best.get('lvs_errors','')} | {best.get('antenna_violations','')} | "
            f"{best.get('status','')} | {best.get('_bundle_rel','')} | {best.get('_viewer_rel','')} |"
        )
    else:
        lines.append("No runs collected.")
    lines.append("")

    lines.append("## All runs")
    lines.append("")
    lines.append("| Variant | Run | Clock (ns) | Setup WNS | Setup TNS | Hold WNS | Core Area | Die Area | Inst | Util (%) | Power (W) | DRC | LVS | Antenna | IR Drop (V) | Status | Bundle | Viewer |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|")

    for row in sorted(rows, key=best_sort_key):
        lines.append(
            f"| {row.get('_variant','')} | {row.get('_run_dir','')} | "
            f"{row.get('clock_ns','')} | {row.get('setup_wns_ns','')} | {row.get('setup_tns_ns','')} | {row.get('hold_wns_ns','')} | "
            f"{row.get('core_area_um2','')} | {row.get('die_area_um2','')} | {row.get('instance_count','')} | "
            f"{row.get('utilization_pct','')} | {row.get('power_total_W','')} | {row.get('drc_errors','')} | "
            f"{row.get('lvs_errors','')} | {row.get('antenna_violations','')} | {row.get('ir_drop_worst_V','')} | "
            f"{row.get('status','')} | {row.get('_bundle_rel','')} | {row.get('_viewer_rel','')} |"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")



def copy_if_exists(src: Optional[Path], dst: Path) -> Optional[Path]:
    if not src or not src.exists():
        return None
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return dst



def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")



def package_best_bundle(best_bundle_dir: Path, best: Dict[str, str]) -> None:
    best_bundle_dir.mkdir(parents=True, exist_ok=True)
    base_dir = Path(best["_base_dir"])
    gds_src = Path(best["_gds_file"]) if best.get("_gds_file") else None
    if gds_src and not gds_src.is_absolute():
        # stored relative to artifacts root, so prefer base_dir-derived file
        gds_src = first_gds(base_dir)

    copied_files: Dict[str, str] = {}
    for src_name, dst_name in [
        (base_dir / "metrics.csv", "metrics.csv"),
        (base_dir / "metrics.md", "metrics.md"),
        (base_dir / "metrics_raw.json", "metrics_raw.json"),
        (base_dir / "run_meta.json", "run_meta.json"),
        (gds_src, "layout.gds"),
    ]:
        copied = copy_if_exists(src_name, best_bundle_dir / dst_name)
        if copied:
            copied_files[dst_name] = copied.name

    manifest = {
        "variant": best.get("_variant"),
        "clock_ns": best.get("clock_ns"),
        "status": best.get("status"),
        "github_run_id": best.get("_github_run_id"),
        "artifact_name": best.get("_artifact"),
        "files": copied_files,
    }
    write_json(best_bundle_dir / "manifest.json", manifest)
    write_json(best_bundle_dir / "best_run.json", best)



def build_site(site_dir: Path, rows: List[Dict[str, str]], viewer_url_format: str) -> List[Dict[str, str]]:
    site_dir.mkdir(parents=True, exist_ok=True)
    bundles_dir = site_dir / "bundles"
    runs_dir = site_dir / "runs"
    bundles_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)

    links: List[Dict[str, str]] = []
    sorted_rows = sorted(rows, key=best_sort_key)
    best_slug = sorted_rows[0].get("_site_slug") if sorted_rows else None

    for row in sorted_rows:
        base_dir = Path(row["_base_dir"])
        slug = row["_site_slug"]
        run_bundle_dir = bundles_dir / slug
        run_page_dir = runs_dir / slug
        run_bundle_dir.mkdir(parents=True, exist_ok=True)
        run_page_dir.mkdir(parents=True, exist_ok=True)

        gds_src = first_gds(base_dir)
        metrics_csv = base_dir / "metrics.csv"
        metrics_raw = base_dir / "metrics_raw.json"
        run_meta = base_dir / "run_meta.json"
        metrics_md = base_dir / "metrics.md"

        copied_files: Dict[str, str] = {}
        for src, dst_name in [
            (gds_src, "layout.gds"),
            (metrics_csv, "metrics.csv"),
            (metrics_md, "metrics.md"),
            (metrics_raw, "metrics_raw.json"),
            (run_meta, "run_meta.json"),
        ]:
            copied = copy_if_exists(src, run_bundle_dir / dst_name)
            if copied:
                copied_files[dst_name] = copied.name

        manifest = {
            "variant": row.get("_variant"),
            "clock_ns": row.get("clock_ns"),
            "clock_ns_requested": row.get("_clock_requested"),
            "github_run_id": row.get("_github_run_id"),
            "status": row.get("status"),
            "artifact_name": row.get("_artifact"),
            "files": copied_files,
        }
        write_json(run_bundle_dir / "manifest.json", manifest)

        bundle_rel = f"bundles/{slug}/"
        gds_rel = f"bundles/{slug}/layout.gds"
        viewer_rel = f"runs/{slug}/"

        row["_bundle_rel"] = bundle_rel
        row["_viewer_rel"] = viewer_rel

        viewer_url = ""
        if viewer_url_format and copied_files.get("layout.gds"):
            viewer_url = viewer_url_format.replace("{gds_url}", f"{{PAGE_URL}}/{gds_rel}")

        html = f"""<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
  <title>{row.get('_variant','')} @ {row.get('clock_ns','')} ns</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 960px; margin: 2rem auto; padding: 0 1rem; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
    th, td {{ border: 1px solid #ddd; padding: 0.5rem; text-align: left; }}
    code {{ background: #f4f4f4; padding: 0.15rem 0.35rem; border-radius: 0.3rem; }}
  </style>
</head>
<body>
  <h1>{row.get('_variant','')} @ {row.get('clock_ns','')} ns</h1>
  <p>Status: <strong>{row.get('status','')}</strong></p>
  <p>This is the published run bundle page. It hosts the raw GDS and extracted metrics for this run.</p>
  <ul>
    <li><a href=\"../../{gds_rel}\">Open raw GDS bundle file</a></li>
    <li><a href=\"../../{bundle_rel}\">Open bundle folder index</a></li>
    <li><a href=\"../../index.html\">Back to run index</a></li>
  </ul>
  <table>
    <tr><th>Metric</th><th>Value</th></tr>
    <tr><td>Variant</td><td>{row.get('_variant','')}</td></tr>
    <tr><td>Clock (ns)</td><td>{row.get('clock_ns','')}</td></tr>
    <tr><td>Setup WNS</td><td>{row.get('setup_wns_ns','')}</td></tr>
    <tr><td>Setup TNS</td><td>{row.get('setup_tns_ns','')}</td></tr>
    <tr><td>DRC errors</td><td>{row.get('drc_errors','')}</td></tr>
    <tr><td>LVS errors</td><td>{row.get('lvs_errors','')}</td></tr>
    <tr><td>Antenna violations</td><td>{row.get('antenna_violations','')}</td></tr>
    <tr><td>Artifact</td><td><code>{row.get('_artifact','')}</code></td></tr>
  </table>
</body>
</html>
"""
        (run_page_dir / "index.html").write_text(html, encoding="utf-8")

        links.append(
            {
                "variant": row.get("_variant", ""),
                "clock_ns": str(row.get("clock_ns", "")),
                "github_run_id": row.get("_github_run_id", ""),
                "status": row.get("status", ""),
                "bundle_rel": bundle_rel,
                "viewer_rel": viewer_rel,
                "gds_rel": gds_rel,
                "viewer_url_template": viewer_url,
                "is_best": slug == best_slug,
            }
        )

    lines = [
        "<!doctype html>",
        "<html>",
        "<head>",
        '  <meta charset="utf-8">',
        '  <meta name="viewport" content="width=device-width,initial-scale=1">',
        "  <title>ASIC Flow Layout Bundles</title>",
        "  <style>",
        "    body { font-family: system-ui, sans-serif; max-width: 1200px; margin: 2rem auto; padding: 0 1rem; }",
        "    table { border-collapse: collapse; width: 100%; margin-top: 1rem; }",
        "    th, td { border: 1px solid #ddd; padding: 0.5rem; text-align: left; }",
        "    .best { background: #eef9ee; }",
        "  </style>",
        "</head>",
        "<body>",
        "  <h1>ASIC Flow Published Layout Bundles</h1>",
        "  <p>This Pages site publishes per-run raw GDS bundles and summary metadata. The final TinyTapeout-style viewer deep link can be layered on top once its URL contract is confirmed.</p>",
        "  <table>",
        "    <tr><th>Best</th><th>Variant</th><th>Clock (ns)</th><th>Status</th><th>Bundle</th><th>Run page</th><th>Raw GDS</th></tr>",
    ]
    for link in links:
        row_class = ' class="best"' if link["is_best"] else ""
        best_mark = "★" if link["is_best"] else ""
        lines.append(
            f"    <tr{row_class}><td>{best_mark}</td><td>{link['variant']}</td><td>{link['clock_ns']}</td><td>{link['status']}</td><td><a href=\"{link['bundle_rel']}\">bundle</a></td><td><a href=\"{link['viewer_rel']}\">run page</a></td><td><a href=\"{link['gds_rel']}\">layout.gds</a></td></tr>"
        )
    lines += ["  </table>", "</body>", "</html>"]
    (site_dir / "index.html").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_json(site_dir / "viewer_links_rel.json", links)
    return links



def write_best_json(path: Path, rows: List[Dict[str, str]]) -> None:
    best = sorted(rows, key=best_sort_key)[0] if rows else {}
    path.write_text(json.dumps(best, indent=2), encoding="utf-8")



def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifacts-root", type=Path, required=True)
    ap.add_argument("--summary-md", type=Path, required=True)
    ap.add_argument("--summary-csv", type=Path, required=True)
    ap.add_argument("--best-json", type=Path, required=True)
    ap.add_argument("--best-bundle-dir", type=Path, required=True)
    ap.add_argument("--site-dir", type=Path, required=True)
    ap.add_argument(
        "--viewer-url-format",
        default="",
        help="Optional external viewer URL template. Use {gds_url} as placeholder.",
    )
    args = ap.parse_args()

    rows = collect_rows(args.artifacts_root)
    build_site(args.site_dir, rows, args.viewer_url_format)
    write_summary_csv(args.summary_csv, rows)
    write_summary_md(args.summary_md, rows)
    write_best_json(args.best_json, rows)

    if rows:
        best = sorted(rows, key=best_sort_key)[0]
        package_best_bundle(args.best_bundle_dir, best)
    else:
        args.best_bundle_dir.mkdir(parents=True, exist_ok=True)
        write_json(args.best_bundle_dir / "manifest.json", {"error": "No runs collected"})


if __name__ == "__main__":
    main()
