# lib/Analysis/CMakeLists.txt — builds the EnergyModel helper library

add_library(EnergyModel STATIC
  EnergyModel.cpp
)

target_include_directories(EnergyModel PUBLIC
  ${CMAKE_SOURCE_DIR}/include
  ${LLVM_INCLUDE_DIRS}
)

# EnergyModel needs LLVM Support (JSON, MemoryBuffer, raw_ostream)
llvm_map_components_to_libnames(ENERGY_MODEL_LLVM_LIBS
  Support
)

target_link_libraries(EnergyModel PUBLIC
  ${ENERGY_MODEL_LLVM_LIBS}
)

set_target_properties(EnergyModel PROPERTIES
  CXX_STANDARD 17
  POSITION_INDEPENDENT_CODE ON
)
