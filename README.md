# LLVM Static Energy Estimation Pass

[design](design.md) · [implementation](implementation.md) · [evaluation](evaluation.md) · [validation](validation.md)

A compiler-integrated energy analysis tool built as an LLVM `MachineFunctionPass`. It estimates per-function and per-block energy consumption at compile time by combining per-instruction energy costs (sourced from published ARM microarchitecture data) with static block frequency analysis — no hardware profiler or physical measurement needed.

---

## How It Works

### Simple Pipeline (Python-based — works on any OS)

```
your_code.c
    │  gcc/clang -O2 -S
    ▼
 test.s  (assembly)
    │  simple_energy_analysis.py
    │       ↕ lookup in JSON energy model
    ▼
 energy_results_raw.json
    │  convert_results.py
    ▼
 energy_results.json
    │  visualize_energy.py
    ▼
 energy_report.html  (dark-themed, sortable, heat-map bars)
```

### Full LLVM Pass (Linux/WSL only — requires LLVM 14+ dev libraries)

```
your_code.c
    │  clang -O2 -target aarch64-linux-gnu -emit-llvm -c
    ▼
 sample.bc  (LLVM bitcode)
    │  llc -load EnergyEstimationPass.so
    ▼
 EnergyEstimationPass  (MachineFunctionPass)
    ├─ MachineBlockFrequencyInfo  →  blockFreq / entryFreq per block
    ├─ TargetInstrInfo::getName() →  opcode mnemonic per instruction
    └─ JSON model lookup          →  pJ cost per instruction
    │
    ├──▶  results.json        (structured energy breakdown)
    └──▶  report_llvm.html    (interactive HTML report)
```

Every machine instruction is looked up in a JSON energy model mapping opcode names to picojoule costs. Each basic block's raw instruction energy is then weighted by its static execution frequency relative to the function entry block, surfacing hot loops automatically.

---

## Quick Start

### Windows (Git Bash) — No LLVM dev libraries needed

```bash
bash bin/run_simple.sh examples/simple_test.c                # run default test
bash bin/run_simple.sh examples/matrix_multiply.c             # run specific test
start output/energy_report.html                               # open report
```

> The script auto-detects whether `clang` or `gcc` is available and picks the right energy model (x86-64 or AArch64) based on the compiled assembly.

### Linux / WSL — Full LLVM Pass

From **cmd.exe**:
```
cd llvm_pipeline
run.bat                           # runs simple_test.c (default)
run01.bat                         # runs string_proc_test.c

---

## Simple Pipeline (Windows / Git Bash)

> **No LLVM development libraries needed.** Works on any system with a C compiler and Python 3.

### Prerequisites

- **A C compiler**: `gcc` or `clang`
- **Python 3.8+**

### Try it

```bash
bash bin/run_simple.sh examples/simple_test.c
```

This runs the full pipeline in one command:
1. Compiles C to assembly (`gcc -O2 -S`)
2. Auto-detects architecture (x86-64 or AArch64)
3. Selects the matching energy model
4. Parses assembly and looks up per-instruction energy costs
5. Generates an interactive HTML report

### One Step at a Time (for explaining the process)

```bash
# Step 1: Compile C to assembly
gcc -O2 -g -S examples/simple_test.c -o output/test.s

# Step 2: Analyze energy
python scripts/simple_energy_analysis.py output/test.s llvm/energy-models/x86_64.json output/energy_results_raw.json

# Step 3: Convert to standard format
python scripts/convert_results.py output/energy_results_raw.json output/energy_results.json

# Step 4: Generate HTML report
python llvm/visualize_energy.py output/energy_results.json --output output/energy_report.html

