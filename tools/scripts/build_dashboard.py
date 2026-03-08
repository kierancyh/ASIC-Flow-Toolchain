#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_manifest() -> dict:
    return yaml.safe_load((ROOT / "manifest.yaml").read_text(encoding="utf-8"))


def safe_variant_name(variant_path: str) -> str:
    return variant_path.replace("/", "_")


def read_metrics_csv(p: Path) -> Optional[Dict[str, str]]:
    if not p.exists():
        return None
    with p.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows[0] if rows else None


def to_float(v: Any) -> Optional[float]:
    try:
        if v in (None, "", "None"):
            return None
        return float(v)
    except Exception:
        return None


def signoff_clean(row: Dict[str, str]) -> bool:
    for k in ("drc_errors", "lvs_errors", "antenna_violations"):
        v = to_float(row.get(k))
        if v is not None and v != 0.0:
            return False
    return True


def timing_ok(row: Dict[str, str]) -> bool:
    swns = to_float(row.get("setup_wns_ns"))
    stns = to_float(row.get("setup_tns_ns"))
    return swns is not None and stns is not None and swns >= 0.0 and stns >= 0.0


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


def status_badge(row: Dict[str, str]) -> str:
    s = row.get("status", "")
    if s == "PASS":
        return "PASS"
    if s == "SIGNOFF_CLEAN_TIMING_FAIL":
        return "TIMING_FAIL"
    return "INCOMPLETE"


