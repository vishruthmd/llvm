//===- EnergyModel.h - JSON Instruction Energy Model -----------*- C++ -*-===//
//
// Declares EnergyModel: loads a JSON file mapping AArch64 instruction
// mnemonics to per-instruction energy costs (pico-joules) and provides
// O(1) lookup used by the EnergyEstimation MachineFunctionPass.
//
// JSON schema:
//   { "arch":"AArch64", "unit":"pJ",
//     "instructions": { "ADD": 2.5, "MUL": 6.2, ... } }
//
//===----------------------------------------------------------------------===//

#ifndef LLVM_ANALYSIS_ENERGYMODEL_H
#define LLVM_ANALYSIS_ENERGYMODEL_H

#include "llvm/ADT/StringMap.h"
#include "llvm/ADT/StringRef.h"
#include <string>

namespace llvm {

/// Loads per-instruction energy costs from a JSON file and provides fast
/// lookup by opcode mnemonic.  Missing entries return 0.0 pJ (safe default).
class EnergyModel {
  StringMap<double> EnergyMap; ///< opcode -> energy (pJ); StringMap owns keys
  std::string Arch;            ///< target architecture string from JSON
  std::string Unit;            ///< energy unit string from JSON (e.g. "pJ")
  bool Loaded = false;         ///< true if the model was successfully parsed

public:
  /// Load the model from \p Path.  On error, prints a message to errs() and
  /// leaves the map empty (all lookups return 0.0).
  explicit EnergyModel(StringRef Path);

  /// Return the energy cost (in the model's unit) for \p Opcode.
  /// Returns 0.0 for unknown opcodes.
  double getEnergy(StringRef Opcode) const;

  /// True if the JSON file was successfully loaded.
  bool isLoaded() const { return Loaded; }

  /// Number of instructions in the model.
  size_t size() const { return EnergyMap.size(); }

  StringRef getArch() const { return Arch; }
  StringRef getUnit() const { return Unit; }
};

} // namespace llvm

#endif // LLVM_ANALYSIS_ENERGYMODEL_H
