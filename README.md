# LLVM Energy Estimation - Windows Edition

A simplified energy estimation tool for Windows that analyzes compiled assembly code to estimate per-function energy consumption.

## 🚀 Quick Start

```bash
# Run analysis on example file
bash run_simple.bat examples/simple_test.c

# Analyze your own code
bash run_simple.bat path/to/your/code.c

# View results
start output/energy_report.html
```

## 📋 Requirements

- **Clang** (LLVM compiler) - Already installed ✅
- **Python 3.x** - Already installed ✅

## 📖 Documentation

- **[QUICKSTART_WINDOWS.md](QUICKSTART_WINDOWS.md)** - Quick reference guide
- **[WINDOWS_GUIDE.md](WINDOWS_GUIDE.md)** - Detailed documentation
- **[VALIDATION.md](VALIDATION.md)** - Energy model validation and references

## 🎯 What This Does

Analyzes compiled code to estimate energy consumption based on:
- Per-instruction energy costs (from ARM Cortex-A53 research)
- Instruction type classification (ALU, multiply, divide, memory, FP, branches)
- Static analysis of generated machine code

## 📊 Example Output

```
Total Functions: 5
Total Energy: 1.89 nJ
Total Instructions: 169

Top Energy Consumers:
1. factorial        - 688.30 pJ (63 instructions)
2. count_evens      - 493.40 pJ (45 instructions)  
3. sum_array        - 471.90 pJ (43 instructions)
```

## 📁 Project Structure

```
llvm/
├── run_simple.bat              # Main script to run analysis
├── examples/                   # Test C files
│   ├── simple_test.c          # Basic test (no stdlib)
│   ├── test.c                 # Full test with stdio
│   ├── fp_compute.c           # Floating-point operations
│   └── matrix_multiply.c      # Matrix operations
├── scripts/
│   ├── simple_energy_analysis.py  # Assembly analyzer
│   └── visualize.py               # HTML report generator
├── models/
│   └── energy_model.json      # Energy costs per instruction
└── output/                    # Generated reports (created on first run)
```

## ⚡ Energy Costs Reference

| Operation | Energy (pJ) |
|-----------|-------------|
| Integer ALU | 10.5 |
| Integer multiply | 28.3 |
| Integer divide | 85.7 |
| Memory load | 45.2 |
| Memory store | 52.8 |
| FP operations | 35.6 - 156.8 |
| Branch | 15.4 |

## 🔍 How It Works

1. **Compile** - Clang compiles your C code to assembly
2. **Analyze** - Python script parses assembly and classifies instructions
3. **Estimate** - Each instruction is assigned an energy cost
4. **Report** - JSON and HTML reports show per-function breakdown

## ⚠️ Limitations

- **Static analysis only** - No runtime profiling or frequency weighting
- **Cache assumptions** - Assumes L1 cache hits (actual misses cost 3-25× more)
- **Architecture-specific** - Energy model based on ARM Cortex-A53
- **No pipeline modeling** - Doesn't account for instruction-level parallelism

## 📚 References

Energy values based on:
- Nunez-Yanez, J. (2017). "Energy measurement and modeling of ARM Cortex-A processors." IEEE Transactions on Computers, 66(3), 471-484.

## 💡 About This Version

This is a **simplified Windows version** that works with just Clang and Python. The original project requires full LLVM development libraries to build a custom compiler pass, which aren't available in standard Windows LLVM installations.

**What's different:**
- ✅ No build step required
- ✅ Works with standard Windows LLVM installation
- ✅ Pure Python analysis of assembly code
- ❌ No execution frequency weighting (treats all instructions equally)
- ❌ No integration with LLVM optimization pipeline

For the full version with frequency weighting, you would need to build LLVM from source or use WSL (Windows Subsystem for Linux).

## 🤝 Contributing

To extend this tool:
- Add new energy models in `models/` for different architectures
- Improve instruction classification in `simple_energy_analysis.py`
- Enhance HTML visualization in `visualize.py`

## 📄 License

Educational and research use.
