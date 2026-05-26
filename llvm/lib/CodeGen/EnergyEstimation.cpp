//===- EnergyEstimation.cpp - Static Energy Estimation Pass ----*- C++ -*-===//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//
///
/// \file
/// MachineFunctionPass that walks machine functions, uses
/// MachineBlockFrequencyInfo for static execution frequency, looks up
/// per-instruction energy costs from a JSON energy model, and emits
/// MachineOptimizationRemarkAnalysis remarks tagged "energy".
///
/// Remarks can be displayed with:  -Rpass-analysis=energy
///
/// Command-line options:
///   -energy-model=<path>   Path to the JSON energy model file.
///                          Default: energy-models/aarch64.json
///   -energy-output=<path>  Optional path for a JSON summary output file.
///
/// JSON output schema:
/// {
///   "arch": "AArch64",
///   "unit": "pJ",
///   "functions": [
///     {
///       "name": "main",
///       "total_energy_pJ": 1234.5678,
///       "blocks": [
///         {
///           "name": "entry",
///           "raw_energy_pJ": 500.0,
///           "freq_scale": 1.0,
///           "weighted_energy_pJ": 500.0,
///           "instructions": 12
///         }
///       ]
///     }
///   ]
/// }
///
//===----------------------------------------------------------------------===//

// Define before Debug.h so LLVM_DEBUG filters on this tag.
#define DEBUG_TYPE "energy"

#include "llvm/Analysis/EnergyModel.h"
#include "llvm/CodeGen/MachineBasicBlock.h"
#include "llvm/CodeGen/MachineBlockFrequencyInfo.h"
#include "llvm/CodeGen/MachineFunction.h"
#include "llvm/CodeGen/MachineFunctionPass.h"
#include "llvm/CodeGen/MachineInstr.h"
#include "llvm/CodeGen/MachineOptimizationRemarkEmitter.h"
#include "llvm/CodeGen/TargetInstrInfo.h"
#include "llvm/CodeGen/TargetSubtargetInfo.h"
#include "llvm/IR/DiagnosticInfo.h"
#include "llvm/IR/Function.h"
#include "llvm/Pass.h"
#include "llvm/Support/CommandLine.h"
#include "llvm/Support/Debug.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/raw_ostream.h"

#include <cassert>
#include <cstdio>
#include <memory>
#include <string>
#include <vector>

using namespace llvm;

//===----------------------------------------------------------------------===//
// Command-line options
//===----------------------------------------------------------------------===//

static cl::opt<std::string> ModelPath(
    "energy-model",
    cl::desc("Path to JSON energy model file"),
    cl::init("energy-models/aarch64.json"));

static cl::opt<std::string> OutputPath(
    "energy-output",
    cl::desc("Path to write JSON energy results (optional)"),
    cl::init(""));

//===----------------------------------------------------------------------===//
// Helper: format a double as a fixed-point string for ore::NV arguments.
// ore::NV (DiagnosticInfoOptimizationBase::Argument) has no double overload,
// so we pre-format all floating-point values as strings.
//===----------------------------------------------------------------------===//

static std::string fmtDouble(double V) {
  char Buf[64];
  std::snprintf(Buf, sizeof(Buf), "%.4f", V);
  return Buf;
}

//===----------------------------------------------------------------------===//
// Result structures for JSON accumulation
//===----------------------------------------------------------------------===//

namespace {

/// Per-block energy data collected during a single runOnMachineFunction call.
struct BlockResult {
  std::string Name;           ///< MachineBasicBlock name
  double      RawEnergy;      ///< Sum of per-instruction energies (unweighted)
  double      FreqScale;      ///< blockFreq / entryFreq
  double      WeightedEnergy; ///< RawEnergy * FreqScale
  unsigned    InstrCount;     ///< Number of real (non-debug, non-implicit) instrs
};

/// Per-function energy data, containing all block results.
struct FunctionResult {
  std::string             Name;        ///< MachineFunction name
  double                  TotalEnergy; ///< Sum of WeightedEnergy over all blocks
  std::vector<BlockResult> Blocks;
};

//===----------------------------------------------------------------------===//
// EnergyEstimationPass
//===----------------------------------------------------------------------===//

class EnergyEstimationPass : public MachineFunctionPass {
public:
  static char ID;

