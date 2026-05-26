# LLVM Static Energy Estimation Pass

[DESIGN](DESIGN.md) · [IMPLEMENTATION](IMPLEMENTATION.md) · [EVALUATION](EVALUATION.md) · [VALIDATION](VALIDATION.md)

A compiler-integrated energy analysis tool built as an LLVM `MachineFunctionPass`. It estimates per-function and per-block energy consumption at compile time by combining per-instruction energy costs (sourced from published ARM microarchitecture data) with static block frequency analysis — no hardware profiler or physical measurement needed.

---

## How It Works

```
your_code.c
    │  clang -O2 -target aarch64-linux-gnu -emit-llvm -c
    ▼
 sample.bc  (LLVM bitcode)
    │  llc -load EnergyEstimationPass.so
    │       -energy-model energy-models/aarch64.json
    │       -energy-output results.json
    │       -Rpass-analysis=energy
    ▼
 EnergyEstimationPass  (MachineFunctionPass)
    ├─ MachineBlockFrequencyInfo  →  blockFreq / entryFreq per block
    ├─ TargetInstrInfo::getName() →  opcode mnemonic per instruction
    └─ JSON model lookup          →  pJ cost per instruction
    │
    ├──▶  results.json        (structured energy breakdown)
    └──▶  remarks to stderr   (-Rpass-analysis=energy)
              │
              │  python visualize_energy.py results.json
              ▼
         energy_report.html  (dark-themed, sortable, heat-map bars)
```

Every machine instruction is looked up in a JSON energy model mapping opcode names to picojoule costs. Each basic block's raw instruction energy is then weighted by its static execution frequency relative to the function entry block, surfacing hot loops automatically.

---

## Quick Start: Full LLVM Pass (Linux/WSL)

```bash
./build.sh                          # build the compiled LLVM pass
./run.sh                            # run on default test (llvm/test/sample.c)
./run.sh examples/simple_test.c     # run on a specific test file
```

---

## Full LLVM Pass (Linux / WSL)

### Prerequisites

- LLVM 14+ with development headers
- CMake 3.16+, Ninja (optional), Python 3.8+

```bash
# Ubuntu / Debian
sudo apt install llvm-14 llvm-14-dev clang-14 cmake ninja-build python3
```

### Build

```bash
cmake -S llvm -B build \
      -DLLVM_DIR=/usr/lib/llvm-14/lib/cmake/llvm \
      -DCMAKE_BUILD_TYPE=Release \
      -G Ninja

cmake --build build --parallel
```

### Run

```bash
# 1. Compile to bitcode
clang -O2 -target aarch64-linux-gnu -emit-llvm -c llvm/test/sample.c -o sample.bc

# 2. Run the pass
llc -load ./build/EnergyEstimationPass.so \
    -energy-estimation \
    -energy-model llvm/energy-models/aarch64.json \
    -energy-output results.json \
    -mtriple aarch64-linux-gnu \
    -Rpass-analysis=energy \
    sample.bc -o sample.s 2>remarks.txt

# 3. Generate HTML report
python3 llvm/visualize_energy.py results.json --output report.html
```

---

## Energy Model

The model lives in `llvm/energy-models/aarch64.json` and targets the **ARM Cortex-A55** at 1800 MHz / 0.8 V. It covers 400+ opcodes across every instruction class:

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

Values are **informed by** published data from Pallister et al. (BEEBS 2013), the ARM Cortex-A55 Software Optimization Guide (ARM-DEN-0060A), and Tiwari et al. (IEEE TVLSI 1994). Note: reference data comes from older process nodes (28–45 nm) and has been scaled to approximate 7 nm — these are heuristic estimates, not validated measurements.

Both canonical assembly mnemonics (`ADD`) and LLVM-internal opcode names (`ADDWri`, `ADDXrs`) are included so the model matches whatever `TargetInstrInfo::getName()` returns.

---

## Optimization Remarks

The pass emits standard LLVM optimization remarks tagged `energy`, visible with:

```bash
-Rpass-analysis=energy              # print to stderr
-fpass-remarks-output=remarks.yaml  # save to YAML file
```

Example output:

```
remark: sample.c:79:5: [energy] BlockEnergy:
  Function=matmul Block=for.body31 RawEnergy=52.5000
  FreqScale=4096.0000 WeightedEnergy=215040.0000 Instructions=18

remark: sample.c:72:1: [energy] FunctionEnergy:
  Function=matmul TotalEnergy=220415.5000
```

The innermost loop of a 16×16×16 matrix multiply runs with a `FreqScale` of 4096 — meaning its energy contribution is 4096× its per-iteration cost. This is exactly what block-frequency weighting surfaces.

---

## Visualization

`llvm/visualize_energy.py` reads the JSON output and generates a self-contained HTML report. Pure Python 3, no pip installs needed.

```bash
python3 llvm/visualize_energy.py results.json \
        --output report.html \
        --title "My Project — AArch64 Cortex-A55"
```

The report includes:
- Sortable function summary table with heat-map bars
- [HIGH] / [MEDIUM] / [LOW] energy category badges
- Collapsible per-function block breakdown
- ASCII summary to stdout

