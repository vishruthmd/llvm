/*
 * string_proc_test.c — String Processing Energy Estimation Test
 * ==============================================================
 *
 * Test file for the LLVM EnergyEstimationPass focusing on byte-level
 * string operations: palindrome check, string reversal, character
 * frequency counting, and substring search.
 *
 * Exercises distinct instruction patterns vs simple_test.c:
 *   - Heavy byte loads (LDRBBroX/LDRBBui — 8.8-9.5 pJ)
 *   - Pointer arithmetic with ADD/SUB (2.8 pJ)
 *   - Conditional branches on byte values (CBZ/CBNZ — 3.5 pJ)
 *   - Byte stores (STRBBui — 7.0 pJ)
 *   - Character comparison loops (CMP + Bcc)
 *
 * Run via:
 *   cd llvm_pipeline && run_string_proc_test.bat
 *
 * No standard library dependencies. Uses volatile sinks to prevent DCE.
 */

/* ─── Constants ─────────────────────────────────────────────────────────── */
#define BUF_SIZE    128     /* Max string length */
#define ALPHABET    26      /* English letters */

/* ─── 1. Palindrome check — byte comparison loop ───────────────────────── */
/* Exercises: LDRBBroX (8.8 pJ), CMP (2.6 pJ), Bcc (3.5 pJ), CBZ (3.5 pJ)
 * Each iteration compares two bytes. For a 28-char palindrome like
 * "racecar": 3 comparisons (14/2 = 7 iterations, early exit).
 * Each iteration: LDR + LDR + CMP + Bcc ≈ 23.4 pJ/iter.
 * Worst case (full palindrome): n/2 iterations.
 */
int is_palindrome(const char *s) {
    int len = 0;
    const char *p = s;
    while (*p) {                /* LDRBBui (8.8) + CBZ (3.5) */
        ++len;
        ++p;
    }
    int left = 0, right = len - 1;
    while (left < right) {                              /* CMP + Bcc */
        if (s[left] != s[right]) return 0;              /* LDR + LDR + CMP + Bcc */
        ++left;                                         /* ADDWri (2.8) */
        --right;                                        /* SUBWri (2.8) */
    }
    return 1;
}

/* ─── 2. String reverse in-place — byte swap ────────────────────────────── */
/* Exercises: LDRBBroX (8.8 pJ), STRBBui (7.0 pJ), XOR swap pattern
 * Reverses a string by swapping characters from both ends.
 * For a 28-char string: 14 swaps. Each swap: 2× LDR + 2× STR ≈ 31.6 pJ.
 * Total raw: 14 × 31.6 = 442 pJ. With freq_scale: weighted ≈ 442 pJ.
 */
void str_reverse(char *s) {
    int len = 0;
    while (s[len]) ++len;
    int i = 0, j = len - 1;
    while (i < j) {
        char tmp = s[i];        /* LDRBBroX — 8.8 pJ */
        s[i] = s[j];            /* LDRBBroX + STRBBui — 15.8 pJ combined */
        s[j] = tmp;             /* STRBBui — 7.0 pJ */
        ++i;
        --j;
    }
}

/* ─── 3. Character frequency counting ───────────────────────────────────── */
/* Exercises: LDRBBroX (8.8), ADD (2.8), STRWui (7.2), array indexing
 * For a 28-char string: 28 iterations. Each iter:
 *   LDRBB (8.8) + SUB (2.8) + LDRsxtw (load from freq array) + ADD + STR
 *   ≈ 26 pJ/iteration.
 * Total raw: 28 × 26 = 728 pJ. With freq_scale: weighted ≈ 728 pJ.
 * This function exercises indexed addressing: LDR array[char - 'a'].
 */
void char_frequency(const char *s, int freq[ALPHABET]) {
    /* Zero the frequency array */
    for (int i = 0; i < ALPHABET; ++i)
        freq[i] = 0;            /* STRWui — 7.2 pJ each */

    while (*s) {
        char c = *s;            /* LDRBBroX — 8.8 pJ */
        if (c >= 'a' && c <= 'z')       /* CMP + Bcc */
            freq[c - 'a']++;            /* LDR + ADD + STR — indexed load/store */
        else if (c >= 'A' && c <= 'Z')
            freq[c - 'A']++;
        ++s;
    }
}

/* ─── 4. Index of first occurrence (strchr) — linear byte search ────────── */
/* Exercises: LDRBB (8.8), CMP (2.6), CBZ/CBNZ (3.5)
 * Simple linear scan through string. For 28 chars: ~28 iterations avg.
 * Each iteration: LDR (8.8) + CMP (2.6) + CBZ (3.5) ≈ 14.9 pJ/iter.
 * This is similar to linear_search but operating on bytes.
 * Early exit on match.
 */
int find_char(const char *s, char target) {
    int i = 0;
    while (s[i]) {              /* LDRBB + CBZ — 12.3 pJ */
        if (s[i] == target) return i;   /* LDRBB + CMP + Bcc — 14.9 pJ */
        ++i;
    }
    return -1;
}

