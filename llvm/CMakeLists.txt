cmake_minimum_required(VERSION 3.16)
project(EnergyEstimationPass
  VERSION 1.0.0
  DESCRIPTION "LLVM Static Energy Estimation Pass (Assignment 22)"
  LANGUAGES CXX
)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# ── Find LLVM ────────────────────────────────────────────────────────────────
# Set LLVM_DIR via -DLLVM_DIR=/path/to/llvm/lib/cmake/llvm  (required)
find_package(LLVM REQUIRED CONFIG)
message(STATUS "Found LLVM ${LLVM_PACKAGE_VERSION}")
message(STATUS "Using LLVMConfig.cmake in: ${LLVM_DIR}")

# Pull in LLVM CMake helpers: HandleLLVMOptions, AddLLVM, llvm_map_components_to_libnames
list(APPEND CMAKE_MODULE_PATH "${LLVM_CMAKE_DIR}")
include(HandleLLVMOptions)
include(AddLLVM)

include_directories(${LLVM_INCLUDE_DIRS})
add_definitions(${LLVM_DEFINITIONS})

# ── Build the EnergyModel library and EnergyEstimationPass plugin ─────────────
# The inner llvm/ subdirectory adds lib/Analysis (EnergyModel) and
# lib/CodeGen (EnergyEstimationPass) as further subdirectories.
add_subdirectory(llvm)

# ── Copy energy model files to build directory for convenient testing ─────────
file(COPY ${CMAKE_SOURCE_DIR}/energy-models
     DESTINATION ${CMAKE_BINARY_DIR})

# ── Install rules ─────────────────────────────────────────────────────────────
install(TARGETS EnergyEstimationPass EnergyModel
  LIBRARY DESTINATION lib
  ARCHIVE DESTINATION lib
)
install(DIRECTORY ${CMAKE_SOURCE_DIR}/energy-models
  DESTINATION share/energy-estimation
)
install(PROGRAMS ${CMAKE_SOURCE_DIR}/visualize_energy.py
  DESTINATION bin
  RENAME visualize-energy
)
install(FILES ${CMAKE_SOURCE_DIR}/README.md
  DESTINATION share/energy-estimation
)
