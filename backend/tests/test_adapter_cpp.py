from polyglot.adapters.cpp import CppAdapter


SRC_H = """
#ifndef SATADD_H
#define SATADD_H
struct Point { int x; int y; };
int add(int a, int b);
int sat_add(int a, int b);
#endif
"""

SRC_C = """
#include "satadd.h"
#include <limits.h>

int add(int a, int b) {
    return a + b;
}

int sat_add(int a, int b) {
    long long s = (long long)a + b;
    if (s > INT_MAX) return INT_MAX;
    if (s < INT_MIN) return INT_MIN;
    return (int)s;
}
"""


def test_indexes_structs_and_functions():
    a = CppAdapter()
    h = a.index_source(SRC_H, "src/satadd.h")
    c = a.index_source(SRC_C, "src/satadd.c")
    assert {s.name for s in h.symbols} >= {"Point", "add", "sat_add"}
    assert c.imports == ["satadd.h"]
    assert a.target_path("src/satadd.c") == "rust-port/src/satadd.rs"
    assert a.target_path("src/satadd.h") == "rust-port/src/satadd.rs"


def test_include_graph_links_c_to_header():
    a = CppAdapter()
    files = {
        "src/satadd.h": a.index_source(SRC_H, "src/satadd.h"),
        "src/satadd.c": a.index_source(SRC_C, "src/satadd.c"),
    }
    edges = a.resolve_imports(files)
    assert ("src/satadd.c", "src/satadd.h") in edges


def test_brace_guard():
    a = CppAdapter()
    assert a.check_syntax("int add(int a) { return a; }", "x.c") == []
    assert a.check_syntax("int add(int a) { return a;", "x.c")
