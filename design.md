# DESIGN — LLVM Static Energy Estimation Pass

## Approach Overview

This project implements a **compile-time static energy estimator** integrated into LLVM as a `MachineFunctionPass`. It estimates per-function and per-block energy consumption by combining per-instruction energy costs (derived from published ARM microarchitecture data) with static block frequency analysis.

```
Input C source
    │  clang -O2 -target aarch64-linux-gnu -emit-llvm -c
    ▼
LLVM Bitcode (.bc)
    │  llc -stop-after=finalize-isel
    ▼
MIR (.mir)
    │  llc -load EnergyEstimationPass.so -run-pass=energy-estimation
    ▼
MachineFunctionPass
    ├── MachineBlockFrequencyInfo → block frequencies
    ├── TargetInstrInfo::getName() → opcode mnemonic
    └── JSON energy model → pJ cost per instruction
    │
    ├── results.json  (structured energy breakdown)
    └── -Rpass-analysis=energy remarks (per-block + per-function)
                  │
                  ▼
         visualize_energy.py → energy_report.html
```

## Key Design Decisions

### 1. MachineFunctionPass (not IR pass)

**Chosen:** `MachineFunctionPass` operating on `MachineInstr` (post-register-allocation, post-scheduling).

**Why:**
- Machine instructions map 1:1 to real hardware instructions, so per-instruction energy costs from published literature apply directly.
- `MachineBlockFrequencyInfo` provides realistic static execution frequencies accounting for loop trip counts and branch probabilities.

**Rejected alternative — IR-level pass:**
- Cannot distinguish between different instructions that lower to the same IR (e.g., `ADDXri` vs `ADDWri` have different word sizes).

### 2. JSON Energy Model (not hardcoded values)

**Chosen:** External JSON file with opcode-to-energy mappings across instruction categories.

**Why:**
- Decouples the pass logic from the energy data — the same pass can target different architectures by swapping the JSON file.
- Easy to update, extend, or validate without recompiling the C++ pass.

**Schema:**
```json
{
  "arch": "AArch64",
  "unit": "pJ",
  "instructions": {
    "ADD": 2.8,
    "MUL": 6.5,
    "SDIV": 18.0,
    ...
  }
}
```

**Rejected alternative — hardcoded enum values:**
- Requires recompilation for every model change.
- Cannot easily support multiple architectures.

### 3. Static Block Frequency Weighting (not dynamic profiling)

**Chosen:** Use `MachineBlockFrequencyInfo` to scale per-block energy by relative execution frequency.

**How it works:**
```
WeightedEnergy(block) = Σ(InstEnergy) × (BlockFreq / EntryFreq)
```

**Why:**
- Zero runtime overhead — everything happens at compile time.
- Hot loops naturally surface with high `FreqScale` values.

**Rejected alternative — assume each block executes once:**
- Completely misses loop effects — estimates would be off by orders of magnitude for loop-heavy code.

### 4. Python Visualization (not in-C++ HTML generation)

**Chosen:** Separate Python script (`visualize_energy.py`) that reads the JSON output and generates HTML.

**Why:**
- Avoid pulling large dependencies into the LLVM pass.
- Python allows rapid iteration on the visual design without recompiling C++.

## How to Run

```
cd llvm_pipeline
run.bat                           # simple_test.c → report_llvm.html
run01.bat                         # string_proc_test.c → report_string_proc.html
```

Each script compiles the C source to AArch64 bitcode, generates MIR, runs the EnergyEstimationPass, and produces an interactive HTML report — which opens automatically in your browser.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                  EnergyEstimationPass                    │
│                   (MachineFunctionPass)                  │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  doInitialization()                                      │
│    └── Reset AllResults                                  │
│                                                          │
│  runOnMachineFunction(MF)                                │
│    ├── Lazy-init EnergyModel (load JSON on first call)   │
│    ├── Get MBFI + ORE analyses                           │
│    ├── For each MachineBasicBlock:                       │
│    │   ├── Compute blockFreq/entryFreq ratio             │
│    │   ├── For each MachineInstr (skip debug/pseudo):    │
│    │   │   └── Lookup energy: Model->getEnergy(opcode)   │
│    │   ├── Emit BlockEnergy remark                       │
│    │   └── Store BlockResult                             │
│    ├── Emit FunctionEnergy remark                        │
│    └── Store FunctionResult                              │
│                                                          │
│  doFinalization()                                        │
│    └── writeJSON() → results.json                        │
│                                                          │
│  Dependencies:                                           │
│    ├── MachineBlockFrequencyInfo                         │
│    ├── MachineOptimizationRemarkEmitterPass              │
│    └── EnergyModel (JSON loader)                         │
└─────────────────────────────────────────────────────────┘
```
