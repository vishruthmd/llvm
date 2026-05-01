#!/usr/bin/env python3
"""
visualize_energy.py — Energy Estimation Pass Report Generator
=============================================================
Reads the JSON output written by the LLVM EnergyEstimationPass
(-energy-output flag) and generates a self-contained HTML report with:
  - Per-function energy summary table with heat-map bar charts
  - Collapsible per-block breakdown tables
  - Color coding: hot (red) / warm (yellow) / cool (green)
  - Sortable columns via pure JavaScript
  - A plain-text ASCII summary printed to stdout

Usage
-----
  python visualize_energy.py results.json [OPTIONS]

Options
-------
  --output FILENAME     Write HTML report to FILENAME (default: energy_report.html)
  --top N               Show only the top N most expensive functions (default: all)
  --min-energy FLOAT    Exclude functions below this energy threshold (pJ)
  --title STRING        Report title shown in the HTML header
  --no-html             Skip HTML generation; only print ASCII summary

Example
-------
  # Compile and run pass (see README.md for full pipeline)
  clang -O2 -target aarch64-linux-gnu -emit-llvm -c sample.c -o sample.bc
  llc -load ./EnergyEstimationPass.so -energy-estimation          \\
      -energy-model energy-models/aarch64.json                    \\
      -energy-output results.json                                  \\
      -Rpass-analysis=energy sample.bc -o sample.s 2>remarks.txt
  python visualize_energy.py results.json --output report.html

"""

