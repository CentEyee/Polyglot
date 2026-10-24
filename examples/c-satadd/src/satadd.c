#include "satadd.h"
#include <limits.h>

int add(int a, int b) {
    return a + b;
}

int sat_add(int a, int b) {
    long long s = (long long)a + (long long)b;
    if (s > INT_MAX) {
        return INT_MAX;
    }
    if (s < INT_MIN) {
        return INT_MIN;
    }
    return (int)s;
}

int sat_sub(int a, int b) {
    long long s = (long long)a - (long long)b;
    if (s > INT_MAX) {
        return INT_MAX;
    }
    if (s < INT_MIN) {
        return INT_MIN;
    }
    return (int)s;
}
