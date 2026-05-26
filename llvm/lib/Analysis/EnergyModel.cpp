//===- EnergyModel.cpp - JSON Instruction Energy Model --------*- C++ -*-===//
//
// Implementation of EnergyModel.  See EnergyModel.h for the JSON schema.
//
//===----------------------------------------------------------------------===//

#include "llvm/Analysis/EnergyModel.h"
#include "llvm/Support/Error.h"
#include "llvm/Support/ErrorOr.h"
#include "llvm/Support/JSON.h"
#include "llvm/Support/MemoryBuffer.h"
#include "llvm/Support/raw_ostream.h"

using namespace llvm;

EnergyModel::EnergyModel(StringRef Path) {
  // ── 1. Read file ─────────────────────────────────────────────────────────
  auto BufOrErr = MemoryBuffer::getFile(Path);
  if (!BufOrErr) {
    errs() << "[EnergyModel] cannot open '" << Path
           << "': " << BufOrErr.getError().message() << '\n';
    return;
  }

  // ── 2. Parse JSON ─────────────────────────────────────────────────────────
  // json::parse returns Expected<json::Value>; must consume error on failure.
  auto ValOrErr = json::parse((*BufOrErr)->getBuffer());
  if (!ValOrErr) {
    errs() << "[EnergyModel] JSON parse error in '" << Path << "': "
           << toString(ValOrErr.takeError()) << '\n';
    return;
  }

  // ── 3. Extract root object ────────────────────────────────────────────────
  const json::Object *Root = ValOrErr->getAsObject();
  if (!Root) {
    errs() << "[EnergyModel] JSON root must be an object in '" << Path << "'\n";
    return;
  }

  // Optional metadata fields
  if (auto A = Root->getString("arch"))
    Arch = A->str();
  if (auto U = Root->getString("unit"))
    Unit = U->str();

  // ── 4. Extract instructions map ───────────────────────────────────────────
  const json::Object *InstrObj = Root->getObject("instructions");
  if (!InstrObj) {
    errs() << "[EnergyModel] missing \"instructions\" object in '" << Path << "'\n";
    return;
  }

  unsigned Skipped = 0;
  for (const auto &KV : *InstrObj) {
    // KV.first  → json::ObjectKey (implicitly converts to StringRef)
    // KV.second → json::Value
    //
    // getAsNumber() returns std::optional<double>; it is NOT a pointer.
    // Check with 'if (auto Val = ...)' then dereference with '*Val'.
    if (auto Val = KV.second.getAsNumber()) {
      // StringMap copies the key string internally — no dangling reference.
      EnergyMap[KV.first] = *Val;
    } else {
      errs() << "[EnergyModel] non-numeric energy for opcode '"
             << KV.first << "' — skipped\n";
      ++Skipped;
    }
  }

  Loaded = true;
  LLVM_DEBUG(
    dbgs() << "[EnergyModel] loaded " << EnergyMap.size()
           << " opcodes from '" << Path << "'"
           << (Skipped ? " (" + std::to_string(Skipped) + " skipped)" : "")
           << '\n';
  );
}

double EnergyModel::getEnergy(StringRef Opcode) const {
  auto It = EnergyMap.find(Opcode);
  return (It != EnergyMap.end()) ? It->second : 0.0;
}
