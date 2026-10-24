#include "../src/satadd.h"
#include <limits.h>
#include <stdio.h>

static int fails;

static void expect(const char *name, int got, int want) {
    if (got != want) {
        printf("FAIL %s: got %d want %d\n", name, got, want);
        fails++;
    } else {
        printf("PASS %s\n", name);
    }
}

int main(void) {
    expect("add", add(2, 2), 4);
    expect("sat_add_ok", sat_add(10, 20), 30);
    expect("sat_add_hi", sat_add(INT_MAX, 1), INT_MAX);
    expect("sat_add_lo", sat_add(INT_MIN, -1), INT_MIN);
    expect("sat_sub_lo", sat_sub(INT_MIN, 1), INT_MIN);
    return fails ? 1 : 0;
}
