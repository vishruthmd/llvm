@echo off
REM Simplified run script for Windows (no custom LLVM pass required)

setlocal enabledelayedexpansion

REM Default test file
set TEST_FILE=%1
if "%TEST_FILE%"=="" set TEST_FILE=examples\test.c

if not exist "%TEST_FILE%" (
    echo Error: Test file not found: %TEST_FILE%
    echo Usage: run_simple.bat [source_file.c]
    exit /b 1
)

echo === LLVM Energy Estimation (Simplified for Windows) ===
echo Input file: %TEST_FILE%
echo.

REM Create output directory
if not exist output mkdir output

REM Step 1: Compile to LLVM IR
echo [1/4] Compiling to LLVM IR...
clang -O2 -g -S -emit-llvm "%TEST_FILE%" -o output\test.ll
if %ERRORLEVEL% NEQ 0 (
    echo Failed to compile to LLVM IR
    exit /b 1
)

REM Step 2: Compile to assembly
echo [2/4] Compiling to assembly...
clang -O2 -S "%TEST_FILE%" -o output\test.s
if %ERRORLEVEL% NEQ 0 (
    echo Failed to compile to assembly
    exit /b 1
)

REM Step 3: Analyze energy consumption
echo [3/4] Analyzing energy consumption...
python scripts\simple_energy_analysis.py output\test.s models\energy_model.json output\energy_report.json
if %ERRORLEVEL% NEQ 0 (
    echo Failed to analyze energy
    exit /b 1
)

REM Step 4: Generate HTML visualization
echo [4/4] Generating HTML report...
python scripts\visualize.py output\energy_report.json -o output\energy_report.html
if %ERRORLEVEL% NEQ 0 (
    echo Warning: Could not generate HTML report
)

echo.
echo === Analysis Complete ===
echo.
echo Results:
echo   - JSON report: output\energy_report.json
echo   - HTML report: output\energy_report.html
echo   - LLVM IR: output\test.ll
echo   - Assembly: output\test.s
echo.
echo To view HTML report: start output\energy_report.html
echo.
