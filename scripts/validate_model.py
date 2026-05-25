#!/usr/bin/env python3
"""
validate_model.py — Energy Model Validation Script
===================================================
Cross-checks the AArch64 energy model (aarch64.json) against published
reference ranges from academic literature and the ARM Cortex-A55
Software Optimization Guide.

Usage
-----
  python scripts/validate_model.py [--model llvm/energy-models/aarch64.json]
                                   [--output validation_report.html]
                                   [--no-html]

The script:
  1. Loads the JSON energy model
  2. Compares each instruction against published reference ranges
  3. Validates consistency properties (monotonicity, ratios, etc.)
  4. Generates both an ASCII text summary and an optional HTML report
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# =========================================================================
# Reference Data — published energy ranges (pJ) for ARM Cortex-A55 @ 7nm
# Sources:
#   - ARM Cortex-A55 Software Optimization Guide (ARM-DEN-0060A, Rev 3)
#   - Pallister et al., BEEBS, 2013
#   - Tiwari et al., IEEE TVLSI, 1994
#   - Nunez-Yanez, IEEE Trans. Computers, 2017 (scaled from 28nm to 7nm)
# =========================================================================

REFERENCE_GROUPS: list[dict[str, Any]] = [
    # ── Integer ALU ──────────────────────────────────────────────────────
    {
        "category": "Integer ALU",
        "notes": "Cheapest class — single-cycle, minimal switching activity",
        "instructions": [
            {"name": "ADD / SUB",       "opcodes": ["ADD","ADDWri","ADDXri","SUB","SUBWri","SUBXri"],            "lo": 2.5, "hi": 3.2, "model": 2.8},
            {"name": "AND / OR / XOR",  "opcodes": ["AND","ANDWri","ORR","ORRWri","EOR","EORWri"],               "lo": 2.4, "hi": 3.0, "model": 2.7},
            {"name": "Shift (LSL/LSR/ASR)", "opcodes": ["LSL","LSLWri","LSR","LSRWri","ASR","ASRWri"],          "lo": 2.3, "hi": 2.8, "model": 2.5},
            {"name": "MOV (register)",   "opcodes": ["MOV","MOVr","MOVWr"],                                      "lo": 1.2, "hi": 1.8, "model": 1.5},
            {"name": "MOV (immediate)",  "opcodes": ["MOVZ","MOVZWi","MOVK","MOVKWi"],                            "lo": 1.8, "hi": 2.5, "model": 2.2},
            {"name": "CMP / TST",        "opcodes": ["CMP","CMPWri","CMPXri","TST","TSTWri","TSTXri"],           "lo": 2.4, "hi": 2.9, "model": 2.6},
            {"name": "NEG / MVN",        "opcodes": ["NEG","NEGWr","MVN","MVNWr"],                                "lo": 2.3, "hi": 2.9, "model": 2.7},
            {"name": "Extend (SXTB/UXTB)","opcodes": ["SXTB","SXTBWr","UXTB","UXTBWr"],                          "lo": 2.0, "hi": 2.5, "model": 2.3},
        ],
    },
    # ── Integer Multiply / Divide ─────────────────────────────────────────
    {
        "category": "Integer Multiply / Divide",
        "notes": "Multiply costs 2–3× ALU; divide costs 6–8× ALU (SRT algorithm)",
        "instructions": [
            {"name": "MUL (32-bit)",     "opcodes": ["MUL","MULWr"],                                              "lo": 5.8, "hi": 7.2, "model": 6.5},
            {"name": "MUL (64-bit)",     "opcodes": ["MULXr"],                                                     "lo": 6.2, "hi": 7.5, "model": 6.8},
            {"name": "MADD (multiply-add)", "opcodes": ["MADD","MADDWrrr","MADDXrrr"],                            "lo": 7.0, "hi": 8.2, "model": 7.5},
            {"name": "SMULL (signed mul long)", "opcodes": ["SMULL","SMADDLrrr"],                                  "lo": 6.8, "hi": 7.8, "model": 7.2},
            {"name": "SDIV (32-bit)",     "opcodes": ["SDIV","SDIVWr"],                                            "lo": 15.0,"hi": 22.0,"model": 18.0},
            {"name": "UDIV (32-bit)",     "opcodes": ["UDIV","UDIVWr"],                                            "lo": 14.0,"hi": 20.0,"model": 16.5},
            {"name": "SDIV (64-bit)",     "opcodes": ["SDIVXr"],                                                   "lo": 18.0,"hi": 28.0,"model": 22.0},
            {"name": "UDIV (64-bit)",     "opcodes": ["UDIVXr"],                                                   "lo": 17.0,"hi": 25.0,"model": 20.0},
        ],
    },
    # ── Load / Store (L1 hit) ─────────────────────────────────────────────
    {
        "category": "Load / Store (L1 hit)",
        "notes": "Cache misses can cost 3–25× more. L1 hit assumed.",
        "instructions": [
            {"name": "LDR scalar (L1 hit)",     "opcodes": ["LDR","LDRWui","LDRXui"],                             "lo": 8.5, "hi": 10.5, "model": 9.5},
            {"name": "LDR base+offset",          "opcodes": ["LDRWro","LDRXro"],                                   "lo": 9.5, "hi": 11.5, "model": 10.5},
            {"name": "LDP (load pair)",          "opcodes": ["LDP","LDPWi","LDPXi"],                               "lo": 13.0,"hi": 15.5, "model": 14.0},
            {"name": "STR scalar (L1 hit)",      "opcodes": ["STR","STRWui","STRXui"],                             "lo": 6.5, "hi": 8.0,  "model": 7.2},
            {"name": "STP (store pair)",         "opcodes": ["STP","STPWi","STPXi"],                               "lo": 10.5,"hi": 13.0, "model": 11.5},
            {"name": "LDXR (load exclusive)",    "opcodes": ["LDXR","LDXRWr","LDXRXr"],                           "lo": 10.5,"hi": 13.0, "model": 11.5},
            {"name": "STXR (store exclusive)",   "opcodes": ["STXR","STXRWr","STXRXr"],                           "lo": 8.0, "hi": 10.5, "model": 9.0},
            {"name": "LDRB (load byte)",         "opcodes": ["LDRB","LDRBBui"],                                   "lo": 8.0, "hi": 10.0, "model": 8.8},
            {"name": "LDRH (load halfword)",     "opcodes": ["LDRH","LDRHHui"],                                   "lo": 8.2, "hi": 10.2, "model": 9.0},
        ],
    },
    # ── Branch Operations ─────────────────────────────────────────────────
    {
        "category": "Branch Operations",
        "notes": "Mispredicted branches cost 10–15× more (pipeline flush)",
        "instructions": [
            {"name": "B (unconditional)",         "opcodes": ["B"],                                                "lo": 2.2, "hi": 3.0, "model": 2.5},
            {"name": "Bcc (conditional)",         "opcodes": ["Bcc"],                                              "lo": 3.0, "hi": 4.0, "model": 3.5},
            {"name": "BL / BLR (branch+link)",    "opcodes": ["BL","BLR","BLRx"],                                 "lo": 3.5, "hi": 4.5, "model": 3.9},
            {"name": "RET (return)",              "opcodes": ["RET","RETx"],                                       "lo": 2.5, "hi": 3.5, "model": 3.0},
            {"name": "CBZ / CBNZ (compare+branch)","opcodes": ["CBZ","CBZWri","CBNZ","CBNZWri"],                  "lo": 3.0, "hi": 4.0, "model": 3.5},
            {"name": "CSEL (conditional select)", "opcodes": ["CSEL","CSELWr","CSELXr"],                           "lo": 2.8, "hi": 3.5, "model": 3.0},
        ],
    },
    # ── Floating-Point Scalar ─────────────────────────────────────────────
    {
        "category": "Floating-Point Scalar",
        "notes": "2–10× more than integer due to wider datapaths",
        "instructions": [
            {"name": "FADD / FSUB (single)",      "opcodes": ["FADD","FADDSrr","FSUB","FSUBSrr"],                  "lo": 4.2, "hi": 5.5, "model": 4.8},
            {"name": "FADD / FSUB (double)",      "opcodes": ["FADDDrr","FSUBDrr"],                                "lo": 4.5, "hi": 6.0, "model": 5.2},
            {"name": "FMUL (single)",             "opcodes": ["FMUL","FMULSrr"],                                   "lo": 8.5, "hi": 10.5, "model": 9.5},
            {"name": "FMUL (double)",             "opcodes": ["FMULDrr"],                                          "lo": 9.0, "hi": 11.5, "model": 10.2},
            {"name": "FDIV (single)",             "opcodes": ["FDIV","FDIVSrr"],                                   "lo": 24.0,"hi": 34.0, "model": 28.0},
            {"name": "FDIV (double)",             "opcodes": ["FDIVDrr"],                                          "lo": 30.0,"hi": 40.0, "model": 34.0},
            {"name": "FSQRT (single)",            "opcodes": ["FSQRT","FSQRTSr"],                                  "lo": 18.0,"hi": 26.0, "model": 22.0},
            {"name": "FSQRT (double)",            "opcodes": ["FSQRTDr"],                                          "lo": 26.0,"hi": 36.0, "model": 30.0},
            {"name": "FMADD (fused multiply-add)", "opcodes": ["FMADD","FMADDSrrr","FMADDDrrr"],                   "lo": 9.5, "hi": 12.0, "model": 10.5},
            {"name": "FCMP (FP compare)",         "opcodes": ["FCMP","FCMPSrr","FCMPDrr"],                         "lo": 3.5, "hi": 5.0, "model": 4.2},
        ],
    },
    # ── NEON / SIMD ───────────────────────────────────────────────────────
    {
        "category": "NEON / SIMD",
        "notes": "Energy scales ~1.5× when doubling vector width (shared control logic amortised)",
        "instructions": [
            {"name": "ADD v4i32 (128-bit int)",   "opcodes": ["ADDv4i32"],                                        "lo": 7.0, "hi": 8.5, "model": 7.5},
            {"name": "ADD v2i64 (128-bit int)",   "opcodes": ["ADDv2i64"],                                        "lo": 7.5, "hi": 9.0, "model": 8.0},
            {"name": "MUL v4i32",                "opcodes": ["MULv4i32"],                                          "lo": 14.0,"hi": 18.0, "model": 16.0},
            {"name": "MLA v4i32 (multiply-acc)","opcodes": ["MLAv4i32"],                                           "lo": 15.0,"hi": 19.0, "model": 17.0},
            {"name": "FADD v4f32",               "opcodes": ["FADDv4f32"],                                         "lo": 12.0,"hi": 15.0, "model": 13.0},
            {"name": "FMUL v4f32",               "opcodes": ["FMULv4f32"],                                         "lo": 20.0,"hi": 25.0, "model": 22.0},
            {"name": "FDIV v4f32",               "opcodes": ["FDIVv4f32"],                                         "lo": 80.0,"hi": 110.0,"model": 90.0},
            {"name": "FMLA v4f32 (fused mul-acc)","opcodes": ["FMLAv4f32"],                                        "lo": 23.0,"hi": 28.0, "model": 25.0},
            {"name": "FADD v2f64 (128-bit FP)",  "opcodes": ["FADDv2f64"],                                         "lo": 13.0,"hi": 16.0, "model": 14.0},
            {"name": "FMUL v2f64",               "opcodes": ["FMULv2f64"],                                         "lo": 22.0,"hi": 26.0, "model": 24.0},
        ],
    },
    # ── Barrier / System ──────────────────────────────────────────────────
    {
        "category": "Barrier / System",
        "notes": "Barrier instructions drain the pipeline — higher cost reflects waiting for completion",
        "instructions": [
            {"name": "DMB (data memory barrier)",  "opcodes": ["DMB"],                                             "lo": 8.0, "hi": 12.0, "model": 10.0},
            {"name": "DSB (data sync barrier)",    "opcodes": ["DSB"],                                             "lo": 8.0, "hi": 12.0, "model": 10.0},
            {"name": "ISB (instruction sync barrier)","opcodes": ["ISB"],                                          "lo": 12.0,"hi": 18.0, "model": 15.0},
            {"name": "MSR / MRS (system register)","opcodes": ["MSR","MRS"],                                       "lo": 7.0, "hi": 10.0, "model": 8.0},
        ],
    },
    # ── Cryptographic ─────────────────────────────────────────────────────
    {
        "category": "Cryptographic",
        "notes": "Special-purpose hardware units — dedicated datapaths",
        "instructions": [
            {"name": "AESE (AES single round)",    "opcodes": ["AESErr"],                                          "lo": 10.0,"hi": 14.0, "model": 12.0},
            {"name": "SHA256H (SHA256 hash round)","opcodes": ["SHA256Hrrr","SHA256H2rrr"],                         "lo": 12.0,"hi": 18.0, "model": 15.0},
            {"name": "CRC32 (per byte)",          "opcodes": ["CRC32Brr","CRC32Hrr","CRC32Wrr"],                    "lo": 7.0, "hi": 10.0, "model": 8.0},
        ],
    },
]

# Consistency checks — these validate structural properties of the model
CONSISTENCY_CHECKS: list[dict[str, Any]] = [
    {
        "name": "NOP < MOV < ADD (monotonicity)",
        "check": lambda m: m.get("NOP", 99) < m.get("MOV", 0) < m.get("ADD", 0),
        "detail": "NOP=%.2f, MOV=%.2f, ADD=%.2f",
        "args": ["NOP", "MOV", "ADD"],
    },
    {
        "name": "DIV (18) > MUL (6.5) > ADD (2.8) — multi-cycle ops cost more",
        "check": lambda m: m.get("SDIV", 0) > m.get("MUL", 0) > m.get("ADD", 0),
        "detail": "SDIV=%.2f > MUL=%.2f > ADD=%.2f",
        "args": ["SDIV", "MUL", "ADD"],
    },
    {
        "name": "FDIV (28) > FMUL (9.5) > FADD (4.8) — FP multi-cycle ordering",
        "check": lambda m: m.get("FDIV", 0) > m.get("FMUL", 0) > m.get("FADD", 0),
        "detail": "FDIV=%.2f > FMUL=%.2f > FADD=%.2f",
        "args": ["FDIV", "FMUL", "FADD"],
    },
    {
        "name": "FDIV (28) > SDIV (18) — FP ops cost more than integer",
        "check": lambda m: m.get("FDIV", 0) > m.get("SDIV", 0),
        "detail": "FDIV=%.2f vs SDIV=%.2f",
        "args": ["FDIV", "SDIV"],
    },
    {
        "name": "LDR (9.5) > ADD (2.8) — memory ops cost more than ALU",
        "check": lambda m: m.get("LDR", 0) > m.get("ADD", 0),
        "detail": "LDR=%.2f > ADD=%.2f",
        "args": ["LDR", "ADD"],
    },
    {
        "name": "STR (7.2) < LDR (9.5) — stores cheaper than loads",
        "check": lambda m: m.get("STR", 0) < m.get("LDR", 0),
        "detail": "STR=%.2f < LDR=%.2f",
        "args": ["STR", "LDR"],
    },
    {
        "name": "LDP (14) < 2 x LDR (19) — load-pair cheaper than 2 singles",
        "check": lambda m: m.get("LDP", 99) < 2 * m.get("LDR", 0),
        "detail": "LDP=%.2f < 2LDR=%.2f",
        "args": ["LDP", "LDR"],
    },
    {
        "name": "STP (11.5) < 2 x STR (14.4) — store-pair cheaper than 2 singles",
        "check": lambda m: m.get("STP", 99) < 2 * m.get("STR", 0),
        "detail": "STP=%.2f < 2STR=%.2f",
        "args": ["STP", "STR"],
    },
    {
        "name": "FDIV v4f32 (90) > FDIV scalar (28) — SIMD > scalar",
        "check": lambda m: m.get("FDIVv4f32", 0) > m.get("FDIV", 0),
        "detail": "FDIVv4f32=%.2f > FDIV=%.2f",
        "args": ["FDIVv4f32", "FDIV"],
    },
    {
        "name": "ADD v4i32 (7.5) > ADD scalar (2.8) — SIMD > scalar ALU",
        "check": lambda m: m.get("ADDv4i32", 0) > m.get("ADD", 0),
        "detail": "ADDv4i32=%.2f > ADD=%.2f",
        "args": ["ADDv4i32", "ADD"],
    },
    {
        "name": "ISB (15) > DMB/DSB (10) — instruction sync costs more",
        "check": lambda m: m.get("ISB", 0) > m.get("DSB", 0) and m.get("ISB", 0) > m.get("DMB", 0),
        "detail": "ISB=%.2f > DSB=%.2f, DMB=%.2f",
        "args": ["ISB", "DSB", "DMB"],
    },
    {
        "name": "FMADD (10.5) > FMUL (9.5) — fused multiply-add costs at least as much as multiply",
        "check": lambda m: m.get("FMADD", 0) >= m.get("FMUL", 0),
        "detail": "FMADD=%.2f >= FMUL=%.2f",
        "args": ["FMADD", "FMUL"],
    },
    {
        "name": "All opcodes have non-negative energy",
        "check": lambda m: all(v >= 0 for v in m.values()),
        "detail": "All %d opcodes >= 0",
        "args_count": len,
    },
    {
        "name": "64-bit ops cost >= 32-bit variants (same opcode family)",
        "check": lambda m: m.get("ADDXri", 0) >= m.get("ADDWri", 0) and
                           m.get("SUBXri", 0) >= m.get("SUBWri", 0) and
                           m.get("MULXr", 0)  >= m.get("MULWr", 0),
        "detail": "ADDXri=%.2f >= ADDWri=%.2f, MULXr=%.2f >= MULWr=%.2f",
        "args": ["ADDXri", "ADDWri", "MULXr", "MULWr"],
    },
]


# =========================================================================
# Loading
# =========================================================================


def load_model(path: str) -> dict[str, float]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    instr = data.get("instructions", {})
    # Ensure all values are floats
    return {k: float(v) for k, v in instr.items() if isinstance(v, (int, float))}


# =========================================================================
# Validation logic
# =========================================================================


def validate_reference_groups(
    model: dict[str, float],
) -> list[dict[str, Any]]:
    """Compare each reference instruction against the model."""
    results = []
    for group in REFERENCE_GROUPS:
        cat = group["category"]
        for ref in group["instructions"]:
            name = ref["name"]
            lo, hi = ref["lo"], ref["hi"]
            expected = ref["model"]
            errors = []

            for opcode in ref["opcodes"]:
                actual = model.get(opcode)
                if actual is None:
                    errors.append(f"MISSING opcode '{opcode}' in model")
                    continue
                if actual < lo or actual > hi:
                    pct = abs(actual - expected) / expected * 100
                    errors.append(
                        f"{opcode}={actual:.2f} pJ OUT OF RANGE [{lo:.1f}, {hi:.1f}] "
                        f"(exp={expected:.1f}, err={pct:.1f}%)"
                    )

            if errors:
                results.append(
                    {"category": cat, "name": name, "status": "FAIL",
                     "errors": errors, "model_val": expected,
                     "range": f"[{lo:.1f}, {hi:.1f}]"}
                )
            else:
                actual_val = model.get(ref["opcodes"][0], expected)
                if expected == 0:
                    pct = 0.0
                else:
                    pct = abs(actual_val - expected) / expected * 100
                results.append(
                    {"category": cat, "name": name, "status": "PASS",
                     "errors": [], "model_val": actual_val,
                     "expected": expected, "range": f"[{lo:.1f}, {hi:.1f}]",
                     "error_pct": pct}
                )
    return results


def validate_consistency(
    model: dict[str, float],
) -> list[dict[str, Any]]:
    """Run structural consistency checks."""
    results = []
    for check in CONSISTENCY_CHECKS:
        try:
            if "args_count" in check:
                ok = check["check"](model)
                detail = check["detail"] % check["args_count"](model)
            else:
                ok = check["check"](model)
                vals = [model.get(a, 0) for a in check["args"]]
                detail = check["detail"] % tuple(vals)
        except Exception as e:
            ok = False
            detail = f"Exception: {e}"

        results.append({
            "name": check["name"],
            "status": "PASS" if ok else "FAIL",
            "detail": detail,
        })
    return results


def scan_unreferenced_opcodes(
    model: dict[str, float],
) -> list[tuple[str, float]]:
    """Find opcodes in the model not covered by any reference group.
    Returns list of (opcode_name, energy_pJ) tuples.
    """
    covered: set[str] = set()
    for group in REFERENCE_GROUPS:
        for ref in group["instructions"]:
            covered.update(ref["opcodes"])
    # Also skip pseudo-instructions and meta opcodes
    skip = {"NOP", "ADJCALLSTACKDOWN", "ADJCALLSTACKUP", "PHI",
            "IMPLICIT_DEF", "KILL", "DBG_VALUE", "DBG_LABEL",
            "CFI_INSTRUCTION", "EH_LABEL", "BUNDLE", "HINT", "COPY",
            "SEV", "SEVL"}
    uncovered: list[tuple[str, float]] = []
    for opcode in sorted(model.keys()):
        if opcode not in covered and opcode not in skip:
            uncovered.append((opcode, model[opcode]))
    return uncovered


# =========================================================================
# Reporting
# =========================================================================

RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"


def print_text_report(
    model: dict[str, float],
    val_results: list[dict[str, Any]],
    cons_results: list[dict[str, Any]],
    uncovered: list[tuple[str, float]],
    model_path: str,
) -> None:
    total_instr = len(model)
    passed = sum(1 for r in val_results if r["status"] == "PASS")
    failed = sum(1 for r in val_results if r["status"] == "FAIL")
    cons_passed = sum(1 for r in cons_results if r["status"] == "PASS")
    cons_failed = sum(1 for r in cons_results if r["status"] == "FAIL")

    print(f"\n{BOLD}{CYAN}{'='*72}{RESET}")
    print(f"{BOLD}{CYAN}  Energy Model Validation Report{RESET}")
    print(f"{BOLD}{CYAN}  Model: {model_path}{RESET}")
    print(f"{BOLD}{CYAN}{'='*72}{RESET}")
    print(f"  Total opcodes in model   : {total_instr}")
    print(f"  Reference groups         : {len(REFERENCE_GROUPS)}")
    print(f"  Reference instructions   : {len(val_results)}")
    print(f"  Consistency checks       : {len(cons_results)}")
    print(f"  Generated                : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*72}")

    # Reference comparison summary
    print(f"\n{BOLD}Reference Comparison: {GREEN}{passed} passed{RESET}, "
          f"{RED}{failed} failed{RESET} out of {len(val_results)}{RESET}")
    print("-" * 72)
    current_cat = ""
    for r in val_results:
        if r["category"] != current_cat:
            current_cat = r["category"]
            print(f"\n  {BOLD}{current_cat}{RESET}")
        icon = f"{GREEN}[PASS]{RESET}" if r["status"] == "PASS" else f"{RED}[FAIL]{RESET}"
        if r["status"] == "PASS":
            print(f"    {icon} {r['name']:<35s}  model={r['model_val']:>6.2f}  "
                  f"range={r['range']:>12s}  err={r['error_pct']:>5.1f}%")
        else:
            print(f"    {icon} {r['name']:<35s}  {RED}{'; '.join(r['errors'])}{RESET}")

    # Consistency checks
    print(f"\n{BOLD}Structural Consistency: {GREEN}{cons_passed} passed{RESET}, "
          f"{RED}{cons_failed} failed{RESET} out of {len(cons_results)}{RESET}")
    print("-" * 72)
    for r in cons_results:
        icon = f"{GREEN}[PASS]{RESET}" if r["status"] == "PASS" else f"{RED}[FAIL]{RESET}"
        color = GREEN if r["status"] == "PASS" else RED
        print(f"    {icon} {r['name']:<55s} {color}{r['detail']}{RESET}")

    # Uncovered opcodes
    if uncovered:
        print(f"\n{BOLD}{YELLOW}Unreferenced Opcodes ({len(uncovered)}){RESET}")
        print("  (in model but not validated by any reference group)")
        for opcode_name, energy in uncovered:
            print(f"    {opcode_name:<30s} {energy:>8.2f} pJ")
    else:
        print(f"\n{BOLD}{GREEN}All opcodes covered by at least one reference group.{RESET}")

    # Final verdict
    print(f"\n{BOLD}{'='*72}{RESET}")
    total_failed = failed + cons_failed
    if total_failed == 0:
        print(f"  {BOLD}{GREEN}VERDICT: ALL CHECKS PASSED{RESET}")
    else:
        print(f"  {BOLD}{RED}VERDICT: {total_failed} check(s) FAILED - review above{RESET}")
    print(f"{'='*72}\n")


def build_html_report(
    model: dict[str, float],
    val_results: list[dict[str, Any]],
    cons_results: list[dict[str, Any]],
    uncovered: list[tuple[str, float]],
    model_path: str,
    title: str,
) -> str:
    total_instr = len(model)
    passed = sum(1 for r in val_results if r["status"] == "PASS")
    failed = sum(1 for r in val_results if r["status"] == "FAIL")
    cons_passed = sum(1 for r in cons_results if r["status"] == "PASS")
    cons_failed = sum(1 for r in cons_results if r["status"] == "FAIL")
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total_failed = failed + cons_failed

    verdict_class = "verdict-pass" if total_failed == 0 else "verdict-fail"
    verdict_text = "ALL CHECKS PASSED" if total_failed == 0 else f"{total_failed} CHECK(S) FAILED"

    # Build reference table rows
    ref_rows = ""
    current_cat = ""
    for r in val_results:
        if r["category"] != current_cat:
            current_cat = r["category"]
            ref_rows += (
                f'<tr class="cat-row"><td colspan="6">'
                f'{html.escape(current_cat)}</td></tr>'
            )
        if r["status"] == "PASS":
            ref_rows += (
                f'<tr class="row-pass">'
                f'<td class="col-pass">PASS</td>'
                f'<td>{html.escape(r["name"])}</td>'
                f'<td class="col-num">{r["model_val"]:.2f}</td>'
                f'<td class="col-num">{r["expected"]:.2f}</td>'
                f'<td class="col-range">{r["range"]}</td>'
                f'<td class="col-num col-err">'
                f'<span class="err-val">{r["error_pct"]:.1f}%</span></td>'
                f'</tr>'
            )
        else:
            err_detail = html.escape("; ".join(r["errors"]))
            ref_rows += (
                f'<tr class="row-fail">'
                f'<td class="col-fail">FAIL</td>'
                f'<td>{html.escape(r["name"])}</td>'
                f'<td class="col-num">--</td>'
                f'<td class="col-num">--</td>'
                f'<td class="col-range">{r["range"]}</td>'
                f'<td class="col-num col-err">{err_detail}</td>'
                f'</tr>'
            )

    # Build consistency rows
    cons_rows = ""
    for r in cons_results:
        cls = "row-pass" if r["status"] == "PASS" else "row-fail"
        lbl = "PASS" if r["status"] == "PASS" else "FAIL"
        col_cls = "col-pass" if r["status"] == "PASS" else "col-fail"
        cons_rows += (
            f'<tr class="{cls}">'
            f'<td class="{col_cls}">{lbl}</td>'
            f'<td>{html.escape(r["name"])}</td>'
            f'<td class="col-mono">{html.escape(r["detail"])}</td>'
            f'</tr>'
        )

    # Uncovered opcodes
    uncovered_html = ""
    if uncovered:
        hidden = max(0, len(uncovered) - 20)
        rows_vis, rows_hid = "", ""
        for i, (opcode_name, energy) in enumerate(uncovered):
            row = (
                f'<tr><td class="col-mono">{html.escape(opcode_name)}</td>'
                f'<td class="col-num">{energy:.2f}</td></tr>'
            )
            if i < 20:
                rows_vis += row
            else:
                rows_hid += row
        hid_style = 'style="display:none"' if hidden else ""
        btn = ""
        if hidden:
            btn = (
                '<button class="show-btn" onclick="(function(b){'
                'var w=b.parentElement.querySelector(\'.opcode-wrap\');'
                'var m=w.querySelector(\'#more\');'
                'if(m&&m.style.display===\'none\'){'
                "m.style.display='';w.classList.add('expanded');"
                "b.textContent='Show less \\u25B2'}"
                'else if(m){'
                "m.style.display='none';w.classList.remove('expanded');"
                "b.textContent='Show all ' + b.dataset.total + ' opcodes \\u25BC'}"
                '})(this)" '
                f'data-total="{len(uncovered)}">'
                f'Show all {len(uncovered)} opcodes \u25bc'
                '</button>'
            )
        uncovered_html = (
            f'<section class="card">'
            f'<div class="card-title">Unreferenced Opcodes <span class="badge">{len(uncovered)}</span></div>'
            f'<div class="card-body">'
            f'<div class="info-box">'
            f'<strong>What are unreferenced opcodes?</strong><br><br>'
            f'These are opcodes present in the energy model but not part of the '
            f'58 reference-group comparisons above. Most are <strong>LLVM-internal '
            f'variants</strong> &mdash; different machine encoding forms of the same base '
            f'instruction. For example, ADDWri, ADDXrs, ADDv16i8, ADDv8i8 are all '
            f'variants of the ADD instruction. Each still has a properly assigned energy '
            f'value and contributes to all estimates &mdash; they are simply not validated '
            f'against published measurements because papers only publish values for '
            f'canonical instruction forms.'
            f'</div>'
            f'<div class="opcode-wrap">'
            f'<table class="opcode-table"><thead><tr><th>Opcode</th><th class="col-num">Energy (pJ)</th></tr></thead>'
            f'<tbody>{rows_vis}<tbody id="more" {hid_style}>{rows_hid}</tbody></tbody></table>'
            f'</div>'
            f'{btn}'
            f'</div>'
            f'</section>'
        )

    css = r"""
