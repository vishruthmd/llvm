//===- EnergyModel.cpp - Simple JSON Energy Model ----------------*- C++ -*-===//
//
// Implementation of the EnergyModel helper that reads a JSON file with the
// format:
// {
//   "arch": "AArch64",
//   "unit": "pJ",
//   "instructions": { "ADD": 2.5, "SUB": 2.5, ... }
// }
//
// The class stores a DenseMap from opcode name to energy (double).  Missing
// entries default to 0.0 pJ.
//
//===----------------------------------------------------------------------===//

#include "llvm/Analysis/EnergyModel.h"
#include "llvm/Support/Debug.h"
#include "llvm/Support/ErrorOr.h"
#include "llvm/Support/JSON.h"
#include "llvm/Support/MemoryBuffer.h"
#include "llvm/Support/raw_ostream.h"

using namespace llvm;

EnergyModel::EnergyModel(StringRef Path) {
  // Load the file contents.
  ErrorOr<std::unique_ptr<MemoryBuffer>> BufferOr = MemoryBuffer::getFile(Path);
  if (!BufferOr) {
    errs() << "[EnergyModel] could not open model file: " << Path << "\n";
    return;
  }

  Expected<json::Value> JSONOr = json::parse(BufferOr.get()->getBuffer());
  if (!JSONOr) {
    errs() << "[EnergyModel] failed to parse JSON model: " << Path << "\n";
    return;
  }

  const json::Object *Root = JSONOr->getAsObject();
  if (!Root) {
    errs() << "[EnergyModel] JSON root is not an object" << "\n";
    return;
  }

  const json::Object *InstrObj = nullptr;
  if (auto *I = Root->getObject("instructions"))
    InstrObj = I;
  else {
    errs() << "[EnergyModel] no \"instructions\" object in model" << "\n";
    return;
  }

  for (auto &KV : *InstrObj) {
    // KV.first = opcode string, KV.second = number (expected double/int)
    if (auto *Num = KV.second.getAsNumber()) {
      double Energy = Num->getAsDouble();
      EnergyMap[KV.first()] = Energy;
    } else {
      // ignore non‑numeric entries, but warn.
      errs() << "[EnergyModel] non‑numeric energy for opcode " << KV.first()
             << " ignored\n";
    }
  }
}

double EnergyModel::getEnergy(StringRef Opcode) const {
  auto It = EnergyMap.find(Opcode);
  if (It != EnergyMap.end())
    return It->second;
  return 0.0; // unknown opcode → zero energy (safe default)
}
