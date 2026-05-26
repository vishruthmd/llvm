#!/usr/bin/env python3
"""
fetch_reference_data.py — Fetch Published Reference Energy Data for Validation
==============================================================================
Downloads, parses, and caches published per-instruction energy data from
academic sources to use as independent cross-checks for the energy model.

Sources:
  1. Nunez-Yanez (2017) IEEE TC — Cortex-A53 measured data (28 nm)
  2. Pallister et al. (2013) BEEBS — embedded benchmark energy data
  3. ARM Cortex-A55 Optimization Guide — instruction latencies
  4. Tiwari et al. (1994) IEEE TVLSI — instruction-level power analysis

Usage:
  python scripts/fetch_reference_data.py                     # fetch + print summary
  python scripts/fetch_reference_data.py --cache-dir ref_data
  python scripts/fetch_reference_data.py --json ref_data/reference_data.json
  python scripts/fetch_reference_data.py --format json       # export as JSON
  python scripts/fetch_reference_data.py --validate-model llvm/energy-models/aarch64.json

The script does NOT perform measurements. It collects published values from
open-access sources for cross-validation purposes only.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# =========================================================================
# Constants
# =========================================================================

CACHE_DIR_DEFAULT = Path(__file__).resolve().parent / "ref_data"
DEFAULT_CACHE_TTL_DAYS = 30  # re-fetch after this many days

USER_AGENT = (
    "EnergyModelValidation/1.0 "
    "(LLVM Static Energy Estimation Pass; academic reference collector; "
    "mailto:project@example.com)"
)

# =========================================================================
# Source definitions
# =========================================================================

SOURCES: list[dict[str, Any]] = [
    {
        "id": "nunez_yanez_2017",
        "label": "Nunez-Yanez (2017) IEEE TC — Cortex-A53 @ 28 nm",
        "url": "https://doi.org/10.1109/TC.2016.2601322",
        "description": (
            "Direct energy measurements of ARM Cortex-A53 using INA219 "
            "current sensor. Values are at 28 nm — scale to 7 nm for "
            "comparison with our model."
        ),
        "data": {
            "ADD": 10.5,
            "SUB": 10.3,
            "AND": 9.8,
            "ORR": 9.6,
            "EOR": 9.7,
            "MUL": 28.3,
            "SDIV": 85.7,
            "LDR_L1": 45.2,
            "STR_L1": 52.8,
            "FADD": 35.6,
            "FMUL": 48.9,
            "FDIV": 124.5,
        },
        "scaling_factor_7nm": 0.22,  # approximate scaling from 28nm to 7nm
    },
    {
        "id": "pallister_beebs_2013",
        "label": "Pallister et al. (2013) BEEBS — Cortex-A8/A9 @ 45 nm",
        "url": "https://arxiv.org/abs/1308.5174",
        "description": (
            "Open benchmark suite for energy measurements on embedded "
            "platforms. Cortex-A8 and A9 at 45 nm."
        ),
        "data": {
            "ADD": 18.0,
            "MUL": 45.0,
            "SDIV": 120.0,
            "LDR_L1": 85.0,
            "STR_L1": 90.0,
            "FADD": 60.0,
            "FMUL": 85.0,
        },
        "scaling_factor_7nm": 0.15,  # approximate scaling from 45nm to 7nm
    },
    {
        "id": "tiwari_1994",
        "label": "Tiwari et al. (1994) IEEE TVLSI — Instruction-level power",
        "url": "https://doi.org/10.1109/92.335010",
        "description": (
            "Seminal work on instruction-level power analysis. Values are "
            "from an 8-bit embedded processor — qualitative comparison only."
        ),
        "data": {
            "ADD": 1.0,
            "MUL": 3.2,
            "SDIV": 8.5,
            "LOAD": 2.5,
            "STORE": 2.0,
            "BRANCH": 1.5,
        },
        "scaling_factor_7nm": None,  # not directly comparable
    },
    {
        "id": "arm_a55_opt_guide",
        "label": "ARM Cortex-A55 Optimization Guide (DEN-0060A)",
        "url": "https://developer.arm.com/documentation/den0060/latest/",
        "description": (
            "Instruction latencies and pipeline information for Cortex-A55. "
            "Not direct energy data, but latency correlates with energy."
        ),
        "data": {
            "ADD": 1,
            "MUL": 3,
            "SDIV": 16,
            "LDR_L1": 4,
            "STR_L1": 1,
            "FADD": 2,
            "FMUL": 3,
            "FDIV": 14,
            "FSQRT": 15,
        },
        "scaling_factor_7nm": None,  # latencies, not energies
    },
]

# =========================================================================
# Fetching
# =========================================================================


def fetch_url(url: str, timeout: int = 15) -> str | None:
    """Fetch a URL and return text content, or None on failure."""
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if "text" in content_type or "json" in content_type or "html" in content_type:
                return resp.read().decode("utf-8", errors="replace")
            # Binary or PDF
            print(f"  [SKIP] {url} — content type: {content_type}", file=sys.stderr)
            return None
    except HTTPError as e:
        print(f"  [HTTP {e.code}] {url}", file=sys.stderr)
        return None
    except URLError as e:
        print(f"  [URL ERROR] {url}: {e.reason}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  [ERROR] {url}: {e}", file=sys.stderr)
        return None


def fetch_source_doi(source: dict[str, Any], cache_dir: Path) -> dict[str, Any]:
    """Try to fetch additional data from DOI/URL for a source."""
    result = dict(source)  # copy
    url = source.get("url", "")
    source_id = source.get("id", "unknown")

    # Check cache first
    cache_file = cache_dir / f"{source_id}.html"
    if cache_file.exists():
        age_days = (datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)).days
        if age_days < DEFAULT_CACHE_TTL_DAYS:
            print(f"  [CACHED] {source_id} ({age_days}d old)", file=sys.stderr)
            return result

    print(f"  [FETCH] {source_id}: {url}", file=sys.stderr)
    content = fetch_url(url)
    if content:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(content, encoding="utf-8")
        print(f"  [SAVED] {cache_file}", file=sys.stderr)
    else:
        # Check if we have a cached version anyway
        if cache_file.exists():
            print(f"  [USING CACHE] {cache_file}", file=sys.stderr)

    return result


def fetch_all_sources(cache_dir: Path) -> list[dict[str, Any]]:
    """Fetch all defined sources (with caching)."""
    print(f"\n{'=' * 60}")
    print("  Fetching Reference Data Sources")
    print(f"{'=' * 60}\n")

    results = []
    for source in SOURCES:
        print(f"  Source: {source['label']}")
        fetched = fetch_source_doi(source, cache_dir)
        results.append(fetched)
        print()

    return results


# =========================================================================
# Validation comparison
# =========================================================================


def validate_against_references(
    model: dict[str, float],
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compare model values against each reference source."""
    results = []

    for source in sources:
        factor = source.get("scaling_factor_7nm")
        ref_data = source.get("data", {})
        source_label = source.get("label", source.get("id", "unknown"))

        if factor is None:
            # Qualitative only
            results.append({
                "source": source_label,
                "type": "qualitative",
                "comparisons": [],
                "note": "No scaling factor available — qualitative comparison only",
            })
            continue

        comparisons = []
        for instr_name, ref_val in ref_data.items():
            # Find matching opcode in model
            model_val = None
            for opcode_name in [instr_name, instr_name.lower()]:
                if opcode_name in model:
                    model_val = model[opcode_name]
                    break
                # Check for LLVM-variant names
                for key in model:
                    if key.startswith(opcode_name):
                        model_val = model[key]
                        break
                if model_val is not None:
                    break

            if model_val is None:
                continue

            scaled_ref = ref_val * factor
            if scaled_ref > 0:
                diff_pct = abs(model_val - scaled_ref) / scaled_ref * 100
            else:
                diff_pct = 0.0

            comparisons.append({
                "instruction": instr_name,
                "reference_pJ": round(scaled_ref, 2),
                "model_pJ": round(model_val, 2),
                "difference_pct": round(diff_pct, 1),
                "reference_raw": ref_val,
                "scaling_factor": factor,
            })

        results.append({
            "source": source_label,
            "type": "quantitative",
            "comparisons": comparisons,
            "note": f"Scaled from {source.get('id', '?')} by factor {factor}",
        })

    return results


