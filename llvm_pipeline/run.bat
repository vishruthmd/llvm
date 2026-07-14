@echo off
REM =============================================================================
REM llvm_pipeline\run.bat — LLVM EnergyEstimationPass Pipeline
REM =============================================================================
REM Runs the full pipeline:
REM   C source -> AArch64 bitcode -> MIR -> EnergyEstimationPass -> JSON -> HTML
REM
REM Usage:
REM   cd llvm_pipeline && run.bat                    (uses default: simple_test.c)
REM   cd llvm_pipeline && run.bat ..\my_file.c       (uses your file)
REM
REM Outputs in output\:
REM   report_llvm.html    — Full HTML report (open in browser)
REM   energy_results.json — Raw JSON from the pass
REM
REM Prerequisites:
REM   - WSL (Ubuntu) with LLVM 14 in conda env
REM   - Pass already built: cd llvm && cmake --build build
REM   - Run from cmd.exe (NOT PowerShell/Git Bash)
REM =============================================================================

setlocal enabledelayedexpansion

REM ── This script is in llvm_pipeline\ — project root is parent
set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%
for %%I in ("%PROJECT_ROOT%..") do set "PROJECT_ROOT=%%~fI"

REM ── Paths to source files (in the original llvm/ directory) ────────────────
set "LLVM_DIR=%PROJECT_ROOT%\llvm"
set "TOOLS_DIR=/home/karan/miniconda3/envs/llvm_env/bin"

REM ── Determine source file (default: simple_test.c at project root) ─────────
set TEST_FILE=%~f1
if "%TEST_FILE%"=="" set "TEST_FILE=%PROJECT_ROOT%\simple_test.c"
if not exist "%TEST_FILE%" (
    echo [ERROR] Source file not found: %TEST_FILE%
    echo Usage: run.bat [path\to\file.c]
    exit /b 1
)

for %%F in ("%TEST_FILE%") do set "BASENAME=%%~nF"

REM ── Clean & create output directory ────────────────────────────────────────
if exist "%SCRIPT_DIR%output" rmdir /s /q "%SCRIPT_DIR%output"
mkdir "%SCRIPT_DIR%output"

REM ── Convert Windows paths to WSL paths ──────────────────────────────────────
call :wslpath WSL_ROOT   "%PROJECT_ROOT%"
call :wslpath WSL_LLVM   "%LLVM_DIR%"
call :wslpath WSL_TEST   "%TEST_FILE%"

set "PLUGIN=%WSL_LLVM%/build/lib/CodeGen/libEnergyEstimationPass.so"
set "MODEL=%WSL_LLVM%/energy-models/aarch64.json"
set "VIZ=%WSL_LLVM%/visualize_energy.py"
set "OUT=%SCRIPT_DIR%output"

echo.
echo =============================================================================
echo   LLVM Static Energy Estimation Pass
echo =============================================================================
echo   Source     : %TEST_FILE%
echo   Plugin     : %PLUGIN%
echo   Model      : %MODEL%
echo   Output     : %OUT%
echo =============================================================================
echo.

REM ─── Step 1: Compile to AArch64 bitcode ─────────────────────────────────────
echo [1/5] Compiling to AArch64 bitcode...
wsl.exe -d Ubuntu -- %TOOLS_DIR%/clang -O2 -target aarch64-linux-gnu -emit-llvm -c "%WSL_TEST%" -o "%WSL_LLVM%/output/%BASENAME%.bc" 2>"%OUT%\clang_err.txt"
if %ERRORLEVEL% NEQ 0 (
    echo [FAIL] Clang compilation failed.
    type "%OUT%\clang_err.txt"
    exit /b 1
)
echo        OK

REM ─── Step 2: Generate MIR ───────────────────────────────────────────────────
echo [2/5] Generating MIR...
wsl.exe -d Ubuntu -- %TOOLS_DIR%/llc -stop-after=finalize-isel "%WSL_LLVM%/output/%BASENAME%.bc" -o "%WSL_LLVM%/output/%BASENAME%.mir" -mtriple aarch64-linux-gnu 2>"%OUT%\mir_err.txt"
if %ERRORLEVEL% NEQ 0 (
    echo [FAIL] MIR generation failed.
    type "%OUT%\mir_err.txt"
    exit /b 1
)
echo        OK

