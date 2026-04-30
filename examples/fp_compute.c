// Floating-point computation example
// Demonstrates high-energy FP operations

#include <math.h>
#include <stdio.h>

// FP arithmetic - moderate energy
double vector_dot_product(double *a, double *b, int n) {
    double sum = 0.0;
    for (int i = 0; i < n; i++) {
        sum += a[i] * b[i];  // FP multiply + add
    }
    return sum;
}

// FP division - high energy
double harmonic_mean(double *values, int n) {
    double sum = 0.0;
    for (int i = 0; i < n; i++) {
        sum += 1.0 / values[i];  // FP divide - expensive
    }
    return n / sum;
}

// FP sqrt - highest FP energy cost
double euclidean_distance(double x1, double y1, double x2, double y2) {
    double dx = x2 - x1;
    double dy = y2 - y1;
    return sqrt(dx*dx + dy*dy);  // FP sqrt - very expensive
}

// Complex FP computation
double compute_variance(double *data, int n) {
    double mean = 0.0;
    for (int i = 0; i < n; i++) {
        mean += data[i];
    }
    mean /= n;

    double variance = 0.0;
    for (int i = 0; i < n; i++) {
        double diff = data[i] - mean;
        variance += diff * diff;
    }
    return variance / n;
}

int main() {
    double a[100], b[100];
    for (int i = 0; i < 100; i++) {
        a[i] = i * 1.5;
        b[i] = i * 2.0 + 1.0;
    }

    double d1 = vector_dot_product(a, b, 100);
    double d2 = harmonic_mean(a + 1, 99);  // Skip zero
    double d3 = euclidean_distance(0.0, 0.0, 3.0, 4.0);
    double d4 = compute_variance(a, 100);

    printf("Results: %f %f %f %f\n", d1, d2, d3, d4);

    return 0;
}
