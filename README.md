# LLVM Static Energy Estimation Pass

[design](design.md) · [implementation](implementation.md) · [evaluation](evaluation.md) · [validation](validation.md)

A compiler-integrated energy analysis tool built as an LLVM `MachineFunctionPass`. It estimates per-function and per-block energy consumption at compile time by combining per-instruction energy costs (sourced from published ARM microarchitecture data) with static block frequency analysis — no hardware profiler or physical measurement needed.

---

## How It Works

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

From **cmd.exe**:
```
cd llvm_pipeline
run.bat                           # runs simple_test.c (default)
run01.bat                         # runs string_proc_test.c
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
