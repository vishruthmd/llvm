@echo off
REM =============================================================================
REM run_simple.bat - LLVM Static Energy Estimation (Windows / Simple Mode)
REM =============================================================================
REM Uses: clang (compile to assembly) + Python (parse + estimate energy)
REM No LLVM development libraries required.
REM
REM Usage:
REM   run_simple.bat [source_file.c]
REM
REM Examples:
REM   run_simple.bat                            (uses examples\simple_test.c)
REM   run_simple.bat llvm\test\sample.c         (uses the assignment test file)
REM   run_simple.bat path\to\your_code.c
REM =============================================================================

setlocal enabledelayedexpansion

REM ── Input file ───────────────────────────────────────────────────────────────
set TEST_FILE=%1
if "%TEST_FILE%"=="" set TEST_FILE=examples\simple_test.c

if not exist "%TEST_FILE%" (
    echo.
    echo [ERROR] Source file not found: %TEST_FILE%
    echo.
    echo Usage: run_simple.bat [source_file.c]
    echo Example: run_simple.bat examples\simple_test.c
    exit /b 1
)

REM ── Paths ────────────────────────────────────────────────────────────────────
set OUTPUT_DIR=output
set MODEL_FILE=llvm\energy-models\aarch64.json
set ANALYSIS_SCRIPT=scripts\simple_energy_analysis.py
set VISUALIZE_SCRIPT=llvm\visualize_energy.py
set LEGACY_VISUALIZE=scripts\visualize.py

REM Fall back to old model if new one not found
if not exist "%MODEL_FILE%" (
    echo [WARN] New model not found, falling back to models\energy_model.json
    set MODEL_FILE=models\energy_model.json
)

echo.
echo ============================================================
echo   LLVM Static Energy Estimation Pass
echo   Assignment 22 - Windows Simple Mode
echo ============================================================
echo   Input  : %TEST_FILE%
echo   Model  : %MODEL_FILE%
echo   Output : %OUTPUT_DIR%\
echo ============================================================
echo.

REM ── Create output directory ──────────────────────────────────────────────────
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

REM ── Step 1: Compile to LLVM IR (human-readable) ──────────────────────────────
echo [1/5] Compiling to LLVM IR...
clang -O2 -g -S -emit-llvm "%TEST_FILE%" -o "%OUTPUT_DIR%\test.ll" 2>"%OUTPUT_DIR%\clang_err.txt"
if %ERRORLEVEL% NEQ 0 (
    echo [FAIL] Compilation to IR failed. Error output:
    type "%OUTPUT_DIR%\clang_err.txt"
    exit /b 1
)
echo       Written: %OUTPUT_DIR%\test.ll

REM ── Step 2: Compile to AArch64-style assembly ────────────────────────────────
echo [2/5] Compiling to assembly...
clang -O2 -S "%TEST_FILE%" -o "%OUTPUT_DIR%\test.s" 2>>"%OUTPUT_DIR%\clang_err.txt"
if %ERRORLEVEL% NEQ 0 (
    echo [FAIL] Compilation to assembly failed. Error output:
    type "%OUTPUT_DIR%\clang_err.txt"
    exit /b 1
)
echo       Written: %OUTPUT_DIR%\test.s

REM ── Step 3: Analyze energy consumption ──────────────────────────────────────
echo [3/5] Analyzing energy consumption...
python "%ANALYSIS_SCRIPT%" "%OUTPUT_DIR%\test.s" "%MODEL_FILE%" "%OUTPUT_DIR%\energy_results_raw.json"
if %ERRORLEVEL% NEQ 0 (
    echo [FAIL] Energy analysis failed.
    exit /b 1
)
echo       Written: %OUTPUT_DIR%\energy_results_raw.json

REM ── Step 4: Convert to standard format and generate HTML ─────────────────────
echo [4/5] Converting results to standard format...
python -c "
import json, sys

with open('output/energy_results_raw.json') as f:
    raw = json.load(f)

# Convert simple_energy_analysis output to EnergyEstimationPass output format
functions = []
for fname, fdata in raw.get('functions', {}).items():
    blocks = [{
        'name': 'body',
        'raw_energy_pJ': fdata.get('energy_pj', 0.0),
        'freq_scale': 1.0,
        'weighted_energy_pJ': fdata.get('energy_pj', 0.0),
        'instructions': fdata.get('instruction_count', 0)
    }]
    functions.append({
        'name': fname,
        'total_energy_pJ': fdata.get('energy_pj', 0.0),
        'blocks': blocks
    })

# Sort by energy descending
functions.sort(key=lambda f: f['total_energy_pJ'], reverse=True)

out = {
    'arch': 'AArch64',
    'unit': 'pJ',
    'functions': functions
}
with open('output/energy_results.json', 'w') as f:
    json.dump(out, f, indent=2)

print(f'  Converted {len(functions)} functions')
total = sum(f[\"total_energy_pJ\"] for f in functions)
print(f'  Total energy: {total:,.2f} pJ')
if functions:
    print(f'  Hottest function: {functions[0][\"name\"]} ({functions[0][\"total_energy_pJ\"]:,.2f} pJ)')
"
if %ERRORLEVEL% NEQ 0 (
    echo [WARN] Conversion failed, using raw format.
    copy "%OUTPUT_DIR%\energy_results_raw.json" "%OUTPUT_DIR%\energy_results.json" >nul
)
echo       Written: %OUTPUT_DIR%\energy_results.json

REM ── Step 5: Generate HTML report ─────────────────────────────────────────────
echo [5/5] Generating HTML report...

REM Try the new visualizer first (dark theme, sortable tables, heat-map bars)
if exist "%VISUALIZE_SCRIPT%" (
    python "%VISUALIZE_SCRIPT%" "%OUTPUT_DIR%\energy_results.json" --output "%OUTPUT_DIR%\energy_report.html" --title "Energy Report: %TEST_FILE%"
    if %ERRORLEVEL% EQU 0 (
        echo       Written: %OUTPUT_DIR%\energy_report.html  [new visualizer]
        goto :report_done
    )
)

REM Fall back to legacy visualizer
if exist "%LEGACY_VISUALIZE%" (
    python "%LEGACY_VISUALIZE%" "%OUTPUT_DIR%\energy_results_raw.json" -o "%OUTPUT_DIR%\energy_report.html"
    if %ERRORLEVEL% EQU 0 (
        echo       Written: %OUTPUT_DIR%\energy_report.html  [legacy visualizer]
        goto :report_done
    )
)
echo [WARN] Could not generate HTML report. JSON results are still available.

:report_done

REM ── Summary ──────────────────────────────────────────────────────────────────
echo.
echo ============================================================
echo   Done!
echo ============================================================
echo.
echo   Output files in: %OUTPUT_DIR%\
echo     energy_results.json   - Structured energy breakdown
echo     energy_report.html    - Interactive HTML report
echo     test.s                - AArch64 assembly
echo     test.ll               - LLVM IR
echo.
echo   Open the report:
echo     start %OUTPUT_DIR%\energy_report.html
echo.

REM Auto-open the report
start "" "%OUTPUT_DIR%\energy_report.html"