def html_page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:1280px;margin:24px auto;padding:0 16px;line-height:1.45}}
h1,h2,h3{{margin-top:1.2em}}
table{{border-collapse:collapse;width:100%;margin:16px 0;font-size:14px}}
th,td{{border:1px solid #ddd;padding:8px 10px;text-align:left;vertical-align:top}}
th{{background:#f6f6f6;position:sticky;top:0}}
code{{background:#f4f4f4;padding:2px 6px;border-radius:6px}}
.card{{border:1px solid #ddd;border-radius:12px;padding:16px;margin:16px 0;background:#fafafa}}
.small{{color:#555;font-size:14px}}
a{{text-decoration:none}}
a:hover{{text-decoration:underline}}
.pass{{font-weight:700;color:#0a7a2f}}
.warn{{font-weight:700;color:#a15c00}}
.fail{{font-weight:700;color:#b00020}}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def link_if_exists(base: Path, rel: str, label: str) -> str:
    p = base / rel
    if p.exists():
        return f'<a href="{html.escape(rel)}">{html.escape(label)}</a>'
    return ""


def build_variant_page(vdir: Path, variant_label: str) -> Optional[Dict[str, str]]:
    run_dirs = sorted([p for p in vdir.iterdir() if p.is_dir()], reverse=True) if vdir.exists() else []
    rows: List[Dict[str, str]] = []

    for rd in run_dirs:
        csv_path = rd / "metrics.csv"
        row = read_metrics_csv(csv_path)
        if not row:
            continue
        row["_run_dir"] = rd.name
        row["_viewer"] = f"{rd.name}/viewer.html" if (rd / "viewer.html").exists() else ""
        row["_metrics"] = f"{rd.name}/metrics.csv" if (rd / "metrics.csv").exists() else ""
        row["_raw"] = f"{rd.name}/metrics_raw.json" if (rd / "metrics_raw.json").exists() else ""
        row["_gds"] = ""
        gds_files = sorted((rd / "final" / "gds").glob("*.gds"))
        if gds_files:
            row["_gds"] = f"{rd.name}/final/gds/{gds_files[0].name}"
        rows.append(row)

    best = sorted(rows, key=best_sort_key)[0] if rows else None

    body = [f"<h1>{html.escape(variant_label)} results</h1>"]
    body.append('<p class="small"><a href="../../index.html">Back to dashboard</a></p>')

    if not rows:
        body.append("<p>No runs collected yet.</p>")
        (vdir / "index.html").write_text(html_page(f"{variant_label} results", "\n".join(body)), encoding="utf-8")
        return None

    if best:
        body.append('<div class="card">')
        body.append("<h2>Best run</h2>")
        body.append("<table>")
        body.append("<tr><th>Run</th><th>Clock (ns)</th><th>Setup WNS</th><th>Setup TNS</th><th>DRC</th><th>LVS</th><th>Antenna</th><th>Status</th></tr>")
        body.append(
            "<tr>"
            f"<td>{html.escape(best['_run_dir'])}</td>"
            f"<td>{html.escape(str(best.get('clock_ns', '')))}</td>"
            f"<td>{html.escape(str(best.get('setup_wns_ns', '')))}</td>"
            f"<td>{html.escape(str(best.get('setup_tns_ns', '')))}</td>"
            f"<td>{html.escape(str(best.get('drc_errors', '')))}</td>"
            f"<td>{html.escape(str(best.get('lvs_errors', '')))}</td>"
            f"<td>{html.escape(str(best.get('antenna_violations', '')))}</td>"
            f"<td>{html.escape(status_badge(best))}</td>"
            "</tr>"
        )
        body.append("</table>")
        body.append("</div>")

    body.append("<h2>All runs</h2>")
    body.append("<table>")
    body.append(
        "<tr>"
        "<th>Run</th>"
        "<th>Clock</th>"
        "<th>Setup WNS</th>"
        "<th>Setup TNS</th>"
        "<th>Hold WNS</th>"
        "<th>Core Area</th>"
        "<th>Die Area</th>"
        "<th>Instances</th>"
        "<th>Util (%)</th>"
        "<th>Power (W)</th>"
        "<th>DRC</th>"
        "<th>LVS</th>"
        "<th>Antenna</th>"
        "<th>Status</th>"
        "<th>Viewer</th>"
        "<th>Metrics</th>"
        "<th>Raw JSON</th>"
        "<th>GDS</th>"
        "</tr>"
    )

    for row in sorted(rows, key=best_sort_key):
        status = status_badge(row)
        status_class = "pass" if status == "PASS" else ("warn" if status == "TIMING_FAIL" else "fail")
        body.append(
            "<tr>"
            f"<td>{html.escape(row['_run_dir'])}</td>"
            f"<td>{html.escape(str(row.get('clock_ns', '')))}</td>"
            f"<td>{html.escape(str(row.get('setup_wns_ns', '')))}</td>"
            f"<td>{html.escape(str(row.get('setup_tns_ns', '')))}</td>"
            f"<td>{html.escape(str(row.get('hold_wns_ns', '')))}</td>"
            f"<td>{html.escape(str(row.get('core_area_um2', '')))}</td>"
            f"<td>{html.escape(str(row.get('die_area_um2', '')))}</td>"
            f"<td>{html.escape(str(row.get('instance_count', '')))}</td>"
            f"<td>{html.escape(str(row.get('utilization_pct', '')))}</td>"
            f"<td>{html.escape(str(row.get('power_total_W', '')))}</td>"
            f"<td>{html.escape(str(row.get('drc_errors', '')))}</td>"
            f"<td>{html.escape(str(row.get('lvs_errors', '')))}</td>"
            f"<td>{html.escape(str(row.get('antenna_violations', '')))}</td>"
            f"<td class='{status_class}'>{html.escape(status)}</td>"
            f"<td>{f'<a href=\"{row['_viewer']}\">viewer</a>' if row['_viewer'] else ''}</td>"
            f"<td>{f'<a href=\"{row['_metrics']}\">csv</a>' if row['_metrics'] else ''}</td>"
            f"<td>{f'<a href=\"{row['_raw']}\">json</a>' if row['_raw'] else ''}</td>"
            f"<td>{f'<a href=\"{row['_gds']}\">gds</a>' if row['_gds'] else ''}</td>"
            "</tr>"
        )
    body.append("</table>")

    (vdir / "index.html").write_text(html_page(f"{variant_label} results", "\n".join(body)), encoding="utf-8")
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="full", choices=["fast", "full"])
    ap.parse_args()

    docs = ROOT / "docs"
    res = docs / "results"
    docs.mkdir(exist_ok=True)
    res.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest()
    title = manifest.get("project", {}).get("title", "ASIC Flow Dashboard")

    summaries = []
    for exp in manifest.get("experiments", []):
        if not exp.get("enabled", True):
            continue
        variant_path = exp["variant"]
        variant_label = Path(variant_path).name
        variant_safe = safe_variant_name(variant_path)
        vdir = res / variant_safe
        vdir.mkdir(parents=True, exist_ok=True)
        best = build_variant_page(vdir, variant_label)
        summaries.append((variant_label, variant_safe, best))

    body = [f"<h1>{html.escape(title)}</h1>"]
    body.append("<p>Auto-generated by GitHub Actions.</p>")
    body.append("<h2>Variants</h2>")
    body.append("<table>")
    body.append("<tr><th>Variant</th><th>Best Clock (ns)</th><th>Setup WNS</th><th>Setup TNS</th><th>DRC</th><th>LVS</th><th>Antenna</th><th>Status</th><th>Link</th></tr>")

    summary_md = ["## Variant summary", "", "| Variant | Best Clock (ns) | Setup WNS | Setup TNS | DRC | LVS | Antenna | Status |", "|---|---:|---:|---:|---:|---:|---:|---|"]

    for variant_label, variant_safe, best in summaries:
        if best:
            status = status_badge(best)
            body.append(
                "<tr>"
                f"<td>{html.escape(variant_label)}</td>"
                f"<td>{html.escape(str(best.get('clock_ns', '')))}</td>"
                f"<td>{html.escape(str(best.get('setup_wns_ns', '')))}</td>"
                f"<td>{html.escape(str(best.get('setup_tns_ns', '')))}</td>"
                f"<td>{html.escape(str(best.get('drc_errors', '')))}</td>"
                f"<td>{html.escape(str(best.get('lvs_errors', '')))}</td>"
                f"<td>{html.escape(str(best.get('antenna_violations', '')))}</td>"
                f"<td>{html.escape(status)}</td>"
                f'<td><a href="results/{variant_safe}/index.html">open</a></td>'
                "</tr>"
            )
            summary_md.append(
                f"| {variant_label} | {best.get('clock_ns','')} | {best.get('setup_wns_ns','')} | {best.get('setup_tns_ns','')} | {best.get('drc_errors','')} | {best.get('lvs_errors','')} | {best.get('antenna_violations','')} | {status} |"
            )
        else:
            body.append(
                "<tr>"
                f"<td>{html.escape(variant_label)}</td>"
                "<td colspan='7'>No runs collected yet</td>"
                f'<td><a href="results/{variant_safe}/index.html">open</a></td>'
                "</tr>"
            )
            summary_md.append(f"| {variant_label} |  |  |  |  |  |  | No runs collected |")

    body.append("</table>")

    (docs / "index.html").write_text(html_page(title, "\n".join(body)), encoding="utf-8")
    (docs / "summary.md").write_text("\n".join(summary_md) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()