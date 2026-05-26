#!/usr/bin/env bash
# =============================================================================
# build.sh — Build the LLVM Static Energy Estimation Pass
# =============================================================================
#
# Usage:
#   ./build.sh                    # auto-detect LLVM
#   ./build.sh /usr/lib/llvm-14   # explicit LLVM directory
#   ./build.sh --help             # show this message
#
# Prerequisites:
#   sudo apt install llvm-14 llvm-14-dev clang-14 cmake ninja-build python3
#
# This script:
#   1. Locates LLVM (auto-detect or from argument)
#   2. Configures the CMake build
#   3. Builds the EnergyEstimationPass plugin
#   4. Reports success/failure
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

# ── Locate LLVM ─────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
BUILD_DIR="${PROJECT_ROOT}/build"
LLVM_DIR="$1"

if [[ -z "$LLVM_DIR" ]]; then
    # Auto-detect common LLVM installation paths
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

# ── Preflight Checks ────────────────────────────────────────────────────────
step "Preflight checks"

if [[ -z "$LLVM_DIR" || ! -d "$LLVM_DIR" ]]; then
    fail "LLVM not found."
    echo ""
    echo "  Install LLVM development libraries:"
    echo "    sudo apt install llvm-14 llvm-14-dev clang-14 cmake ninja-build"
    echo ""
    echo "  Then specify the LLVM directory:"
    echo "    ./build.sh /usr/lib/llvm-14/lib/cmake/llvm"
    echo ""
    echo "  Or let the script auto-detect (tries common paths)."
    exit 1
fi

# Detect clang
CLANG=$(command -v clang-14 2>/dev/null || command -v clang 2>/dev/null || true)
if [[ -z "$CLANG" ]]; then
    fail "clang not found. Install: sudo apt install clang-14"
    exit 1
fi

# Detect cmake
if ! command -v cmake &>/dev/null; then
    fail "cmake not found. Install: sudo apt install cmake"
    exit 1
fi

pass "LLVM_DIR = ${LLVM_DIR}"
pass "clang    = ${CLANG} ($(clang --version | head -1))"
pass "cmake    = $(cmake --version | head -1)"

# ── CMake Configure ─────────────────────────────────────────────────────────
step "Configuring CMake build (BUILD_DIR=${BUILD_DIR})"

mkdir -p "$BUILD_DIR"

cmake -S "$PROJECT_ROOT/llvm" -B "$BUILD_DIR" \
    -DLLVM_DIR="$LLVM_DIR" \
    -DCMAKE_BUILD_TYPE=Release \
    -G Ninja \
    2>&1

if [[ $? -ne 0 ]]; then
    fail "CMake configuration failed."
    info "Check LLVM_DIR=$LLVM_DIR"
    info "Try: apt install llvm-14-dev"
    exit 1
fi

pass "CMake configuration successful"

# ── Build ───────────────────────────────────────────────────────────────────
step "Building EnergyEstimationPass"

cmake --build "$BUILD_DIR" --parallel 2>&1

if [[ $? -ne 0 ]]; then
    fail "Build failed."
    exit 1
fi

# Locate the plugin
PLUGIN=$(find "$BUILD_DIR" -name "*EnergyEstimation*" -type f 2>/dev/null | head -1)
if [[ -n "$PLUGIN" ]]; then
    pass "Plugin built: $(basename "$PLUGIN") ($(du -h "$PLUGIN" | cut -f1))"
else
    # Try common extensions
    for ext in .so .dylib .dll; do
        PLUGIN=$(find "$BUILD_DIR" -name "*EnergyEstimation*${ext}" -type f 2>/dev/null | head -1)
        [[ -n "$PLUGIN" ]] && break
    done
    if [[ -n "$PLUGIN" ]]; then
        pass "Plugin built: $(basename "$PLUGIN") ($(du -h "$PLUGIN" | cut -f1))"
    else
        fail "Plugin binary not found in $BUILD_DIR"
        info "Build may have partial success; check build output above."
    fi
fi

# ── Summary ─────────────────────────────────────────────────────────────────
echo ""
SEP=$(printf '=%.0s' $(seq 1 60))
echo -e "${BOLD}${GREEN}${SEP}${RESET}"
echo -e "${BOLD}${GREEN}  Build complete!${RESET}"
echo -e "${BOLD}${GREEN}${SEP}${RESET}"
echo ""
echo "  Plugin : ${PLUGIN:-$BUILD_DIR/ (check for .so/.dylib)}"
echo "  Model  : $PROJECT_ROOT/llvm/energy-models/aarch64.json"
echo ""
echo "  To run the full pipeline:"
echo "    ./run.sh                          # runs default test (sample.c)"
echo "    ./run.sh examples/simple_test.c   # runs specific test file"
echo ""