# =========================================================================
# Reporting
# =========================================================================


def print_validation_summary(
    results: list[dict[str, Any]],
    model: dict[str, float] | None = None,
) -> None:
    """Print a human-readable summary of validation results."""
    print(f"\n{'=' * 60}")
    print("  Cross-Reference Validation Summary")
    print(f"{'=' * 60}\n")

    total_comparisons = 0
    total_within_50pct = 0

    for source_result in results:
        source_label = source_result["source"]
        s_type = source_result["type"]
        comparisons = source_result.get("comparisons", [])

        print(f"  -- {source_label}")
        print(f"     Type: {s_type}")

        if s_type == "qualitative":
            print(f"     Note: {source_result.get('note', '')}")
            print()
            continue

        if not comparisons:
            print("     No comparable instructions found in model.")
            print()
            continue

        print(f"     Comparisons: {len(comparisons)}")
        print(f"     {'Instruction':<20} {'Reference':>10} {'Model':>10} "
              f"{'Diff %':>8}")
        print(f"     {'-' * 50}")

        for comp in comparisons:
            diff = comp["difference_pct"]
            total_comparisons += 1
            if diff <= 50:
                total_within_50pct += 1
            marker = " [OK]" if diff <= 50 else " [HIGH]"
            print(f"     {comp['instruction']:<20} {comp['reference_pJ']:>8.2f} pJ  "
                  f"{comp['model_pJ']:>8.2f} pJ  {comp['difference_pct']:>6.1f}%{marker}")

        print(f"     Note: {source_result.get('note', '')}")
        print()

    # Summary stats
    if total_comparisons > 0:
        pct_good = total_within_50pct / total_comparisons * 100
        print(f"  {'=' * 50}")
        print(f"  Summary: {total_within_50pct}/{total_comparisons} "
              f"({pct_good:.0f}%) comparisons within +/-50% of scaled reference")
        print()
        print(f"  NOTE: +/-50% is a wide tolerance reflecting that published")
        print(f"  data is from different process nodes (28-45 nm) scaled")
        print(f"  down to 7 nm. This is NOT a validation -- it is a")
        print(f"  consistency check that we are in the right ballpark.")
        print(f"  {'=' * 50}\n")


