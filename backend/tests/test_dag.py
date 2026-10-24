import pytest

from polyglot.models import Plan, PlanStep
from polyglot.planner.dag import PlanError, validate_and_repair, waves


def step(i, files, deps=()):
    return PlanStep(id=i, title=i, files=files, depends_on=list(deps))


def test_waves_order_dependencies_first():
    p = Plan(summary="", steps=[step("b", ["b.c"], ["a"]), step("a", ["a.h"]), step("c", ["c.c"], ["a"])])
    w = waves(p)
    assert [[s.id for s in lvl] for lvl in w] == [["a"], ["b", "c"]]


def test_cycle_detected():
    p = Plan(summary="", steps=[step("a", ["a.c"], ["b"]), step("b", ["b.c"], ["a"])])
    with pytest.raises(PlanError):
        waves(p)


def test_validate_drops_hallucinated_files_and_dedupes_ownership():
    p = Plan(summary="", steps=[step("a", ["a.c", "ghost.c"]), step("b", ["a.c", "b.c"])])
    notes = validate_and_repair(p, {"a.c", "b.c"}, [])
    assert p.steps[0].files == ["a.c"] and p.steps[1].files == ["b.c"]
    assert any("ghost.c" in n for n in notes)


def test_include_graph_adds_missing_dependency_edge():
    p = Plan(summary="", steps=[step("a", ["a.h"]), step("b", ["b.c"])])
    validate_and_repair(p, {"a.h", "b.c"}, [("b.c", "a.h")])
    assert "a" in p.steps[1].depends_on


def test_cyclic_import_steps_are_merged():
    p = Plan(summary="", steps=[step("a", ["a.c"]), step("b", ["b.c"])])
    notes = validate_and_repair(p, {"a.c", "b.c"}, [("a.c", "b.c"), ("b.c", "a.c")])
    assert len(p.steps) == 1 and sorted(p.steps[0].files) == ["a.c", "b.c"]
    assert any("merged" in n for n in notes)
    assert len(waves(p)) == 1