# Step 5: Open the report
start output/energy_report.html
```

### Test Files

| File | Functions | What It Exercises |
|------|-----------|-------------------|
| `examples/simple_test.c` | 15 | Integer ops, FP, sorting, recursion, matrix multiply |
| `examples/fp_compute.c` | 5 | Floating-point: dot product, FDIV-heavy harmonic mean |
| `examples/matrix_multiply.c` | 3 | Standard vs. optimized matrix multiply comparison |
| `llvm/test/sample.c` | 14 | Full comprehensive test suite |

> **Note:** The script auto-detects which compiler is available (`clang` preferred, `gcc` fallback) and selects the correct energy model based on the compiled assembly architecture.

---

## Full LLVM Pass (Linux / WSL)

> ⚠️ **Requires LLVM 14+ development libraries.** Not available on vanilla Windows.

### Prerequisites

- LLVM 14+ with development headers
- CMake 3.16+, Ninja (optional), Python 3.8+

```bash
# Ubuntu / Debian
sudo apt install llvm-14 llvm-14-dev clang-14 cmake ninja-build python3
```

Output: `llvm_pipeline\output\report_llvm.html` (or `report_string_proc.html`)

Inline usage:
```
C:\Users\Karan\Desktop\llvm\llvm\llvm_pipeline\run.bat
```

> Requires the compiled LLVM pass (`build/`). To rebuild:
> ```
> cmake -S llvm -B build -DLLVM_DIR=/usr/lib/llvm-14/lib/cmake/llvm -DCMAKE_BUILD_TYPE=Release -G Ninja
> cmake --build build --parallel
> ```

---

## Project Structure

```
.
├── simple_test.c                  ← 15 functions (integer, FP, matmul, sort, etc.)
├── string_proc_test.c             ← 6 string processing functions (palindrome, cipher, etc.)
│
├── llvm_pipeline/                 ← Batch pipeline scripts
│   ├── run.bat                    ← runs simple_test.c → report_llvm.html
│   ├── run01.bat                  ← runs string_proc_test.c → report_string_proc.html
│   └── output/                    ← Generated HTML reports + JSON
│
├── llvm/                          ← LLVM pass source + build
│   ├── energy-models/
│   │   └── aarch64.json           ← ARM Cortex-A55 model (300+ opcodes)
│   ├── build/                     ← Compiled LLVM pass
│   ├── visualize_energy.py        ← HTML report generator
│   ├── include/llvm/Analysis/
│   │   └── EnergyModel.h
│   └── lib/
│       ├── Analysis/
│       │   ├── EnergyModel.cpp    ← JSON model loader
│       │   └── CMakeLists.txt
│       └── CodeGen/
│           ├── EnergyEstimation.cpp ← MachineFunctionPass
│           └── CMakeLists.txt
│
├── README.md                      ← This file
├── design.md                      ← Architecture & design decisions
├── implementation.md              ← Pass internals & build system
├── evaluation.md                  ← Metrics, test cases, baseline
└── validation.md                  ← Cross-check against published literature
```

---

## Energy Model

The model (`llvm/energy-models/aarch64.json`) targets the **ARM Cortex-A55** at 1800 MHz / 0.8 V. It covers 300+ opcodes:

| Category | Examples | Range |
|---|---|---|
| Integer ALU | `ADD`, `SUB`, `AND`, `LSL` | 2–4 pJ |
| Multiply / MAC | `MUL`, `MADD`, `SMULL` | 6–10 pJ |
| Divide | `SDIV`, `UDIV` | 16–22 pJ |
| Load (L1 hit) | `LDR`, `LDP`, `LDRSW` | 9–15 pJ |
| Store | `STR`, `STP`, `STLR` | 7–13 pJ |
| Branch | `B`, `BL`, `CBZ`, `Bcc` | 2–5 pJ |
| Float scalar | `FADD`, `FMUL`, `FDIV`, `FMADD` | 4–34 pJ |
| NEON / SIMD | `FADDv4f32`, `FMLAv2f64` | 9–120 pJ |
| Crypto | `AESErr`, `SHA256Hrrr` | 12–15 pJ |

Values are **informed by** published data from the ARM Cortex-A55 Software Optimization Guide (ARM-DEN-0060A), Pallister et al. (BEEBS 2013), Tiwari et al. (IEEE TVLSI 1994), and others. See [validation.md](validation.md) for the full cross-check.

---

## Sample Results

When run against `simple_test.c` (17 functions, 1,210 instructions):
`llvm/visualize_energy.py` reads the JSON output and generates a self-contained HTML report. Pure Python 3, no pip installs needed.

```bash
# Linux / macOS
python3 llvm/visualize_energy.py results.json --output report.html

