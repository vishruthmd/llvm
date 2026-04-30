# LLVM Energy Estimation - Windows Guide

## Overview

This is a simplified version of the LLVM Energy Estimation Pass adapted for Windows systems where only Clang is available (without full LLVM development libraries).

## What This Does

Analyzes compiled assembly code to estimate energy consumption based on:
- Per-instruction energy costs (from ARM Cortex-A53 research)
- Instruction type classification (ALU, multiply, divide, memory, FP, branches)
- Static analysis of generated machine code

## Requirements

- **Clang** (already installed at `C:\Program Files\LLVM\bin\clang.exe`)
- **Python 3.x** (already installed - Python 3.10.0)

## How to Run

### Quick Start

```bash
# Run analysis on the example file
bash run_simple.bat examples/simple_test.c
```

Or step by step:

```bash
# 1. Compile your C code to assembly
clang -O2 -S examples/simple_test.c -o output/test.s

# 2. Analyze energy consumption
python scripts/simple_energy_analysis.py output/test.s models/energy_model.json output/energy_report.json

# 3. Generate HTML report
python scripts/visualize.py output/energy_report.json -o output/energy_report.html

# 4. View the report
start output/energy_report.html
```

### Analyze Your Own Code

```bash
bash run_simple.bat path/to/your/file.c
```

## Output Files

After running the analysis, you'll find:

- `output/energy_report.json` - Detailed JSON report with per-function energy breakdown
- `output/energy_report.html` - Interactive HTML visualization
- `output/test.s` - Generated assembly code
- `output/test.ll` - LLVM IR (intermediate representation)

## Understanding the Results

### Energy Values (in picojoules)

- **Integer ALU** (add, sub, and, or): 10.5 pJ
- **Integer multiply**: 28.3 pJ
- **Integer divide**: 85.7 pJ (most expensive integer op)
- **Memory load**: 45.2 pJ
- **Memory store**: 52.8 pJ
- **FP operations**: 35.6 - 156.8 pJ
- **Branches**: 15.4 pJ

### Example Output

```
Total functions analyzed: 5
Total instructions: 169
Total estimated energy: 1888.90 pJ

Per-function breakdown:
Function                       Instructions    Energy (pJ)     Avg/Instr      
---------------------------------------------------------------------------
factorial                      63              688.30          10.93          
count_evens                    45              493.40          10.96          
sum_array                      43              471.90          10.97          
compute_sum                    11              140.10          12.74          
divide_loop                    7               95.20           13.60
```

## Differences from Full LLVM Pass Version

**This simplified version:**
- ✅ Works on Windows with just Clang installed
- ✅ Analyzes assembly code and estimates energy
- ✅ Generates JSON and HTML reports
- ❌ Does NOT use execution frequency weighting (assumes all instructions execute once)
- ❌ Does NOT integrate with LLVM's optimization pipeline
- ❌ Does NOT emit compiler remarks during compilation

**The full version (requires LLVM dev libraries):**
- Uses LLVM's MachineBlockFrequencyInfo for accurate frequency weighting
- Integrates as a proper LLVM pass
- Emits optimization remarks tied to source locations

## Limitations

- **Static analysis only**: Cannot account for runtime behavior or input-dependent execution
- **No frequency weighting**: Treats all instructions equally (loops not weighted by iteration count)
- **Cache assumptions**: Assumes L1 cache hits (actual cache misses increase energy 3-25×)
- **Architecture-specific**: Energy model based on ARM Cortex-A53 research
- **No pipeline modeling**: Doesn't account for instruction-level parallelism or stalls

## Example Functions

The `examples/simple_test.c` file demonstrates different instruction types:

1. **compute_sum**: Simple ALU operations in a loop
2. **sum_array**: Memory loads + ALU operations
3. **factorial**: Multiplication-heavy (higher energy)
4. **divide_loop**: Division operations (highest integer energy)
5. **count_evens**: Conditional branches and modulo operations

## Troubleshooting

### "stdio.h not found"
Use the simplified test file without standard library includes:
```bash
bash run_simple.bat examples/simple_test.c
```

### Python not found
Install Python 3.x from python.org

### Clang not found
Add `C:\Program Files\LLVM\bin` to your PATH environment variable

## References

Energy values based on:
- Nunez-Yanez, J. (2017). "Energy measurement and modeling of ARM Cortex-A processors." IEEE Transactions on Computers, 66(3), 471-484.

## Next Steps

To use the full LLVM pass version with frequency weighting:
1. Install LLVM development libraries (llvm-dev package)
2. Use CMake to build the custom pass
3. Run with `llc -load=build/lib/EnergyPass.so`

For Windows, this typically requires building LLVM from source or using WSL (Windows Subsystem for Linux).