REM ─── Step 3: Run EnergyEstimationPass ────────────────────────────────────────
echo [3/5] Running EnergyEstimationPass...
wsl.exe -d Ubuntu -- %TOOLS_DIR%/llc -load "%PLUGIN%" -run-pass=energy-estimation -energy-model "%MODEL%" -energy-output "%WSL_LLVM%/output/energy_results.json" -mtriple aarch64-linux-gnu "%WSL_LLVM%/output/%BASENAME%.mir" -o "%WSL_LLVM%/output/%BASENAME%.s" 2>"%OUT%\llc_stderr.txt"
if %ERRORLEVEL% NEQ 0 (
    echo [WARN] llc reported warnings:
    type "%OUT%\llc_stderr.txt"
)
echo        OK

REM ─── Step 4: Copy results to llvm_pipeline\output\ ──────────────────────────
copy "%LLVM_DIR%\output\energy_results.json" "%OUT%\energy_results.json" >nul

REM ─── Step 5: Generate HTML report ───────────────────────────────────────────
echo [4/5] Generating HTML report...
wsl.exe -d Ubuntu -- python3 "%VIZ%" "%WSL_LLVM%/output/energy_results.json" --title "LLVM Pass: %BASENAME%.c" --output "%WSL_LLVM%/output/report_llvm.html" --model "%MODEL%" 2>"%OUT%\viz_stderr.txt"
copy "%LLVM_DIR%\output\report_llvm.html" "%OUT%\report_llvm.html" >nul
echo        OK  →  output\report_llvm.html

REM ─── Step 6: Print summary ──────────────────────────────────────────────────
echo [5/5] Summary:
echo.
wsl.exe -d Ubuntu -- python3 "%VIZ%" "%WSL_LLVM%/output/energy_results.json" --no-html --title "LLVM Pass: %BASENAME%.c" 2>nul

echo.
echo =============================================================================
echo   Done!  Output: %OUT%
echo     report_llvm.html       — Full HTML report
echo.
echo Opening report in browser...
start "" "%OUT%\report_llvm.html"
goto :end

REM ===========================================================================
REM wslpath subroutine — Convert Windows path to WSL /mnt/ path
REM ===========================================================================
:wslpath
set "__PATH=%~2"
set "__DRIVE=%__PATH:~0,1%"
if /i "!__DRIVE!"=="A" set "__DRIVE=a"
if /i "!__DRIVE!"=="B" set "__DRIVE=b"
if /i "!__DRIVE!"=="C" set "__DRIVE=c"
if /i "!__DRIVE!"=="D" set "__DRIVE=d"
if /i "!__DRIVE!"=="E" set "__DRIVE=e"
if /i "!__DRIVE!"=="F" set "__DRIVE=f"
if /i "!__DRIVE!"=="G" set "__DRIVE=g"
if /i "!__DRIVE!"=="H" set "__DRIVE=h"
if /i "!__DRIVE!"=="I" set "__DRIVE=i"
if /i "!__DRIVE!"=="J" set "__DRIVE=j"
if /i "!__DRIVE!"=="K" set "__DRIVE=k"
if /i "!__DRIVE!"=="L" set "__DRIVE=l"
if /i "!__DRIVE!"=="M" set "__DRIVE=m"
if /i "!__DRIVE!"=="N" set "__DRIVE=n"
if /i "!__DRIVE!"=="O" set "__DRIVE=o"
if /i "!__DRIVE!"=="P" set "__DRIVE=p"
if /i "!__DRIVE!"=="Q" set "__DRIVE=q"
if /i "!__DRIVE!"=="R" set "__DRIVE=r"
if /i "!__DRIVE!"=="S" set "__DRIVE=s"
if /i "!__DRIVE!"=="T" set "__DRIVE=t"
if /i "!__DRIVE!"=="U" set "__DRIVE=u"
if /i "!__DRIVE!"=="V" set "__DRIVE=v"
if /i "!__DRIVE!"=="W" set "__DRIVE=w"
if /i "!__DRIVE!"=="X" set "__DRIVE=x"
if /i "!__DRIVE!"=="Y" set "__DRIVE=y"
if /i "!__DRIVE!"=="Z" set "__DRIVE=z"
set "__REST=%__PATH:~2%"
set "__REST=!__REST:\=/!"
if "!__REST:~-1!"=="/" set "__REST=!__REST:~0,-1!"
set "%~1=/mnt/!__DRIVE!!__REST!"
goto :eof

:end
endlocal