  EnergyEstimationPass() : MachineFunctionPass(ID) {}

  StringRef getPassName() const override {
    return "Static Energy Estimation Pass";
  }

  //--------------------------------------------------------------------------
  // Analysis usage: require MBFI and the machine ORE pass; preserve everything.
  //--------------------------------------------------------------------------
  void getAnalysisUsage(AnalysisUsage &AU) const override {
    AU.addRequired<MachineBlockFrequencyInfo>();
    AU.addRequired<MachineOptimizationRemarkEmitterPass>();
    AU.setPreservesAll();
    MachineFunctionPass::getAnalysisUsage(AU);
  }

  //--------------------------------------------------------------------------
  // doInitialization – called once per module before any MF is processed.
  // Resets accumulated results so the pass is safe to reuse across modules.
  //--------------------------------------------------------------------------
  bool doInitialization(Module & /*M*/) override {
    AllResults.clear();
    return false; // did not modify the module
  }

  //--------------------------------------------------------------------------
  // runOnMachineFunction – core analysis loop.
  //--------------------------------------------------------------------------
  bool runOnMachineFunction(MachineFunction &MF) override {
    // ── Lazy model initialization ─────────────────────────────────────────
    // We initialize on the first call rather than in the constructor so that
    // the command-line option is fully parsed by the time we read ModelPath.
    if (!Model) {
      Model = std::make_unique<EnergyModel>(ModelPath);
      if (Model->isLoaded()) {
        LLVM_DEBUG(dbgs() << "[EnergyEstimation] model loaded: arch="
                          << Model->getArch() << "  unit=" << Model->getUnit()
                          << "  opcodes=" << Model->size() << "\n");
      } else {
        LLVM_DEBUG(dbgs() << "[EnergyEstimation] WARNING: model not loaded from '"
                          << ModelPath << "'; all energies will be 0.0\n");
      }
    }

    // ── Guard: skip empty functions ───────────────────────────────────────
    if (MF.empty())
      return false;

    // ── Acquire required analyses ─────────────────────────────────────────
    MachineBlockFrequencyInfo &MBFI =
        getAnalysis<MachineBlockFrequencyInfo>();

    MachineOptimizationRemarkEmitter &ORE =
        getAnalysis<MachineOptimizationRemarkEmitterPass>().getORE();

    // Entry frequency is used as the normalization denominator.
    // Guard against zero to avoid undefined division behavior.
    const uint64_t EntryFreqRaw = MBFI.getEntryFreq();
    const double   EntryFreqD   = (EntryFreqRaw > 0)
                                      ? static_cast<double>(EntryFreqRaw)
                                      : 1.0;

    LLVM_DEBUG(dbgs() << "[EnergyEstimation] Function: " << MF.getName()
                      << "  entry_freq=" << EntryFreqRaw << "\n");

    // ── Per-function accumulators ─────────────────────────────────────────
    double         FuncTotalEnergy = 0.0;
    FunctionResult FuncResult;
    FuncResult.Name = std::string(MF.getName());

    // ── Walk basic blocks ─────────────────────────────────────────────────
    for (MachineBasicBlock &MBB : MF) {

      // Normalize the raw block frequency against the entry frequency so that
      // hot loops appear with FreqScale > 1 and cold blocks with FreqScale < 1.
      const uint64_t BlockFreqRaw = MBFI.getBlockFreq(&MBB).getFrequency();
      const double   FreqScale    = static_cast<double>(BlockFreqRaw) / EntryFreqD;

      double   RawBlockEnergy = 0.0;
      unsigned InstrCount     = 0;

      // ── Walk instructions ───────────────────────────────────────────────
      for (MachineInstr &MI : MBB) {
        // Skip pseudo-instructions that carry no real execution cost.
        if (MI.isDebugInstr())
          continue;
        if (MI.isImplicitDef())
          continue;

        // Resolve the canonical opcode mnemonic through the subtarget's
        // InstrInfo so we match whatever the model uses (e.g. "ADDWri").
        StringRef OpName =
            MF.getSubtarget().getInstrInfo()->getName(MI.getOpcode());

        const double InstEnergy = Model->getEnergy(OpName);
        RawBlockEnergy += InstEnergy;
        ++InstrCount;

        LLVM_DEBUG(dbgs() << "  [" << MBB.getName() << "] " << OpName
                          << "  e=" << InstEnergy << " pJ\n");
      }

      const double WeightedBlockEnergy = RawBlockEnergy * FreqScale;
      FuncTotalEnergy += WeightedBlockEnergy;

      // ── Determine a DebugLoc for the per-block remark ───────────────────
      // Walk forward to find the first real instruction that carries debug
      // location metadata.  Fall back to a default-constructed (empty) DebugLoc
      // when no debug info is present — DiagnosticLocation handles this safely.
      DebugLoc BlockLoc;
      for (const MachineInstr &MI : MBB) {
        if (!MI.isDebugInstr() && !MI.isImplicitDef()) {
          BlockLoc = MI.getDebugLoc();
          break;
        }
      }

      // ── Emit per-block remark ───────────────────────────────────────────
      // Tag: "energy"  RemarkName: "BlockEnergy"
      // Visible with: -Rpass-analysis=energy
      {
        MachineOptimizationRemarkAnalysis Remark(
            DEBUG_TYPE,                    // PassName  → "energy"
            "BlockEnergy",                 // RemarkName
            DiagnosticLocation(BlockLoc),  // location (empty DebugLoc is OK)
            &MBB);                         // anchor basic block
        Remark << ore::NV("Function",       MF.getName())
               << ore::NV("Block",          MBB.getName())
               << ore::NV("RawEnergy",      fmtDouble(RawBlockEnergy))
               << ore::NV("FreqScale",      fmtDouble(FreqScale))
               << ore::NV("WeightedEnergy", fmtDouble(WeightedBlockEnergy))
               << ore::NV("Instructions",   static_cast<int>(InstrCount));
        ORE.emit(Remark);
      }

      LLVM_DEBUG(dbgs() << "  BB=" << MBB.getName()
                        << "  raw_freq=" << BlockFreqRaw
                        << "  freq_scale=" << FreqScale
                        << "  raw_energy=" << RawBlockEnergy
                        << "  weighted_energy=" << WeightedBlockEnergy << "\n");

      // ── Accumulate block result for JSON output ──────────────────────────
      if (!OutputPath.empty()) {
        BlockResult BR;
        BR.Name           = std::string(MBB.getName());
        BR.RawEnergy      = RawBlockEnergy;
        BR.FreqScale      = FreqScale;
        BR.WeightedEnergy = WeightedBlockEnergy;
        BR.InstrCount     = InstrCount;
        FuncResult.Blocks.push_back(std::move(BR));
      }
    } // end MBB loop

    FuncResult.TotalEnergy = FuncTotalEnergy;

    // ── Emit function-level remark ────────────────────────────────────────
    // Anchor on the first MBB (we already guarded against MF.empty() above).
    {
      const MachineBasicBlock *FirstMBB = &MF.front();

      // Find the first real instruction's debug location for the remark.
      DebugLoc FuncLoc;
      for (const MachineInstr &MI : *FirstMBB) {
        if (!MI.isDebugInstr() && !MI.isImplicitDef()) {
          FuncLoc = MI.getDebugLoc();
          break;
        }
      }

      MachineOptimizationRemarkAnalysis Remark(
          DEBUG_TYPE,                   // PassName  → "energy"
          "FunctionEnergy",             // RemarkName
          DiagnosticLocation(FuncLoc),  // location
          FirstMBB);                    // anchor basic block
      Remark << ore::NV("Function",    MF.getName())
             << ore::NV("TotalEnergy", fmtDouble(FuncTotalEnergy));
      ORE.emit(Remark);
    }

    LLVM_DEBUG(dbgs() << "[EnergyEstimation] " << MF.getName()
                      << "  total_weighted_energy=" << FuncTotalEnergy
                      << " " << (Model->isLoaded() ? Model->getUnit() : "pJ")
                      << "\n");

    // ── Accumulate function result for JSON output ────────────────────────
    if (!OutputPath.empty())
      AllResults.push_back(std::move(FuncResult));

    return false; // analysis pass — does not modify the MachineFunction
  }