/* ─── 5. Substring search — double-nested byte comparison ───────────────── */
/* Exercises: nested loops (CMP + Bcc at two levels), LDRBB (8.8)
 * Outer loop: position in s. Inner loop: compare with substr.
 * For s="hello world" (11 chars), substr="world" (5 chars):
 *   ~7 outer iterations × up to 5 inner = ~35 char comparisons.
 * Each inner iter: LDR (8.8) + CMP (2.6) + Bcc (3.5) ≈ 14.9 pJ.
 * Total raw: 35 × 14.9 = 522 pJ. With freq_scale: weighted higher.
 * This is a classic O(n×m) string matching worst case.
 */
int find_substring(const char *haystack, const char *needle) {
    if (!*needle) return 0;     /* Empty needle matches at position 0 */

    for (int i = 0; haystack[i]; ++i) {             /* Outer loop */
        /* Check if needle matches at position i */
        int match = 1;
        for (int j = 0; needle[j]; ++j) {           /* Inner loop */
            if (haystack[i + j] != needle[j]) {     /* LDR + LDR + CMP */
                match = 0;
                break;                              /* Bcc — early exit */
            }
        }
        if (match) return i;
    }
    return -1;  /* Not found */
}

/* ─── 6. Caesar cipher shift — transform each char ──────────────────────── */
/* Exercises: LDRBB (8.8), ADD (2.8), CMP (2.6), STRBB (7.0), conditional
 * For a 28-char string: 28 iterations. Each iteration:
 *   LDR (8.8) + SUB (2.8) + CMP (2.6) + ADD (2.8) + STR (7.0) ≈ 24 pJ/iter
 * Total raw: 28 × 24 = 672 pJ.
 * Applies shift to each letter, wrapping around the alphabet.
 */
void caesar_cipher(char *s, int shift) {
    shift = shift % 26;
    if (shift < 0) shift += 26;

    for (int i = 0; s[i]; ++i) {
        char c = s[i];                          /* LDRBB — 8.8 pJ */
        if (c >= 'a' && c <= 'z') {             /* CMP + Bcc */
            c = 'a' + (c - 'a' + shift) % 26;   /* ADD + MUL + ADD */
            s[i] = c;                           /* STRBB — 7.0 pJ */
        } else if (c >= 'A' && c <= 'Z') {
            c = 'A' + (c - 'A' + shift) % 26;
            s[i] = c;
        }
    }
}

/* ─── Driver / main ────────────────────────────────────────────────────── */
/* Uses volatile results to prevent dead-code elimination at -O2. */

/* Static buffers (BSS, not stack) */
static char str_buf_1[BUF_SIZE];
static char str_buf_2[BUF_SIZE];
static int  freq_buf[ALPHABET];

/* Volatile sinks */
volatile int     result_i;
volatile int     result_found;

int main(void) {
    /* ── Initialise strings ────────────────────────────────────────────── */
    /* "A man a plan a canal panama" — well-known palindrome */
    const char *palindrome = "amanaplanacanalpanama";
    const char *sentence   = "hello world from arm aarch64";
    const char *substr     = "world";
    const char *greeting   = "Hello AArch64 Energy Model!";

    /* Copy greeting into writable buffer for in-place operations */
    {
        int i = 0;
        while (greeting[i]) {
            str_buf_1[i] = greeting[i];
            ++i;
        }
        str_buf_1[i] = '\0';
    }

    /* ── 1. Palindrome check ───────────────────────────────────────────── */
    result_i = is_palindrome(palindrome);            /* Should be 1 (true) */
    result_i = is_palindrome("notapalindrome");      /* Should be 0 (false) */

    /* ── 2. String reverse ─────────────────────────────────────────────── */
    {
        int i = 0;
        while (greeting[i]) {
            str_buf_2[i] = greeting[i];
            ++i;
        }
        str_buf_2[i] = '\0';
    }
    str_reverse(str_buf_2);                          /* In-place reverse */
    result_i = str_buf_2[0];                         /* Should be '!' */

    /* ── 3. Character frequency ────────────────────────────────────────── */
    char_frequency(greeting, freq_buf);
    /* Most frequent char in "Hello AArch64 Energy Model!":
       'e' appears 3 times → freq_buf['e' - 'a'] = 3 (after lowercasing) */
    result_i = freq_buf[0];                          /* 'a' frequency */

    /* ── 4. Find char ──────────────────────────────────────────────────── */
    result_found = find_char(sentence, 'w');          /* Should be 6 */
    result_found = find_char(sentence, 'z');          /* Should be -1 */

    /* ── 5. Substring search ───────────────────────────────────────────── */
    result_found = find_substring(sentence, substr);  /* Should be 6 */
    result_found = find_substring(sentence, "xyz");   /* Should be -1 */

    /* ── 6. Caesar cipher ──────────────────────────────────────────────── */
    caesar_cipher(str_buf_1, 3);                     /* Shift by 3 */
    result_i = str_buf_1[0];                         /* First char shifted */

    return (int)(result_i & 0xFF);
}
