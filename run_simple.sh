#!/bin/bash
# Simplified run script for Windows (works in bash)

set -e

# Default test file
TEST_FILE="${1:-examples/simple_test.c}"

if [ ! -f "$TEST_FILE" ]; then
    echo "Error: Test file not found: $TEST_FILE"
    echo "Usage: ./run_simple.sh [source_file.c]"
    exit 1
fi

echo "=== LLVM Energy Estimation (Windows) ==="
echo "Input file: $TEST_FILE"
echo ""

# Create output directory
mkdir -p output

# Step 1: Compile to assembly
echo "[1/3] Compiling to assembly..."
clang -O2 -S "$TEST_FILE" -o output/test.s

# Step 2: Analyze energy consumption
echo "[2/3] Analyzing energy consumption..."
python scripts/simple_energy_analysis.py output/test.s models/energy_model.json output/energy_report.json

# Step 3: Generate HTML visualization
echo "[3/3] Generating HTML report..."
python scripts/visualize.py output/energy_report.json -o output/energy_report.html

echo ""
echo "=== Analysis Complete ==="
echo ""
echo "Results:"
echo "  - JSON report: output/energy_report.json"
echo "  - HTML report: output/energy_report.html"
echo "  - Assembly: output/test.s"
echo ""
echo "To view HTML report: start output/energy_report.html"
echo ""
