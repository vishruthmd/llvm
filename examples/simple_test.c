/*
 * simple_test.c — Comprehensive test for the LLVM Static Energy Estimation Pass
 *
 * Covers 13 different functions exercising a wide range of instruction types:
 *   - Integer ALU (add/sub/mul/div/shift/bitwise)
 *   - Floating-point arithmetic
 *   - Load/store with various access patterns
 *   - Nested loops (matrix multiply)
 *   - Recursive functions (fibonacci)
 *   - Sorting algorithms (bubble sort, quick sort partition)
 *   - Bit manipulation (popcount, CRC-32)
 *   - String operations (palindrome check)
 *   - Array search and filtering
 *
 * No standard library dependencies — all functions are self-contained.
 */

/* ─── 1. Simple integer arithmetic ──────────────────────────────────────────── */
/* Exercises: ADD, SUB, MUL, DIV, AND, OR, XOR, shifts, CMP, branches */
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

/* ─── 2. Floating-point arithmetic ─────────────────────────────────────────── */
/* Exercises: FADD, FSUB, FMUL, FDIV, FCMP, FMOV */
double fp_ops(double x, double y) {
    double sum  = x + y;
    double diff = x - y;
    double prod = x * y;
    double quot = (y != 0.0) ? (x / y) : 0.0;
    double fma  = x * y + sum;
    double t    = (x > 0.0) ? x : -x;
    double sq   = t * 0.5;
    return sum + diff + prod + quot + fma + sq;
}

/* ─── 3. Array sum (memory + ALU) ──────────────────────────────────────────── */
/* Exercises: LDR, ADD, CMP, B (loop) */
int sum_array(int *arr, int n) {
    int total = 0;
    for (int i = 0; i < n; i++) {
        total += arr[i];
    }
    return total;
}

/* ─── 4. Factorial (multiply-heavy) ────────────────────────────────────────── */
/* Exercises: MUL (expensive!), loop control */
int factorial(int n) {
    int result = 1;
    for (int i = 2; i <= n; i++) {
        result *= i;
    }
    return result;
}

/* ─── 5. Nested-loop matrix multiply (most energy-intensive) ────────────────── */
/* Exercises: triple-nested loops, FMUL/FADD, indexed LDR/STR */
#define MAT_SIZE 16
void mat_multiply(float C[MAT_SIZE][MAT_SIZE],
                  float A[MAT_SIZE][MAT_SIZE],
                  float B[MAT_SIZE][MAT_SIZE]) {
    for (int i = 0; i < MAT_SIZE; ++i) {
        for (int j = 0; j < MAT_SIZE; ++j) {
            float acc = 0.0f;
            for (int k = 0; k < MAT_SIZE; ++k) {
                acc += A[i][k] * B[k][j];
            }
            C[i][j] = acc;
        }
    }
}

/* ─── 6. Recursive Fibonacci (exercises BL/BLR, RET, CBZ) ──────────────────── */
int fib_recursive(int n) {
    if (n <= 1) return n;
    return fib_recursive(n - 1) + fib_recursive(n - 2);
}

/* ─── 7. Iterative Fibonacci (loop + MADD pattern) ─────────────────────────── */
int fib_iterative(int n) {
    if (n <= 0) return 0;
    if (n == 1) return 1;
    int prev = 0, curr = 1;
    for (int i = 2; i <= n; ++i) {
        int next = prev + curr;
        prev = curr;
        curr = next;
    }
    return curr;
}

/* ─── 8. Popcount (bit manipulation) ───────────────────────────────────────── */
/* Exercises: AND, SUB, CMP, B, shifts — Brian Kernighan's method */
unsigned popcount(unsigned long long x) {
    unsigned count = 0;
    while (x) {
        x &= (x - 1);
        ++count;
    }
    return count;
}

/* ─── 9. Bubble sort (comparison-heavy, nested loops) ──────────────────────── */
/* Exercises: nested loops, loads/stores, CMP/CSEL, conditional branches */
void bubble_sort(int *arr, int n) {
    for (int i = 0; i < n - 1; ++i) {
        for (int j = 0; j < n - i - 1; ++j) {
            if (arr[j] > arr[j + 1]) {
                int tmp = arr[j];
                arr[j] = arr[j + 1];
                arr[j + 1] = tmp;
            }
        }
    }
}

