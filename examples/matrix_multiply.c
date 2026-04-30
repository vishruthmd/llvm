// Matrix multiplication example
// Demonstrates nested loops with high execution frequency

#include <stdio.h>
#include <stdlib.h>

#define N 32

// Classic matrix multiplication - O(n^3) complexity
// Inner loop has very high execution frequency
void matrix_multiply(double A[N][N], double B[N][N], double C[N][N]) {
    for (int i = 0; i < N; i++) {
        for (int j = 0; j < N; j++) {
            C[i][j] = 0.0;
            for (int k = 0; k < N; k++) {
                // This line executes N^3 times
                // High frequency → high weighted energy
                C[i][j] += A[i][k] * B[k][j];
            }
        }
    }
}

// Optimized version with better cache locality
void matrix_multiply_optimized(double A[N][N], double B[N][N], double C[N][N]) {
    // Initialize result
    for (int i = 0; i < N; i++) {
        for (int j = 0; j < N; j++) {
            C[i][j] = 0.0;
        }
    }

    // Reordered loops for better cache performance
    for (int i = 0; i < N; i++) {
        for (int k = 0; k < N; k++) {
            double a_ik = A[i][k];
            for (int j = 0; j < N; j++) {
                C[i][j] += a_ik * B[k][j];
            }
        }
    }
}

int main() {
    double (*A)[N] = malloc(sizeof(double[N][N]));
    double (*B)[N] = malloc(sizeof(double[N][N]));
    double (*C)[N] = malloc(sizeof(double[N][N]));

    // Initialize matrices
    for (int i = 0; i < N; i++) {
        for (int j = 0; j < N; j++) {
            A[i][j] = i + j;
            B[i][j] = i - j;
        }
    }

    // Perform multiplication
    matrix_multiply(A, B, C);

    // Print one element to prevent optimization
    printf("C[0][0] = %f\n", C[0][0]);

    free(A);
    free(B);
    free(C);

    return 0;
}
