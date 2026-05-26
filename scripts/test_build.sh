#!/usr/bin/env bash
# =============================================================================
# test_build.sh — Build Verification Script for LLVM Energy Estimation Pass
# =============================================================================
#
# Usage:
#   ./scripts/test_build.sh                    # auto-detect LLVM
#   ./scripts/test_build.sh /usr/lib/llvm-14   # explicit LLVM_DIR
#   ./scripts/test_build.sh --skip-python      # skip Python visualizer test
#
# What this script does:
#   1. Checks prerequisites (cmake, clang, llc, python3)
#   2. Runs CMake configure
#   3. Builds the EnergyEstimationPass plugin
#   4. Runs the pass on llvm/test/sample.c
#   5. Validates the JSON output
#   6. Generates HTML report with the visualizer
#   7. Prints a pass/fail summary
#
# Prerequisites:
#   sudo apt install llvm-14 llvm-14-dev clang-14 cmake ninja-build python3
#
# Exit codes:
#   0 — all tests passed
#   1 — one or more tests failed
#
# =============================================================================

set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
pass() { echo -e "  ${GREEN}[PASS]${RESET} $*"; }
fail() { echo -e "  ${RED}[FAIL]${RESET} $*"; failures=$((failures + 1)); }
info() { echo -e "  ${CYAN}[INFO]${RESET} $*"; }
warn() { echo -e "  ${YELLOW}[WARN]${RESET} $*"; }
step() { echo -e "\n${BOLD}${YELLOW}▶ $*${RESET}"; }

# ── Configuration ────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BUILD_DIR="${PROJECT_ROOT}/build"
OUTPUT_DIR="${BUILD_DIR}/test-output"
failures=0

