"""Convert simple_energy_analysis output to visualize_energy.py input format."""

import json
import sys

in_file = sys.argv[1] if len(sys.argv) > 1 else "output/energy_results_raw.json"
out_file = sys.argv[2] if len(sys.argv) > 2 else "output/energy_results.json"

with open(in_file) as f:
    raw = json.load(f)

functions = []
for fname, fdata in raw.get("functions", {}).items():
    e = fdata.get("energy_pj", 0.0)
    functions.append(
        {
            "name": fname,
            "total_energy_pJ": e,
            "blocks": [
                {
                    "name": "body",
                    "raw_energy_pJ": e,
                    "freq_scale": 1.0,
                    "weighted_energy_pJ": e,
                    "instructions": fdata.get("instruction_count", 0),
                }
            ],
        }
    )

functions.sort(key=lambda f: f["total_energy_pJ"], reverse=True)
out = {"arch": "AArch64", "unit": "pJ", "functions": functions}

with open(out_file, "w") as f:
    json.dump(out, f, indent=2)

total = sum(f["total_energy_pJ"] for f in functions)
print(f"Converted {len(functions)} functions — Total: {total:,.2f} pJ")
if functions:
    print(
        f"Hottest : {functions[0]['name']}  ({functions[0]['total_energy_pJ']:,.2f} pJ)"
    )
    print(
        f"Coolest : {functions[-1]['name']}  ({functions[-1]['total_energy_pJ']:,.2f} pJ)"
    )
print(f"Written  : {out_file}")
