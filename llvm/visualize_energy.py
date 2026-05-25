#!/usr/bin/env python3
"""
visualize_energy.py -- Energy Estimation Pass Report Generator
==============================================================
Reads the JSON output written by the LLVM EnergyEstimationPass
(-energy-output flag) and generates a self-contained HTML report with:
  - Per-function energy summary table with bar charts
  - SVG donut chart for energy distribution
  - Collapsible per-block breakdown tables
  - Dark/light mode toggle
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
  llc -load ./EnergyEstimationPass.so -energy-estimation          \
      -energy-model energy-models/aarch64.json                    \
      -energy-output results.json                                  \
      -Rpass-analysis=energy sample.bc -o sample.s 2>remarks.txt
  python visualize_energy.py results.json --output report.html

"""

from __future__ import annotations

import argparse
import html
import json
import math
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


# SVG donut chart colours (qualitative palette)
DONUT_COLORS = [
    "#6c8ff7", "#f87171", "#34d399", "#fbbf24",
    "#a78bfa", "#fb923c", "#22d3ee", "#f472b6",
    "#4ade80", "#facc15",
]

# Table colour classes
COLOUR_HOT = "#f87171"
COLOUR_WARM = "#fbbf24"
COLOUR_COOL = "#34d399"


def heat_css_class(ratio: float) -> str:
    if ratio >= 0.75:
        return "cell-hot"
    if ratio >= 0.35:
        return "cell-warm"
    return "cell-cool"


def badge_html(ratio: float) -> str:
    if ratio >= 0.75:
        return '<span class="badge badge-hot">HIGH</span>'
    if ratio >= 0.35:
        return '<span class="badge badge-warm">MEDIUM</span>'
    return '<span class="badge badge-cool">LOW</span>'


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
        f"{BOLD}{CYAN}  Static Energy Estimation Report  --  {arch}  (unit: {unit}){RESET}"
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

    # Per-function block breakdown (top 3 functions only)
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
* { box-sizing: border-box; margin: 0; padding: 0; }

/* ---- Light / Dark theme variables ---- */
:root {
  --bg: #0f1117;
  --card: #1a1d27;
  --card2: #22263a;
  --border: #2e3350;
  --text: #e2e8f0;
  --muted: #8892a4;
  --accent: #6c8ff7;
  --link: #818cf8;
  --input-bg: #1a1d27;
  --input-border: #2e3350;
  --shadow: rgba(0,0,0,0.3);
}
.theme-light {
  --bg: #f5f7fa;
  --card: #ffffff;
  --card2: #edf2f7;
  --border: #cbd5e1;
  --text: #1a202c;
  --muted: #64748b;
  --accent: #4a6cf7;
  --link: #4a6cf7;
  --input-bg: #ffffff;
  --input-border: #cbd5e1;
  --shadow: rgba(0,0,0,0.08);
}

body {
  font-family: 'Cascadia Code', 'Consolas', 'Courier New', monospace;
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
  padding: 0 0 60px 0;
  transition: background 0.45s ease, color 0.4s ease, border-color 0.35s ease, box-shadow 0.35s ease;
}

/* Smooth transitions for all themed elements */
header, .stat-card, section.panel, .footnote, .badge, .theme-toggle,
details > summary, th, td, .bar-outer, .donut-legend-item {
  transition: background 0.35s ease, color 0.3s ease, border-color 0.3s ease, box-shadow 0.3s ease;
}

@keyframes themeSpin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

header {
  background: #151828;
  border-bottom: 1px solid #2e3350;
  padding: 24px 40px 18px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}
header .head-left h1 {
  font-size: 1.5rem;
  font-weight: 700;
  color: #6c8ff7;
  letter-spacing: -0.5px;
}
header .head-left .sub {
  color: #8892a4;
  font-size: 0.78rem;
  margin-top: 4px;
}
header .badge {
  background: #22263a;
  border-color: #2e3350;
  color: #8892a4;
}
header .theme-toggle {
  background: #1a1d27;
  border-color: #2e3350;
  color: #8892a4;
}

