#!/usr/bin/env bash
# =============================================================================
# run_test.sh — End-to-end pipeline test for the Static Energy Estimation Pass
# =============================================================================
#
# Usage:
#   ./run_test.sh [LLVM_BUILD_DIR]
#
# Arguments:
#   LLVM_BUILD_DIR  Path to an LLVM installation or build directory that
#                   contains bin/clang, bin/opt, and bin/llc.
#                   Default: /usr/local
#
# What this script does:
#   1. Compiles sample.c to LLVM bitcode (AArch64 target)
#   2. Loads the EnergyEstimationPass plugin into llc
#   3. Runs the -energy-estimation pass with the AArch64 JSON model
#   4. Captures -Rpass-analysis=energy remarks to a file
#   5. Reads the JSON energy results and generates an HTML report
#   6. Prints a summary and validates the output files exist
#
# Prerequisites:
#   - LLVM 14+ installed (clang, llc)
#   - The project built: cd .. && cmake -S . -B build && cmake --build build
#   - Python 3.8+ on PATH
#
# =============================================================================

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────

LLVM_BUILD="${1:-/usr/local}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BUILD_DIR="${PROJECT_ROOT}/build"

CLANG="${LLVM_BUILD}/bin/clang"
LLC="${LLVM_BUILD}/bin/llc"
OPT="${LLVM_BUILD}/bin/opt"
PYTHON="${PYTHON:-python3}"

# Detect plugin extension (Linux = .so, macOS = .dylib, Windows = .dll)
case "$(uname -s)" in
  Darwin*)  PLUGIN_EXT=".dylib" ;;
  MINGW*|CYGWIN*|MSYS*) PLUGIN_EXT=".dll" ;;
  *)        PLUGIN_EXT=".so"    ;;
esac
PLUGIN="${BUILD_DIR}/EnergyEstimationPass${PLUGIN_EXT}"

MODEL="${PROJECT_ROOT}/energy-models/aarch64.json"
SOURCE="${SCRIPT_DIR}/sample.c"
OUTPUT_DIR="${BUILD_DIR}/test-output"

mkdir -p "${OUTPUT_DIR}"

# Colours for output
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

pass() { echo -e "${GREEN}[PASS]${RESET} $*"; }
fail() { echo -e "${RED}[FAIL]${RESET} $*"; exit 1; }
info() { echo -e "${CYAN}[INFO]${RESET} $*"; }
step() { echo -e "\n${BOLD}${YELLOW}=== $* ===${RESET}"; }

# ── Preflight checks ──────────────────────────────────────────────────────────

step "Preflight checks"

[[ -f "${CLANG}"  ]] || fail "clang not found at ${CLANG}"
[[ -f "${LLC}"    ]] || fail "llc not found at ${LLC}"
[[ -f "${SOURCE}" ]] || fail "sample.c not found at ${SOURCE}"
[[ -f "${MODEL}"  ]] || fail "energy model not found at ${MODEL}"
[[ -f "${PLUGIN}" ]] || {
  echo -e "${YELLOW}[WARN]${RESET} Plugin not found at ${PLUGIN}"
  echo    "       Building the project now..."
  cmake -S "${PROJECT_ROOT}" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE=Release
  cmake --build "${BUILD_DIR}" --parallel
  [[ -f "${PLUGIN}" ]] || fail "Build failed — plugin still not found at ${PLUGIN}"
}

info "LLVM build : ${LLVM_BUILD}"
info "Plugin     : ${PLUGIN}"
info "Model      : ${MODEL}"
info "Output dir : ${OUTPUT_DIR}"

# ── Step 1: Compile sample.c to LLVM bitcode ──────────────────────────────────

step "Step 1: Compile sample.c → LLVM bitcode (AArch64)"

BITCODE="${OUTPUT_DIR}/sample.bc"
CLANG_TRIPLE="aarch64-linux-gnu"

"${CLANG}"                         \
    -O2                             \
    -target "${CLANG_TRIPLE}"       \
    -emit-llvm                      \
    -g                              \
    -c "${SOURCE}"                  \
    -o "${BITCODE}"

[[ -f "${BITCODE}" ]] || fail "Bitcode not produced"
info "Bitcode written to: ${BITCODE}  ($(du -sh "${BITCODE}" | cut -f1))"
pass "Compilation successful"

# ── Step 2: (Optional) Run opt to inspect IR ──────────────────────────────────

step "Step 2: Inspect LLVM IR (opt -print-function-names)"

FUNC_LIST="${OUTPUT_DIR}/functions.txt"
"${OPT}" --print-function-names "${BITCODE}" -o /dev/null 2>"${FUNC_LIST}" || true

if [[ -s "${FUNC_LIST}" ]]; then
  NUM_FUNCS=$(wc -l < "${FUNC_LIST}" | tr -d ' ')
  info "Found ${NUM_FUNCS} function(s) in bitcode:"
  cat "${FUNC_LIST}" | sed 's/^/    /'
  pass "IR inspection done"
else
  info "(--print-function-names not supported in this LLVM build; skipping)"
fi

# ── Step 3: Run energy estimation pass via llc ────────────────────────────────

step "Step 3: Run EnergyEstimationPass via llc"

