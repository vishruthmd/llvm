# lib/CodeGen/CMakeLists.txt — builds the EnergyEstimation pass as a loadable plugin

# Build as a MODULE so it can be loaded with:
#   opt -load-pass-plugin=./EnergyEstimationPass.so ...
#   opt -load=./EnergyEstimationPass.so --energy-estimation ...
add_library(EnergyEstimationPass MODULE
  EnergyEstimation.cpp
)

target_include_directories(EnergyEstimationPass PRIVATE
  ${CMAKE_SOURCE_DIR}/include
  ${LLVM_INCLUDE_DIRS}
)

# Only link against EnergyModel (static). DO NOT link LLVM libraries —
# they are resolved at runtime from the host tool (opt/llc) and linking
# them explicitly causes 'option registered more than once' errors.
target_link_libraries(EnergyEstimationPass PRIVATE
  EnergyModel
)

set_target_properties(EnergyEstimationPass PROPERTIES
  CXX_STANDARD 17
  LINKER_LANGUAGE CXX
)

# Allow unresolved symbols — they're provided by the host (opt/llc) at runtime
if(APPLE)
  set_target_properties(EnergyEstimationPass PROPERTIES
    LINK_FLAGS "-undefined dynamic_lookup"
  )
elseif(UNIX)
  set_target_properties(EnergyEstimationPass PROPERTIES
    LINK_FLAGS "-Wl,--allow-shlib-undefined"
  )
endif()