/* Theme toggle button -- icon-only circular button */
.theme-toggle {
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: var(--card2);
  border: 1px solid var(--border);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--muted);
  padding: 0;
  flex-shrink: 0;
  transition: background 0.25s ease, color 0.25s ease, border-color 0.25s ease, transform 0.25s ease, box-shadow 0.25s ease;
}
.theme-toggle:hover {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
  box-shadow: 0 0 20px rgba(108,143,247,0.2);
  transform: scale(1.1);
}
.theme-toggle:active {
  transform: scale(0.9);
}
.theme-toggle svg {
  width: 18px;
  height: 18px;
  transition: transform 0.5s ease;
}
.theme-toggle.spin svg {
  animation: themeSpin 0.5s ease;
}

.badge {
  display: inline-block;
  background: var(--card2);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 0.72rem;
  color: var(--muted);
  margin: 2px 4px 2px 0;
}

.container { max-width: 1200px; margin: 0 auto; padding: 28px 20px; }

/* Summary stat cards */
.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 14px;
  margin-bottom: 28px;
}
.stat-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px 18px;
  box-shadow: 0 1px 4px var(--shadow);
}
.stat-card .label {
  font-size: 0.68rem;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.6px;
}
.stat-card .value {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text);
  margin-top: 4px;
  font-variant-numeric: tabular-nums;
}
.stat-card .unit {
  font-size: 0.72rem;
  color: var(--muted);
}

/* Panel sections */
section.panel {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 24px;
  overflow: hidden;
  box-shadow: 0 1px 4px var(--shadow);
}
section.panel h2 {
  padding: 14px 20px;
  font-size: 0.88rem;
  font-weight: 600;
  border-bottom: 1px solid var(--border);
  background: var(--card2);
  display: flex;
  align-items: center;
  gap: 8px;
}
section.panel h2 .hint {
  color: var(--muted);
  font-size: 0.72rem;
  font-weight: 400;
}

/* Tables */
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}
thead th {
  padding: 8px 14px;
  text-align: left;
  font-size: 0.68rem;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--muted);
  background: var(--card2);
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
  font-weight: 600;
}
thead th:hover { color: var(--accent); }
thead th.num { text-align: right; }
thead th.sorted-asc::after  { content: " ^"; color: var(--accent); }
thead th.sorted-desc::after { content: " v"; color: var(--accent); }
tbody tr { border-bottom: 1px solid var(--border); transition: background 0.1s; }
tbody tr:last-child { border-bottom: none; }
tbody tr:hover { background: var(--card2); }
td { padding: 8px 14px; vertical-align: middle; }
td.name { font-size: 0.82rem; }
td.number { text-align: right; font-variant-numeric: tabular-nums; }

.bar-cell { width: 160px; }
.bar-outer {
  background: rgba(128,128,128,0.12);
  border-radius: 3px;
  height: 10px;
  overflow: hidden;
}
.bar-inner {
  height: 100%;
  border-radius: 3px;
  transition: width 0.3s ease;
}

