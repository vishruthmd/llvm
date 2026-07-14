/*
 * simple_test.c — Comprehensive Energy Estimation Test
 * ======================================================
 *
 * Test file for the LLVM EnergyEstimationPass.
 *
 * Run via:
 *   cd llvm_pipeline && run.bat
 *
 * Or manually:
 *   clang -O2 -target aarch64-linux-gnu -emit-llvm -c simple_test.c -o simple_test.bc
 *   llc -stop-after=finalize-isel simple_test.bc -o simple_test.mir -mtriple aarch64-linux-gnu
 *   llc -load EnergyEstimationPass.so -run-pass=energy-estimation   \
 *       -energy-model energy-models/aarch64.json                    \
 *       -energy-output results.json                                 \
 *       -mtriple aarch64-linux-gnu simple_test.mir -o simple_test.s
 *   python visualize_energy.py results.json --output report.html
 *
 * Covers 15 different functions exercising:
 *   - Integer ALU (add/sub/mul/div/shift/bitwise)
 *   - Floating-point arithmetic (add/sub/mul/div)
 *   - Load/store with array access patterns
 *   - Nested loops (matrix multiply — most energy-intensive)
 *   - Recursive functions (Fibonacci)
 *   - Sorting algorithms (bubble sort, merge sort)
 *   - Bit manipulation (popcount, CRC-32)
 *   - String operations (strlen)
 *   - Atomic operations (atomic increment via __atomic builtins)
 *   - Linear search (branchy loop)
 *
 * No standard library dependencies — all functions are self-contained.
 * Uses volatile sinks to prevent dead-code elimination at -O2.
 */

#include <stdint.h>
#include <stddef.h>

/* ─── Constants ─────────────────────────────────────────────────────────── */
#define N       64      /* Array size for most operations */
#define M       8       /* Matrix dimension (keeps runtime low) */
#define WARMUP  8       /* Iterations for warmup loops */

/* ─── 1. Simple integer arithmetic ─────────────────────────────────────── */
/* Exercises: ADD, SUB, MUL, SDIV, AND, OR, EOR, LSL, LSR, ASR, CMP, B
 * Each integer ALU instruction costs ~2.5-3.5 pJ on Cortex-A55.
 * SDIV is the most expensive ALU instruction at ~18 pJ because it
 * requires multiple cycles in the divider unit.
 */
int integer_ops(int a, int b) {
    int sum  = a + b;           /* ADDWri     — 2.8 pJ */
    int diff = a - b;           /* SUBWri     — 2.8 pJ */
    int prod = a * b;           /* MULWr      — 6.5 pJ (2.3x ADD) */
    int quot = (b != 0) ? (a / b) : 0;  /* SDIVWr  — 18.0 pJ (6.4x ADD) */
    int band = a & b;           /* ANDWrs     — 3.0 pJ */
    int bor  = a | b;           /* ORRWrs     — 3.0 pJ */
    int bxor = a ^ b;           /* EORWrs     — 3.0 pJ */
    int lsl  = a << 3;          /* LSLWri     — 2.5 pJ */
    int lsr  = (unsigned int)a >> 2;  /* LSRWri — 2.5 pJ */
    int asr  = a >> 1;          /* ASRWri     — 2.5 pJ */
    return sum + diff + prod + quot + band + bor + bxor + lsl + lsr + asr;
}

/* ─── 2. Floating-point arithmetic ─────────────────────────────────────── */
/* Exercises: FADD, FSUB, FMUL, FDIV, FCMP, FMOV
 * FP ops cost 2-10x more than integer ops due to wider datapaths.
 * FDIV is expensive (~28 pJ) — it uses iterative approximation hardware.
 * FMADD (fused multiply-add) is efficient: one instruction = one mul + one add.
 */
double fp_ops(double x, double y) {
    double sum  = x + y;        /* FADDDrr    — 5.2 pJ */
    double diff = x - y;        /* FSUBDrr    — 5.2 pJ */
    double prod = x * y;        /* FMULDrr    — 10.2 pJ (2x FADD) */
    double quot = (y != 0.0) ? (x / y) : 0.0; /* FDIVDrr — 34.0 pJ (6.5x FADD) */
    double fma  = x * y + sum;  /* FMADDDrrr  — 11.5 pJ (efficient fused op) */
    double t    = (x > 0.0) ? x : -x;  /* FABSD + FCMP — ~7.7 pJ combined */
    double sq   = t * 0.5;      /* FMULDrr    — 10.2 pJ */
    return sum + diff + prod + quot + fma + sq;
}

/* ─── 3. Array sum — memory + ALU ──────────────────────────────────────── */
/* Exercises: LDR, ADD, CMP, B (loop), CSEL
 * Loads cost ~9.5 pJ (L1 cache hit). Each loop iteration:
 *   LDR (9.5) + ADD (2.8) + CMP (2.6) + B (2.5) ≈ 17.4 pJ/iteration
 * Running N=64 times → ~1,114 pJ unweighted.
 * With freq_scale from loop: weighted = 1,114 × (64/2) ≈ 35,648 pJ
 */
