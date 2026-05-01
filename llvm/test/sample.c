/*
 * sample.c — Test program for the LLVM Static Energy Estimation Pass
 *
 * Exercises a broad range of AArch64 instruction categories so the energy
 * model is exercised meaningfully:
 *
 *   - Integer ALU (add/sub/mul/div)
 *   - Bitwise and shift operations
 *   - Load/store (array access patterns)
 *   - Branches and conditional logic
 *   - Floating-point arithmetic
 *   - Loops (exposing block-frequency weighting)
 *   - Function calls (exercising CALL / RET)
 *   - Recursive functions (fibonacci)
 *
 * Compile to LLVM IR (for IR-level passes):
 *   clang -O2 -target aarch64-linux-gnu -emit-llvm -c sample.c -o sample.bc
 *
 * Compile to AArch64 assembly (for machine-level passes / llc):
 *   clang -O2 -target aarch64-linux-gnu -S sample.c -o sample.s
 *
 * Run energy estimation pass:
 *   llc -load ./EnergyEstimationPass.so                            \
 *       -energy-estimation                                          \
 *       -energy-model ../energy-models/aarch64.json                \
 *       -energy-output results.json                                 \
 *       -Rpass-analysis=energy                                      \
 *       sample.bc -o sample.s 2>remarks.txt
 */

#include <stdint.h>
#include <stddef.h>

/* ─── Constants ─────────────────────────────────────────────────────────── */
#define N       256
#define M       16
#define WARMUP  8

/* ─── 1. Simple integer arithmetic ─────────────────────────────────────── */

/* Exercises: ADD, SUB, MUL, SDIV, AND, OR, EOR, LSL, LSR, ASR, CMP, B */
int integer_ops(int a, int b) {
    int sum  = a + b;
    int diff = a - b;
    int prod = a * b;
    int quot = (b != 0) ? (a / b) : 0;
    int band = a & b;
    int bor  = a | b;
    int bxor = a ^ b;
    int lsl  = a << 3;
    int lsr  = (unsigned int)a >> 2;
    int asr  = a >> 1;
    return sum + diff + prod + quot + band + bor + bxor + lsl + lsr + asr;
}

/* ─── 2. Floating-point arithmetic ─────────────────────────────────────── */

/* Exercises: FADD, FSUB, FMUL, FDIV, FMADD, FSQRT, FCMP */
double fp_ops(double x, double y) {
    double sum  = x + y;
    double diff = x - y;
    double prod = x * y;
    double quot = (y != 0.0) ? (x / y) : 0.0;
    double fma  = x * y + sum;   /* fused multiply-add */
    /* Manual integer sqrt approximation to avoid linking libm */
    double t = (x > 0.0) ? x : -x;
    double sq = t * 0.5;  /* rough approximation to avoid sqrt */
    return sum + diff + prod + quot + fma + sq;
}

/* ─── 3. Array loads and stores ─────────────────────────────────────────── */

/* Exercises: LDRWui, STRWui, LDPWi, STPWi, loop control */
void array_copy(int * restrict dst, const int * restrict src, int n) {
    for (int i = 0; i < n; ++i) {
        dst[i] = src[i];
    }
}

/* ─── 4. Vectorisable dot product (potential NEON generation) ─────────── */

/* Exercises: LDRWui, MUL/MADD (or NEON MLA), accumulate loop */
long long dot_product(const int * restrict a, const int * restrict b, int n) {
    long long acc = 0;
    for (int i = 0; i < n; ++i) {
        acc += (long long)a[i] * (long long)b[i];
    }
    return acc;
}

/* ─── 5. Matrix multiply kernel ─────────────────────────────────────────── */

/* Exercises: multi-level loops, MADD/MUL, indexed loads, CBZ/CBNZ */
void matmul(float C[M][M], const float A[M][M], const float B[M][M]) {
    for (int i = 0; i < M; ++i) {
        for (int j = 0; j < M; ++j) {
            float acc = 0.0f;
            for (int k = 0; k < M; ++k) {
                acc += A[i][k] * B[k][j];   /* FMLAv? or FMADDSrrr */
            }
            C[i][j] = acc;
        }
    }
}

/* ─── 6. Recursive Fibonacci (exercises BL / RET / CBZ) ─────────────── */

long long fib_recursive(int n) {
    if (n <= 1) return (long long)n;
    return fib_recursive(n - 1) + fib_recursive(n - 2);
}

/* ─── 7. Iterative Fibonacci (exercises loop, MADD pattern) ─────────── */

long long fib_iterative(int n) {
    if (n <= 0) return 0;
    if (n == 1) return 1;
    long long prev = 0, curr = 1;
    for (int i = 2; i <= n; ++i) {
        long long next = prev + curr;
        prev = curr;
        curr = next;
    }
    return curr;
}

