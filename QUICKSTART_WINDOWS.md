# Quick Start Guide - Windows

## ✅ Setup Complete!

Your LLVM Energy Estimation tool is ready to use on Windows.

## How to Run

### Option 1: Use the batch script (easiest)
```bash
bash run_simple.bat examples/simple_test.c
```

### Option 2: Analyze your own C files
```bash
bash run_simple.bat path/to/your/code.c
```

### Option 3: Manual steps
```bash
# Compile to assembly
clang -O2 -S your_code.c -o output/code.s

# Analyze energy
python scripts/simple_energy_analysis.py output/code.s models/energy_model.json output/energy_report.json

# Generate HTML report
python scripts/visualize.py output/energy_report.json -o output/energy_report.html

# View report
start output/energy_report.html
```

## Example Results

From the test run on `examples/simple_test.c`:

```
Total Functions: 5
Total Energy: 1.89 nJ (1888.90 pJ)
Total Instructions: 169

Top Energy Consumers:
1. factorial        - 688.30 pJ (63 instructions)
2. count_evens      - 493.40 pJ (45 instructions)  
3. sum_array        - 471.90 pJ (43 instructions)
4. compute_sum      - 140.10 pJ (11 instructions)
5. divide_loop      -  95.20 pJ (7 instructions)
```

## Output Files

After running analysis, check the `output/` directory:
- `energy_report.json` - Detailed JSON data
- `energy_report.html` - Interactive visualization (open in browser)
- `test.s` - Generated assembly code
- `test.ll` - LLVM intermediate representation

## Energy Costs Reference

| Operation | Energy (pJ) |
|-----------|-------------|
| Integer ALU (add, sub, and, or) | 10.5 |
| Integer multiply | 28.3 |
| Integer divide | 85.7 |
| Memory load | 45.2 |
| Memory store | 52.8 |
| FP add/sub | 35.6 |
| FP multiply | 48.9 |
| FP divide | 124.5 |
| FP sqrt | 156.8 |
| Branch | 15.4 |

## What This Tool Does

✅ Analyzes compiled assembly code
✅ Estimates energy per instruction
✅ Identifies energy hotspots
✅ Generates JSON and HTML reports
✅ Works on Windows with just Clang + Python

## Limitations

⚠️ Static analysis only (no runtime profiling)
⚠️ No execution frequency weighting
⚠️ Assumes L1 cache hits
⚠️ Based on ARM Cortex-A53 energy model

## Need Help?

- See `WINDOWS_GUIDE.md` for detailed documentation
- Check `README.md` for background information
- Example files in `examples/` directory

## View Your Results

```bash
start output/energy_report.html
```

---

**Note**: This is a simplified version for Windows. The full LLVM pass version (with frequency weighting) requires LLVM development libraries, which aren't available in your current setup.