int sum_array(int *arr, int n) {
    int total = 0;
    for (int i = 0; i < n; i++) {
        total += arr[i];
    }
    return total;
}

/* ─── 4. Factorial — multiply-heavy ────────────────────────────────────── */
/* Exercises: MUL (expensive!), loop control
 * MUL costs ~6.5 pJ vs ADD's ~2.8 pJ — MUL is 2.3x more expensive.
 * For factorial(10): 9 multiplications × 6.5 pJ = 58.5 pJ raw.
 * With loop freq_scale: weighted ≈ 58.5 × 5.5 = 322 pJ.
 */
int factorial(int n) {
    int result = 1;
    for (int i = 2; i <= n; i++) {
        result *= i;            /* MULWr — 6.5 pJ each */
    }
    return result;
}

/* ─── 5. Nested-loop matrix multiply — most energy-intensive ────────────── */
/* Exercises: triple-nested loops, FMUL/FADD, indexed LDR/STR
 * WHY THIS DOMINATES: M=8 means 8×8×8 = 512 inner iterations.
 * Inner block has ~22 instructions including FMUL (9.5 pJ) and FADD (4.8 pJ).
 * Raw inner block energy: ~71.9 pJ. Freq_scale = 512× (loop trip count).
 * Weighted: 71.9 × 512 = 36,813 pJ just for the inner block.
 * Total for matmul: ~50,000+ pJ — typically 80-95% of all energy.
 */
void mat_multiply(float C[M][M], float A[M][M], float B[M][M]) {
    for (int i = 0; i < M; ++i) {
        for (int j = 0; j < M; ++j) {
            float acc = 0.0f;
            for (int k = 0; k < M; ++k) {
                acc += A[i][k] * B[k][j];   /* FMUL + FADD */
            }
            C[i][j] = acc;                  /* STR */
        }
    }
}

/* ─── 6. Recursive Fibonacci — function calls ──────────────────────────── */
/* Exercises: BL/BLR (4.0 pJ), RET (3.0 pJ), CBZ (3.5 pJ), CMP (2.6 pJ)
 * Each recursive call costs ~13 pJ just for call/return overhead.
 * fib(20) makes 21,891 calls → ~284,583 pJ just for call overhead.
 * This is why fib dominates in the old x86 report despite small code size.
 * With block frequency weighting from recursion, the entry block is
 * visited 21,891 times: freq_scale = 21,891×.
 */
long long fib_recursive(int n) {
    if (n <= 1) return (long long)n;  /* CBZ/CMP + RET — ~6.6 pJ */
    return fib_recursive(n - 1) + fib_recursive(n - 2);  /* BL + BL + ADD */
}

/* ─── 7. Iterative Fibonacci — loop version ─────────────────────────────── */
/* Exercises: loop, ADD (2.8 pJ), CMP (2.6 pJ), B (2.5 pJ)
 * Much more efficient than recursive: O(n) vs O(2^n) calls.
 * For n=50: ~48 iterations × ~10.5 pJ/iter = 504 pJ raw.
 * With freq_scale: ~504 × 25 = 12,600 pJ.
 * Compare to recursive fib(20) which makes 21,891 calls!
 */
long long fib_iterative(int n) {
    if (n <= 0) return 0;
    if (n == 1) return 1;
    long long prev = 0, curr = 1;
    for (int i = 2; i <= n; ++i) {
        long long next = prev + curr;  /* ADD */
        prev = curr;
        curr = next;
    }
    return curr;
}

/* ─── 8. Popcount — bit manipulation ────────────────────────────────────── */
/* Exercises: AND (2.7 pJ), SUB (2.8 pJ), CBNZ (3.5 pJ), LSR (2.5 pJ)
 * Brian Kernighan's method: each iteration clears the lowest set bit.
 * For 64-bit input: at most 64 iterations, on average ~32.
 * Each iteration: AND + SUB + CBNZ + conditional ops ≈ 12 pJ/iter.
 */
unsigned popcount64(uint64_t x) {
    unsigned count = 0;
    while (x) {             /* CBNZ — 3.5 pJ */
        x &= (x - 1);       /* ANDWrs (3.0) + SUBWri (2.8) = 5.8 pJ */
        ++count;            /* ADDWri — 2.8 pJ */
    }
    return count;
}

/* ─── 9. Bubble sort — comparison-heavy nested loops ────────────────────── */
/* Exercises: nested loops, LDR/STR, CMP/CSEL, conditional branches
 * O(n²) algorithm — for n=64: 64×63/2 = 2,016 comparisons.
 * Each inner iteration: LDR (9.5) + CMP (2.6) + B (2.5) + STR (7.2) ≈ 22 pJ.
 * Raw: 2,016 × 22 = 44,352 pJ. With freq_scale: weighted much higher.
 */
