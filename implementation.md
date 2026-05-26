# IMPLEMENTATION — LLVM Static Energy Estimation Pass

## File Structure

```
llvm/
├── CMakeLists.txt                          # Outer CMake — find_package(LLVM)
├── include/llvm/Analysis/
│   └── EnergyModel.h                       # EnergyModel class declaration
├── lib/
│   ├── Analysis/
│   │   ├── EnergyModel.cpp                 # JSON model loader implementation
│   │   └── CMakeLists.txt                  # Builds libEnergyModel
│   └── CodeGen/
│       ├── EnergyEstimation.cpp            # MachineFunctionPass (417 lines)
│       └── CMakeLists.txt                  # Builds EnergyEstimationPass.so
├── energy-models/
│   └── aarch64.json                        # ARM Cortex-A55 model (624 opcodes)
├── visualize_energy.py                     # HTML + ASCII report generator
└── test/
    ├── sample.c                            # 12-function comprehensive test
    └── run_test.sh                         # End-to-end pipeline script
```

## Core Classes

### EnergyModel (`EnergyModel.h` / `EnergyModel.cpp`)

```cpp
class EnergyModel {
    StringMap<double> EnergyMap;  // opcode → energy (pJ); StringMap owns keys
    std::string Arch;             // target architecture from JSON
    std::string Unit;             // energy unit from JSON (e.g. "pJ")
    bool Loaded = false;          // true if successfully parsed

public:
    explicit EnergyModel(StringRef Path);
    double getEnergy(StringRef Opcode) const;
    bool isLoaded() const;
    size_t size() const;
    StringRef getArch() const;
    StringRef getUnit() const;
};
```

