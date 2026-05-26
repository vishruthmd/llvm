@echo off
REM =============================================================================
REM run_energy.bat - LLVM Static Energy Estimation (Redirect to Simple Pipeline)
REM =============================================================================
REM
REM NOTE: The compiled C++ LLVM pass requires LLVM 14+ dev libraries and
REM cannot be built directly on vanilla Windows without LLVM build tools.
REM
REM For a working pipeline on Windows, use run_simple.bat instead:
REM   run_simple.bat examples\simple_test.c
REM   run_simple.bat llvm\test\sample.c
REM
REM The simple pipeline: compile C -> Clang AArch64 -> parse assembly ->
REM look up per-instruction energy from JSON model -> interactive HTML report.
REM
REM To build the actual LLVM pass on Linux/WSL:
REM   sudo apt install llvm-14 llvm-14-dev clang-14 cmake ninja-build
REM   cmake -S . -B build -DLLVM_DIR=/usr/lib/llvm-14/lib/cmake/llvm -GNinja
REM   cmake --build build --parallel
REM =============================================================================

echo.
echo === run_energy.bat ===
echo The full compiled LLVM pass requires Linux/WSL with LLVM 14+ dev headers.
echo.
echo Redirecting to run_simple.bat for the working Python-based pipeline...
echo.

if "%~1"=="" (
    echo Usage: run_energy.bat path\to\your\file.c
    echo.
    echo Example: run_energy.bat examples\simple_test.c
    echo          run_energy.bat llvm\test\sample.c
    echo.
    goto :end
)

call run_simple.bat %*

:end
echo.
echo === run_energy.bat finished ===