void bubble_sort(int *arr, int n) {
    for (int i = 0; i < n - 1; ++i) {
        for (int j = 0; j < n - i - 1; ++j) {
            if (arr[j] > arr[j + 1]) {     /* LDR + CMP */
                int tmp = arr[j];
                arr[j] = arr[j + 1];       /* STR */
                arr[j + 1] = tmp;          /* STR */
            }
        }
    }
}

/* ─── 10. String length — pointer arithmetic ───────────────────────────── */
/* Exercises: LDRB (9.0 pJ), CBZ (3.5 pJ), ADD (2.8 pJ), SUB (2.8 pJ)
 * For a 28-char string: 29 iterations (including null terminator check).
 * Each iteration: LDRB (9.0) + ADD (2.8) + CBZ/CMP (3.5) ≈ 15.3 pJ/char.
 * Raw: 29 × 15.3 = 444 pJ. With freq_scale: weighted ≈ 444 pJ.
 */
size_t my_strlen(const char *s) {
    const char *p = s;
    while (*p) ++p;          /* LDRBBui — 8.8 pJ, CBZ — 3.5 pJ */
    return (size_t)(p - s);  /* SUB — 2.8 pJ */
}

/* ─── 11. CRC-32 checksum — bit manipulation heavy ──────────────────────── */
/* Exercises: XOR (2.7 pJ), AND (2.7 pJ), LSR (2.5 pJ), conditional branches
 * Each byte: 8 iterations of the bit loop.
 * For 256 bytes (N*sizeof(int)): 256 × 8 = 2,048 inner iterations.
 * Inner loop: ~5 instructions × ~3 pJ avg = 15 pJ/iter.
 * Raw: 2,048 × 15 = 30,720 pJ. With freq_scale: weighted much higher.
 */
uint32_t crc32_byte(uint32_t crc, uint8_t data) {
    crc ^= (uint32_t)data;           /* EORWrs — 3.0 pJ */
    for (int i = 0; i < 8; ++i) {
        if (crc & 1u)                /* TSTWri (2.6) + conditional branch */
            crc = (crc >> 1) ^ 0xEDB88320u;  /* LSR (2.5) + EOR (2.7) = 5.2 pJ */
        else
            crc >>= 1;               /* LSR — 2.5 pJ */
    }
    return crc;
}

uint32_t crc32(const uint8_t *buf, size_t len) {
    uint32_t crc = 0xFFFFFFFFu;
    for (size_t i = 0; i < len; ++i)
        crc = crc32_byte(crc, buf[i]);
    return crc ^ 0xFFFFFFFFu;
}

/* ─── 12. Merge sort — recursive sorting ────────────────────────────────── */
/* Exercises: recursion, LDR/STR, CMP, conditional branches, CSEL
 * Merge sort is O(n log n) — for n=64: ~64 × 6 = 384 element merges.
 * Each merge step: compare + copy operations ≈ 20 pJ per element.
 * Raw: 384 × 20 = 7,680 pJ.
 */
static void merge(int *arr, int *tmp, int left, int mid, int right) {
    int i = left, j = mid, k = left;
    while (i < mid && j < right) {
        if (arr[i] <= arr[j])               /* LDR + CMP + CSEL */
            tmp[k++] = arr[i++];            /* LDR + STR */
        else
            tmp[k++] = arr[j++];            /* LDR + STR */
    }
    while (i < mid)   tmp[k++] = arr[i++];
    while (j < right) tmp[k++] = arr[j++];
    for (int l = left; l < right; ++l)
        arr[l] = tmp[l];                    /* LDR + STR */
}

void merge_sort(int *arr, int *tmp, int left, int right) {
    if (right - left < 2) return;           /* CMP + B */
    int mid = (left + right) / 2;
    merge_sort(arr, tmp, left, mid);        /* BL — recursive */
    merge_sort(arr, tmp, mid, right);       /* BL — recursive */
    merge(arr, tmp, left, mid, right);      /* BL — merge */
}

/* ─── 13. Atomic increment ───────────────────────────────────────────────── */
/* Exercises: LDXR (11.5 pJ), ADD (2.8 pJ), STXR (9.0 pJ), CBNZ (3.5 pJ)
 * The compare-and-swap loop: on success, 1 iteration (~27 pJ).
 * On contention (rare in single-thread): retry loop.
 * Each call costs roughly 27 pJ for the successful CAS.
 */
void atomic_increment(volatile int *counter) {
    /* In AArch64 lowering this becomes: LDXR, ADD, STXR loop */
    __atomic_fetch_add(counter, 1, __ATOMIC_SEQ_CST);
}

