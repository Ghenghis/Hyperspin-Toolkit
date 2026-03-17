#!/usr/bin/env python3
"""Build a small extension dashboard from the latest HyperSpin inventory CSV."""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def find_latest_csv(output_root: Path, default_name: str) -> Path:
    candidates = sorted(output_root.glob(f"run_*/{default_name}.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No inventory CSV found under {output_root}")
    return candidates[0]


def build_dashboard(csv_path: Path) -> Path:
    ext_stats: dict[str, dict[str, float]] = defaultdict(lambda: {"count": 0, "bytes": 0})
    with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            ext = row.get("Extension", "[unknown]")
            size = int(float(row.get("SizeBytes", "0") or 0))
            ext_stats[ext]["count"] += 1
            ext_stats[ext]["bytes"] += size

    rows = sorted(ext_stats.items(), key=lambda kv: (-kv[1]["count"], kv[0]))
    html = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head>",
        "  <meta charset='UTF-8'>",
        "  <meta name='viewport' content='width=device-width, initial-scale=1.0'>",
        "  <title>HyperSpin Extension Dashboard</title>",
        "  <style>",
        "    body { font-family: Arial, sans-serif; margin: 24px; background: #0f172a; color: #e5e7eb; }",
        "    h1 { margin-bottom: 6px; }",
        "    .muted { color: #94a3b8; margin-bottom: 18px; }",
        "    table { border-collapse: collapse; width: 100%; background: #111827; }",
        "    th, td { padding: 10px 12px; border-bottom: 1px solid #334155; text-align: left; }",
        "    th { background: #1f2937; }",
        "    tr:hover { background: #172033; }",
        "  </style>",
        "</head>",
        "<body>",
        f"  <h1>HyperSpin Extension Dashboard</h1>",
        f"  <div class='muted'>Built from: {csv_path} · Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>",
        "  <table>",
        "    <thead><tr><th>Extension</th><th>Count</th><th>Total GB</th></tr></thead>",
        "    <tbody>",
    ]
    for ext, stats in rows:
        total_gb = stats["bytes"] / (1024 ** 3)
        html.append(f"      <tr><td>{ext}</td><td>{int(stats['count'])}</td><td>{total_gb:.4f}</td></tr>")
    html.extend(["    </tbody>", "  </table>", "</body>", "</html>"])

    output_path = csv_path.parent / "extension_dashboard.html"
    output_path.write_text("\n".join(html), encoding="utf-8")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, help="Path to config.json")
    args = parser.parse_args()

    config = load_config(Path(args.config))
    output_root = Path(config["output_root"])
    csv_path = find_latest_csv(output_root, config.get("default_report_name", "hyperspin_inventory"))
    output_path = build_dashboard(csv_path)
    print(f"Dashboard created: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