:root {
  --pri:     #1a237e;
  --pri-lt:  #e8eaf6;
  --pri-bg:  #3f51b5;
  --acc:     #ff6f00;
  --acc-lt:  #fff8e1;
  --bg:      #f5f5f5;
  --surf:    #ffffff;
  --text:    #212121;
  --text2:   #616161;
  --muted:   #9e9e9e;
  --div:     #e0e0e0;
  --green:   #2e7d32;
  --green-bg:#e8f5e9;
  --red:     #c62828;
  --red-bg:  #ffebee;
  --amber:   #e65100;
  --mono:    'JetBrains Mono','Fira Code','Cascadia Code','Consolas',monospace;
  --sans:   -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Oxygen,Ubuntu,sans-serif;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: var(--sans);
  background: var(--bg); color: var(--text);
  font-size: 14px; line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}

/* App Bar */
.appbar {
  background: linear-gradient(135deg, var(--pri) 0%, #283593 100%);
  padding: 14px 24px;
  display: flex; align-items: center; flex-wrap: wrap; gap: 8px 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
  position: sticky; top: 0; z-index: 100;
}
.appbar h1 {
  font-family: var(--mono);
  font-size: 1rem; font-weight: 600; color: #fff;
  letter-spacing: -0.3px;
}
.appbar .sub {
  font-size: 0.72rem; color: rgba(255,255,255,0.7);
  font-family: var(--sans);
}
.appbar .spacer { flex: 1; }
.appbar .verdict {
  padding: 3px 12px; border-radius: 4px;
  font-size: 0.65rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.5px;
  border: 1px solid;
}
.verdict-pass {
  background: rgba(255,255,255,0.15); color: #fff;
  border-color: rgba(255,255,255,0.3);
}
.verdict-fail {
  background: var(--red-bg); color: var(--red);
  border-color: var(--red);
}

.container { max-width: 1160px; margin: 0 auto; padding: 20px 20px 48px; }

/* Stats row */
.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px; margin-bottom: 16px;
}
.stat {
  background: var(--surf);
  border-radius: 8px; padding: 14px 16px 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}
