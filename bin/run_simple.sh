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
clang -O2 -g -S "$TEST_FILE" -o output/test.s 2>output/clang_err.txt || {
    echo "[FAIL] Compilation failed:"
    cat output/clang_err.txt
    exit 1
}
echo "       Written: output/test.s"

# Step 2: Detect architecture and select energy model
echo "[2/5] Selecting energy model..."
MODEL="${PROJECT_ROOT}/llvm/energy-models/aarch64.json"
if [ ! -f "$MODEL" ]; then
    echo "  Warning: aarch64.json not found, falling back to legacy model"
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
