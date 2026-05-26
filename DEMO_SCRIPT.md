# Demo Video Script — LLVM Static Energy Estimation Pass

## Overview

This script walks through recording a ~5 minute demo showing:
1. **Working case** (3 min) — Full pipeline from C source → energy report
2. **Limitation/failure case** (2 min) — Showing what the tool cannot do

---

## Prerequisites for Recording

- A terminal with dark background (green/cyan text for energy output)
- Python 3, Clang, and the project cloned
- `cd` into the project root directory
- Run `chmod +x build.sh run.sh run_simple.sh` if on Linux/macOS
- Screen recording software (OBS, QuickTime, Xbox Game Bar, etc.)

---

## Part 1: Working Case (~3 minutes)

### Scene 1: Project Tour (30s)

```
 Show the project file tree
 > ls -la
 > tree -L 2   (or just scroll through files)
```

**Narrator voiceover:**
> "This is the LLVM Static Energy Estimation Pass — a compiler-integrated tool that estimates per-function and per-block energy consumption at compile time. No hardware needed."

### Scene 2: Run the Simple Pipeline (60s)

```
 Show the command and output:
 > ./run_simple.sh examples/simple_test.c
```

**Narrator:**
> "Let's run it on a comprehensive test file with 13 functions. The simple pipeline compiles the C source to assembly, then parses the assembly and looks up each instruction's energy cost in our JSON model."

**Expected terminal output:**
```
=== Static Energy Estimation (Simple Pipeline) ===
Input file: examples/simple_test.c

[1/5] Compiling to assembly...
       Written: output/test.s
[2/5] Selecting energy model...
       Model: llvm/energy-models/aarch64.json
  Detected architecture: x86-64
[3/5] Analyzing energy consumption...
       Written: output/energy_results_raw.json
[4/5] Converting to standard format...
       Written: output/energy_results.json
[5/5] Generating HTML report...
       Written: output/energy_report.html  [new visualizer]

=== Analysis Complete ===
```

> **⌨️ Action:** After the command completes, scroll up to show the ASCII summary table in the terminal.

### Scene 3: ASCII Energy Summary (30s)

```
 Zoom in on the ASCII output:
```

**Expected output to show:**
```
  Function                          Energy (pJ)   %Total  Chart
  --------------------------------------------------------------------
  main                               2,742.80    33.4%  [####################]
  mat_multiply                       2,127.90    25.9%  [################--]
  factorial                            618.50     7.5%  [#####---------------]
  quick_sort                           495.30     6.0%  [####----------------]
  bubble_sort                          356.10     4.3%  [###-----------------]
  sum_array                            343.90     4.2%  [###-----------------]
  crc32                                328.70     4.0%  [###-----------------]
  fp_ops                               320.60     3.9%  [###-----------------]
  fib_iterative                        222.90     2.7%  [##------------------]
  fib_recursive                        169.40     2.1%  [#-------------------]
  integer_ops                          169.30     2.1%  [#-------------------]
  is_palindrome                          91.60     1.1%  [#-------------------]
  linear_search                          87.70     1.1%  [--------------------]
  popcount                               79.20     1.0%  [--------------------]
  crc32_byte                             64.50     0.8%  [--------------------]
```

**Narrator:**
> "Here's the per-function energy breakdown. `main` and `mat_multiply` dominate — that's expected for a matrix multiply-heavy workload. The color coding shows hot (red) vs warm (yellow) vs cool (green) functions. The dynamic range is 42x from hottest to coolest."

### Scene 4: HTML Report — Summary Table (30s)

```
 Open output/energy_report.html in a browser
 Point to:
   - Sortable columns (click on "Energy" header to sort)
   - Heat-map bars
   - [HIGH] / [MEDIUM] / [LOW] badges
   - Donut chart showing energy distribution
```

**Narrator:**
> "The interactive HTML report opens in your browser. We have sortable columns, heat-map bars showing relative energy cost, and category badges. The donut chart shows that main and mat_multiply together account for nearly 60% of total energy."

### Scene 5: HTML Report — Block Breakdown (30s)

```
 Click on the "mat_multiply" function row to expand the block breakdown
 Show per-opcode breakdown nested inside
```

**Narrator:**
> "Expanding a function shows per-block breakdown with raw energy, frequency scale, weighted energy, and instruction count. Further down we can see per-instruction opcode analysis — MOVAPS and MOVSS are the most frequent instructions in this function."

---

## Part 2: Limitation/Failure Case (~2 minutes)

### Scene 6: Compare with Simple Compute Function (45s)