/* ─── 10. Quick sort partition step ────────────────────────────────────────── */
/* Exercises: conditional moves (CSEL), pointer arithmetic, comparison chains */
static int partition(int *arr, int lo, int hi) {
    int pivot = arr[hi];
    int i = lo - 1;
    for (int j = lo; j < hi; ++j) {
        if (arr[j] <= pivot) {
            ++i;
            int tmp = arr[i];
            arr[i] = arr[j];
            arr[j] = tmp;
        }
    }
    int tmp = arr[i + 1];
    arr[i + 1] = arr[hi];
    arr[hi] = tmp;
    return i + 1;
}

void quick_sort(int *arr, int lo, int hi) {
    if (lo < hi) {
        int p = partition(arr, lo, hi);
        quick_sort(arr, lo, p - 1);
        quick_sort(arr, p + 1, hi);
    }
}

/* ─── 11. Palindrome check (string ops + branches) ────────────────────────── */
/* Exercises: LDRB, pointer arithmetic, CMP, CBZ, conditional branches */
int is_palindrome(const char *s, int len) {
    int i = 0, j = len - 1;
    while (i < j) {
        if (s[i] != s[j]) return 0;
        ++i;
        --j;
    }
    return 1;
}

/* ─── 12. CRC-32 checksum byte (heavy bit ops) ─────────────────────────────── */
/* Exercises: XOR, AND, LSR, shifts, conditional branch */
unsigned crc32_byte(unsigned crc, unsigned char data) {
    crc ^= (unsigned)data;
    for (int i = 0; i < 8; ++i) {
        if (crc & 1u)
            crc = (crc >> 1) ^ 0xEDB88320u;
        else
            crc >>= 1;
    }
    return crc;
}

unsigned crc32(const unsigned char *buf, int len) {
    unsigned crc = 0xFFFFFFFFu;
    for (int i = 0; i < len; ++i)
        crc = crc32_byte(crc, buf[i]);
    return crc ^ 0xFFFFFFFFu;
}

/* ─── 13. Linear search (branchy, loads + CMP + conditional branch) ────────── */
int linear_search(int *arr, int n, int target) {
    for (int i = 0; i < n; ++i) {
        if (arr[i] == target) return i;
    }
    return -1;
}

/* ─── Driver / main ────────────────────────────────────────────────────────── */
/* Uses volatile results to prevent dead-code elimination */

#define BUF_SIZE 64

volatile int    g_result_i;
volatile double g_result_d;
volatile unsigned g_result_u;

static int    buf_a[BUF_SIZE];
static int    buf_b[BUF_SIZE];
static float  mat_a[MAT_SIZE][MAT_SIZE];
static float  mat_b[MAT_SIZE][MAT_SIZE];
static float  mat_c[MAT_SIZE][MAT_SIZE];

int main(void) {
    /* Init buffers */
    for (int i = 0; i < BUF_SIZE; ++i) {
        buf_a[i] = i * 7 + 3;
        buf_b[i] = buf_a[i];
    }

    for (int i = 0; i < MAT_SIZE; ++i)
        for (int j = 0; j < MAT_SIZE; ++j) {
            mat_a[i][j] = (float)(i + j + 1);
            mat_b[i][j] = (float)(i * j + 1);
        }

    /* Run all 13 functions */
    g_result_i  = integer_ops(42, 7);
    g_result_d  = fp_ops(3.14159, 2.71828);
    g_result_i  = sum_array(buf_a, BUF_SIZE);
    g_result_i  = factorial(10);
    mat_multiply(mat_c, mat_a, mat_b);
    g_result_i  = fib_recursive(15);
    g_result_i  = fib_iterative(40);
    g_result_u  = popcount(0xDEADBEEFCAFEBABEULL);
    bubble_sort(buf_b, BUF_SIZE);
    quick_sort(buf_a, 0, BUF_SIZE - 1);
    g_result_i  = is_palindrome("racecar", 7);
    g_result_u  = crc32((const unsigned char *)buf_a, BUF_SIZE * sizeof(int));
    g_result_i  = linear_search(buf_a, BUF_SIZE, 42);

    return g_result_i & 0xFF;
}