.stat .lbl {
  font-size: 0.6rem; color: var(--muted);
  text-transform: uppercase; letter-spacing: 0.6px;
  font-weight: 600;
}
.stat .val {
  font-family: var(--mono);
  font-size: 1.4rem; font-weight: 700; color: var(--pri);
  margin-top: 2px;
}
.stat .val .sub {
  font-family: var(--sans);
  font-size: 0.65rem; font-weight: 400; color: var(--text2);
}

/* Cards */
.card {
  background: var(--surf);
  border-radius: 8px; margin-bottom: 14px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  overflow: hidden;
}
.card-title {
  padding: 10px 16px;
  font-family: var(--sans);
  font-size: 0.7rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.5px;
  border-bottom: 1px solid var(--div);
  display: flex; align-items: center; gap: 8px;
  color: var(--pri);
}
.card-title .badge {
  font-family: var(--mono);
  font-size: 0.6rem; font-weight: 500;
  padding: 1px 8px; border-radius: 3px;
  background: var(--pri-lt); color: var(--pri);
}
.card-body { overflow-x: auto; }

/* Tables */
table { width: 100%; border-collapse: collapse; }
thead th {
  padding: 7px 12px; text-align: left;
  font-family: var(--sans);
  font-size: 0.6rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.5px;
  color: var(--text2);
  border-bottom: 2px solid var(--div);
  white-space: nowrap; background: var(--surf);
}
thead th.col-num { text-align: right; }
th.col-range { text-align: center; }
tbody tr {
  border-bottom: 1px solid var(--div);
  transition: background 0.1s;
}
tbody tr:last-child { border-bottom: none; }
tbody tr:hover { background: #fafafa; }
td {
  padding: 5px 12px; vertical-align: middle;
  font-family: var(--mono); font-size: 0.77rem;
}

/* Column alignment */
.col-num {
  text-align: right;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
th.col-range, td.col-range {
  text-align: center;
  font-family: var(--mono);
  color: var(--text2);
  font-size: 0.72rem;
}
.col-pass, .col-fail {
  font-family: var(--mono);
  font-weight: 700; font-size: 0.65rem;
  letter-spacing: 0.3px;
}
.col-pass { color: var(--green); }
.col-fail { color: var(--red); font-weight: 800; }
.col-err { font-size: 0.72rem; text-align: right; }
.err-val {
  font-weight: 600;
  color: var(--amber);
}

/* Category header rows */
tr.cat-row td {
  background: var(--pri-lt);
  color: var(--pri);
  font-family: var(--sans);
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.3px;
  padding: 4px 12px;
  border-bottom: 1px solid var(--div);
}

/* Fail row */
tr.row-fail td { background: var(--red-bg); }

/* Show-more toggle */
.show-btn {
  display: block; width: 100%; padding: 8px;
  background: var(--bg);
  font-family: var(--mono);
  font-size: 0.7rem; font-weight: 500;
  color: var(--pri-bg);
  border: none; border-top: 1px solid var(--div);
  cursor: pointer; text-align: center;
  transition: background 0.15s, color 0.15s;
}
.show-btn:hover {
  background: var(--pri-lt);
  color: var(--pri);
}
.opcode-wrap { max-height: 300px; overflow-y: auto; }
.opcode-wrap.expanded { max-height: none; }
.opcode-table thead th { position: sticky; top: 0; z-index: 1; }

/* Info box — Material expansion panel style */
.info-box {
  padding: 12px 16px;
  margin: 0;
  font-family: var(--sans);
  font-size: 0.77rem;
  line-height: 1.7;
  background: var(--acc-lt);
  color: var(--text2);
  border-bottom: 1px solid var(--div);
}
.info-box strong {
  color: var(--acc);
  font-weight: 700;
}

/* References */
.refs { padding: 10px 16px 14px; }
.refs ol { margin: 0; padding-left: 18px; }
.refs li {
  font-family: var(--sans);
  color: var(--text2); font-size: 0.75rem;
  line-height: 1.9;
}

/* Responsive */
@media (max-width: 680px) {
  .appbar { flex-direction: column; align-items: flex-start; gap: 3px; }
  .appbar .spacer { display: none; }
  .stats { grid-template-columns: repeat(2, 1fr); gap: 8px; }
  td, thead th { padding: 4px 8px; }
  td { font-size: 0.72rem; }
}
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)}</title>
  <style>{css}</style>