# Windows (Git Bash)
python llvm/visualize_energy.py output/energy_results.json --output output/energy_report.html
start output/energy_report.html    # open in browser
```

The report includes:
- Sortable function summary table with heat-map bars
- [HIGH] / [MEDIUM] / [LOW] energy category badges
- Collapsible per-function block breakdown
- ASCII summary to stdout

**Real output from `llvm/test/sample.c` (13 functions, 644 instructions):**

```
  Function                          Energy (pJ)   %Total
  mat_multiply                      101,010.96    61.8%   [####################]
  main                               46,576.08    28.5%   [#############-------]
  bubble_sort                        10,364.13     6.3%   [####----------------]
  crc32                               1,196.92     0.7%   [--------------------]
  merge_sort                          1,025.56     0.6%   [--------------------]
  factorial                             682.69     0.4%   [--------------------]
  sum_array                             583.16     0.4%   [--------------------]
  ...
  Total: 163,438.22 pJ
```

---

## Limitations
## Project Structure

```
.
├── README.md                       project overview
├── design.md                       architecture & design
├── implementation.md               pass internals & build
├── evaluation.md                   metrics & baseline
├── validation.md                   literature cross-check
├── bin/
│   ├── build.sh                    build LLVM pass (Linux)
│   ├── run.sh                      run LLVM pipeline (Linux)
│   ├── run_simple.bat              quick-run script (CMD)
│   ├── run_simple.sh               quick-run script (Bash)
│   └── run_energy.bat              redirect to simple (CMD)
│
├── llvm/                           LLVM pass source code
│   ├── CMakeLists.txt              outer CMake config
│   ├── progress.md                 completion status
│   ├── visualize_energy.py         HTML report generator
│   ├── energy-models/
│   │   ├── aarch64.json            ARM Cortex-A55 model
│   │   └── x86_64.json            x86-64 model (experimental)
│   ├── test/
│   │   ├── sample.c                14-function test suite
│   │   └── run_test.sh             pipeline test script
│   └── lib/
│       ├── Analysis/
│       │   ├── EnergyModel.h       model loader header
│       │   ├── EnergyModel.cpp     model loader impl
│       │   └── CMakeLists.txt
│       └── CodeGen/
│           ├── EnergyEstimation.cpp  MachineFunctionPass
│           └── CMakeLists.txt
│
├── examples/                       test C source files
│   ├── simple_test.c               15-function test
│   ├── fp_compute.c                FP-heavy test
│   ├── matrix_multiply.c           matrix multiply test
│   └── test.c                      5-function basic test
│
├── scripts/                        Python analysis tools
│   ├── simple_energy_analysis.py   assembly parser
│   ├── convert_results.py          format converter
│   ├── validate_model.py           cross-check validator
│   └── visualize.py                legacy HTML generator
│
├── models/
│   └── energy_model.json           legacy 28nm model
└── output/                         generated reports
```

---

> **⚠️ IMPORTANT DISCLAIMER:** This tool produces **static heuristic energy estimates** — not measured values. The energy model is **informed by** published academic data but has **not been validated against physical hardware measurements**. All numerical outputs should be treated as **relative guidance** (function A costs more than function B) rather than absolute predictions.

## Known Limitations

| Limitation | Effect |
|---|---|
| Static frequency only | Estimates can be ±30% off on branch-heavy code |
| L1 cache hit ALWAYS assumed | Cache misses cost 3–25× more — #1 source of underestimation |
| No operand switching activity | Likely underestimates data-dependent ALU energy by ~10% |
| No pipeline / IPC modelling | May overcount on superscalar paths |
| No hardware validation | All claims are heuristic — see [validation.md](validation.md) |

---

## Additional Documentation

| Document | Contents |
|---|---|
| [design.md](design.md) | Architecture approach, key design decisions, alternatives considered |
| [implementation.md](implementation.md) | LLVM pass internals, file structure, build system, energy model schema |
| [evaluation.md](evaluation.md) | Metrics, baseline comparison, test case results, validation |
| [validation.md](validation.md) | Detailed cross-check against published literature |

---

## References

1. ARM Ltd. — *Cortex-A55 Software Optimization Guide*, ARM-DEN-0060A Rev 3, 2019
2. Pallister et al. — *BEEBS: Open Benchmarks for Energy Measurements on Embedded Platforms*, arXiv:1308.5174, 2013
3. Tiwari et al. — *Power analysis of embedded software: A first step towards software power minimization*, IEEE TVLSI, 1994
4. Kerrison & Eder — *Energy modeling of software for a hardware multithreaded embedded microprocessor*, ACM TECS, 2015
5. Nunez-Yanez — *Energy measurement and modeling of ARM Cortex-A processors*, IEEE TC, 2017
