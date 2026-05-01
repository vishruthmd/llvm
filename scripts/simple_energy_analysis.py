#!/usr/bin/env python3
"""
Simplified energy estimation tool for Windows
Analyzes assembly output and estimates energy consumption
"""

import json
import re
import sys
from collections import defaultdict


def load_energy_model(model_path):
    """Load energy costs from JSON model"""
    with open(model_path, "r") as f:
        model = json.load(f)
    return model["instructions"]


def parse_assembly(asm_file):
    """Parse AArch64 / x86-64 assembly and extract real instructions."""
    functions = defaultdict(lambda: {"instructions": [], "total_energy": 0})
    current_function = None

    with open(asm_file, "r", errors="replace") as f:
        for raw_line in f:
            line = raw_line.strip()

            # ── Skip empty lines ─────────────────────────────────────────
            if not line:
                continue

            # ── Strip trailing inline comments (// … or # …) ─────────────
            # Do this early so label detection works on lines like:
            #   integer_ops:                // @integer_ops
            line_no_comment = re.split(r"//|#", line)[0].rstrip()

            # ── Skip pure comment or directive lines ─────────────────────
            if not line_no_comment:
                continue
            if line_no_comment.startswith((";", "/*", "*")):
                continue

            # ── Skip assembler directives (.cfi_*, .type, .globl …) ──────
            if line_no_comment.startswith("."):
                continue

            # ── Detect label / function header ───────────────────────────
            # Handles both:  "integer_ops:"  and  "integer_ops:   // comment"
            if line_no_comment.endswith(":"):
                label = line_no_comment[:-1].strip()
                # Global function labels are plain identifiers (no leading dot).
                # Local branch targets start with '.' or digits — skip them.
                if label and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", label):
                    current_function = label
                continue

            # ── Parse instruction ─────────────────────────────────────────
            if current_function:
                parts = line_no_comment.split()
                if not parts:
                    continue
                raw = parts[0]

                instr = raw.upper()

                # Strip AT&T size suffixes: addl→ADD, movq→MOV, imulq→IMUL
                instr = re.sub(r"[BWLQ]$", "", instr)

                # Strip LLVM IR type suffixes: .I32, .F64 → bare mnemonic
                instr = re.sub(r"\.\w+$", "", instr)

                # Must be a plausible mnemonic: 2–12 uppercase alpha chars
                if instr and re.match(r"^[A-Z]{2,12}$", instr):
                    functions[current_function]["instructions"].append(instr)

    return functions


def calculate_energy(functions, energy_model):
    """Calculate total energy per function"""
    results = {"functions": {}, "total_energy_pj": 0, "total_instructions": 0}

    for func_name, data in functions.items():
        total = 0
        instruction_counts = defaultdict(int)

        for instr in data["instructions"]:
            # Look up instruction energy cost
            energy = energy_model.get(instr, energy_model.get("default", 12.0))
            total += energy
            instruction_counts[instr] += 1

        results["functions"][func_name] = {
            "instructions": data["instructions"],
            "instruction_count": len(data["instructions"]),
            "instruction_breakdown": dict(instruction_counts),
            "energy_pj": round(total, 2),
            "energy_nj": round(total / 1000, 2),
        }

        results["total_energy_pj"] += total
        results["total_instructions"] += len(data["instructions"])

    results["total_energy_pj"] = round(results["total_energy_pj"], 2)
    results["total_energy_nj"] = round(results["total_energy_pj"] / 1000, 2)

    return results


def main():
    if len(sys.argv) != 4:
        print(
            "Usage: python simple_energy_analysis.py <assembly.s> <energy_model.json> <output.json>"
        )
        sys.exit(1)

    asm_file = sys.argv[1]
    model_file = sys.argv[2]
    output_file = sys.argv[3]

    print(f"Loading energy model from {model_file}")
    energy_model = load_energy_model(model_file)

    print(f"Parsing assembly from {asm_file}")
    functions = parse_assembly(asm_file)

    if not functions:
        print("ERROR: No functions found in assembly!")
        sys.exit(1)

    print(f"Calculating energy for {len(functions)} functions")
    results = calculate_energy(functions, energy_model)

    # Save results
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to {output_file}")
    print(f"Total Energy: {results['total_energy_nj']} nJ")
    print(f"Total Instructions: {results['total_instructions']}")
    print(f"Functions analyzed: {len(results['functions'])}")

    # Print per-function summary
    for func_name, func_data in results["functions"].items():
        print(
            f"  {func_name}: {func_data['energy_pj']} pJ ({func_data['instruction_count']} instructions)"
        )


if __name__ == "__main__":
    main()