  //--------------------------------------------------------------------------
  // doFinalization – called once per module after all MFs have been processed.
  // Writes the accumulated JSON summary if -energy-output was specified.
  //--------------------------------------------------------------------------
  bool doFinalization(Module & /*M*/) override {
    if (!OutputPath.empty() && !AllResults.empty())
      writeJSON();
    return false; // did not modify the module
  }

private:
  /// Lazily initialized energy model (null until first runOnMachineFunction).
  std::unique_ptr<EnergyModel> Model;

  /// Accumulated per-function results, built up across runOnMachineFunction
  /// calls and flushed to disk in doFinalization.
  std::vector<FunctionResult> AllResults;

  //--------------------------------------------------------------------------
  // writeJSON – serialize AllResults to the file at OutputPath.
  // JSON is constructed manually as a string to avoid a dependency on
  // llvm::json::Object (which would require linking additional LLVM libs).
  //--------------------------------------------------------------------------
  void writeJSON() const {
    std::error_code EC;
    raw_fd_ostream OS(OutputPath, EC, sys::fs::OF_Text);
    if (EC) {
      errs() << "[EnergyEstimation] cannot open output file '"
             << OutputPath << "': " << EC.message() << "\n";
      return;
    }

    // Prefer metadata from the loaded model; fall back to safe defaults.
    StringRef Arch = (Model && Model->isLoaded()) ? Model->getArch() : "unknown";
    StringRef Unit = (Model && Model->isLoaded()) ? Model->getUnit() : "pJ";

    // ── Root object ───────────────────────────────────────────────────────
    OS << "{\n";
    OS << "  \"arch\": \"" << Arch << "\",\n";
    OS << "  \"unit\": \"" << Unit << "\",\n";
    OS << "  \"functions\": [\n";

    for (size_t fi = 0, fn = AllResults.size(); fi < fn; ++fi) {
      const FunctionResult &FR = AllResults[fi];

      OS << "    {\n";
      OS << "      \"name\": \"" << FR.Name << "\",\n";
      OS << "      \"total_energy_pJ\": " << fmtDouble(FR.TotalEnergy) << ",\n";
      OS << "      \"blocks\": [\n";

      for (size_t bi = 0, bn = FR.Blocks.size(); bi < bn; ++bi) {
        const BlockResult &BR = FR.Blocks[bi];

        OS << "        {\n";
        OS << "          \"name\": \""          << BR.Name              << "\",\n";
        OS << "          \"raw_energy_pJ\": "   << fmtDouble(BR.RawEnergy)      << ",\n";
        OS << "          \"freq_scale\": "      << fmtDouble(BR.FreqScale)      << ",\n";
        OS << "          \"weighted_energy_pJ\": " << fmtDouble(BR.WeightedEnergy) << ",\n";
        OS << "          \"instructions\": "    << BR.InstrCount        << "\n";
        OS << "        }";
        if (bi + 1 < bn) OS << ",";
        OS << "\n";
      }

      OS << "      ]\n";   // close "blocks"
      OS << "    }";
      if (fi + 1 < fn) OS << ",";
      OS << "\n";
    }

    OS << "  ]\n"; // close "functions"
    OS << "}\n";

    if (OS.has_error()) {
      errs() << "[EnergyEstimation] error writing JSON to '"
             << OutputPath << "': " << OS.error().message() << "\n";
    } else {
      LLVM_DEBUG(dbgs() << "[EnergyEstimation] JSON summary written to '"
                        << OutputPath << "'\n");
    }
  }
};

} // end anonymous namespace

//===----------------------------------------------------------------------===//
// Pass registration
//===----------------------------------------------------------------------===//

char EnergyEstimationPass::ID = 0;

/// Register the pass so it is available as "-energy-estimation" in opt/llc.
/// The pass is analysis-only (true) and does not modify the CFG (false).
static RegisterPass<EnergyEstimationPass> X(
    "energy-estimation",             // CLI flag name
    "Static Energy Estimation Pass", // human-readable description
    false,                           // does not modify the CFG
    true                             // is an analysis pass
);
