# DESIGN — LLVM Static Energy Estimation Pass

## Approach Overview

This project implements a **compile-time static energy estimator** integrated into LLVM as a `MachineFunctionPass`. It estimates per-function and per-block energy consumption by combining per-instruction energy costs (derived from published ARM microarchitecture data) with static block frequency analysis.

```
Input C source
    │  clang -O2 -target aarch64-linux-gnu -emit-llvm -c
    ▼
LLVM Bitcode (.bc)
    │  llc -load EnergyEstimationPass.so
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
- LLVM IR instructions (e.g., `getelementptr`, `load`, `add`) are abstract and may be lowered into multiple machine instructions, making energy attribution ambiguous.
- `MachineBlockFrequencyInfo` provides realistic static execution frequencies accounting for loop trip counts and branch probabilities.

**Rejected alternative — IR-level pass:**
- Simpler to implement (no LLVM CodeGen dependency).
- Cannot distinguish between different instructions that lower to the same IR (e.g., `ADDXri` vs `ADDWri` have different word sizes and thus different energy costs).
- Lacks access to machine-level frequency information.

### 2. JSON Energy Model (not hardcoded values)

**Chosen:** External JSON file with 624 opcode-to-energy mappings across 12 instruction categories.

**Why:**
- Decouples the pass logic from the energy data — the same pass can target different architectures by swapping the JSON file.
- Easy to update, extend, or validate without recompiling the C++ pass.
- The JSON can be automatically generated or cross-checked by Python scripts.

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
- Faster lookup (compile-time constant).
- Requires recompilation for every model change.
- Cannot easily support multiple architectures.

**Rejected alternative — LLVM TableGen backend:**
- Tighter integration with LLVM's instruction definitions.
- More complex build system dependency.
- No advantage over JSON for a research/educational project.

### 3. Static Block Frequency Weighting (not dynamic profiling)

**Chosen:** Use `MachineBlockFrequencyInfo` to scale per-block energy by relative execution frequency.

**How it works:**
```
WeightedEnergy(block) = Σ(InstEnergy) × (BlockFreq / EntryFreq)
```

`BlockFreq` is the estimated execution count of the basic block; `EntryFreq` is the function's entry frequency. This ratio gives the number of times the block executes relative to a single function call.

**Why:**
- Zero runtime overhead — everything happens at compile time.
- Hot loops naturally surface with high `FreqScale` values (e.g., `4096×` for a 16×16×16 matrix multiply inner loop).
- Cold paths (rarely executed error handlers) correctly contribute negligible energy.

**Rejected alternative — dynamic profiling (PGO):**
- Requires instrumented builds and representative training inputs.
- More accurate for production use.
- Out of scope for a static analysis tool.

**Rejected alternative — assume each block executes once:**
- Simple but completely misses loop effects — energy estimates would be off by orders of magnitude for loop-heavy code.

### 4. Python Visualization (not in-C++ HTML generation)

**Chosen:** Separate Python script (`visualize_energy.py`) that reads the JSON output and generates HTML.

**Why:**
- Avoid pulling large dependencies (e.g., a JSON-to-HTML library) into the LLVM pass.
- Python allows rapid iteration on the visual design without recompiling C++.
- The JSON output is machine-readable, so users can build their own tooling.

### 5. Opcode Name Resolution

LLVM's `TargetInstrInfo::getName()` returns the LLVM-internal opcode name (e.g., `ADDWri`, `ADDXrs`), which may differ from the assembly mnemonic (`ADD`).

**Approach:**
- The JSON model includes both canonical mnemonics (`ADD`) and LLVM-internal names (`ADDWri`, `ADDXrs`, `ADDv16i8`).
- Lookup tries the exact name first, falls back to a category default if not found.
- This ensures the model works regardless of which name format `getName()` returns.

## Alternatives Not Yet Explored

| Alternative | Potential Benefit | Complexity |
|---|---|---|
| **Cache miss modelling** | Would fix the #1 source of underestimation | High — requires data flow analysis |
| **Pipeline/IPC simulation** | More accurate for superscalar architectures | Very high — essentially a full microarch simulator |
| **Machine learning model** | Could learn from real measurements | Requires large labelled dataset |
| **Dynamic voltage/frequency scaling** | Models power management states | Moderate — requires OS interface data |
| **Multi-architecture support** | Broadens applicability | Moderate — need models for x86, RISC-V |

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