/* ─── 14. Linear search — branchy loop ──────────────────────────────────── */
/* Exercises: LDR (9.5 pJ), CMP (2.6 pJ), conditional branch, B
 * Worst case: n comparisons. For n=64: 64 iterations.
 * Each iteration: LDR (9.5) + CMP (2.6) + B (2.5) + CBZ (3.5) ≈ 18 pJ.
 * Raw: 64 × 18 = 1,152 pJ. With freq_scale: ~1,152 × 32 = 36,864 pJ.
 */
int linear_search(int *arr, int n, int target) {
    for (int i = 0; i < n; ++i) {
        if (arr[i] == target) return i;     /* LDR + CMP + CBZ */
    }
    return -1;
}

/* ─── 15. Dot product ───────────────────────────────────────────────────── */
/* Exercises: LDR (9.5), MUL (6.5), SMLAL/ADD (2.8), loop control
 * For n=64: 64 iterations. Each: 2× LDR + MUL + ADD ≈ 28.3 pJ/iter.
 * Raw: 64 × 28.3 = 1,811 pJ. With freq_scale: much higher.
 */
long long dot_product(const int *restrict a, const int *restrict b, int n) {
    long long acc = 0;
    for (int i = 0; i < n; ++i) {
        /* LDR + LDR + SMADDL + ADD/scalar extend */
        acc += (long long)a[i] * (long long)b[i];
    }
    return acc;
}

/* ─── Driver / main ────────────────────────────────────────────────────── */
/* Uses volatile results to prevent dead-code elimination.
 * Without volatile, the compiler would see the results are never used
 * and optimize away entire function calls at -O2.
 */

/* Static buffers (in BSS, not on stack) to avoid stack size limits */
static int   int_buf[N];
static int   int_tmp[N];
static float mat_a[M][M];
static float mat_b[M][M];
static float mat_c[M][M];

/* Volatile sinks — writes to these prevent the compiler from discarding
 * the results of function calls, even if the values are never read back. */
volatile long long  result_ll;
volatile int        result_i;
volatile uint32_t   result_u32;
volatile size_t     result_sz;

int main(void) {
    /* ── Initialise buffers ────────────────────────────────────────────── */
    /* This loop generates LDR/STR pairs with strided access patterns.
     * Each iteration: STR (7.2 pJ), ADD (2.8 pJ), CMP (2.6 pJ), B (2.5 pJ)
     * For N=64: 64 iterations × ~15 pJ = 960 pJ raw.
     */
    for (int i = 0; i < N; ++i) {
        int_buf[i] = i * 7 + 3;             /* MUL + ADD + STR */
    }

    /* Matrix initialisation — nested loops: 8×8 = 64 iterations per matrix */
    for (int i = 0; i < M; ++i)
        for (int j = 0; j < M; ++j) {
            mat_a[i][j] = (float)(i + j + 1);   /* SITOF + STR */
            mat_b[i][j] = (float)(i * j + 1);   /* MUL + SITOF + STR */
        }

    /* ── Run all 14 functions ──────────────────────────────────────────── */
    result_i  = integer_ops(42, 7);             /* 1. Integer ALU */
    result_ll = (long long)fp_ops(3.14159, 2.71828);  /* 2. FP arithmetic */
    result_i  = sum_array(int_buf, N);          /* 3. Array sum */
    result_i  = factorial(10);                  /* 4. Factorial */
    mat_multiply(mat_c, mat_a, mat_b);          /* 5. Matrix multiply (HEAVY) */
    result_ll = fib_recursive(15);              /* 6. Recursive Fibonacci */
    result_ll = fib_iterative(50);              /* 7. Iterative Fibonacci */
    result_u32 = popcount64(0xDEADBEEFCAFEBABEULL);  /* 8. Popcount */
    bubble_sort(int_buf, N);                    /* 9. Bubble sort */

    {   /* 10. String length (scoped to limit stack) */
        const char *s = "Hello, AArch64 Energy Model!";
        result_sz = my_strlen(s);
    }

    result_u32 = crc32((const uint8_t *)int_buf, N * sizeof(int));  /* 11. CRC-32 */
    merge_sort(int_buf, int_tmp, 0, N);         /* 12. Merge sort */

    {   /* 13. Atomic increment */
        volatile int counter = 0;
        for (int i = 0; i < WARMUP; ++i)
            atomic_increment((int*)&counter);
        result_i = counter;
    }

    /* Reset buffer for linear search (bubble_sort scrambled it) */
    for (int i = 0; i < N; ++i)
        int_buf[i] = i * 7 + 3;
    result_i = linear_search(int_buf, N, 42);   /* 14. Linear search */

    /* 15. Dot product */
    result_ll = dot_product(int_buf, int_buf, N);

    return (int)(result_i & 0xFF);
}
