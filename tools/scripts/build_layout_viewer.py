#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True, help="Per-run output directory")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    renders_dir = out_dir / "renders"
    manifest_path = renders_dir / "renders_manifest.json"
    viewer_path = out_dir / "viewer.html"
    readme_path = out_dir / "README.txt"

    renders = []
    gds_rel = ""

    if manifest_path.exists():
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        renders = data.get("renders", [])

    gds_files = sorted((out_dir / "final" / "gds").glob("*.gds"))
    if gds_files:
        gds_rel = f"final/gds/{gds_files[0].name}"

    readme_lines = [
        "ASIC Flow Layout Artifact",
        "",
        "How to use:",
        "1. Extract the entire artifact zip first.",
        "2. Open viewer.html in a web browser.",
        "3. Open final/gds/*.gds in KLayout for true layout inspection.",
        "",
        "Important:",
        "- Do not open viewer.html from inside the zip preview.",
        "- Do not move viewer.html away from the renders/ and final/ folders.",
    ]
    readme_path.write_text("\n".join(readme_lines) + "\n", encoding="utf-8")

    parts = []
    parts.append("<!doctype html>")
    parts.append("<html>")
    parts.append("<head>")
    parts.append('<meta charset="utf-8">')
    parts.append('<meta name="viewport" content="width=device-width,initial-scale=1">')
    parts.append("<title>Layout Viewer</title>")
    parts.append("<style>")
    parts.append("body { font-family: system-ui, sans-serif; margin: 24px; max-width: 1200px; }")
    parts.append("h1, h2, h3 { margin-bottom: 0.4em; }")
    parts.append(".grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 18px; }")
    parts.append(".card { border: 1px solid #ddd; border-radius: 12px; padding: 14px; background: #fafafa; }")
    parts.append("img { width: 100%; height: auto; border: 1px solid #ccc; border-radius: 8px; }")
    parts.append("code { background: #f4f4f4; padding: 2px 6px; border-radius: 6px; }")
    parts.append("a { text-decoration: none; }")
    parts.append("a:hover { text-decoration: underline; }")
    parts.append("</style>")
    parts.append("</head>")
    parts.append("<body>")
    parts.append("<h1>Layout Viewer</h1>")
    parts.append("<p>This page shows static PNG previews of the generated GDS layout.</p>")
    parts.append("<div class='card'>")
    parts.append("<h2>How to use</h2>")
    parts.append("<ol>")
    parts.append("<li>Extract the entire artifact zip first.</li>")
    parts.append("<li>Open <code>viewer.html</code> from the extracted folder.</li>")
    parts.append("<li>For full layout inspection, open the GDS in KLayout.</li>")
    parts.append("</ol>")
    parts.append("</div>")

    if gds_rel:
        parts.append(f'<p><a href="{gds_rel}">Open GDS file location</a> (download/open locally in KLayout).</p>')
    else:
        parts.append("<p>No GDS file was copied into this artifact.</p>")

    if not renders:
        parts.append("<p><strong>No PNG renders were generated.</strong></p>")
        parts.append("<p>This usually means KLayout rendering failed or no GDS was found during the render step.</p>")
    else:
        parts.append("<h2>Preview images</h2>")
        parts.append('<div class="grid">')
        for r in renders:
            fname = r.get("file", "")
            kind = r.get("kind", "")
            w = r.get("width", "")
            h = r.get("height", "")
            rel = f"renders/{fname}"
            parts.append('<div class="card">')
            parts.append(f"<h3>{kind}</h3>")
            parts.append(f'<a href="{rel}"><img src="{rel}" alt="{fname}"></a>')
            parts.append(f"<p><code>{fname}</code></p>")
            parts.append(f"<p>{w} × {h}</p>")
            parts.append(f'<p><a href="{rel}">Open image</a></p>')
            parts.append("</div>")
        parts.append("</div>")

    parts.append("</body>")
    parts.append("</html>")

    viewer_path.write_text("\n".join(parts) + "\n", encoding="utf-8")
    print(f"Wrote: {viewer_path}")
    print(f"Wrote: {readme_path}")


if __name__ == "__main__":
    main()