@echo off
rem --------------------------------------------------------------
rem [1] Variables – adapt only if your layout differs
rem --------------------------------------------------------------
set REPO_ROOT=C:\Users\Karan\Desktop\llvm\llvm          rem <‑‑ worktree where branch karan is checked out
set BUILD_DIR=%REPO_ROOT%\build
set INSTALL_DIR=%BUILD_DIR%\install
set PLUGIN_NAME=LLVMEnergyEstimation
set PLUGIN_DLL=%INSTALL_DIR%\lib\%PLUGIN_NAME%.dll
set TEST_SRC=%REPO_ROOT%\examples\fp_compute.c
set TEST_BC=%REPO_ROOT%\fp_compute.bc
set REMARKS_JSON=%REPO_ROOT%\remarks.json
set REPORT_HTML=%REPO_ROOT%\energy_report.html

rem --------------------------------------------------------------
rem [2] Build LLVM (if not already built)
rem --------------------------------------------------------------
if not exist "%BUILD_DIR%" (
    echo *** Creating build directory …
    mkdir "%BUILD_DIR%"
    cd /d "%BUILD_DIR%"

    echo *** Configuring CMake …
    cmake -G "Visual Studio 17 2022" -A x64 ^
          -DLLVM_ENABLE_PROJECTS=llvm ^
          -DLLVM_TARGETS_TO_BUILD="AArch64;X86" ^
          -DCMAKE_BUILD_TYPE=Release ^
          -DLLVM_ENABLE_ASSERTIONS=ON ^
          -DLLVM_ENABLE_RTTI=ON ^
          -DCMAKE_INSTALL_PREFIX=%INSTALL_DIR% ^
          ..\llvm
) else (
    cd /d "%BUILD_DIR%"
)

echo *** Building LLVM (incl. the plugin) …
cmake --build . --target install --config Release -- /m
if errorlevel 1 (
    echo *** Build failed. Check the output above.
    exit /b 1
)

rem --------------------------------------------------------------
rem [3] Compile the test program to LLVM bitcode
rem --------------------------------------------------------------
echo *** Compiling example program to bitcode …
clang -O2 -emit-llvm -c "%TEST_SRC%" -o "%TEST_BC%"
if errorlevel 1 (
    echo *** clang failed – maybe the source file is missing?
    exit /b 1
)

rem --------------------------------------------------------------
rem [4] Run the EnergyEstimation pass and capture remarks as JSON
rem --------------------------------------------------------------
echo *** Running the EnergyEstimation pass …
opt -load-pass-plugin="%PLUGIN_DLL%" ^
    -passes=energy-estimation ^
    -debug-only=remarks ^
    "%TEST_BC%" -o NUL 2> "%REMARKS_JSON%"
if errorlevel 1 (
    echo *** opt failed – likely the plugin was not built or could not be loaded.
    exit /b 1
)

rem --------------------------------------------------------------
rem [5] Generate the HTML report
rem --------------------------------------------------------------
echo *** Generating HTML report …
python "%REPO_ROOT%\scripts\visualize_energy.py" "%REMARKS_JSON%" -o "%REPORT_HTML%"
if errorlevel 1 (
    echo *** Python visualiser failed.
    exit /b 1
)

echo.
echo ==================== DONE ====================
echo Report written to: %REPORT_HTML%
echo You can open it with any browser:
echo   start "" "%REPORT_HTML%"
echo =================================================