# Auto-detect LLVM_DIR if not provided
if [[ $# -ge 1 && "$1" != "--skip-python" ]]; then
    LLVM_DIR="$1"
    shift
else
    # Try common locations
    for candidate in \
        /usr/lib/llvm-19/lib/cmake/llvm \
        /usr/lib/llvm-18/lib/cmake/llvm \
        /usr/lib/llvm-17/lib/cmake/llvm \
        /usr/lib/llvm-16/lib/cmake/llvm \
        /usr/lib/llvm-15/lib/cmake/llvm \
        /usr/lib/llvm-14/lib/cmake/llvm \
        /usr/lib/llvm-13/lib/cmake/llvm \
        /usr/lib/llvm-12/lib/cmake/llvm \
        /usr/local/lib/cmake/llvm \
        /opt/homebrew/opt/llvm/lib/cmake/llvm; do
        if [[ -d "$candidate" ]]; then
            LLVM_DIR="$candidate"
            break
        fi
    done
fi

SKIP_PYTHON=false
for arg in "$@"; do
    case "$arg" in
        --skip-python) SKIP_PYTHON=true ;;
    esac
done

# ── Prerequisites ────────────────────────────────────────────────────────────
step "Checking prerequisites"

command -v cmake  >/dev/null 2>&1 || { fail "cmake not found"; exit 1; }
command -v python3 >/dev/null 2>&1 || { warn "python3 not found — will skip visualizer tests"; SKIP_PYTHON=true; }

if [[ -n "${LLVM_DIR:-}" && -d "${LLVM_DIR}" ]]; then
    pass "LLVM_DIR = ${LLVM_DIR}"
else
    fail "LLVM not found. Try: apt install llvm-14-dev"
    fail "Then run: $0 /usr/lib/llvm-14/lib/cmake/llvm"
    exit 1
fi

# Check clang and llc are available
CLANG="$(command -v clang-14 2>/dev/null || command -v clang 2>/dev/null || true)"
LLC="$(command -v llc-14 2>/dev/null || command -v llc 2>/dev/null || true)"
if [[ -z "$CLANG" ]]; then fail "clang not found"; fi
if [[ -z "$LLC" ]];   then fail "llc not found"; fi

pass "clang = ${CLANG}"
pass "llc   = ${LLC}"
pass "cmake = $(cmake --version | head -1)"
python3 --version >/dev/null 2>&1 && pass "python3 = $(python3 --version 2>&1)"

# ── CMake Configure ──────────────────────────────────────────────────────────
step "Configuring with CMake"

mkdir -p "$BUILD_DIR"
cmake -S "$PROJECT_ROOT" -B "$BUILD_DIR" \
    -DLLVM_DIR="$LLVM_DIR" \
    -DCMAKE_BUILD_TYPE=Release \
    -G Ninja \
    2>&1 | tail -5

if cmake --build "$BUILD_DIR" --target help >/dev/null 2>&1; then
    pass "CMake configuration successful"
else
    fail "CMake configuration failed — check LLVM_DIR=$LLVM_DIR"
fi

# ── Build ────────────────────────────────────────────────────────────────────
step "Building EnergyEstimationPass"

cmake --build "$BUILD_DIR" --parallel 2>&1 | tail -10

# Check for the plugin
PLUGIN=""
for ext in .so .dylib .dll; do
    candidate=$(find "$BUILD_DIR" -name "*EnergyEstimation*${ext}" -type f 2>/dev/null | head -1)
    if [[ -n "$candidate" ]]; then
        PLUGIN="$candidate"
        break
    fi
done

if [[ -z "$PLUGIN" ]]; then
    # Try building just the target
    cmake --build "$BUILD_DIR" --target EnergyEstimationPass --parallel 2>&1 || true
    for ext in .so .dylib .dll; do
        candidate=$(find "$BUILD_DIR" -name "*EnergyEstimation*${ext}" -type f 2>/dev/null | head -1)
        if [[ -n "$candidate" ]]; then
            PLUGIN="$candidate"
            break
        fi
    done
fi

if [[ -n "$PLUGIN" ]]; then
    pass "Plugin built: $(basename "$PLUGIN") ($(du -h "$PLUGIN" | cut -f1))"
else
    fail "Plugin not found in build directory"
    info "Build output files:"
    find "$BUILD_DIR" -name "*.so" -o -name "*.dylib" -o -name "*.dll" 2>/dev/null | head -5
fi

# ── Compile Test Source ──────────────────────────────────────────────────────
step "Compiling test source: llvm/test/sample.c"

SOURCE="${PROJECT_ROOT}/llvm/test/sample.c"
if [[ ! -f "$SOURCE" ]]; then
    fail "Test source not found: $SOURCE"
    exit 1
fi

mkdir -p "$OUTPUT_DIR"
BITCODE="${OUTPUT_DIR}/sample.bc"
ASM="${OUTPUT_DIR}/sample.s"

"$CLANG" -O2 -target aarch64-linux-gnu -emit-llvm -g \
    -c "$SOURCE" -o "$BITCODE" 2>&1

if [[ -f "$BITCODE" ]]; then
    pass "Bitcode generated: $(du -h "$BITCODE" | cut -f1)"
else
    fail "Bitcode generation failed"
fi

# ── Run Pass (if plugin built) ──────────────────────────────────────────────
ENERGY_JSON="${OUTPUT_DIR}/energy_results.json"
REMARKS="${OUTPUT_DIR}/remarks.txt"

if [[ -f "$PLUGIN" ]]; then
    step "Running EnergyEstimationPass"

    "$LLC" \
        -load "$PLUGIN" \
        -energy-estimation \
        -energy-model "${PROJECT_ROOT}/llvm/energy-models/aarch64.json" \
        -energy-output "$ENERGY_JSON" \
        -mtriple aarch64-linux-gnu \
        -Rpass-analysis=energy \
        "$BITCODE" -o "$ASM" 2>"$REMARKS" || \
    warn "llc returned non-zero — check remarks for details"

    if [[ -f "$ENERGY_JSON" ]]; then
        pass "Energy JSON: $(du -h "$ENERGY_JSON" | cut -f1)"
    else
        fail "Energy JSON not produced"
    fi

    if [[ -f "$REMARKS" ]]; then
        remark_count=$(grep -c "remark:" "$REMARKS" 2>/dev/null || echo 0)
        pass "Remarks: ${remark_count} lines"
    fi

    # Validate JSON content
    if [[ -f "$ENERGY_JSON" ]]; then
        step "Validating JSON output"
        python3 -c "
import json, sys
with open('$ENERGY_JSON') as f:
    data = json.load(f)
funcs = data.get('functions', [])
print(f'  Functions  : {len(funcs)}')
if funcs:
    total = sum(f.get('total_energy_pJ', 0) for f in funcs)
    hottest = max(funcs, key=lambda f: f.get('total_energy_pJ', 0))
    print(f'  Total      : {total:,.2f} pJ')
    print(f'  Hottest    : {hottest[\"name\"]} ({hottest[\"total_energy_pJ\"]:,.2f} pJ)')
    print(f'  Verified   : JSON is valid and contains function data')
" && pass "JSON validation passed" || fail "JSON validation failed"
    fi
else
    warn "Skipping pass execution (plugin not available)"
    warn "To build the pass, install LLVM dev libraries and run:"
    warn "  cmake -S . -B build -DLLVM_DIR=<path> -G Ninja"
    warn "  cmake --build build --parallel"
fi

# ── HTML Report ─────────────────────────────────────────────────────────────
if [[ "$SKIP_PYTHON" == "false" ]] && [[ -f "$ENERGY_JSON" ]]; then
    step "Generating HTML report"

    VIZ="${PROJECT_ROOT}/llvm/visualize_energy.py"
    if [[ -f "$VIZ" ]]; then
        python3 "$VIZ" "$ENERGY_JSON" \
            --output "${OUTPUT_DIR}/energy_report.html" \
            --title "Build Test: sample.c (AArch64 Cortex-A55)" \
            2>&1 && pass "HTML report generated" || fail "HTML report generation failed"
    else
        warn "visualize_energy.py not found at $VIZ"
    fi
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
SEP=$(printf '=%.0s' $(seq 1 60))
echo -e "${BOLD}${SEP}${RESET}"
if [[ $failures -eq 0 ]]; then
    echo -e "${BOLD}${GREEN}  BUILD VERIFICATION: ALL CHECKS PASSED${RESET}"
else
    echo -e "${BOLD}${RED}  BUILD VERIFICATION: ${failures} CHECK(S) FAILED${RESET}"
fi
SEP=$(printf '=%.0s' $(seq 1 60))
echo -e "${BOLD}${SEP}${RESET}"
echo ""
echo "  Output files:"
echo "    Bitcode      : ${BITCODE}"
echo "    Assembly     : ${ASM}"
echo "    Energy JSON  : ${ENERGY_JSON}"
echo "    Remarks      : ${REMARKS}"
echo "    HTML report  : ${OUTPUT_DIR}/energy_report.html"
echo ""

exit $(( failures > 0 ? 1 : 0 ))
