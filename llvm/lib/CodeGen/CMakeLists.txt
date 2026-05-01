# lib/CodeGen/CMakeLists.txt — builds the EnergyEstimation pass as a loadable plugin

# Build as a MODULE so it can be loaded with:
#   opt -load-pass-plugin=./EnergyEstimationPass.so ...
#   opt -load=./EnergyEstimationPass.so --energy-estimation ...
add_library(EnergyEstimationPass MODULE
  EnergyEstimation.cpp
)

target_include_directories(EnergyEstimationPass PRIVATE
  ${CMAKE_SOURCE_DIR}/llvm/include
  ${LLVM_INCLUDE_DIRS}
)

# Link against EnergyModel (static) and needed LLVM components
llvm_map_components_to_libnames(ENERGY_PASS_LLVM_LIBS
  Analysis
  CodeGen
  Core
  MC
  Remarks
  Support
  Target
)

target_link_libraries(EnergyEstimationPass PRIVATE
  EnergyModel
  ${ENERGY_PASS_LLVM_LIBS}
)

set_target_properties(EnergyEstimationPass PROPERTIES
  CXX_STANDARD 17
  # On macOS / Linux, don't link against libllvm here — it's loaded at runtime
  LINKER_LANGUAGE CXX
)

if(APPLE)
  # Allow undefined symbols — they'll be resolved from the host tool (opt/llc)
  set_target_properties(EnergyEstimationPass PROPERTIES
    LINK_FLAGS "-undefined dynamic_lookup"
  )
endif()
