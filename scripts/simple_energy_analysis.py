#!/usr/bin/env python3
"""
Simplified energy estimation tool for Windows
Analyzes assembly output and estimates energy consumption
"""

import json
import re
import sys
from pathlib import Path
from collections import defaultdict

def load_energy_model(model_path):
    """Load energy model from JSON file"""
    with open(model_path, 'r') as f:
        return json.load(f)

def classify_instruction(instr, energy_model):
    """Classify an instruction and return its energy cost"""
    instr = instr.strip().upper()

    # Map instruction patterns to energy classes
    for class_name, class_data in energy_model['instruction_classes'].items():
        for opcode in class_data.get('opcodes', []):
            if instr.startswith(opcode.upper()):
                return class_name, class_data['energy_pj']

    # Default patterns for common instruction types
    if any(instr.startswith(op) for op in ['ADD', 'SUB', 'AND', 'OR', 'XOR', 'MOV', 'CMP', 'TEST']):
        return 'integer_alu', 10.5
    elif any(instr.startswith(op) for op in ['IMUL', 'MUL']):
        return 'integer_multiply', 28.3
    elif any(instr.startswith(op) for op in ['IDIV', 'DIV']):
        return 'integer_divide', 85.7
    elif any(instr.startswith(op) for op in ['LD', 'LDR', 'LOAD', 'MOV']) and '[' in instr:
        return 'load', 45.2
    elif any(instr.startswith(op) for op in ['ST', 'STR', 'STORE']) and '[' in instr:
        return 'store', 52.8
    elif any(instr.startswith(op) for op in ['FADD', 'FSUB', 'VADD', 'VSUB']):
        return 'fp_add_sub', 35.6
    elif any(instr.startswith(op) for op in ['FMUL', 'VMUL']):
        return 'fp_multiply', 48.9
    elif any(instr.startswith(op) for op in ['FDIV', 'VDIV']):
        return 'fp_divide', 124.5
    elif any(instr.startswith(op) for op in ['FSQRT', 'VSQRT']):
        return 'fp_sqrt', 156.8
    elif any(instr.startswith(op) for op in ['B', 'JMP', 'JE', 'JNE', 'JZ', 'JNZ', 'CALL', 'RET']):
        return 'branch', 15.4

    return 'unknown', 10.0  # Default energy for unknown instructions

def parse_assembly(asm_file):
    """Parse assembly file and extract functions and instructions"""
    functions = {}
    current_function = None

    with open(asm_file, 'r') as f:
        for line in f:
            line = line.strip()

            # Detect function start (various assembly formats)
            if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*:', line):
                func_name = line.rstrip(':')
                current_function = func_name
                functions[current_function] = []

            # Skip empty lines, comments, and directives
            elif not line or line.startswith('.') or line.startswith('#') or line.startswith(';'):
                continue

            # Collect instructions
            elif current_function:
                # Remove comments
                instr = re.sub(r'[#;].*$', '', line).strip()
                if instr:
                    functions[current_function].append(instr)

    return functions

def analyze_energy(functions, energy_model):
    """Analyze energy consumption for each function"""
    results = []

    for func_name, instructions in functions.items():
        if not instructions:
            continue

        instruction_classes = defaultdict(int)
        total_energy = 0.0

        for instr in instructions:
            class_name, energy = classify_instruction(instr, energy_model)
            instruction_classes[class_name] += 1
            total_energy += energy

        results.append({
            'name': func_name,
            'total_energy_pj': total_energy,
            'total_instructions': len(instructions),
            'avg_energy_per_instruction': total_energy / len(instructions) if instructions else 0,
            'instruction_classes': dict(instruction_classes)
        })

    return results

def generate_report(results, energy_model, output_file):
    """Generate JSON report"""
    report = {
        'architecture': energy_model.get('architecture', 'x86-64'),
        'processor': energy_model.get('processor', 'Generic'),
        'note': 'Simplified static analysis without frequency weighting',
        'functions': results
    }

    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2)

    return report

def print_summary(results):
    """Print summary to console"""
    print("\n=== Energy Estimation Summary ===\n")

    total_energy = sum(f['total_energy_pj'] for f in results)
    total_instructions = sum(f['total_instructions'] for f in results)

    print(f"Total functions analyzed: {len(results)}")
    print(f"Total instructions: {total_instructions}")
    print(f"Total estimated energy: {total_energy:.2f} pJ\n")

    print("Per-function breakdown:")
    print(f"{'Function':<30} {'Instructions':<15} {'Energy (pJ)':<15} {'Avg/Instr':<15}")
    print("-" * 75)

    for func in sorted(results, key=lambda x: x['total_energy_pj'], reverse=True):
        print(f"{func['name']:<30} {func['total_instructions']:<15} "
              f"{func['total_energy_pj']:<15.2f} {func['avg_energy_per_instruction']:<15.2f}")

def main():
    if len(sys.argv) < 3:
        print("Usage: python simple_energy_analysis.py <assembly_file> <energy_model.json> [output.json]")
        sys.exit(1)

    asm_file = sys.argv[1]
    model_file = sys.argv[2]
    output_file = sys.argv[3] if len(sys.argv) > 3 else 'energy_report.json'

    # Load energy model
    energy_model = load_energy_model(model_file)

    # Parse assembly
    print(f"Parsing assembly file: {asm_file}")
    functions = parse_assembly(asm_file)
    print(f"Found {len(functions)} functions")

    # Analyze energy
    print("Analyzing energy consumption...")
    results = analyze_energy(functions, energy_model)

    # Generate report
    report = generate_report(results, energy_model, output_file)
    print(f"\nJSON report saved to: {output_file}")

    # Print summary
    print_summary(results)

if __name__ == '__main__':
    main()