/* ─── 8. Bitwise population count ────────────────────────────────────── */

/* Exercises: CLZ, RBIT, EOR, AND, LSR chain — or NEON CNT on wide paths */
unsigned popcount64(uint64_t x) {
    /* Brian Kernighan's method */
    unsigned count = 0;
    while (x) {
        x &= (x - 1);   /* clear lowest set bit */
        ++count;
    }
    return count;
}

/* ─── 9. Memory barrier / atomic pattern ────────────────────────────── */

/* Exercises: LDAR, STLR, DSB, DMB patterns (via __atomic builtins) */
void atomic_increment(volatile int *counter) {
    /* In AArch64 lowering this becomes: LDXR, ADD, STXR loop */
    __atomic_fetch_add(counter, 1, __ATOMIC_SEQ_CST);
}

/* ─── 10. String length (pointer arithmetic, LDRB, CBZ) ─────────────── */

size_t my_strlen(const char *s) {
    const char *p = s;
    while (*p) ++p;
    return (size_t)(p - s);
}

/* ─── 11. Merge-sort inner merge step ───────────────────────────────── */

/* Exercises: compare + conditional branches, loads, stores, CSEL */
static void merge(int *arr, int *tmp,
                  int left, int mid, int right) {
    int i = left, j = mid, k = left;
    while (i < mid && j < right) {
        if (arr[i] <= arr[j])
            tmp[k++] = arr[i++];
        else
            tmp[k++] = arr[j++];
    }
    while (i < mid)   tmp[k++] = arr[i++];
    while (j < right) tmp[k++] = arr[j++];
    for (int l = left; l < right; ++l)
        arr[l] = tmp[l];
}

void merge_sort(int *arr, int *tmp, int left, int right) {
    if (right - left < 2) return;
    int mid = (left + right) / 2;
    merge_sort(arr, tmp, left, mid);
    merge_sort(arr, tmp, mid, right);
    merge(arr, tmp, left, mid, right);
}

/* ─── 12. CRC-32-like checksum (bit manipulation heavy) ─────────────── */

uint32_t crc32_byte(uint32_t crc, uint8_t data) {
    crc ^= (uint32_t)data;
    for (int i = 0; i < 8; ++i) {
        if (crc & 1u)
            crc = (crc >> 1) ^ 0xEDB88320u;
        else
            crc >>= 1;
    }
    return crc;
}

uint32_t crc32(const uint8_t *buf, size_t len) {
    uint32_t crc = 0xFFFFFFFFu;
    for (size_t i = 0; i < len; ++i)
        crc = crc32_byte(crc, buf[i]);
    return crc ^ 0xFFFFFFFFu;
}

/* ─── 13. Warmup / driver (used to prevent dead-code elimination) ───── */

static int   int_buf[N];
static int   int_tmp[N];
static float mat_a[M][M], mat_b[M][M], mat_c[M][M];

/* Prevent the compiler from removing our kernels by using volatile sinks. */
volatile long long  result_ll;
volatile int        result_i;
volatile uint32_t   result_u32;
volatile size_t     result_sz;

int main(void) {
    /* Initialise buffers */
    for (int i = 0; i < N; ++i) {
        int_buf[i] = i * 7 + 3;
    }
    for (int i = 0; i < M; ++i)
        for (int j = 0; j < M; ++j) {
            mat_a[i][j] = (float)(i + j + 1);
            mat_b[i][j] = (float)(i * j + 1);
        }

    /* 1. Integer ops */
    result_i = integer_ops(42, 7);

    /* 2. Floating-point ops */
    result_ll = (long long)fp_ops(3.14159265358979, 2.71828182845905);

    /* 3. Array copy */
    array_copy(int_tmp, int_buf, N);

    /* 4. Dot product */
    result_ll = dot_product(int_buf, int_tmp, N);

    /* 5. Matrix multiply */
    matmul(mat_c, mat_a, mat_b);

    /* 6. Recursive fibonacci (small n to keep runtime sane) */
    result_ll = fib_recursive(20);

    /* 7. Iterative fibonacci */
    result_ll = fib_iterative(50);

    /* 8. Popcount */
    result_i = (int)popcount64(0xDEADBEEFCAFEBABEULL);

    /* 9. Atomic increment */
    {
        volatile int counter = 0;
        for (int i = 0; i < WARMUP; ++i)
            atomic_increment((int*)&counter);
        result_i = counter;
    }

    /* 10. String length */
    {
        const char *s = "Hello, AArch64 Energy Model!";
        result_sz = my_strlen(s);
    }

    /* 11. Merge sort */
    merge_sort(int_buf, int_tmp, 0, N);

    /* 12. CRC-32 */
    result_u32 = crc32((const uint8_t *)int_buf, N * sizeof(int));

    return (int)(result_i & 0xFF);
}
