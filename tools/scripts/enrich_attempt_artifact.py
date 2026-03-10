#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[2]


def clock_label(clock_ns: float) -> str:
    as_float = float(clock_ns)
    if as_float.is_integer():
        return str(int(as_float))
    return str(as_float).replace('.', 'p')


def newest_attempt_dir(base_dir: Path, clock_ns: float) -> Optional[Path]:
    pattern = f"clk_{clock_label(clock_ns)}ns_attempt_*"
    matches = sorted(base_dir.glob(pattern))
    if matches:
        return matches[-1]
    return None


def copy_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=True)


def run_optional(cmd: list[str]) -> None:
    print('>', ' '.join(cmd), flush=True)
    subprocess.run(cmd, cwd=str(ROOT), check=False)


def main() -> None:
    ap = argparse.ArgumentParser(description='Enrich a single attempt artifact bundle with run outputs and viewer files.')
    ap.add_argument('--base-dir', type=Path, required=True)
    ap.add_argument('--clock-ns', type=float, required=True)
    args = ap.parse_args()

    base_dir = (ROOT / args.base_dir).resolve() if not args.base_dir.is_absolute() else args.base_dir.resolve()
    if not base_dir.exists():
        raise SystemExit(f'Base directory not found: {base_dir}')

    attempt_dir = newest_attempt_dir(base_dir, args.clock_ns)
    if attempt_dir is None:
        raise SystemExit(f'No attempt directory matching clock {args.clock_ns} ns was found under {base_dir}')

    print(f'Using attempt directory: {attempt_dir}', flush=True)

    run_dir: Optional[Path] = None
    run_dir_used = attempt_dir / 'run_dir_used.txt'
    if run_dir_used.exists():
        run_dir_text = run_dir_used.read_text(encoding='utf-8').splitlines()[0].strip()
        if run_dir_text and run_dir_text != '(missing)':
            candidate = Path(run_dir_text)
            if candidate.exists() and candidate.is_dir():
                run_dir = candidate

    if run_dir is not None:
        copy_tree(run_dir, attempt_dir / 'openlane_run')

        final_metrics = run_dir / 'final' / 'metrics.json'
        if final_metrics.exists() and not (attempt_dir / 'metrics_raw.json').exists():
            shutil.copy2(final_metrics, attempt_dir / 'metrics_raw.json')

        final_gds = run_dir / 'final' / 'gds'
        if final_gds.exists() and final_gds.is_dir():
            copy_tree(final_gds, attempt_dir / 'final' / 'gds')

        run_optional([
            sys.executable,
            str(ROOT / 'tools/scripts/render_gds.py'),
            '--run-root',
            str(run_dir),
            '--out',
            str(attempt_dir / 'renders'),
        ])

    run_optional([
        sys.executable,
        str(ROOT / 'tools/scripts/build_layout_viewer.py'),
        '--out-dir',
        str(attempt_dir),
    ])

    viewer_html = attempt_dir / 'viewer.html'
    index_html = attempt_dir / 'index.html'
    if viewer_html.exists() and not index_html.exists():
        shutil.copy2(viewer_html, index_html)


if __name__ == '__main__':
    main()
