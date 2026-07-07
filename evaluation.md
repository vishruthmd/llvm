# EVALUATION — LLVM Static Energy Estimation Pass

## 1. Metrics

The following metrics are used to evaluate the energy estimation:

| Metric | Description | Unit |
|---|---|---|
| **Total Energy** | Sum of weighted energy across all functions | pJ |
| **Per-Function Energy** | Σ(weighted block energy) per function | pJ |
| **Per-Block Energy** | Σ(instruction energy) × freq_scale per block | pJ |
| **Per-Instruction Energy** | Energy cost of a single opcode instance | pJ |
| **FreqScale** | Block execution frequency relative to function entry | dimensionless |
| **Instruction Count** | Number of real (non-debug, non-pseudo) machine instructions | count |
| **Dynamic Range** | Ratio of hottest to coolest function energy | dimensionless |

## 2. Baseline Comparison

### 2.1 Energy Model

The project uses the ARM Cortex-A55 energy model (`llvm/energy-models/aarch64.json`). See [validation.md](validation.md) for the full cross-check against published literature.

| Feature | Value |
|---|---|
| **Core** | ARM Cortex-A55 |
| **Process node** | 7 nm (TSMC) |
| **Opcodes** | 300+ across 12 categories |
| **LLVM names** | Both canonical mnemonics + LLVM-internal opcode names |
| **Validation** | Cross-checked vs. 5 published sources — 58/58 comparisons pass |

### 2.2 Instruction Energy Costs (Cortex-A55 @ 7 nm)

| Instruction | Energy (pJ) | Relative Cost |
|---|---|---|
| NOP | 0.5 | 0.2× |
| MOV (register) | 1.5 | 0.5× |
| ADD / SUB | 2.8 | 1.0× (baseline) |
| AND / ORR / EOR | 2.7 | 1.0× |
| Shift (LSL/LSR/ASR) | 2.5 | 0.9× |
| Branch (B) | 2.5 | 0.9× |
| RET | 3.0 | 1.1× |
| Conditional branch (Bcc) | 3.5 | 1.3× |
| MUL (32-bit) | 6.5 | 2.3× |
| STR (L1 hit) | 7.2 | 2.6× |
| LDR (L1 hit) | 9.5 | 3.4× |
| FMADD (fused multiply-add) | 10.5 | 3.8× |
| LDP (load pair) | 14.0 | 5.0× |
| SDIV (32-bit) | 18.0 | 6.4× |
| FDIV (single) | 28.0 | 10.0× |
| SVC (system call) | 25.0 | 8.9× |
| FDIV (double) | 34.0 | 12.1× |
| NEON FDIV (v4f32) | 90.0 | 32.1× |

## 3. Test Case: `simple_test.c`

The test file (`simple_test.c` at project root) contains **15 functions** exercising a broad range of instruction categories.

**Results (LLVM EnergyEstimationPass with loop weighting):**

| # | Function | Energy (pJ) | %Total | Instructions | Category |
|---|---|---|---|---|---|
| 1 | `mat_multiply` | 101,011 | 61.8% | 44 | Triple-nested FP loop |
| 2 | `main` | 46,576 | 28.5% | 210 | Driver + initialization |
| 3 | `bubble_sort` | 10,364 | 6.3% | 22 | Nested loop comparisons |
| 4 | `merge_sort` | 3,142 | 1.9% | 144 | Recursive sort |
| 5 | `dot_product` | 844 | 0.5% | 34 | Multiply-accumulate |
| 6 | `fib_recursive` | 331 | 0.2% | 17 | Recursive calls (15 calls) |
| 7 | `crc32` | 198 | 0.1% | 43 | Bit manipulation |
| 8 | `fib_iterative` | 175 | 0.1% | 12 | Loop + ADD |
| 9 | `crc32_byte` | 163 | 0.1% | 37 | Bit manipulation |
| 10 | `factorial` | 153 | 0.1% | 34 | Multiply-heavy loop |
| 11 | `fp_ops` | 145 | 0.1% | 19 | Floating-point |
| 12 | `linear_search` | 99 | 0.1% | 10 | Branchy loop |
| 13 | `sum_array` | 88 | 0.1% | 28 | Load/store + ALU |
| 14 | `integer_ops` | 61 | <0.1% | 15 | ALU operations |
| 15 | `popcount64` | 28 | <0.1% | 5 | Bit manipulation |
| 16 | `my_strlen` | 20 | <0.1% | 6 | Pointer arithmetic |
| 17 | `atomic_increment` | 11 | <0.1% | 6 | Atomic RMW |
| | **Total** | **163,438** | **100%** | **686** | |

**Dynamic range:** ~9,184× (mat_multiply vs. atomic_increment)

### Key Observations

1. **`mat_multiply` dominates (61.8%):** The triple-nested loop (8×8×8 = 512 inner iterations) multiplies the raw block energy by `freq_scale ≈ 512`, turning ~197 pJ raw into ~101,011 pJ weighted.