from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_results(path: str) -> dict:
    """Load and validate the JSON file written by EnergyEstimationPass."""
    p = Path(path)
    if not p.exists():
        sys.exit(f"[visualize_energy] ERROR: results file not found: {path}")
    with p.open(encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            sys.exit(f"[visualize_energy] ERROR: JSON parse failed: {e}")

    if "functions" not in data:
        sys.exit('[visualize_energy] ERROR: JSON missing "functions" key')

    return data


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------


def energy_color(energy: float, max_energy: float) -> str:
    """Return a CSS rgb() colour from green (low) to red (high)."""
    if max_energy <= 0:
        return "rgb(60,180,75)"
    ratio = min(energy / max_energy, 1.0)
    # Smooth interpolation: green → yellow → red
    if ratio < 0.5:
        t = ratio / 0.5
        r = int(60 + t * (255 - 60))
        g = int(180 + t * (220 - 180))
        b = 75
    else:
        t = (ratio - 0.5) / 0.5
        r = 255
        g = int(220 - t * 220)
        b = 75
    return f"rgb({r},{g},{b})"


def heat_class(ratio: float) -> str:
    """Return a CSS class name based on the energy ratio."""
    if ratio >= 0.75:
        return "heat-hot"
    if ratio >= 0.35:
        return "heat-warm"
    return "heat-cool"


# ---------------------------------------------------------------------------
# ASCII summary (stdout)
# ---------------------------------------------------------------------------

RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
CYAN = "\033[96m"


def ascii_bar(ratio: float, width: int = 20) -> str:
    filled = round(ratio * width)
    bar = "#" * filled + "-" * (width - filled)
    return f"[{bar}]"


def print_ascii_summary(data: dict, top_n: int | None, min_energy: float) -> None:
    functions = data.get("functions", [])
    arch = data.get("arch", "unknown")
    unit = data.get("unit", "pJ")

    functions = [f for f in functions if f.get("total_energy_pJ", 0.0) >= min_energy]
    functions.sort(key=lambda f: f.get("total_energy_pJ", 0.0), reverse=True)
    if top_n:
        functions = functions[:top_n]

    if not functions:
        print("[visualize_energy] No functions to report.")
        return

    total_all = sum(f.get("total_energy_pJ", 0.0) for f in functions)
    max_energy = functions[0].get("total_energy_pJ", 1.0)

    print(f"\n{BOLD}{CYAN}{'=' * 72}{RESET}")
    print(
        f"{BOLD}{CYAN}  Static Energy Estimation Report  —  {arch}  (unit: {unit}){RESET}"
    )
    print(f"{BOLD}{CYAN}{'=' * 72}{RESET}")
    print(f"  Functions analysed : {len(functions)}")
    print(f"  Total energy       : {total_all:,.2f} {unit}")
    print(
        f"  Generated          : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )
    print(f"{BOLD}{CYAN}{'=' * 72}{RESET}\n")

    hdr = f"  {'Function':<40} {'Energy (pJ)':>14} {'%Total':>8}  {'Chart'}"
    print(BOLD + hdr + RESET)
    print("  " + "-" * 68)

    for fn in functions:
        name = fn.get("name", "?")
        energy = fn.get("total_energy_pJ", 0.0)
        pct = (energy / total_all * 100) if total_all > 0 else 0.0
        ratio = energy / max_energy if max_energy > 0 else 0.0
        bar = ascii_bar(ratio)

        if ratio >= 0.75:
            color = RED
        elif ratio >= 0.35:
            color = YELLOW
        else:
            color = GREEN

        name_str = name if len(name) <= 40 else name[:37] + "..."
        print(
            f"  {color}{name_str:<40}{RESET} {energy:>14,.2f} {pct:>7.1f}%  {color}{bar}{RESET}"
        )

    print()

    # Per-function block breakdown (top 3 functions only to keep output compact)
    for fn in functions[:3]:
        blocks = fn.get("blocks", [])
        if not blocks:
            continue
        blocks_sorted = sorted(
            blocks, key=lambda b: b.get("weighted_energy_pJ", 0.0), reverse=True
        )
        fn_energy = fn.get("total_energy_pJ", 1.0) or 1.0

        print(f"  {BOLD}Function: {fn['name']}{RESET}  ({fn_energy:,.2f} {unit})")
        print(
            f"    {'Block':<30} {'Raw(pJ)':>10} {'FreqScale':>10} {'Weighted(pJ)':>13} {'Instrs':>7}"
        )
        print("    " + "-" * 74)
        for blk in blocks_sorted[:8]:
            bname = blk.get("name", "?")
            raw = blk.get("raw_energy_pJ", 0.0)
            freq = blk.get("freq_scale", 0.0)
            wt = blk.get("weighted_energy_pJ", 0.0)
            ic = blk.get("instructions", 0)
            pct_b = wt / fn_energy * 100 if fn_energy > 0 else 0.0
            bname_str = bname if len(bname) <= 30 else bname[:27] + "..."
            print(f"    {bname_str:<30} {raw:>10.2f} {freq:>10.4f} {wt:>13.2f} {ic:>7}")
        print()


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

CSS = """
:root {
  --bg: #0f1117;
  --card: #1a1d27;
  --card2: #22263a;
  --border: #2e3350;
  --text: #e2e8f0;
  --muted: #8892a4;
  --accent: #6c8ff7;
  --hot: #f87171;
  --warm: #fbbf24;
  --cool: #34d399;
  --link: #818cf8;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
  padding: 0 0 60px 0;
}
header {
  background: linear-gradient(135deg, #1e2340 0%, #0f1117 100%);
  border-bottom: 1px solid var(--border);
  padding: 28px 40px 22px;
}
header h1 { font-size: 1.8rem; font-weight: 700; color: #fff; letter-spacing: -0.5px; }
header .sub { color: var(--muted); font-size: 0.9rem; margin-top: 6px; }
header .badge {
  display: inline-block;
  background: var(--card2);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 3px 10px;
  font-size: 0.78rem;
  color: var(--accent);
  margin: 4px 4px 0 0;
}
.container { max-width: 1200px; margin: 0 auto; padding: 32px 20px; }
.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 36px;
}
.stat-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 18px 22px;
}
.stat-card .label { font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.8px; }
.stat-card .value { font-size: 1.6rem; font-weight: 700; color: #fff; margin-top: 4px; }
.stat-card .unit  { font-size: 0.8rem; color: var(--muted); }
section.panel {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  margin-bottom: 28px;
  overflow: hidden;
}
section.panel h2 {
  padding: 16px 22px;
  font-size: 1rem;
  font-weight: 600;
  border-bottom: 1px solid var(--border);
  background: var(--card2);
  display: flex;
  align-items: center;
  gap: 10px;
}
section.panel h2 .icon { font-size: 1.1rem; }
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.88rem;
}
thead th {
  padding: 10px 16px;
  text-align: left;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.7px;
  color: var(--muted);
  background: var(--card2);
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}
thead th:hover { color: var(--text); }
thead th.sorted-asc::after  { content: " ↑"; color: var(--accent); }
thead th.sorted-desc::after { content: " ↓"; color: var(--accent); }
tbody tr { border-bottom: 1px solid var(--border); transition: background 0.1s; }
tbody tr:last-child { border-bottom: none; }
tbody tr:hover { background: var(--card2); }
td { padding: 10px 16px; vertical-align: middle; }
td.name { font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 0.85rem; }
td.number { text-align: right; font-variant-numeric: tabular-nums; }
.bar-cell { width: 180px; }
.bar-outer {
  background: rgba(255,255,255,0.06);
  border-radius: 4px;
  height: 10px;
  overflow: hidden;
}
.bar-inner {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s ease;
}
.heat-hot  { color: var(--hot); }
.heat-warm { color: var(--warm); }
.heat-cool { color: var(--cool); }
.badge-cat {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 100px;
  font-size: 0.72rem;
  font-weight: 600;
}
.badge-hot  { background: rgba(248,113,113,0.15); color: var(--hot); }
.badge-warm { background: rgba(251,191,36, 0.15); color: var(--warm); }
.badge-cool { background: rgba(52, 211,153,0.15); color: var(--cool); }
details { border-top: 1px solid var(--border); }
details > summary {
  padding: 12px 22px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.88rem;
  font-weight: 500;
  background: var(--card2);
  list-style: none;
  transition: background 0.1s;
}
details > summary::-webkit-details-marker { display: none; }
details > summary:hover { background: rgba(108,143,247,0.08); }
details > summary .arrow { transition: transform 0.2s; font-size: 0.8rem; }
details[open] > summary .arrow { transform: rotate(90deg); }
details > .block-table { padding: 0; }
.block-table table { font-size: 0.84rem; }
.block-table thead th { font-size: 0.72rem; }
.footnote {
  font-size: 0.78rem;
  color: var(--muted);
  margin-top: 36px;
  padding: 16px 22px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--card);
  line-height: 1.8;
}
.footnote a { color: var(--link); text-decoration: none; }
.footnote a:hover { text-decoration: underline; }
""".strip()

JS = """
function sortTable(tableId, col, isNumeric) {
  const table = document.getElementById(tableId);
  const tbody = table.querySelector('tbody');
  const rows  = Array.from(tbody.querySelectorAll('tr'));
  const ths   = table.querySelectorAll('thead th');

  // Determine sort direction
  const th = ths[col];
  const asc = !th.classList.contains('sorted-asc');

  // Clear all sorted markers
  ths.forEach(h => { h.classList.remove('sorted-asc', 'sorted-desc'); });
  th.classList.add(asc ? 'sorted-asc' : 'sorted-desc');

  rows.sort((a, b) => {
    const aVal = a.querySelectorAll('td')[col].dataset.sort || a.querySelectorAll('td')[col].textContent;
    const bVal = b.querySelectorAll('td')[col].dataset.sort || b.querySelectorAll('td')[col].textContent;
    if (isNumeric) {
      return asc ? parseFloat(aVal) - parseFloat(bVal)
                 : parseFloat(bVal) - parseFloat(aVal);
    }
    return asc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
  });
  rows.forEach(r => tbody.appendChild(r));
}
""".strip()


def fmt_pJ(v: float) -> str:
    if v >= 1_000_000:
        return f"{v / 1_000_000:.3f} MpJ"
    if v >= 1_000:
        return f"{v / 1_000:.3f} npJ"
    return f"{v:,.4f} pJ"


def pct_bar_html(ratio: float, color: str) -> str:
    width = round(ratio * 100, 2)
    return (
        f'<div class="bar-outer">'
        f'<div class="bar-inner" style="width:{width}%;background:{color};"></div>'
        f"</div>"
    )


def badge_html(ratio: float) -> str:
    if ratio >= 0.75:
        return '<span class="badge-cat badge-hot">HOT</span>'
    if ratio >= 0.35:
        return '<span class="badge-cat badge-warm">WARM</span>'
    return '<span class="badge-cat badge-cool">COOL</span>'


def build_html(data: dict, title: str, functions: list[dict], total_all: float) -> str:
    arch = data.get("arch", "unknown")
    unit = data.get("unit", "pJ")
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    max_energy = functions[0].get("total_energy_pJ", 1.0) if functions else 1.0
    total_instrs = sum(
        sum(b.get("instructions", 0) for b in f.get("blocks", [])) for f in functions
    )

    # ── Header badges ───────────────────────────────────────────────────────
    badges_html = (
        f'<span class="badge">Arch: {html.escape(arch)}</span>'
        f'<span class="badge">Unit: {html.escape(unit)}</span>'
        f'<span class="badge">Functions: {len(functions)}</span>'
        f'<span class="badge">Generated: {now_str}</span>'
    )

    # ── Summary stat cards ──────────────────────────────────────────────────
    stat_cards = f"""
    <div class="summary-grid">
      <div class="stat-card">
        <div class="label">Total Energy</div>
        <div class="value">{total_all:,.2f}</div>
        <div class="unit">{html.escape(unit)}</div>
      </div>
      <div class="stat-card">
        <div class="label">Functions</div>
        <div class="value">{len(functions)}</div>
        <div class="unit">analysed</div>
      </div>
      <div class="stat-card">
        <div class="label">Instructions</div>
        <div class="value">{total_instrs:,}</div>
        <div class="unit">real machine instructions</div>
      </div>
      <div class="stat-card">
        <div class="label">Hottest Function</div>
        <div class="value" style="font-size:1.1rem;word-break:break-all;">
          {html.escape(functions[0]["name"]) if functions else "—"}
        </div>
        <div class="unit">{fmt_pJ(max_energy)}</div>
      </div>
    </div>
    """

    # ── Function summary table ───────────────────────────────────────────────
    func_rows = []
    for idx, fn in enumerate(functions):
        name = fn.get("name", "?")
        energy = fn.get("total_energy_pJ", 0.0)
        pct = (energy / total_all * 100) if total_all > 0 else 0.0
        ratio = energy / max_energy if max_energy > 0 else 0.0
        color = energy_color(energy, max_energy)
        cls = heat_class(ratio)
        blk_n = len(fn.get("blocks", []))

        func_rows.append(f"""
        <tr>
          <td class="number">{idx + 1}</td>
          <td class="name {cls}" data-sort="{html.escape(name)}">{html.escape(name)}</td>
          <td class="number" data-sort="{energy:.6f}">{energy:,.4f}</td>
          <td class="number" data-sort="{pct:.4f}">{pct:.2f}%</td>
          <td class="number">{blk_n}</td>
          <td class="bar-cell">{pct_bar_html(ratio, color)}</td>
          <td>{badge_html(ratio)}</td>
        </tr>""")

    summary_table = f"""
    <section class="panel">
      <h2><span class="icon">⚡</span> Function Energy Summary</h2>
      <table id="fn-table">
        <thead>
          <tr>
            <th onclick="sortTable('fn-table',0,true)">#</th>
            <th onclick="sortTable('fn-table',1,false)">Function</th>
            <th onclick="sortTable('fn-table',2,true)">Energy ({html.escape(unit)})</th>
            <th onclick="sortTable('fn-table',3,true)">% Total</th>
            <th onclick="sortTable('fn-table',4,true)">Blocks</th>
            <th>Bar</th>
            <th>Category</th>
          </tr>
        </thead>
        <tbody>
          {"".join(func_rows)}
        </tbody>
      </table>
    </section>
    """

    # ── Per-function block breakdown ─────────────────────────────────────────
    details_html_parts = []
    for fn in functions:
        fn_name = fn.get("name", "?")
        fn_energy = fn.get("total_energy_pJ", 0.0)
        blocks = sorted(
            fn.get("blocks", []),
            key=lambda b: b.get("weighted_energy_pJ", 0.0),
            reverse=True,
        )
        if not blocks:
            continue

        max_blk = blocks[0].get("weighted_energy_pJ", 1.0) or 1.0
        fn_ratio = fn_energy / max_energy if max_energy > 0 else 0.0
        cat_badge = badge_html(fn_ratio)

        blk_rows = []
        for bidx, blk in enumerate(blocks):
            bname = blk.get("name", "?")
            raw = blk.get("raw_energy_pJ", 0.0)
            freq = blk.get("freq_scale", 0.0)
            wt = blk.get("weighted_energy_pJ", 0.0)
            ic = blk.get("instructions", 0)
            bpct = (wt / fn_energy * 100) if fn_energy > 0 else 0.0
            bratio = wt / max_blk if max_blk > 0 else 0.0
            bcolor = energy_color(wt, max_blk)

            blk_rows.append(f"""
            <tr>
              <td class="number">{bidx + 1}</td>
              <td class="name" data-sort="{html.escape(bname)}">{html.escape(bname)}</td>
              <td class="number" data-sort="{raw:.6f}">{raw:,.4f}</td>
              <td class="number" data-sort="{freq:.6f}">{freq:.4f}×</td>
              <td class="number" data-sort="{wt:.6f}">{wt:,.4f}</td>
              <td class="number" data-sort="{bpct:.4f}">{bpct:.2f}%</td>
              <td class="number">{ic}</td>
              <td class="bar-cell">{pct_bar_html(bratio, bcolor)}</td>
            </tr>""")

        tid = f"blk-{html.escape(fn_name, quote=True).replace(' ', '_')[:30]}-{id(fn)}"
        details_html_parts.append(f"""
      <details>
        <summary>
          <span class="arrow">▶</span>
          <code style="color:var(--accent);font-size:0.9rem;">{html.escape(fn_name)}</code>
          &nbsp;—&nbsp;
          <strong>{fn_energy:,.4f} {html.escape(unit)}</strong>
          &nbsp;&nbsp;{cat_badge}
          &nbsp;&nbsp;<span style="color:var(--muted);font-size:0.82rem;">{len(blocks)} block(s)</span>
        </summary>
        <div class="block-table">
          <table id="{tid}">
            <thead>
              <tr>
                <th onclick="sortTable('{tid}',0,true)">#</th>
                <th onclick="sortTable('{tid}',1,false)">Basic Block</th>
                <th onclick="sortTable('{tid}',2,true)">Raw Energy ({html.escape(unit)})</th>
                <th onclick="sortTable('{tid}',3,true)">Freq Scale</th>
                <th onclick="sortTable('{tid}',4,true)">Weighted ({html.escape(unit)})</th>
                <th onclick="sortTable('{tid}',5,true)">% of Func</th>
                <th onclick="sortTable('{tid}',6,true)">Instructions</th>
                <th>Bar</th>
              </tr>
            </thead>
            <tbody>
              {"".join(blk_rows)}
            </tbody>
          </table>
        </div>
      </details>""")

    details_section = f"""
    <section class="panel">
      <h2><span class="icon">🔍</span> Per-Function Block Breakdown
        <span style="color:var(--muted);font-size:0.78rem;font-weight:400;">
          (click a row to expand)
        </span>
      </h2>
      {"".join(details_html_parts)}
    </section>
    """

    # ── Footnote / references ────────────────────────────────────────────────
    footnote = """
    <div class="footnote">
      <strong>Energy Model:</strong> ARM Cortex-A55 (7 nm, 1800 MHz, 0.8 V) &mdash;
      values derived from:<br>
      &bull; ARM Cortex-A55 Software Optimization Guide (ARM-DEN-0060A, Rev 3)<br>
      &bull; Pallister et al., <em>BEEBS: Open Benchmarks for Energy Measurements on Embedded Platforms</em>, 2013<br>
      &bull; Tiwari et al., <em>Power analysis of embedded software: A first step towards software power minimization</em>, IEEE TVLSI 1994<br>
      &bull; Abdelhadi &amp; Bhattacharyya, <em>Energy modeling for superscalar processors</em>, ACM TECS 2016<br>
      &bull; Kerrison &amp; Eder, <em>Energy modeling of software for a hardware multithreaded embedded microprocessor</em>, ACM TECS 2015<br>
      <br>
      <strong>Disclaimer:</strong> This is a <em>static</em> energy estimate based on published per-instruction
      data and compile-time block frequency analysis.  Actual dynamic energy depends on cache behaviour,
      branch prediction, operand switching activity, and workload-specific memory access patterns.
    </div>
    """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)}</title>
  <style>{CSS}</style>
