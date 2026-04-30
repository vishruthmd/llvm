//===- EnergyEstimation.cpp - Static Energy Estimation Pass --------*- C++ -*-===//
//
// This pass walks machine functions, uses BlockFrequencyInfo to obtain a
// static execution count for each basic block, looks up per‑instruction
// energy values from a JSON model, and emits LLVM remarks containing the
// per‑block and per‑function energy totals.
//
// The remarks are emitted with the tag "energy" and can be displayed with
// "-Rpass-analysis=energy" or collected via -passes='-print-pass-comments'.
//
//===----------------------------------------------------------------------===//

#include "llvm/Analysis/EnergyModel.h"
#include "llvm/CodeGen/MachineFunctionPass.h"
#include "llvm/CodeGen/MachineBasicBlock.h"
#include "llvm/CodeGen/MachineInstr.h"
#include "llvm/CodeGen/MachineFunction.h"
#include "llvm/Analysis/BlockFrequencyInfo.h"
#include "llvm/Analysis/BlockFrequencyInfoWrapperPass.h"
#include "llvm/Support/CommandLine.h"
#include "llvm/Support/Debug.h"
#include "llvm/Support/raw_ostream.h"
#include "llvm/IR/DebugInfoMetadata.h"
#include "llvm/IR/Function.h"
#include "llvm/IR/OptimizationRemarkEmitter.h"

using namespace llvm;

static cl::opt<std::string> ModelPath(
    "energy-model", cl::desc("Path to JSON energy model"),
    cl::init("energy-models/aarch64.json"));

namespace {
class EnergyEstimationPass : public MachineFunctionPass {
  static char ID;
  std::unique_ptr<EnergyModel> Model;

public:
  EnergyEstimationPass() : MachineFunctionPass(ID) {}

  bool doInitialization(Module &M) override {
    Model = std::make_unique<EnergyModel>(ModelPath);
    return false;
  }

  bool runOnMachineFunction(MachineFunction &MF) override {
    // Get block frequency analysis.
    auto &BFI = getAnalysis<BlockFrequencyInfoWrapperPass>().getBFI();
    OptimizationRemarkEmitter ORE(MF);
    double FuncEnergy = 0.0;

    for (MachineBasicBlock &MBB : MF) {
      // Block frequency is a 64‑bit value scaled by a constant; we keep the
      // raw value because we only need relative weighting.
      uint64_t BlockFreq = BFI.getBlockFreq(&MBB).getFrequency();
      double BlockEnergy = 0.0;

      for (MachineInstr &MI : MBB) {
        // Opcode name like "ADD", "SUB", etc.
        StringRef OpcodeName = MI.getOpcodeName();
        double InstEnergy = Model->getEnergy(OpcodeName);
        BlockEnergy += InstEnergy * static_cast<double>(BlockFreq);
      }

      FuncEnergy += BlockEnergy;

      // Emit a remark for the block.
      ORE.emit(OptimizationRemark("energy", "BasicBlockEnergy", DebugLoc(), MF.getFunction())
               << "block=" << MBB.getName() << " energy=" << BlockEnergy << "pJ");
    }

    // Emit a remark for the whole function.
    ORE.emit(OptimizationRemark("energy", "FunctionEnergy", DebugLoc(), MF.getFunction())
             << "function=" << MF.getName() << " total_energy=" << FuncEnergy << "pJ");

    return false; // analysis only – does not modify the function.
  }

  void getAnalysisUsage(AnalysisUsage &AU) const override {
    AU.addRequired<BlockFrequencyInfoWrapperPass>();
    AU.setPreservesAll();
  }
};
} // end anonymous namespace

char EnergyEstimationPass::ID = 0;

// Register the pass so it can be enabled with "-passes=energy".
static RegisterPass<EnergyEstimationPass> X("energy", "Static Energy Estimation Pass",
                                            false, // does not modify CFG
                                            true   // analysis pass
);
