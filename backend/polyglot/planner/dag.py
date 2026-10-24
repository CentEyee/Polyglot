from __future__ import annotations

from graphlib import CycleError, TopologicalSorter

from polyglot.models import Plan, PlanStep


class PlanError(Exception):
    pass


def waves(plan: Plan) -> list[list[PlanStep]]:
    by_id = {s.id: s for s in plan.steps}
    ts = TopologicalSorter({s.id: set(s.depends_on) for s in plan.steps})
    try:
        ts.prepare()
    except CycleError as e:
        raise PlanError(f"cycle in plan: {e.args[1]}") from e
    out: list[list[PlanStep]] = []
    while ts.is_active():
        ready = sorted(ts.get_ready())
        out.append([by_id[i] for i in ready])
        ts.done(*ready)
    return out


def validate_and_repair(plan: Plan, existing_files: set[str], import_edges: list[tuple[str, str]]) -> list[str]:
    """LLM proposes, code disposes: drop hallucinated paths, unique ownership, real include order."""
    notes: list[str] = []
    seen_ids: set[str] = set()
    owner: dict[str, str] = {}
    for s in plan.steps:
        if s.id in seen_ids:
            raise PlanError(f"duplicate step id {s.id}")
        seen_ids.add(s.id)
        kept = []
        for f in s.files:
            if f not in existing_files:
                notes.append(f"dropped nonexistent file {f} from {s.id}")
            elif f in owner:
                notes.append(f"{f} claimed by {owner[f]} and {s.id}; kept in {owner[f]}")
            else:
                owner[f] = s.id
                kept.append(f)
        s.files = kept
    plan.steps = [s for s in plan.steps if s.files]
    ids = {s.id for s in plan.steps}
    for s in plan.steps:
        s.depends_on = [d for d in s.depends_on if d in ids and d != s.id]

    by_id = {s.id: s for s in plan.steps}
    for dependent, dependency in import_edges:
        a, b = owner.get(dependent), owner.get(dependency)
        if a and b and a != b and b not in by_id[a].depends_on:
            by_id[a].depends_on.append(b)

    for _ in range(len(plan.steps) + 1):
        ts = TopologicalSorter({s.id: set(s.depends_on) for s in plan.steps})
        try:
            ts.prepare()
            break
        except CycleError as e:
            cyc = [c for c in dict.fromkeys(e.args[1])]
            keep, rest = by_id[cyc[0]], [by_id[c] for c in cyc[1:] if c in by_id]
            for r in rest:
                keep.files += r.files
                keep.depends_on = list({*keep.depends_on, *r.depends_on} - {keep.id, r.id})
                keep.allowed_symbol_changes += r.allowed_symbol_changes
                for s in plan.steps:
                    s.depends_on = [keep.id if d == r.id else d for d in s.depends_on]
                    s.depends_on = [d for d in s.depends_on if d != s.id]
                plan.steps.remove(r)
                by_id.pop(r.id, None)
            notes.append(f"merged cyclic steps {cyc} into {keep.id}")
    return notes
