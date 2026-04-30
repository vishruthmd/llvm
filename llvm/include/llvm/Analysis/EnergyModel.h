//===- EnergyModel.h - Simple JSON Energy Model ----------------*- C++ -*-===//
//
// This file declares a tiny helper class that loads a JSON file mapping
// instruction mnemonics to energy values (pico‑joules) and provides a lookup
// interface used by the EnergyEstimation pass.
//
//===----------------------------------------------------------------------===//

#ifndef LLVM_ANALYSIS_ENERGYMODEL_H
#define LLVM_ANALYSIS_ENERGYMODEL_H

#include "llvm/Support/Error.h"
#include "llvm/Support/JSON.h"
#include "llvm/ADT/DenseMap.h"
#include "llvm/ADT/StringRef.h"

namespace llvm {

class EnergyModel {
  DenseMap<StringRef, double> EnergyMap; // opcode name -> energy (pJ)

public:
  explicit EnergyModel(StringRef Path);
  double getEnergy(StringRef Opcode) const;
};

} // end namespace llvm

#endif // LLVM_ANALYSIS_ENERGYMODEL_H
