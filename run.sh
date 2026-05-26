#!/usr/bin/env bash
# =============================================================================
# run.sh — Run the LLVM Static Energy Estimation Pipeline
# =============================================================================
#
# Usage:
#   ./run.sh                              # run default test (llvm/test/sample.c)
#   ./run.sh examples/simple_test.c       # run a specific test file
#   ./run.sh --help                       # show this message
#   ./run.sh --simple                     # use Python simple pipeline (no LLVM build)
#
# What this script does:
#   1. Compiles the C source to LLVM bitcode (AArch64 target)
#   2. Runs the EnergyEstimationPass via llc (if built)
#   3. Generates an interactive HTML report
#
# Two modes:
#   - Full pipeline (default): uses the compiled LLVM pass plugin
#   - Simple pipeline (--simple): uses Python-based assembly parser (no LLVM build)
#
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
pass() { echo -e "  ${GREEN}[PASS]${RESET} $*"; }
fail() { echo -e "  ${RED}[FAIL]${RESET} $*"; }
info() { echo -e "  ${CYAN}[INFO]${RESET} $*"; }
step() { echo -e "\n${BOLD}${YELLOW}▶ $*${RESET}"; }

# ── Help ────────────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    sed -n '2,20p' "$0"
    exit 0
fi

# ── Configuration ───────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
BUILD_DIR="${PROJECT_ROOT}/build"
OUTPUT_DIR="${PROJECT_ROOT}/output"

# Detect simple mode
SIMPLE_MODE=false
if [[ "${1:-}" == "--simple" ]]; then
    SIMPLE_MODE=true
    shift
fi

