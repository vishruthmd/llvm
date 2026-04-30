// Simple test without standard library dependencies
// Demonstrates different instruction types and their energy costs

// Simple integer computation - mostly ALU operations
int compute_sum(int n) {
    int sum = 0;
    for (int i = 1; i <= n; i++) {
        sum += i;
    }
    return sum;
}

// Array processing - memory operations dominate
int sum_array(int *arr, int n) {
    int total = 0;
    for (int i = 0; i < n; i++) {
        total += arr[i];  // Load + ALU
    }
    return total;
}

// Multiplication-heavy computation
int factorial(int n) {
    int result = 1;
    for (int i = 2; i <= n; i++) {
        result *= i;  // Integer multiply - higher energy
    }
    return result;
}

// Division operations - highest integer energy cost
int divide_loop(int n) {
    int result = n;
    for (int i = 1; i < 10; i++) {
        result = result / (i + 1);  // Integer divide - expensive
    }
    return result;
}

// Conditional branches - branch prediction impact
int count_evens(int *arr, int n) {
    int count = 0;
    for (int i = 0; i < n; i++) {
        if (arr[i] % 2 == 0) {  // Branches
            count++;
        }
    }
    return count;
}
