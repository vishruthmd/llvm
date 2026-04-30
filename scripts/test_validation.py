#!/usr/bin/env python3
"""
Test validation script for Energy Estimation Pass

Runs the pass on test cases and validates the output format and values.
"""

import json
import sys
import subprocess
import os
from pathlib import Path


class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'


def run_command(cmd, cwd=None):
    """Run a shell command and return output."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"


def test_pass_builds():
    """Test that the pass builds successfully."""
    print(f"{Colors.BLUE}[TEST]{Colors.END} Building pass...")

    if not os.path.exists("build.sh"):
        print(f"{Colors.RED}[FAIL]{Colors.END} build.sh not found")
        return False

    returncode, stdout, stderr = run_command("bash build.sh")

    # Check for pass library
    pass_lib = "build/lib/EnergyPass.so"
    if sys.platform == "darwin":
        pass_lib = "build/lib/EnergyPass.dylib"

    if os.path.exists(pass_lib):
        print(f"{Colors.GREEN}[PASS]{Colors.END} Pass built successfully")
        return True
    else:
        print(f"{Colors.RED}[FAIL]{Colors.END} Pass library not found at {pass_lib}")
        return False


def test_energy_model_valid():
    """Test that the energy model JSON is valid."""
    print(f"{Colors.BLUE}[TEST]{Colors.END} Validating energy model...")

    model_path = "models/energy_model.json"
    if not os.path.exists(model_path):
        print(f"{Colors.RED}[FAIL]{Colors.END} Energy model not found")
        return False

    try:
        with open(model_path, 'r') as f:
            model = json.load(f)

        # Check required fields
        required_fields = ["architecture", "processor", "instruction_classes"]
        for field in required_fields:
            if field not in model:
                print(f"{Colors.RED}[FAIL]{Colors.END} Missing field: {field}")
                return False

        # Check instruction classes
        classes = model["instruction_classes"]
        if len(classes) == 0:
            print(f"{Colors.RED}[FAIL]{Colors.END} No instruction classes defined")
            return False

        # Validate each class has energy_pj
        for class_name, class_data in classes.items():
            if "energy_pj" not in class_data:
                print(f"{Colors.RED}[FAIL]{Colors.END} Class {class_name} missing energy_pj")
                return False

        print(f"{Colors.GREEN}[PASS]{Colors.END} Energy model is valid ({len(classes)} classes)")
        return True

    except json.JSONDecodeError as e:
        print(f"{Colors.RED}[FAIL]{Colors.END} Invalid JSON: {e}")
        return False


def test_example_compilation():
    """Test that example files compile and produce energy reports."""
    print(f"{Colors.BLUE}[TEST]{Colors.END} Testing example compilation...")

    example = "examples/test.c"
    if not os.path.exists(example):
        print(f"{Colors.RED}[FAIL]{Colors.END} Example file not found: {example}")
        return False

    # Run the pass
    returncode, stdout, stderr = run_command(f"bash run.sh {example}")

    # Check for output files
    output_json = "output/energy_report.json"
    output_html = "output/energy_report.html"

    if not os.path.exists(output_json):
        print(f"{Colors.RED}[FAIL]{Colors.END} Energy report JSON not generated")
        return False

    if not os.path.exists(output_html):
        print(f"{Colors.RED}[FAIL]{Colors.END} Energy report HTML not generated")
        return False

    print(f"{Colors.GREEN}[PASS]{Colors.END} Example compiled and analyzed successfully")
    return True


def test_energy_report_format():
    """Test that the energy report has correct format."""
    print(f"{Colors.BLUE}[TEST]{Colors.END} Validating energy report format...")

    report_path = "output/energy_report.json"
    if not os.path.exists(report_path):
        print(f"{Colors.YELLOW}[SKIP]{Colors.END} No energy report to validate")
        return True

    try:
        with open(report_path, 'r') as f:
            report = json.load(f)

        # Check required fields
        if "functions" not in report:
            print(f"{Colors.RED}[FAIL]{Colors.END} Missing 'functions' field")
            return False

        functions = report["functions"]
        if len(functions) == 0:
            print(f"{Colors.YELLOW}[WARN]{Colors.END} No functions in report")
            return True

        # Validate function structure
        for func in functions:
            required = ["name", "total_energy_pj", "total_instructions"]
            for field in required:
                if field not in func:
                    print(f"{Colors.RED}[FAIL]{Colors.END} Function missing field: {field}")
                    return False

            # Check energy is positive
            if func["total_energy_pj"] < 0:
                print(f"{Colors.RED}[FAIL]{Colors.END} Negative energy value")
                return False

        print(f"{Colors.GREEN}[PASS]{Colors.END} Energy report format is valid ({len(functions)} functions)")
        return True

    except json.JSONDecodeError as e:
        print(f"{Colors.RED}[FAIL]{Colors.END} Invalid JSON: {e}")
        return False


def test_energy_values_reasonable():
    """Test that energy values are in reasonable ranges."""
    print(f"{Colors.BLUE}[TEST]{Colors.END} Checking energy value ranges...")

    report_path = "output/energy_report.json"
    if not os.path.exists(report_path):
        print(f"{Colors.YELLOW}[SKIP]{Colors.END} No energy report to validate")
        return True

    try:
        with open(report_path, 'r') as f:
            report = json.load(f)

        functions = report.get("functions", [])
        if len(functions) == 0:
            print(f"{Colors.YELLOW}[SKIP]{Colors.END} No functions to check")
            return True

        warnings = []

        for func in functions:
            energy = func.get("total_energy_pj", 0)
            instructions = func.get("total_instructions", 0)

            if instructions > 0:
                avg_energy = energy / instructions

                # Check if average energy per instruction is reasonable
                # Should be between 2 pJ (NOP) and 200 pJ (complex FP)
                if avg_energy < 2.0:
                    warnings.append(f"Function {func['name']}: unusually low avg energy ({avg_energy:.2f} pJ)")
                elif avg_energy > 200.0:
                    warnings.append(f"Function {func['name']}: unusually high avg energy ({avg_energy:.2f} pJ)")

        if warnings:
            print(f"{Colors.YELLOW}[WARN]{Colors.END} Energy value warnings:")
            for warning in warnings:
                print(f"  - {warning}")
        else:
            print(f"{Colors.GREEN}[PASS]{Colors.END} Energy values are in reasonable ranges")

        return True

    except Exception as e:
        print(f"{Colors.RED}[FAIL]{Colors.END} Error checking values: {e}")
        return False


def test_visualization_script():
    """Test that the visualization script works."""
    print(f"{Colors.BLUE}[TEST]{Colors.END} Testing visualization script...")

    if not os.path.exists("scripts/visualize.py"):
        print(f"{Colors.RED}[FAIL]{Colors.END} Visualization script not found")
        return False

    report_path = "output/energy_report.json"
    if not os.path.exists(report_path):
        print(f"{Colors.YELLOW}[SKIP]{Colors.END} No energy report to visualize")
        return True

    returncode, stdout, stderr = run_command(
        f"python3 scripts/visualize.py {report_path} --no-html"
    )

    if returncode != 0:
        print(f"{Colors.RED}[FAIL]{Colors.END} Visualization script failed")
        print(stderr)
        return False

    print(f"{Colors.GREEN}[PASS]{Colors.END} Visualization script works")
    return True


def main():
    print("="*70)
    print("LLVM Energy Estimation Pass - Validation Tests")
    print("="*70)
    print()

    tests = [
        ("Energy Model Valid", test_energy_model_valid),
        ("Pass Builds", test_pass_builds),
        ("Example Compilation", test_example_compilation),
        ("Energy Report Format", test_energy_report_format),
        ("Energy Values Reasonable", test_energy_values_reasonable),
        ("Visualization Script", test_visualization_script),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"{Colors.RED}[ERROR]{Colors.END} {test_name}: {e}")
            results.append((test_name, False))
        print()

    # Summary
    print("="*70)
    print("Test Summary")
    print("="*70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = f"{Colors.GREEN}PASS{Colors.END}" if result else f"{Colors.RED}FAIL{Colors.END}"
        print(f"  {status} - {test_name}")

    print()
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print(f"{Colors.GREEN}All tests passed!{Colors.END}")
        return 0
    else:
        print(f"{Colors.RED}Some tests failed{Colors.END}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