**Key implementation details:**
- Uses `MemoryBuffer::getFile()` for efficient file I/O.
- Parses JSON using `llvm::json::parse()` (LLVM's built-in JSON parser — no external dependency).
- Uses `StringMap<double>` instead of `DenseMap<StringRef, double>` to avoid dangling key references when the JSON `json::Object` goes out of scope.
- Returns `0.0` for unknown opcodes (safe default — the instruction contributes nothing to energy).

### EnergyEstimationPass (`EnergyEstimation.cpp`)

```cpp
class EnergyEstimationPass : public MachineFunctionPass {
    std::unique_ptr<EnergyModel> Model;     // Lazy-initialized
    std::vector<FunctionResult> AllResults; // Accumulated for JSON output

public:
    // CLI flags
    static cl::opt<std::string> ModelPath;  // -energy-model=<path>
    static cl::opt<std::string> OutputPath;  // -energy-output=<path>
};
```

## Pass Pipeline

### 1. `doInitialization(Module &M)`
- Resets `AllResults` vector.
- Called once per module before any function is processed.
- Returns `false` (analysis pass — does not modify).

### 2. `runOnMachineFunction(MachineFunction &MF)`

**Step-by-step:**

1. **Lazy model initialization** (first call only):
   - Creates `EnergyModel` from the `-energy-model` path.
   - Prints debug info if `LLVM_DEBUG` is enabled.

2. **Acquire analyses:**
   - `MachineBlockFrequencyInfo &MBFI` — for block frequency data.
   - `MachineOptimizationRemarkEmitter &ORE` — for remark emission.

3. **Get entry frequency:**
   - `MBFI.getEntryFreq()` — the frequency of the function's entry block.
   - Used as the normalization denominator (guarded against zero).

4. **For each basic block:**
   - Compute `FreqScale = blockFreq / entryFreq`.
   - For each machine instruction:
     - Skip debug instructions (`isDebugInstr()`).
     - Skip implicit defs (`isImplicitDef()`).
     - Get opcode name: `Subtarget.getInstrInfo()->getName(opcode)`.
     - Look up energy: `Model->getEnergy(opcodeName)`.
     - Accumulate `RawBlockEnergy += instEnergy`.
   - Compute `WeightedBlockEnergy = RawBlockEnergy × FreqScale`.
   - Emit `BlockEnergy` remark with fields: Function, Block, RawEnergy, FreqScale, WeightedEnergy, Instructions.
   - Optionally store `BlockResult` for JSON output.

5. **Emit `FunctionEnergy` remark** with total energy for the function.

6. **Store `FunctionResult`** (only if `-energy-output` is specified).

### 3. `doFinalization(Module &M)`
- If `-energy-output` was specified and results exist, calls `writeJSON()`.
- Serializes `AllResults` to the output file.

## JSON Output Schema

```json
{
  "arch": "AArch64",
  "unit": "pJ",
  "functions": [
    {
      "name": "matmul",
      "total_energy_pJ": 2127.90,
      "blocks": [
        {
          "name": "for.body31",
          "raw_energy_pJ": 52.50,
          "freq_scale": 4096.00,
          "weighted_energy_pJ": 215040.00,
          "instructions": 18
        }
      ]
    }
  ]
}
```

## Optimization Remarks

The pass emits standard LLVM optimization remarks tagged with `PassName = "energy"`:

```bash
-Rpass-analysis=energy              # print to stderr
-fpass-remarks-output=remarks.yaml  # save to YAML file
```

**Per-block remark:**
```
remark: sample.c:79:5: [energy] BlockEnergy:
  Function=matmul Block=for.body31 RawEnergy=52.5000
  FreqScale=4096.0000 WeightedEnergy=215040.0000 Instructions=18
```

**Per-function remark:**
```
remark: sample.c:72:1: [energy] FunctionEnergy:
  Function=matmul TotalEnergy=220415.5000
```

Remarks are anchored to `DiagnosticLocation` derived from the first real instruction's `DebugLoc` in each block, enabling source-level annotation when compiled with `-g`.

## Build System

### CMake Configuration (`llvm/CMakeLists.txt`)

```cmake
cmake_minimum_required(VERSION 3.16)
project(EnergyEstimationPass VERSION 1.0.0 LANGUAGES CXX C)

find_package(LLVM REQUIRED CONFIG)
include(HandleLLVMOptions)
include(AddLLVM)

add_subdirectory(lib/Analysis)    # Builds EnergyModel
add_subdirectory(lib/CodeGen)     # Builds EnergyEstimationPass
```

### Building

```bash
# Prerequisites: LLVM 14+ dev libraries
sudo apt install llvm-14 llvm-14-dev clang-14 cmake ninja-build

# Configure
cmake -S llvm -B build \
      -DLLVM_DIR=/usr/lib/llvm-14/lib/cmake/llvm \
      -DCMAKE_BUILD_TYPE=Release \
      -G Ninja

# Build
cmake --build build --parallel
```

## Energy Model (`llvm/energy-models/aarch64.json`)

### Target Configuration

| Parameter | Value |
|---|---|
| Core | ARM Cortex-A55 |
| Process | 7 nm (TSMC) — values scaled from 28 nm / 45 nm data |
| Frequency | 1800 MHz |
| Voltage | 0.8 V |
| Opcodes | 624 across 12 categories |

### Instruction Categories

| Category | Count | Energy Range (pJ) | Examples |
|---|---|---|---|
| Integer ALU | 180+ | 0.5–3.5 | ADD, SUB, AND, LSL |
| Integer Multiply | 20+ | 6.5–8.0 | MUL, MADD, SMULL |
| Integer Divide | 6 | 16.5–22.0 | SDIV, UDIV |
| Load (L1 hit) | 40+ | 8.8–18.0 | LDR, LDP, LDAR |
| Store (L1 hit) | 35+ | 6.8–16.0 | STR, STP, STLR |
| Branch | 15+ | 2.5–4.0 | B, BL, CBZ, Bcc |
| Conditional Select | 15+ | 2.8–3.1 | CSEL, CSINC, CSET |
| Float Scalar | 40+ | 3.0–34.0 | FADD, FMUL, FDIV |
| NEON / SIMD | 50+ | 5.0–120.0 | FADDv4f32, FMLAv2f64 |
| Crypto | 15+ | 8.0–15.0 | AESE, SHA256H, CRC32 |
| Barrier / System | 10+ | 0.2–15.0 | DMB, DSB, ISB |
| Misc | 5+ | 5.0–25.0 | SVC, BRK |

### Sources

Energy values are informed by:
- ARM Cortex-A55 Software Optimization Guide (ARM-DEN-0060A, Rev 3)
- Pallister et al., *BEEBS: Open Benchmarks for Energy Measurements on Embedded Platforms*, 2013
- Tiwari et al., *Power analysis of embedded software*, IEEE TVLSI 1994
- Nunez-Yanez, *Energy measurement and modeling of ARM Cortex-A processors*, IEEE TC 2017
- Kerrison & Eder, *Energy modeling of software for a hardware multithreaded embedded microprocessor*, ACM TECS 2015

## Known Bugs Fixed

| Bug | Symptom | Fix |
|---|---|---|
| Dangling `StringRef` keys | Crashes after JSON object destroyed | Replaced `DenseMap<StringRef,double>` with `StringMap<double>` |
| Wrong `getAsNumber()` use | Compile error | Corrected `optional<double>` handling |
| Wrong BFI type | Compile error | `MachineBlockFrequencyInfo` not `BlockFrequencyInfo` |
| Wrong ORE type | Compile error | `MachineOptimizationRemarkEmitter` not `OptimizationRemarkEmitter` |
| `MI.getOpcodeName()` doesn't exist | Compile error | Use `TII->getName(MI.getOpcode())` |
| No `double` overload for `ore::NV` | Compile error | Pre-format with `snprintf` → string |
| Wrong include path | Compile error | Use `llvm/Analysis/OptimizationRemarkEmitter.h` |