```
 Run the pipeline on examples/test.c (simple 5-function test):
 > ./run_simple.sh examples/test.c
```

**Narrator:**
> "This test file has only 5 simple functions — sum, factorial, divide_loop, count_evens, and array_sum. The results look reasonable:"

```
  sum                300.20 pJ
  factorial          291.40 pJ
  divide_loop        185.60 pJ
  count_evens        155.10 pJ
  array_sum          142.80 pJ
```

**Narrator:**
> "The divide_loop function is correctly identified as the third most expensive — SDIV instructions cost about 18 pJ each vs. 2.8 pJ for ADD. This cross-check validates that the model's relative ordering makes sense."

### Scene 7: The Cache Miss Problem (45s)

```
 Switch to showing a comparison table:
```

**Narrator:**
> "Here's the #1 limitation. Our tool assumes L1 cache hits for ALL loads and stores. In reality:"

```
 L1 hit:      9.5 pJ  (what we estimate)
 L2 hit:    ~35 pJ   (3.5x more)
 DRAM:     ~250 pJ   (25x more)
```

**Narrator:**
> "For memory-intensive code like array_copy or merge_sort, our tool may underestimate real energy by 3-25x. That's the single largest source of error in static estimation."

### Scene 8: The Hardware Validation Gap (30s)

```
 Show the disclaimer from VALIDATION.md or README.md:
```

**Narrator:**
> "Finally, the most important caveat: this tool produces **heuristic estimates**, not measured values. The energy model is informed by published academic data from different hardware (28nm-45nm processors), scaled down to approximate 7nm. Without physical measurement, all numbers should be treated as relative guidance, not absolute predictions."

---

## Part 3: Closing (30s)

### Scene 9: Summary Card

```
 Hold up a summary frame (or use a slide):
```

**Narrator:**
> "In summary: the LLVM Static Energy Estimation Pass provides useful relative energy comparisons at compile time — great for algorithm selection, hotspot identification, and compiler optimization tuning. But it's not a substitute for hardware measurement. For production use, pair it with physical current sensing or performance counters."

---

## Screenshot Checklist

For a screenshot-based demo, capture:

| # | What to Capture | Details |
|---|---|---|
| 1 | Terminal: `run_simple.sh` output | Full pipeline output showing all 5 steps |
| 2 | Terminal: ASCII summary table | Function list with colored energy bars |
| 3 | Browser: Report header | Dark-themed header with badges |
| 4 | Browser: Summary table sorted by energy | Click "Energy" column header |
| 5 | Browser: Donut chart | SVG donut with energy distribution |
| 6 | Browser: Expanded block breakdown | Click a function row |
| 7 | Browser: Opcode breakdown | Nested instruction table |
| 8 | Terminal: Simple test output | examples/test.c results |
| 9 | The disclaimer/limitation | From VALIDATION.md footer |

---

## Recording Tips

- **Resolution:** 1920×1080 or 1280×720
- **Terminal font:** Use a monospace font at 14-16pt
- **Terminal theme:** Dark background (solarized, monokai, or similar)
- **No mouse jitter:** Use slow, deliberate movements
- **Audio:** Clear voice, ~150 words per minute
- **Total length:** Aim for 4-6 minutes

---

## Suggested Narration Script (Full)

```
"Hi! Today I'm demoing my LLVM Static Energy Estimation Pass —
a compiler-integrated tool that estimates energy consumption
at compile time without any hardware profiler.

[show project structure]

It works by combining per-instruction energy costs from published
ARM microarchitecture data with LLVM's static block frequency
analysis to estimate per-function and per-block energy.

[run simple pipeline]

Let's run it on a comprehensive test file. The pipeline compiles
the C source to assembly, parses it, looks up each instruction
in our energy model, and generates an interactive HTML report.

[show ASCII output]

The summary shows 15 functions analyzed with a total of 8,218 pJ.
Main and mat_multiply dominate — that's expected for a test that
includes matrix multiplication. The color-coded bars make it easy
to spot hotspots at a glance.

[show HTML report]

The HTML report adds sortable columns, heat-map bars, category badges,
and a donut chart showing energy distribution. Expanding a function
reveals per-block breakdown with frequency scaling, and a nested
per-instruction opcode analysis.

[limitation case]

But here's the important limitation. Our tool assumes L1 cache hits
for ALL memory operations. Real cache misses can cost 3 to 25 times
more energy. For memory-intensive code like merge_sort, our estimates
can be significantly off.

[closing]

So this tool is great for relative comparisons — finding hotspots,
comparing algorithms, tuning compiler flags. But don't use it for
absolute battery life predictions without hardware validation.
Thanks for watching!"
```