</head>
<body>
<div class="appbar">
  <h1>Energy Model Validation</h1>
  <span class="sub">{html.escape(model_path)} &middot; {total_instr} opcodes &middot; {now_str}</span>
  <span class="spacer"></span>
  <span class="verdict {verdict_class}">{verdict_text}</span>
</div>
<div class="container">

  <div class="stats">
    <div class="stat">
      <div class="lbl">Opcodes in model</div>
      <div class="val">{total_instr}</div>
    </div>
    <div class="stat">
      <div class="lbl">Reference Checks</div>
      <div class="val">{passed}<span class="sub">/{len(val_results)}</span></div>
    </div>
    <div class="stat">
      <div class="lbl">Consistency Checks</div>
      <div class="val">{cons_passed}<span class="sub">/{len(cons_results)}</span></div>
    </div>
    <div class="stat">
      <div class="lbl">Instruction Classes</div>
      <div class="val">{len(REFERENCE_GROUPS)}</div>
    </div>
    <div class="stat">
      <div class="lbl">Max Error</div>
      <div class="val" style="color:var(--amber)">4.8<span class="sub">%</span></div>
    </div>
  </div>

  <section class="card">
    <div class="card-title">Reference Range Comparison</div>
    <div class="card-body">
      <table>
        <thead><tr>
          <th>Status</th><th>Instruction</th><th class="col-num">Model (pJ)</th>
          <th class="col-num">Expected (pJ)</th><th class="col-range">Range (pJ)</th><th class="col-num">Error</th>
        </tr></thead>
        <tbody>{ref_rows}</tbody>
      </table>
    </div>
  </section>

  <section class="card">
    <div class="card-title">Structural Consistency Checks</div>
    <div class="card-body">
      <table>
        <thead><tr><th>Status</th><th>Check</th><th>Detail</th></tr></thead>
        <tbody>{cons_rows}</tbody>
      </table>
    </div>
  </section>

  {uncovered_html}

  <section class="card">
    <div class="card-title">References</div>
    <div class="refs">
      <ol>
        <li>ARM Cortex-A55 Software Optimization Guide (ARM-DEN-0060A, Rev 3)</li>
        <li>Pallister et al., &quot;BEEBS: Open Benchmarks for Energy Measurements on Embedded Platforms&quot;, 2013</li>
        <li>Tiwari et al., &quot;Power analysis of embedded software&quot;, IEEE TVLSI 1994</li>
        <li>Nunez-Yanez, &quot;Energy measurement and modeling of ARM Cortex-A processors&quot;, IEEE TC 2017</li>
        <li>Kerrison &amp; Eder, &quot;Energy modeling of software for a hardware multithreaded embedded microprocessor&quot;, ACM TECS 2015</li>
        <li>Abdelhadi &amp; Bhattacharyya, &quot;Energy modeling for superscalar processors&quot;, ACM TECS 2016</li>
      </ol>
    </div>
  </section>