.cell-hot  { color: var(--hot, #f87171); }
.cell-warm { color: var(--warm, #fbbf24); }
.cell-cool { color: var(--cool, #34d399); }
:root { --hot: #f87171; --warm: #fbbf24; --cool: #34d399; }

.badge-hot, .badge-warm, .badge-cool {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 0.68rem;
  font-weight: 600;
  letter-spacing: 0.3px;
}
.badge-hot  { background: rgba(248,113,113,0.15); color: var(--hot); }
.badge-warm { background: rgba(251,191,36,  0.15); color: var(--warm); }
.badge-cool { background: rgba(52, 211,153, 0.15); color: var(--cool); }

/* Collapsible block details */
details { border-top: 1px solid var(--border); }
details > summary {
  padding: 10px 20px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.82rem;
  font-weight: 500;
  background: var(--card2);
  list-style: none;
  transition: background 0.1s;
}
details > summary::-webkit-details-marker { display: none; }
details > summary:hover { background: rgba(108,143,247,0.08); }
details > summary .arrow { transition: transform 0.2s; font-size: 0.7rem; color: var(--muted); }
details[open] > summary .arrow { transform: rotate(90deg); }
details > .block-table { padding: 0; }
.block-table table { font-size: 0.78rem; }
.block-table thead th { font-size: 0.65rem; }

/* Opcode breakdown nested inside function details */
.opcode-detail {
  border-top: 1px solid var(--border);
}
.opcode-detail > summary {
  padding: 7px 20px 7px 40px;
  cursor: pointer;
  font-size: 0.76rem;
  font-weight: 500;
  background: rgba(108,143,247,0.03);
  list-style: none;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: background 0.15s;
}
.opcode-detail > summary::-webkit-details-marker { display: none; }
.opcode-detail > summary:hover { background: rgba(108,143,247,0.08); }
.opcode-detail > summary .arrow { transition: transform 0.2s; font-size: 0.65rem; color: var(--muted); }
.opcode-detail[open] > summary .arrow { transform: rotate(90deg); }
.opcode-detail > .opcode-table { padding: 0; }
.opcode-table table { font-size: 0.73rem; }
.opcode-table thead th { font-size: 0.6rem; }
.opcode-table td.opcode code {
  font-family: 'Cascadia Code', 'Consolas', monospace;
  font-size: 0.75rem;
  color: var(--accent);
}

/* SVG donut chart */
.donut-section {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  padding: 20px;
  align-items: center;
}
.donut-chart-container {
  flex: 0 0 260px;
  display: flex;
  justify-content: center;
}
.donut-legend {
  flex: 1;
  min-width: 200px;
}
.donut-legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 0;
  font-size: 0.78rem;
}
.donut-legend-swatch {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  flex-shrink: 0;
}
.donut-legend-pct {
  margin-left: auto;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}

/* Footnote */
.footnote {
  font-size: 0.74rem;
  color: var(--muted);
  margin-top: 28px;
  padding: 14px 18px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--card);
  line-height: 1.7;
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

  const th = ths[col];
  const asc = !th.classList.contains('sorted-asc');

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

function toggleTheme() {
  const body = document.body;
  const btn = document.getElementById('themeBtn');
  body.classList.toggle('theme-light');
  const isLight = body.classList.contains('theme-light');
  btn.innerHTML = isLight
    ? '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>'
    : '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
  btn.classList.remove('spin');
  void btn.offsetWidth;
  btn.classList.add('spin');
  localStorage.setItem('theme', isLight ? 'light' : 'dark');
}

(function() {
  const saved = localStorage.getItem('theme');
  const body = document.body;
  const btn = document.getElementById('themeBtn');
  const moonSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
  const sunSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>';
  if (saved === 'light') {
    body.classList.add('theme-light');
    if (btn) btn.innerHTML = sunSvg;
  } else {
    if (btn) btn.innerHTML = moonSvg;
  }
})();
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


def _build_donut_chart(functions: list[dict], total_all: float) -> str:
    """Generate SVG donut chart for energy distribution (top 8 functions + other)."""
    top = functions[:8]
    other_energy = sum(f.get("total_energy_pJ", 0.0) for f in functions[8:])
    if other_energy > 0:
        top.append({"name": "(other)", "total_energy_pJ": other_energy})

    if not top or total_all <= 0:
        return '<p style="padding:20px;color:var(--muted);font-size:0.82rem;">No data for chart.</p>'

    # Compute SVG arc paths
    cx, cy, r, inner_r = 130, 130, 100, 60
    total = total_all
    segments = []
    legend_items = []
    start_angle = -90  # start at top

    for i, fn in enumerate(top):
        energy = fn.get("total_energy_pJ", 0.0)
        pct = energy / total * 100
        angle = (energy / total) * 360.0
        color = DONUT_COLORS[i % len(DONUT_COLORS)]
        end_angle = start_angle + angle

        # SVG arc path
        start_rad = math.radians(start_angle)
        end_rad = math.radians(end_angle)
        x1 = cx + r * math.cos(start_rad)
        y1 = cy + r * math.sin(start_rad)
        x2 = cx + r * math.cos(end_rad)
        y2 = cy + r * math.sin(end_rad)
        large_arc = 1 if angle > 180 else 0

        # Inner circle points (for the donut hole)
        ix1 = cx + inner_r * math.cos(start_rad)
        iy1 = cy + inner_r * math.sin(start_rad)
        ix2 = cx + inner_r * math.cos(end_rad)
        iy2 = cy + inner_r * math.sin(end_rad)

        path_d = (
            f"M {x1},{y1} "
            f"A {r},{r} 0 {large_arc},1 {x2},{y2} "
            f"L {ix2},{iy2} "
            f"A {inner_r},{inner_r} 0 {large_arc},0 {ix1},{iy1} "
            f"Z"
        )

        segments.append(
            f'<path d="{path_d}" fill="{color}" '
            f'stroke="var(--bg)" stroke-width="1.5" '
            f'title="{html.escape(fn["name"])}: {pct:.1f}%" />'
        )

        name_str = fn["name"] if len(fn["name"]) <= 28 else fn["name"][:25] + "..."
        legend_items.append(
            f'<div class="donut-legend-item">'
            f'<span class="donut-legend-swatch" style="background:{color};"></span>'
            f'<span>{html.escape(name_str)}</span>'
            f'<span class="donut-legend-pct">{pct:.1f}%</span>'
            f"</div>"
        )

        start_angle = end_angle

    svg = (
        f'<svg width="260" height="260" viewBox="0 0 260 260">'
        f'{"".join(segments)}'
        f'<text x="130" y="126" text-anchor="middle" '
        f'fill="var(--text)" font-size="1.1rem" font-weight="700" '
        f'font-family="Cascadia Code, Consolas, monospace">'
        f'{total:,.0f}</text>'
        f'<text x="130" y="142" text-anchor="middle" '
        f'fill="var(--muted)" font-size="0.65rem" '
        f'font-family="Cascadia Code, Consolas, monospace">pJ</text>'
        f'</svg>'
    )

    return (
        f'<div class="donut-section">'
        f'<div class="donut-chart-container">{svg}</div>'
        f'<div class="donut-legend">{"".join(legend_items)}</div>'
        f"</div>"
    )


def _build_footnote(arch: str) -> str:
    """Return architecture-appropriate footnote HTML."""
    arch_lower = arch.lower()

    if "x86" in arch_lower or "intel" in arch_lower or "amd" in arch_lower:
        return (
            '<div class="footnote">'
            "<strong>Energy Model:</strong> Intel Skylake-X (14 nm++, 3.0 GHz, 1.0 V) &mdash; "
            "values derived from:<br>"
            "&bull; Intel 64 and IA-32 Architectures Optimization Reference Manual (248966-044)<br>"
            "&bull; Intel Skylake Microarchitecture Software Optimization Guide<br>"
            "&bull; Bircher &amp; John, <em>Complete System Power Estimation Using Processor "
            "Performance Events</em>, IEEE TC 2012<br>"
            "&bull; Tiwari et al., <em>Power analysis of embedded software</em>, IEEE TVLSI 1994<br>"
            "<br>"
            "<strong>Note:</strong> x86-64 instructions typically cost ~1.5-3x more than equivalent "
            "ARM A55 instructions due to complex instruction decode and out-of-order execution overhead.<br>"
            "<strong>Disclaimer:</strong> This is a <em>static</em> energy estimate. "
            "Actual dynamic energy depends on cache behaviour, branch prediction, "
            "operand switching activity, and workload-specific memory access patterns."
            "</div>"
        )

    return (
        '<div class="footnote">'
        "<strong>Energy Model:</strong> ARM Cortex-A55 (7 nm, 1800 MHz, 0.8 V) &mdash; "
        "values derived from:<br>"
        "&bull; ARM Cortex-A55 Software Optimization Guide (ARM-DEN-0060A, Rev 3)<br>"
        "&bull; Pallister et al., <em>BEEBS: Open Benchmarks for Energy Measurements on "
        "Embedded Platforms</em>, 2013<br>"
        "&bull; Tiwari et al., <em>Power analysis of embedded software</em>, IEEE TVLSI 1994<br>"
        "&bull; Abdelhadi &amp; Bhattacharyya, <em>Energy modeling for superscalar processors</em>, "
        "ACM TECS 2016<br>"
        "<br>"
        "<strong>Disclaimer:</strong> This is a <em>static</em> energy estimate based on published "
        "per-instruction data and compile-time block frequency analysis. Actual dynamic energy "
        "depends on cache behaviour, branch prediction, operand switching activity, "
        "and workload-specific memory access patterns."
        "</div>"
    )


def build_html(data: dict, title: str, functions: list[dict], total_all: float) -> str:
    arch = data.get("arch", "unknown")
    unit = data.get("unit", "pJ")
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    max_energy = functions[0].get("total_energy_pJ", 1.0) if functions else 1.0
    total_instrs = sum(
        sum(b.get("instructions", 0) for b in f.get("blocks", [])) for f in functions
    )

    # -- Header badges ---
    badges_html = (
        f'<span class="badge">Arch: {html.escape(arch)}</span>'
        f'<span class="badge">Unit: {html.escape(unit)}</span>'
        f'<span class="badge">Functions: {len(functions)}</span>'
        f'<span class="badge">Generated: {now_str}</span>'
    )

    # -- Summary stat cards ---
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
        <div class="value" style="font-size:1.0rem;word-break:break-all;">
          {html.escape(functions[0]["name"]) if functions else "---"}
        </div>
        <div class="unit">{fmt_pJ(max_energy)}</div>
      </div>
    </div>
    """

    # -- Donut chart ---
    donut_chart = _build_donut_chart(functions, total_all)

    # -- Function summary table ---
    func_rows = []
    for idx, fn in enumerate(functions):
        name = fn.get("name", "?")
        energy = fn.get("total_energy_pJ", 0.0)
        pct = (energy / total_all * 100) if total_all > 0 else 0.0
        ratio = energy / max_energy if max_energy > 0 else 0.0
        color = energy_color(energy, max_energy)
        cls = heat_css_class(ratio)
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
    <section class="panel" id="sec-summary">
      <h2>[A] Function Energy Summary <span class="hint">(click any column header to sort &mdash; click a function name to see its block breakdown in <a href="#sec-blocks" style="color:var(--accent);text-decoration:none;">[B]</a>)</span></h2>
      <table id="fn-table">
        <thead>
          <tr>
            <th class="num" onclick="sortTable('fn-table',0,true)">#</th>
            <th onclick="sortTable('fn-table',1,false)">Function</th>
            <th class="num" onclick="sortTable('fn-table',2,true)">Energy ({html.escape(unit)})</th>
            <th class="num" onclick="sortTable('fn-table',3,true)">% Total</th>
            <th class="num" onclick="sortTable('fn-table',4,true)">Blocks</th>
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

    # -- Per-function block breakdown ---
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
              <td class="number" data-sort="{freq:.6f}">{freq:.4f}x</td>
              <td class="number" data-sort="{wt:.6f}">{wt:,.4f}</td>
              <td class="number" data-sort="{bpct:.4f}">{bpct:.2f}%</td>
              <td class="number">{ic}</td>
              <td class="bar-cell">{pct_bar_html(bratio, bcolor)}</td>
            </tr>""")

        tid = f"blk-{html.escape(fn_name, quote=True).replace(' ', '_')[:30]}-{id(fn)}"

        # --- Opcode breakdown ---
        ib = fn.get("instruction_breakdown", {})
        if ib:
            max_op_energy = max(op["total"] for op in ib.values()) if ib else 1.0
            op_rows = []
            for opcode, info in sorted(ib.items(), key=lambda x: x[1]["total"], reverse=True):
                op_ratio = info["total"] / max_op_energy if max_op_energy > 0 else 0.0
                op_color = energy_color(info["total"], max_op_energy)
                op_rows.append(f"""
            <tr>
              <td class="opcode" data-sort="{html.escape(opcode)}"><code>{html.escape(opcode)}</code></td>
              <td class="number">{info["count"]}</td>
              <td class="number">{info["energy_per"]:.2f}</td>
              <td class="number" data-sort="{info["total"]:.6f}">{info["total"]:.2f}</td>
              <td class="bar-cell">{pct_bar_html(op_ratio, op_color)}</td>
            </tr>""")
            total_opcodes = len(ib)
            opcode_section = f"""
      <details class="opcode-detail">
        <summary>
          <span class="arrow">></span>
          Instruction Breakdown &mdash; {total_opcodes} opcodes
        </summary>
        <div class="opcode-table">
          <table>
            <thead>
              <tr>
                <th>Opcode</th>
                <th class="num">Count</th>
                <th class="num">Energy/Inst ({html.escape(unit)})</th>
                <th class="num">Total ({html.escape(unit)})</th>
                <th>Bar</th>
              </tr>
            </thead>
            <tbody>
              {"".join(op_rows)}
            </tbody>
          </table>
        </div>
      </details>"""
        else:
            opcode_section = ""

        details_html_parts.append(f"""
      <details>
        <summary>
          <span class="arrow">></span>
          <code style="color:var(--accent);font-size:0.85rem;">{html.escape(fn_name)}</code>
          &nbsp;---&nbsp;
          <strong>{fn_energy:,.4f} {html.escape(unit)}</strong>
          &nbsp;&nbsp;{cat_badge}
          &nbsp;&nbsp;<span style="color:var(--muted);font-size:0.76rem;">{len(blocks)} block(s)</span>
        </summary>
        <div class="block-table">
          <table id="{tid}">
            <thead>
              <tr>
                <th class="num" onclick="sortTable('{tid}',0,true)">#</th>
                <th onclick="sortTable('{tid}',1,false)">Basic Block</th>
                <th class="num" onclick="sortTable('{tid}',2,true)">Raw ({html.escape(unit)})</th>
                <th class="num" onclick="sortTable('{tid}',3,true)">Freq Scale</th>
                <th class="num" onclick="sortTable('{tid}',4,true)">Weighted ({html.escape(unit)})</th>
                <th class="num" onclick="sortTable('{tid}',5,true)">% of Func</th>
                <th class="num" onclick="sortTable('{tid}',6,true)">Instrs</th>
                <th>Bar</th>
              </tr>
            </thead>
            <tbody>
              {"".join(blk_rows)}
            </tbody>
          </table>
        </div>
        {opcode_section}
      </details>""")

    details_section = f"""
    <section class="panel" id="sec-blocks">
      <h2>[B] Per-Function Block Breakdown
        <span class="hint">(click a row to expand &mdash; overview in <a href="#sec-summary" style="color:var(--accent);text-decoration:none;">[A]</a> &mdash; distribution in <a href="#sec-donut" style="color:var(--accent);text-decoration:none;">[C]</a>)</span>
      </h2>
      {"".join(details_html_parts)}
    </section>
    """

    footnote = _build_footnote(arch)

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
  <div class="head-left">
    <h1>[E] {html.escape(title)}</h1>
    <div class="sub">
      Static energy estimation via LLVM EnergyEstimationPass (MachineFunctionPass)
    </div>      <div style="margin-top:10px">{badges_html}</div>
      <div style="margin-top:6px;color:#8892a4;font-size:0.72rem;">
        Sections: <a href="#sec-summary" style="color:#6c8ff7;text-decoration:none;">[A] Summary</a>
        &middot; <a href="#sec-blocks" style="color:#6c8ff7;text-decoration:none;">[B] Blocks</a>
        &middot; <a href="#sec-donut" style="color:#6c8ff7;text-decoration:none;">[C] Distribution</a>
      </div>
  </div>
  <button id="themeBtn" class="theme-toggle" onclick="toggleTheme()" aria-label="Toggle theme">
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" /></svg>
  </button>
</header>

<div class="container">
  {stat_cards}    <section class="panel" id="sec-donut">
      <h2>[C] Energy Distribution <span class="hint">(per-function breakdown in <a href="#sec-summary" style="color:var(--accent);text-decoration:none;">[A]</a> &mdash; block details in <a href="#sec-blocks" style="color:var(--accent);text-decoration:none;">[B]</a>)</span></h2>
      {donut_chart}
  </section>

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
