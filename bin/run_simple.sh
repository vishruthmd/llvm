SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Default test file
TEST_FILE="${1:-${PROJECT_ROOT}/examples/simple_test.c}"

if [ ! -f "$TEST_FILE" ]; then
    echo "Error: Test file not found: $TEST_FILE"
    echo "Usage: $0 [source_file.c]"
    exit 1
fi

cd "$PROJECT_ROOT"

echo "=== Static Energy Estimation (Simple Pipeline) ==="
echo "Input file: $TEST_FILE"
echo ""

# Create output directory
mkdir -p output

# Step 1: Compile to assembly (native target)
echo "[1/5] Compiling to assembly..."
CC=""
if command -v clang &>/dev/null; then
    CC="clang"
elif command -v gcc &>/dev/null; then
    CC="gcc"
    echo "       (clang not found, using gcc instead)"
else
    echo "[FAIL] Neither clang nor gcc found. Install a C compiler."
    exit 1
fi
$CC -O2 -g -S "$TEST_FILE" -o output/test.s 2>output/compile_err.txt || {
    echo "[FAIL] Compilation failed:"
    cat output/compile_err.txt
    exit 1
}
echo "       Written: output/test.s"

# Step 2: Detect architecture and select energy model
echo "[2/5] Selecting energy model..."
# Auto-detect architecture from assembly
if grep -q -i "\.arch arm\|\.arch aarch64\|aarch64\|ldr\b.*\[\|stp\b.*\[\|cbz\b\|cbnz\b" output/test.s 2>/dev/null; then
    ARCH="AArch64"
    MODEL="${PROJECT_ROOT}/llvm/energy-models/aarch64.json"
elif grep -q "%\(eax\|rax\|rdi\|rsi\|rbp\|rsp\|rip\)" output/test.s 2>/dev/null || grep -q "\.code64\|\.intel_syntax\|\.att_syntax\|\.seh_proc" output/test.s 2>/dev/null; then
    ARCH="x86-64"
    MODEL="${PROJECT_ROOT}/llvm/energy-models/x86_64.json"
else
    # Fall back to Python-based detection
    ARCH="auto"
    MODEL="${PROJECT_ROOT}/llvm/energy-models/aarch64.json"
fi
echo "       Architecture: $ARCH"
if [ ! -f "$MODEL" ]; then
    echo "  Warning: $MODEL not found, falling back to legacy model"
    MODEL="${PROJECT_ROOT}/models/energy_model.json"
fi
echo "       Model: $MODEL"

# Step 3: Analyze energy consumption
echo "[3/5] Analyzing energy consumption..."
python "${PROJECT_ROOT}/scripts/simple_energy_analysis.py" output/test.s "$MODEL" output/energy_results_raw.json
echo "       Written: output/energy_results_raw.json"

# Step 4: Convert to standard format
echo "[4/5] Converting to standard format..."
python "${PROJECT_ROOT}/scripts/convert_results.py" output/energy_results_raw.json output/energy_results.json
echo "       Written: output/energy_results.json"

# Step 5: Generate HTML report (use new visualizer if available)
echo "[5/5] Generating HTML report..."
VIZ="${PROJECT_ROOT}/llvm/visualize_energy.py"
if [ -f "$VIZ" ]; then
    python "$VIZ" output/energy_results.json --output output/energy_report.html --title "Energy Report: $TEST_FILE"
    echo "       Written: output/energy_report.html  [new visualizer]"
else
    python "${PROJECT_ROOT}/scripts/visualize.py" output/energy_results_raw.json -o output/energy_report.html
    echo "       Written: output/energy_report.html  [legacy visualizer]"
fi

echo ""
echo "=== Analysis Complete ==="
echo ""
echo "Output files in output/:"
echo "  energy_results.json       - Structured energy breakdown"
echo "  energy_report.html        - Interactive HTML report"
echo "  test.s                    - Assembly output"
echo ""