**Real output from `llvm/test/sample.c` (13 functions, 644 instructions):**

```
  Function                          Energy (pJ)   %Total
  matmul                              1,919.50    39.8%   [####################]
  main                                1,285.20    26.7%   [#############-------]
  merge_sort                            824.30    17.1%   [#########-----------]
  dot_product                           252.40     5.2%   [###-----------------]
  fp_ops                                156.80     3.3%   [##------------------]
  fib_recursive                          96.30     2.0%   [#-------------------]
  integer_ops                            70.50     1.5%   [#-------------------]
  ...
  Total: 4,819.20 pJ
```

---

## Project Structure

```
.
├── README.md                       this file — project overview
├── DESIGN.md                       architecture approach and alternatives
├── IMPLEMENTATION.md               LLVM pass internals and build details
├── EVALUATION.md                   metrics, baseline comparison, test cases
├── VALIDATION.md                   cross-check against published literature
├── build.sh                        build the LLVM pass (Linux/WSL)
├── run.sh                          run the energy estimation pipeline
├── run_simple.bat                  Windows quick-run script (no build)
├── run_simple.sh                   Unix quick-run script (no build)
├── run_energy.bat                  redirect to simple pipeline (Windows)
│
├── llvm/                           # main LLVM pass source
│   ├── CMakeLists.txt              outer CMake — find_package(LLVM)
│   ├── PROGRESS.md                 completion status and bug log
│   ├── visualize_energy.py         HTML + ASCII report generator
│   ├── energy-models/
│   │   ├── aarch64.json            ARM Cortex-A55 model — 624 opcodes
│   │   └── x86_64.json            x86-64 model (experimental)
│   ├── test/
│   │   ├── sample.c                14-function comprehensive test
│   │   └── run_test.sh             end-to-end Linux/WSL pipeline script
│   └── lib/
│       ├── Analysis/
│       │   ├── EnergyModel.h       JSON model loader header
│       │   ├── EnergyModel.cpp     JSON loader implementation
│       │   └── CMakeLists.txt
│       └── CodeGen/
│           ├── EnergyEstimation.cpp  MachineFunctionPass (417 lines)
│           └── CMakeLists.txt
│
├── examples/                       # test case source files
│   ├── simple_test.c               13-function comprehensive test
│   ├── fp_compute.c                FP-heavy test (4 functions)
│   ├── matrix_multiply.c           Matrix multiply (2 implementations)
│   └── test.c                      5-function basic test
│
├── scripts/                        # Python analysis and validation tools
│   ├── simple_energy_analysis.py   assembly parser (simple pipeline)
│   ├── convert_results.py          format converter
│   ├── validate_model.py           automated cross-check against literature
│   └── visualize.py                legacy HTML report generator
│
├── models/
│   └── energy_model.json           legacy 28 nm model (~60 opcodes)
└── output/                         generated reports (after running)
```

**Total: 36+ test functions across 5 test files · 624 opcodes in energy model · 3,100+ lines of C++/Python**

---

> **⚠️ IMPORTANT DISCLAIMER:** This tool produces **static heuristic energy estimates** — not measured values. The energy model is **informed by** published academic data but has **not been validated against physical hardware measurements**. All numerical outputs should be treated as **relative guidance** (function A costs more than function B) rather than absolute predictions.

## Known Limitations

| Limitation | Effect |
|---|---|
| Static frequency only | Estimates can be ±30% off on branch-heavy code vs. actual execution |
| L1 cache hit ALWAYS assumed | Cache misses can cost 3–25× more — the #1 source of underestimation |
| No operand switching activity | Likely underestimates data-dependent ALU energy by ~10% |
| No pipeline / IPC modelling | May overcount on superscalar paths where instructions execute in parallel |
| No hardware validation | All claims are heuristic — see VALIDATION.md for full caveats |

---

## Additional Documentation

| Document | Contents |
|---|---|
| [DESIGN.md](DESIGN.md) | Architecture approach, key design decisions, alternatives considered |
| [IMPLEMENTATION.md](IMPLEMENTATION.md) | LLVM pass internals, file structure, build system, energy model schema |
| [EVALUATION.md](EVALUATION.md) | Metrics, baseline comparison, test case results, validation |
| [VALIDATION.md](VALIDATION.md) | Detailed cross-check against published literature |

---

## References

1. ARM Ltd. — *Cortex-A55 Software Optimization Guide*, ARM-DEN-0060A Rev 3, 2019
2. Pallister et al. — *BEEBS: Open Benchmarks for Energy Measurements on Embedded Platforms*, arXiv:1308.5174, 2013
3. Tiwari et al. — *Power analysis of embedded software: A first step towards software power minimization*, IEEE TVLSI, 1994
4. Kerrison & Eder — *Energy modeling of software for a hardware multithreaded embedded microprocessor*, ACM TECS, 2015
5. Abdelhadi & Bhattacharyya — *Energy modeling for superscalar processors*, ACM TECS, 2016
