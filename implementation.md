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
│   └── aarch64.json                        # ARM Cortex-A55 model (300+ opcodes)
├── visualize_energy.py                     # HTML + ASCII report generator
└── build/                                  # Compiled output (generated)

Test files (project root):
├── simple_test.c                           # 15 functions (integer, FP, matmul, sort...)
└── string_proc_test.c                      # 6 string processing functions

Pipeline scripts (llvm_pipeline/):
├── run.bat                                 # runs simple_test.c → report_llvm.html
├── run01.bat                               # runs string_proc_test.c → report_string_proc.html
└── output/                                 # generated HTML reports + JSON
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

### 2. `runOnMachineFunction(MachineFunction &MF)`

1. **Lazy model initialization** — creates `EnergyModel` from the `-energy-model` path.
2. **Acquire analyses:** `MachineBlockFrequencyInfo` for block frequency data; `MachineOptimizationRemarkEmitter` for remark emission.
3. **Get entry frequency** via `MBFI.getEntryFreq()`.
4. **For each basic block:**
   - Compute `FreqScale = blockFreq / entryFreq`.
   - For each machine instruction: skip debug/pseudo, get opcode name via `Subtarget.getInstrInfo()->getName(opcode)`, look up energy.
   - Compute `WeightedBlockEnergy = RawBlockEnergy × FreqScale`.
5. **Emit `FunctionEnergy` remark** with total energy.
6. **Store `FunctionResult`** (only if `-energy-output` is specified).

### 3. `doFinalization(Module &M)`
- If `-energy-output` was specified, calls `writeJSON()` to serialize results.

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
| Opcodes | 300+ across 12 categories |

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