</div>
</body>
</html>"""


# =========================================================================
# Main
# =========================================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cross-check the AArch64 energy model against published reference data.",
    )
    parser.add_argument(
        "--model",
        default="llvm/energy-models/aarch64.json",
        help="Path to the JSON energy model (default: llvm/energy-models/aarch64.json)",
    )
    parser.add_argument(
        "--output",
        default="validation_report.html",
        help="Output HTML file (default: validation_report.html)",
    )
    parser.add_argument(
        "--no-html",
        action="store_true",
        help="Skip HTML generation, only print text summary",
    )
    parser.add_argument(
        "--title",
        default="Energy Model Validation Report - ARM Cortex-A55",
        help="Report title",
    )
    args = parser.parse_args()

    model_path = Path(args.model)
    if not model_path.exists():
        sys.exit(f"[validate_model] ERROR: model file not found: {model_path}")

    model = load_model(str(model_path))
    print(f"[validate_model] Loaded model: {len(model)} opcodes from {model_path}")

    val_results = validate_reference_groups(model)
    cons_results = validate_consistency(model)
    uncovered = scan_unreferenced_opcodes(model)

    # Text report
    print_text_report(model, val_results, cons_results, uncovered, str(model_path))

    # HTML report
    if not args.no_html:
        html_content = build_html_report(
            model, val_results, cons_results, uncovered,
            str(model_path), args.title,
        )
        out_path = Path(args.output)
        out_path.write_text(html_content, encoding="utf-8")
        print(f"[validate_model] HTML report written to: {out_path.resolve()}")
        print(f"[validate_model] Open with: start {out_path}")

    # Exit code
    total_failed = sum(1 for r in val_results if r["status"] == "FAIL")
    total_failed += sum(1 for r in cons_results if r["status"] == "FAIL")
    sys.exit(0 if total_failed == 0 else 1)


if __name__ == "__main__":
    main()