# Default test file if none provided
if [[ $# -ge 1 && "$1" != "--simple" ]]; then
    TEST_FILE="$1"
    shift
else
    TEST_FILE="${PROJECT_ROOT}/llvm/test/sample.c"
fi

if [[ ! -f "$TEST_FILE" ]]; then
    fail "Test file not found: $TEST_FILE"
    exit 1
fi

MODEL="${PROJECT_ROOT}/llvm/energy-models/aarch64.json"
VIZ_SCRIPT="${PROJECT_ROOT}/llvm/visualize_energy.py"
mkdir -p "$OUTPUT_DIR"

TEST_NAME="$(basename "$TEST_FILE" .c)"

# ── Mode Detection ──────────────────────────────────────────────────────────
if [[ "$SIMPLE_MODE" == true ]]; then
    echo -e "${BOLD}${YELLOW}=== Simple Python Pipeline ===${RESET}"
    bash "${PROJECT_ROOT}/run_simple.sh" "$TEST_FILE"
    exit $?
fi

# Check if the full pass plugin is built
PLUGIN=""
for ext in .so .dylib .dll; do
    candidate=$(find "$BUILD_DIR" -name "*EnergyEstimation*${ext}" -type f 2>/dev/null | head -1)
    if [[ -n "$candidate" ]]; then
        PLUGIN="$candidate"
        break
    fi
done

if [[ -z "$PLUGIN" ]]; then
    echo ""
    echo -e "${YELLOW}============================================================${RESET}"
    echo -e "${YELLOW}  LLVM pass plugin not found.${RESET}"
    echo -e "${YELLOW}  Falling back to Python simple pipeline...${RESET}"
    echo -e "${YELLOW}  To build the full pass, run: ./build.sh${RESET}"
    echo -e "${YELLOW}============================================================${RESET}"
    echo ""
    bash "${PROJECT_ROOT}/run_simple.sh" "$TEST_FILE"
    exit 0
fi

# ── Full Pipeline ───────────────────────────────────────────────────────────
step "Full pipeline: $TEST_FILE"

# 1. Compile to LLVM bitcode
step "[1/5] Compiling to LLVM bitcode (AArch64)"
BITCODE="${OUTPUT_DIR}/${TEST_NAME}.bc"
clang -O2 -target aarch64-linux-gnu -emit-llvm -g \
    -c "$TEST_FILE" -o "$BITCODE" 2>"${OUTPUT_DIR}/clang_err.txt" || {
    fail "Compilation failed"
    cat "${OUTPUT_DIR}/clang_err.txt"
    exit 1
}
pass "Bitcode: $(du -h "$BITCODE" | cut -f1)"

# 2. Run energy estimation pass
step "[2/5] Running EnergyEstimationPass"
ASM="${OUTPUT_DIR}/${TEST_NAME}.s"
ENERGY_JSON="${OUTPUT_DIR}/energy_results.json"
REMARKS="${OUTPUT_DIR}/remarks.txt"

LLC="$(command -v llc-14 2>/dev/null || command -v llc 2>/dev/null || true)"
if [[ -z "$LLC" ]]; then
    fail "llc not found"
    exit 1
fi

"$LLC" \
    -load "$PLUGIN" \
    -energy-estimation \
    -energy-model "$MODEL" \
    -energy-output "$ENERGY_JSON" \
    -mtriple aarch64-linux-gnu \
    -Rpass-analysis=energy \
    "$BITCODE" -o "$ASM" 2>"$REMARKS" || {
    fail "llc returned error — see remarks below:"
    head -20 "$REMARKS"
    exit 1
}
pass "Assembly  : $(du -h "$ASM" | cut -f1)"
pass "JSON      : $(du -h "$ENERGY_JSON" | cut -f1)"
pass "Remarks   : $(wc -l < "$REMARKS") lines"

# 3. Validate JSON
step "[3/5] Validating energy results"
python3 -c "
import json, sys
with open('${ENERGY_JSON}') as f:
    data = json.load(f)
funcs = data.get('functions', [])
if not funcs:
    print('WARNING: No functions in output')
    sys.exit(1)
total = sum(f.get('total_energy_pJ', 0) for f in funcs)
hottest = max(funcs, key=lambda f: f.get('total_energy_pJ', 0))
print(f'  Functions       : {len(funcs)}')
print(f'  Total energy    : {total:,.2f} pJ')
print(f'  Hottest function: {hottest[\"name\"]} ({hottest[\"total_energy_pJ\"]:,.2f} pJ)')
"
pass "JSON validation passed"

# 4. Generate HTML report
step "[4/5] Generating HTML report"
HTML_REPORT="${OUTPUT_DIR}/energy_report.html"

if [[ -f "$VIZ_SCRIPT" ]]; then
    python3 "$VIZ_SCRIPT" "$ENERGY_JSON" \
        --output "$HTML_REPORT" \
        --title "Energy Report: ${TEST_NAME} (AArch64 Cortex-A55)" \
        --source "$TEST_FILE" \
        --remarks "$REMARKS" 2>&1
else
    # Fallback to legacy visualizer
    python3 "${PROJECT_ROOT}/scripts/visualize.py" "$ENERGY_JSON" -o "$HTML_REPORT"
fi

if [[ -f "$HTML_REPORT" ]]; then
    pass "HTML report: $(du -h "$HTML_REPORT" | cut -f1)"
else
    fail "HTML report not generated"
fi

# 5. Try to open report
step "[5/5] Opening report (optional)"

if command -v open &>/dev/null; then
    open "$HTML_REPORT" 2>/dev/null || true
elif command -v xdg-open &>/dev/null && [[ -n "${DISPLAY:-}" ]]; then
    xdg-open "$HTML_REPORT" 2>/dev/null || true
elif command -v start &>/dev/null; then
    start "$HTML_REPORT" 2>/dev/null || true
fi

# ── Summary ─────────────────────────────────────────────────────────────────
echo ""
SEP=$(printf '=%.0s' $(seq 1 60))
echo -e "${BOLD}${GREEN}${SEP}${RESET}"
echo -e "${BOLD}${GREEN}  Pipeline complete!${RESET}"
echo -e "${BOLD}${GREEN}${SEP}${RESET}"
echo ""
echo "  Test file    : $TEST_FILE"
echo "  Output dir   : $OUTPUT_DIR/"
echo ""
echo "  Output files:"
echo "    JSON      : $ENERGY_JSON"
echo "    HTML      : $HTML_REPORT"
echo "    Assembly  : $ASM"
echo "    Bitcode   : $BITCODE"
echo "    Remarks   : $REMARKS"
echo ""
echo "  To view the report:"
echo "    open $HTML_REPORT"
echo ""