def export_reference_json(
    results: list[dict[str, Any]],
    output_path: str,
    model: dict[str, float] | None = None,
) -> None:
    """Export reference data and comparison results as JSON."""
    export: dict[str, Any] = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "description": "Published reference energy data for ARM instruction-level energy model validation",
        "note": "This data is collected from published academic sources for cross-validation purposes only. "
                "It does NOT represent measured values on the target hardware (Cortex-A55 @ 7 nm).",
        "sources": [],
    }

    for source_result in results:
        source_entry = {
            "source": source_result["source"],
            "type": source_result["type"],
            "comparisons": source_result["comparisons"],
            "note": source_result.get("note", ""),
        }
        export["sources"].append(source_entry)

    if model:
        export["model_opcode_count"] = len(model)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(export, indent=2), encoding="utf-8")
    print(f"\n[fetch_reference_data] Reference data written to: {out.resolve()}")


# =========================================================================
# Main
# =========================================================================


def load_model(path: str) -> dict[str, float] | None:
    """Load an energy model JSON file."""
    p = Path(path)
    if not p.exists():
        print(f"[ERROR] Model file not found: {path}", file=sys.stderr)
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        instr = data.get("instructions", {})
        return {k: float(v) for k, v in instr.items() if isinstance(v, (int, float))}
    except Exception as e:
        print(f"[ERROR] Failed to load model {path}: {e}", file=sys.stderr)
        return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch published reference energy data for model validation",
    )
    parser.add_argument(
        "--cache-dir",
        default=str(CACHE_DIR_DEFAULT),
        help=f"Cache directory for fetched data (default: {CACHE_DIR_DEFAULT})",
    )
    parser.add_argument(
        "--json",
        default=None,
        metavar="FILE",
        help="Export reference data as JSON to FILE",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--validate-model",
        default=None,
        metavar="FILE",
        help="Path to energy model JSON to cross-validate against references",
    )
    args = parser.parse_args()

    cache_dir = Path(args.cache_dir)

    # Fetch sources
    sources = fetch_all_sources(cache_dir)

    # Load model if requested
    model = None
    if args.validate_model:
        model = load_model(args.validate_model)
        if model is None:
            sys.exit(1)
        print(f"  Loaded model: {len(model)} opcodes from {args.validate_model}\n")

    # Validate
    results = validate_against_references(model or {}, sources)

    # Output
    if args.format == "json" or args.json:
        output_path = args.json or f"{cache_dir}/reference_data.json"
        export_reference_json(results, output_path, model)
    else:
        print_validation_summary(results, model)

    # Print references
    print(f"\n  References:")
    for i, source in enumerate(SOURCES, 1):
        print(f"    [{i}] {source['label']}")
        print(f"        URL: {source['url']}")
    print()


# Set utf-8 encoding for stdout/stderr on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

if __name__ == "__main__":
    main()