2. **`main` is second (28.5%):** This includes matrix initialization loops (8×8 = 64 iterations each), plus calls to all 15 functions. The init loops add significant weighted energy.

3. **`bubble_sort` third (6.3%):** O(n²) algorithm with n=64 produces 2,016 inner comparisons. Each comparison includes LDR + CMP + conditional branch + STR ≈ 22 pJ, multiplied by freq_scale ~1,008.

4. **`fp_ops` is cheap despite FP ops:** Only called once — the FreqScale from the single call doesn't amplify it. Most of the energy comes from loop-heavy functions.

5. **Recursive fib is surprisingly low:** fib_recursive(15) makes 1,973 recursive calls, but LLVM's MBFI estimates the entry runs once per call from main, so the FreqScale isn't as high as expected.

## 4. Validation Cross-Check

The model's energy values have been cross-checked against published reference ranges. See [validation.md](validation.md) for full details.

| Instruction Class | Model (pJ) | Published Range (pJ) | In Range? |
|---|---|---|---|
| ADD / SUB | 2.8 | 2.5–3.2 | YES |
| MUL (32-bit) | 6.5 | 5.8–7.2 | YES |
| SDIV (32-bit) | 18.0 | 15–22 | YES |
| LDR (L1 hit) | 9.5 | 8.5–10.5 | YES |
| STR (L1 hit) | 7.2 | 6.5–8.0 | YES |
| FADD (single) | 4.8 | 4.2–5.5 | YES |
| FDIV (single) | 28.0 | 24–34 | YES |

**58/58 reference comparisons passed.**

## 5. Consistency Checks

| Check | Expected | Actual | Result |
|---|---|---|---|
| NOP < MOV < ADD | 0.5 < 1.5 < 2.8 | ✓ | PASS |
| DIV > MUL > ADD | 18.0 > 6.5 > 2.8 | ✓ | PASS |
| FDIV > FMUL > FADD | 28.0 > 9.5 > 4.8 | ✓ | PASS |
| LDR > ADD (mem > ALU) | 9.5 > 2.8 | ✓ | PASS |
| STR < LDR (store < load) | 7.2 < 9.5 | ✓ | PASS |
| All opcodes ≥ 0 energy | min = 0.2 (NOP) | ✓ | PASS |

## 6. HTML Report Features

The interactive HTML report (`report_llvm.html`) includes:

| Section | Label | Description |
|---|---|---|
| **Methodology Guide** | [M] | Explains how energy is calculated, what each column means, model details, limitations — designed for non-technical readers |
| **Summary Table** | [A] | Sortable function table with energy, % total, bar charts, and category badges (HIGH/MEDIUM/LOW) |
| **Block Breakdown** | [B] | Collapsible per-function block details showing raw/weighted energy, freq_scale, and per-instruction (opcode) breakdowns |
| **Distribution Chart** | [C] | SVG donut chart showing energy distribution across functions with colour-coded legend |
| **Source Annotation** | [D] | Line-level energy mapping when `--source` and `--remarks` flags are provided |
| **Theme Toggle** | 🌙/☀️ | Dark/light mode toggle with smooth transitions |

## 7. Known Limitations

| Limitation | Impact |
|---|---|
| **Static frequency estimation** | Frequencies are compile-time heuristics — can be ±30% off vs. actual execution counts |
| **L1 cache hit ALWAYS assumed** | Cache misses cost 3–25× more; #1 source of underestimation |
| **No operand switching activity** | ~10% underestimate on data-dependent ALU energy |
| **No pipeline / IPC modelling** | May overcount on wide-issue superscalar paths |
| **No DVFS or thermal modelling** | Cannot model frequency scaling or throttling |
| **No hardware validation** | Values are **informed by**, not measured against, real hardware |

## 8. Appropriate Use Cases

| Scenario | Recommended? | Rationale |
|---|---|---|
| Comparing algorithms (quick sort vs. merge sort) | ✅ YES | Relative comparison preserves ordering |
| Identifying energy hotspots | ✅ YES | Dynamic range > 9,000× clearly separates hot/cold |
| Compiler optimization tuning | ✅ YES | `-O2` vs. `-Os` trade-offs visible |
| Compute-intensive kernels | ✅ YES | ALU/FP activity well-predicted |
| Educational demonstrations | ✅ YES | Shows where energy goes in code |
| Absolute battery life prediction | ❌ NO | Static heuristic, not measurement |
| Safety-critical energy budgeting | ❌ NO | Needs hardware-validated data |

## 9. Reproduction

To reproduce these results:

```
cd llvm_pipeline
run.bat
```

Output files:
- `output/report_llvm.html` — interactive HTML report
- `output/energy_results.json` — structured data (JSON)

To run on a different `.c` file:
```
run.bat path\to\your_file.c
```