</head>
<body>
<header>
  <h1>⚡ {html.escape(title)}</h1>
  <div class="sub">
    Static energy estimation via LLVM EnergyEstimationPass (MachineFunctionPass)
  </div>
  <div style="margin-top:12px">{badges_html}</div>
</header>

<div class="container">
  {stat_cards}
  {summary_table}
  {details_section}
  {footnote}
</div>

<script>{JS}</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate an HTML energy report from EnergyEstimationPass JSON output.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "results_json", help="Path to the JSON file written by -energy-output"
    )
    parser.add_argument(
        "--output",
        default="energy_report.html",
        help="Output HTML file (default: energy_report.html)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        metavar="N",
        help="Include only the top N most expensive functions",
    )
    parser.add_argument(
        "--min-energy",
        type=float,
        default=0.0,
        metavar="FLOAT",
        help="Exclude functions below this energy threshold (pJ)",
    )
    parser.add_argument(
        "--title",
        default="Static Energy Estimation Report",
        help="Report title shown in the HTML header",
    )
    parser.add_argument(
        "--no-html",
        action="store_true",
        help="Skip HTML generation; only print ASCII summary to stdout",
    )
    args = parser.parse_args()

    data = load_results(args.results_json)
    functions = data.get("functions", [])

    # Filter and sort
    functions = [
        f for f in functions if f.get("total_energy_pJ", 0.0) >= args.min_energy
    ]
    functions.sort(key=lambda f: f.get("total_energy_pJ", 0.0), reverse=True)
    if args.top:
        functions = functions[: args.top]

    total_all = sum(f.get("total_energy_pJ", 0.0) for f in functions)

    # ASCII summary always goes to stdout
    print_ascii_summary(data, args.top, args.min_energy)

    if args.no_html:
        return

    html_content = build_html(data, args.title, functions, total_all)
    out_path = Path(args.output)
    out_path.write_text(html_content, encoding="utf-8")

    print(f"[visualize_energy] HTML report written to: {out_path.resolve()}")
    print(f"[visualize_energy] Open with:  open {out_path}  (macOS)")
    print(f"                               xdg-open {out_path}  (Linux)")
    print(f"                               start {out_path}  (Windows)\n")


if __name__ == "__main__":
    main()