ASM_OUTPUT="${OUTPUT_DIR}/sample.s"
ENERGY_JSON="${OUTPUT_DIR}/energy_results.json"
REMARKS_FILE="${OUTPUT_DIR}/remarks.txt"

# -mtriple forces AArch64 code generation even when llc is not cross-compiled
"${LLC}"                                             \
    -load "${PLUGIN}"                                 \
    -energy-estimation                                \
    -energy-model "${MODEL}"                          \
    -energy-output "${ENERGY_JSON}"                   \
    -mtriple "${CLANG_TRIPLE}"                        \
    -Rpass-analysis=energy                            \
    "${BITCODE}"                                      \
    -o "${ASM_OUTPUT}"                               \
    2>"${REMARKS_FILE}"

[[ -f "${ASM_OUTPUT}"  ]] || fail "Assembly output not produced at ${ASM_OUTPUT}"
[[ -f "${ENERGY_JSON}" ]] || fail "Energy JSON not produced at ${ENERGY_JSON}"

info "Assembly  : ${ASM_OUTPUT}"
info "JSON      : ${ENERGY_JSON}  ($(du -sh "${ENERGY_JSON}" | cut -f1))"
info "Remarks   : ${REMARKS_FILE}  ($(wc -l < "${REMARKS_FILE}") lines)"
pass "Energy estimation pass completed"

# ── Step 4: Validate JSON output ──────────────────────────────────────────────

step "Step 4: Validate JSON output"

# Check JSON is valid
"${PYTHON}" -c "
import json, sys
with open('${ENERGY_JSON}') as f:
    data = json.load(f)
funcs = data.get('functions', [])
if not funcs:
    print('WARNING: no functions in JSON', file=sys.stderr)
    sys.exit(1)
total = sum(f.get('total_energy_pJ', 0) for f in funcs)
print(f'  Functions : {len(funcs)}')
print(f'  Total energy : {total:,.2f} pJ')
print(f'  Hottest  : {funcs[0][\"name\"]}  ({funcs[0][\"total_energy_pJ\"]:,.2f} pJ)')
"

pass "JSON validation successful"

# ── Step 5: Show remark summary ───────────────────────────────────────────────

step "Step 5: Remark file summary"

REMARK_COUNT=$(grep -c "remark:" "${REMARKS_FILE}" 2>/dev/null || echo 0)
FUNC_REMARKS=$(grep -c "FunctionEnergy" "${REMARKS_FILE}" 2>/dev/null || echo 0)
BLOCK_REMARKS=$(grep -c "BlockEnergy"   "${REMARKS_FILE}" 2>/dev/null || echo 0)

info "Total remark lines : ${REMARK_COUNT}"
info "FunctionEnergy remarks : ${FUNC_REMARKS}"
info "BlockEnergy remarks    : ${BLOCK_REMARKS}"

echo ""
echo "--- First 10 energy remarks ---"
grep "remark:" "${REMARKS_FILE}" | head -10 | sed 's/^/    /'

pass "Remark summary done"

# ── Step 6: Generate HTML report ──────────────────────────────────────────────

step "Step 6: Generate HTML energy report"

HTML_REPORT="${OUTPUT_DIR}/energy_report.html"
VIZ_SCRIPT="${PROJECT_ROOT}/visualize_energy.py"

[[ -f "${VIZ_SCRIPT}" ]] || fail "visualize_energy.py not found at ${VIZ_SCRIPT}"

"${PYTHON}" "${VIZ_SCRIPT}"                         \
    "${ENERGY_JSON}"                                  \
    --output "${HTML_REPORT}"                         \
    --title "Energy Report: sample.c (AArch64 Cortex-A55)"

[[ -f "${HTML_REPORT}" ]] || fail "HTML report not generated at ${HTML_REPORT}"
info "HTML report : ${HTML_REPORT}  ($(du -sh "${HTML_REPORT}" | cut -f1))"
pass "HTML report generated"

# ── Step 7: Open report (if on macOS/Linux with display) ─────────────────────

step "Step 7: Open report (optional)"

if command -v open &>/dev/null; then
    info "Opening report with 'open' (macOS)..."
    open "${HTML_REPORT}" &
elif command -v xdg-open &>/dev/null && [[ -n "${DISPLAY:-}" ]]; then
    info "Opening report with xdg-open (Linux)..."
    xdg-open "${HTML_REPORT}" &
else
    info "Cannot auto-open browser. Open manually:"
    echo "    file://${HTML_REPORT}"
fi

# ── Final summary ─────────────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}${GREEN}============================================================${RESET}"
echo -e "${BOLD}${GREEN}  All steps completed successfully!${RESET}"
echo -e "${BOLD}${GREEN}============================================================${RESET}"
echo ""
echo "  Output files:"
echo "    Bitcode      : ${BITCODE}"
echo "    Assembly     : ${ASM_OUTPUT}"
echo "    Energy JSON  : ${ENERGY_JSON}"
echo "    Remarks      : ${REMARKS_FILE}"
echo "    HTML report  : ${HTML_REPORT}"
echo ""
echo "  To view the report:"
echo "    open ${HTML_REPORT}     # macOS"
echo "    xdg-open ${HTML_REPORT} # Linux"
echo "    start ${HTML_REPORT}    # Windows"
echo ""
