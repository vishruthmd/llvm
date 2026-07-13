#!/usr/bin/env bash
# =============================================================================
# run_energy.sh — native macOS pipeline for the LLVM Energy Estimation Pass
# =============================================================================
# Runs the full pipeline in one command:
#   C source -> AArch64 bitcode -> MIR -> EnergyEstimationPass -> JSON -> HTML
#
# Usage:
#   ./run_energy.sh                    # uses simple_test.c (default)
#   ./run_energy.sh string_proc_test.c # uses your file
#
# Output: run_output/report.html (opened automatically) + energy_results.json
#
# Requires: llvm@14 (brew install llvm@14) — the pass targets LLVM 14's API.
# Builds llvm/build/ automatically on first run if it doesn't exist yet.
# =============================================================================

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

LLVM_PREFIX="${LLVM_PREFIX:-$(brew --prefix llvm@14 2>/dev/null || echo /opt/homebrew/opt/llvm@14)}"
CLANG="$LLVM_PREFIX/bin/clang"
LLC="$LLVM_PREFIX/bin/llc"

if [ ! -x "$CLANG" ] || [ ! -x "$LLC" ]; then
    echo "[ERROR] llvm@14 not found at $LLVM_PREFIX"
    echo "        Install it with: brew install llvm@14"
    exit 1
fi

TEST_FILE="${1:-$PROJECT_ROOT/simple_test.c}"
if [ ! -f "$TEST_FILE" ]; then
    echo "[ERROR] Source file not found: $TEST_FILE"
    echo "Usage: $0 [path/to/file.c]"
    exit 1
fi
BASENAME="$(basename "$TEST_FILE" .c)"

PLUGIN="$PROJECT_ROOT/build/lib/CodeGen/libEnergyEstimationPass.so"
MODEL="$PROJECT_ROOT/llvm/energy-models/aarch64.json"
OUT="$PROJECT_ROOT/run_output"

# ── Build the pass plugin if it doesn't exist yet ────────────────────────────
if [ ! -f "$PLUGIN" ]; then
    echo "[0/4] Building EnergyEstimationPass (first run only)..."
    cmake -S llvm -B build -DLLVM_DIR="$LLVM_PREFIX/lib/cmake/llvm" -DCMAKE_BUILD_TYPE=Release -G Ninja
    cmake --build build --parallel
fi

rm -rf "$OUT"
mkdir -p "$OUT"

echo "[1/4] Compiling to AArch64 bitcode..."
"$CLANG" -O2 -target aarch64-linux-gnu -ffreestanding -emit-llvm -c "$TEST_FILE" -o "$OUT/$BASENAME.bc"

echo "[2/4] Generating MIR..."
"$LLC" -stop-after=finalize-isel "$OUT/$BASENAME.bc" -o "$OUT/$BASENAME.mir" -mtriple aarch64-linux-gnu

echo "[3/4] Running EnergyEstimationPass..."
"$LLC" -load "$PLUGIN" \
    -run-pass=energy-estimation \
    -energy-model "$MODEL" \
    -energy-output "$OUT/energy_results.json" \
    -mtriple aarch64-linux-gnu "$OUT/$BASENAME.mir" -o "$OUT/$BASENAME.s"

echo "[4/4] Generating HTML report..."
python3 "$PROJECT_ROOT/llvm/visualize_energy.py" "$OUT/energy_results.json" \
    --output "$OUT/report.html" --title "Energy Report: $BASENAME.c"

echo ""
echo "Done! Output in $OUT/"
echo "  report.html          — interactive HTML report"
echo "  energy_results.json  — structured energy breakdown"

if command -v open >/dev/null 2>&1; then
    open "$OUT/report.html"
fi
