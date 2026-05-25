#!/usr/bin/env python3
"""
Energy Estimation Visualization Script

Reads energy analysis results from JSON and generates:
1. HTML report with annotated source code
2. Summary statistics and charts
3. Per-function energy breakdown
"""

import json
import sys
import os
import argparse
from pathlib import Path
from typing import Dict, List, Any
import html


def load_energy_report(json_path: str) -> Dict[str, Any]:
    """Load energy report from JSON file."""
    try:
        with open(json_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Energy report not found at {json_path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {json_path}: {e}", file=sys.stderr)
        sys.exit(1)


def format_energy(energy_pj: float) -> str:
    """Format energy value with appropriate unit."""
    if energy_pj < 1000:
        return f"{energy_pj:.2f} pJ"
    elif energy_pj < 1_000_000:
        return f"{energy_pj / 1000:.2f} nJ"
    elif energy_pj < 1_000_000_000:
        return f"{energy_pj / 1_000_000:.2f} µJ"
    else:
        return f"{energy_pj / 1_000_000_000:.2f} mJ"


def get_energy_color(energy_pj: float, max_energy: float) -> str:
    """Get color based on energy level (green to red gradient)."""
    if max_energy == 0:
        return "#90EE90"

    ratio = energy_pj / max_energy
    if ratio < 0.2:
        return "#90EE90"  # Light green
    elif ratio < 0.4:
        return "#FFFF99"  # Light yellow
    elif ratio < 0.6:
        return "#FFD700"  # Gold
    elif ratio < 0.8:
        return "#FFA500"  # Orange
    else:
        return "#FF6B6B"  # Light red


def generate_summary_html(report: Dict[str, Any]) -> str:
    """Generate summary section of HTML report."""
    functions = report.get('functions', [])
    total_energy = sum(f.get('total_energy_pj', 0) for f in functions)
    total_instructions = sum(f.get('total_instructions', 0) for f in functions)

    html_parts = [
        '<div class="summary">',
        '<h2>Energy Analysis Summary</h2>',
        f'<p><strong>Architecture:</strong> {report.get("architecture", "Unknown")}</p>',
        f'<p><strong>Processor:</strong> {report.get("processor", "Unknown")}</p>',
        f'<p><strong>Total Functions:</strong> {len(functions)}</p>',
        f'<p><strong>Total Energy:</strong> {format_energy(total_energy)}</p>',
        f'<p><strong>Total Instructions:</strong> {total_instructions:,}</p>',
    ]

    if total_instructions > 0:
        avg_energy = total_energy / total_instructions
        html_parts.append(f'<p><strong>Average Energy per Instruction:</strong> {format_energy(avg_energy)}</p>')

    html_parts.append('</div>')
    return '\n'.join(html_parts)


def generate_function_table_html(report: Dict[str, Any]) -> str:
    """Generate function-level energy table."""
    functions = report.get('functions', [])

    if not functions:
        return '<p>No functions analyzed.</p>'

    sorted_functions = sorted(functions,
                             key=lambda f: f.get('total_energy_pj', 0),
                             reverse=True)

    max_energy = max(f.get('total_energy_pj', 0) for f in functions)

    html_parts = [
        '<div class="function-table">',
        '<h2>Per-Function Energy Breakdown</h2>',
        '<table>',
        '<thead>',
        '<tr>',
        '<th>Function</th>',
        '<th>Total Energy</th>',
        '<th>Instructions</th>',
        '<th>Avg Energy/Instr</th>',
        '<th>Energy Distribution</th>',
        '</tr>',
        '</thead>',
        '<tbody>',
    ]

    for func in sorted_functions:
        name = func.get('name', 'unknown')
        energy = func.get('total_energy_pj', 0)
        instructions = func.get('total_instructions', 0)
        avg_energy = func.get('avg_energy_per_instruction', 0)

        bar_width = (energy / max_energy * 100) if max_energy > 0 else 0
        bar_color = get_energy_color(energy, max_energy)

        html_parts.extend([
            '<tr>',
            f'<td class="func-name">{html.escape(name)}</td>',
            f'<td>{format_energy(energy)}</td>',
            f'<td>{instructions:,}</td>',
            f'<td>{format_energy(avg_energy)}</td>',
            f'<td><div class="energy-bar" style="width: {bar_width}%; background-color: {bar_color};"></div></td>',
            '</tr>',
        ])

    html_parts.extend([
        '</tbody>',
        '</table>',
        '</div>',
    ])

    return '\n'.join(html_parts)


def generate_instruction_class_chart(report: Dict[str, Any]) -> str:
    """Generate instruction class breakdown chart."""
    functions = report.get('functions', [])

    class_totals: Dict[str, int] = {}
    for func in functions:
        classes = func.get('instruction_classes', {})
        for class_name, count in classes.items():
            class_totals[class_name] = class_totals.get(class_name, 0) + count

    if not class_totals:
        return '<p>No instruction class data available.</p>'

    sorted_classes = sorted(class_totals.items(), key=lambda x: x[1], reverse=True)
    total_instructions = sum(class_totals.values())

    html_parts = [
        '<div class="instruction-classes">',
        '<h2>Instruction Class Distribution</h2>',
        '<table>',
        '<thead>',
        '<tr>',
        '<th>Instruction Class</th>',
        '<th>Count</th>',
        '<th>Percentage</th>',
        '<th>Distribution</th>',
        '</tr>',
        '</thead>',
        '<tbody>',
    ]

    for class_name, count in sorted_classes:
        percentage = (count / total_instructions * 100) if total_instructions > 0 else 0

        html_parts.extend([
            '<tr>',
            f'<td>{html.escape(class_name)}</td>',
            f'<td>{count:,}</td>',
            f'<td>{percentage:.1f}%</td>',
            f'<td><div class="energy-bar" style="width: {percentage}%; background-color: #4A90E2;"></div></td>',
            '</tr>',
        ])

    html_parts.extend([
        '</tbody>',
        '</table>',
        '</div>',
    ])

    return '\n'.join(html_parts)


def generate_block_details_html(report: Dict[str, Any]) -> str:
    """Generate detailed block-level energy information."""
    functions = report.get('functions', [])

    html_parts = [
        '<div class="block-details">',
        '<h2>Basic Block Energy Details</h2>',
    ]

    for func in functions:
        func_name = func.get('name', 'unknown')
        blocks = func.get('blocks', [])

        if not blocks:
            continue

        html_parts.extend([
            f'<h3>Function: {html.escape(func_name)}</h3>',
            '<table>',
            '<thead>',
            '<tr>',
            '<th>Block</th>',
            '<th>Static Energy</th>',
            '<th>Weighted Energy</th>',
            '<th>Frequency</th>',
            '<th>Instructions</th>',
            '</tr>',
            '</thead>',
            '<tbody>',
        ])

        for block in blocks:
            block_name = block.get('name', 'unknown')
            static_energy = block.get('static_energy_pj', 0)
            weighted_energy = block.get('weighted_energy_pj', 0)
            frequency = block.get('frequency', 0)
            instr_count = block.get('instruction_count', 0)

            html_parts.extend([
                '<tr>',
                f'<td>{html.escape(block_name)}</td>',
                f'<td>{format_energy(static_energy)}</td>',
                f'<td>{format_energy(weighted_energy)}</td>',
                f'<td>{frequency:,}</td>',
                f'<td>{instr_count}</td>',
                '</tr>',
            ])

        html_parts.extend([
            '</tbody>',
            '</table>',
        ])

    html_parts.append('</div>')
    return '\n'.join(html_parts)


def generate_html_report(report: Dict[str, Any], output_path: str):
    """Generate complete HTML report."""

    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Energy Estimation Report</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            border-radius: 8px;
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #34495e;
            margin-top: 30px;
            border-bottom: 2px solid #ecf0f1;
            padding-bottom: 8px;
        }}
        h3 {{
            color: #7f8c8d;
            margin-top: 20px;
        }}
        .summary {{
            background-color: #ecf0f1;
            padding: 20px;
            border-radius: 5px;
            margin-bottom: 30px;
        }}
        .summary p {{
            margin: 8px 0;
            font-size: 16px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        thead {{
            background-color: #3498db;
            color: white;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        tbody tr:hover {{
            background-color: #f8f9fa;
        }}
        .func-name {{
            font-family: 'Courier New', monospace;
            font-weight: bold;
        }}
        .energy-bar {{
            height: 20px;
            background-color: #3498db;
            border-radius: 3px;
            min-width: 2px;
        }}
        .function-table, .instruction-classes, .block-details {{
            margin-top: 30px;
        }}
        .footer {{
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            text-align: center;
            color: #7f8c8d;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Static Energy Estimation Report</h1>

        {generate_summary_html(report)}

        {generate_function_table_html(report)}

        {generate_instruction_class_chart(report)}

        {generate_block_details_html(report)}

        <div class="footer">
            <p>Generated by LLVM Static Energy Estimation Pass</p>
            <p>Energy values based on {html.escape(report.get('processor', 'Unknown'))} architecture</p>
        </div>
    </div>
</body>
</html>
"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_template)

    print(f"HTML report generated: {output_path}")


def print_text_summary(report: Dict[str, Any]):
    """Print text summary to console."""
    print("\n" + "="*70)
    print("ENERGY ESTIMATION SUMMARY")
    print("="*70)
    print(f"Architecture: {report.get('architecture', 'Unknown')}")
    print(f"Processor: {report.get('processor', 'Unknown')}")
    print()

    functions = report.get('functions', {})
    
    # FIX: Handle dict format (key-value pairs)
    if isinstance(functions, dict):
        function_list = list(functions.values())
    else:
        function_list = functions
    
    total_energy = sum(f.get('energy_pj', 0) if isinstance(f, dict) else 0 for f in function_list)
    total_instructions = sum(f.get('instruction_count', 0) if isinstance(f, dict) else 0 for f in function_list)

    print(f"Total Functions: {len(function_list)}")
    print(f"Total Energy: {format_energy(total_energy)}")
    print(f"Total Instructions: {total_instructions:,}")

    if total_instructions > 0:
        avg_energy = total_energy / total_instructions
        print(f"Average Energy per Instruction: {format_energy(avg_energy)}")

    print("\n" + "-"*70)
    print("TOP ENERGY-CONSUMING FUNCTIONS")
    print("-"*70)

    sorted_functions = sorted(
        [(name, data) for name, data in functions.items()] if isinstance(functions, dict) else [(f.get('name', 'unknown'), f) for f in function_list],
        key=lambda x: x[1].get('energy_pj', 0) if isinstance(x[1], dict) else 0,
        reverse=True
    )

    for i, (name, func) in enumerate(sorted_functions[:10], 1):
        energy = func.get('energy_pj', 0) if isinstance(func, dict) else 0
        instructions = func.get('instruction_count', 0) if isinstance(func, dict) else 0
        print(f"{i:2d}. {name:40s} {format_energy(energy):>15s} ({instructions:>6,d} instr)")

    print("="*70 + "\n")


def generate_html(data, output_file):
    """Generate HTML report from energy analysis results"""
    
    # Get functions dict
    if 'functions' in data:
        functions = data['functions']
    else:
        functions = {}
    
    # Sort by energy
    sorted_funcs = sorted(
        functions.items(),
        key=lambda x: x[1].get('energy_pj', 0) if isinstance(x[1], dict) else 0,
        reverse=True
    )
    
    # Calculate totals
    total_energy_pj = data.get('total_energy_pj', 0)
    total_energy_nj = data.get('total_energy_nj', 0)
    total_instructions = data.get('total_instructions', 0)
    
    # Find max energy for bar visualization - FIX: Define this BEFORE using it!
    max_energy = max([f[1].get('energy_pj', 0) for f in sorted_funcs if isinstance(f[1], dict)]) if sorted_funcs else 1
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Energy Estimation Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 3px solid #0066cc; padding-bottom: 10px; margin-bottom: 30px; }}
        h2 {{ color: #0066cc; margin-top: 30px; margin-bottom: 15px; }}
        .summary {{ background: #e8f4f8; padding: 20px; border-radius: 5px; margin: 20px 0; }}
        .summary-item {{ display: inline-block; margin-right: 40px; margin-bottom: 10px; }}
        .summary-item strong {{ color: #0066cc; font-size: 16px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th {{ background: #0066cc; color: white; padding: 12px; text-align: left; font-weight: bold; }}
        td {{ padding: 10px; border-bottom: 1px solid #ddd; }}
        tr:hover {{ background: #f9f9f9; }}
        .bar {{ height: 22px; border-radius: 3px; display: inline-block; min-width: 5px; }}
        .energy-high {{ background: #ff6b6b; }}
        .energy-medium {{ background: #ffa500; }}
        .energy-low {{ background: #51cf66; }}
        .code {{ font-family: monospace; background: #f5f5f5; padding: 5px 8px; border-radius: 3px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Energy Estimation Report</h1>
        
        <div class="summary">
            <div class="summary-item">
                <strong>Total Energy:</strong> {total_energy_nj:.2f} nJ ({total_energy_pj:.2f} pJ)
            </div>
            <div class="summary-item">
                <strong>Total Instructions:</strong> {total_instructions}
            </div>
            <div class="summary-item">
                <strong>Functions/Blocks:</strong> {len(sorted_funcs)}
            </div>
            <div class="summary-item">
                <strong>Avg/Instruction:</strong> {(total_energy_pj/total_instructions if total_instructions > 0 else 0):.2f} pJ
            </div>
        </div>
        
        <h2>Top Energy Consumers</h2>
        <table>
            <tr>
                <th>Function/Block</th>
                <th>Energy (pJ)</th>
                <th>Instructions</th>
                <th>Energy/Instr (pJ)</th>
                <th>Energy Distribution</th>
            </tr>
"""
    
    # Add function rows
    for func_name, func_data in sorted_funcs:
        if not isinstance(func_data, dict):
            continue
            
        energy = func_data.get('energy_pj', 0)
        instr_count = func_data.get('instruction_count', 0)
        energy_per_instr = round(energy / instr_count, 2) if instr_count > 0 else 0
        
        # Determine color
        if energy > max_energy * 0.6:
            color_class = "energy-high"
        elif energy > max_energy * 0.3:
            color_class = "energy-medium"
        else:
            color_class = "energy-low"
        
        bar_width = int((energy / max_energy) * 350) if max_energy > 0 else 0
        
        html += f"""            <tr>
                <td><span class="code">{func_name}</span></td>
                <td>{energy:.2f}</td>
                <td>{instr_count}</td>
                <td>{energy_per_instr}</td>
                <td><div class="bar {color_class}" style="width: {bar_width}px;"></div></td>
            </tr>
"""
    
    html += """        </table>
    </div>
</body>
</html>"""
    
    # Write HTML file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"HTML report generated: {output_file}")

def main():
    parser = argparse.ArgumentParser(
        description='Visualize LLVM energy estimation results'
    )
    parser.add_argument(
        'input',
        nargs='?',
        default='energy_report.json',
        help='Input JSON file from energy analysis (default: energy_report.json)'
    )
    parser.add_argument(
        '-o', '--output',
        default='energy_report.html',
        help='Output HTML file (default: energy_report.html)'
    )
    parser.add_argument(
        '--no-html',
        action='store_true',
        help='Skip HTML generation, only print text summary'
    )

    args = parser.parse_args()

    report = load_energy_report(args.input)
    print_text_summary(report)

    if not args.no_html:
        generate_html(report, args.output)
        print(f"\nOpen {args.output} in a web browser to view the detailed report.")

if __name__ == '__main__':
    main()
