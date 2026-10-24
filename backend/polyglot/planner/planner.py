from __future__ import annotations

from pathlib import Path

from polyglot.analysis.graph import summarize
from polyglot.context import RunContext
from polyglot.llm.client import Tier, extract_json
from polyglot.models import Plan, PlanStep
from polyglot.planner.dag import PlanError, validate_and_repair

PLAN_SYSTEM = """You are a staff engineer planning a C/C++ → Rust migration of a whole repository.
You are given the request, documented C→Rust mappings, and an include/call graph.
Produce a step plan as JSON ONLY:
{"summary": str,
 "steps":[{"id": "s1", "title": str, "files": [repo-relative C/C++ paths], "depends_on": [step ids],
           "breaking_change": str, "strategy": "codemod"|"llm", "codemod": null|"c_null_to_option",
           "codemod_args": {}, "risk": "low"|"medium"|"high",
           "allowed_symbol_changes": [C names that may disappear]}]}
Rules:
- Headers (.h/.hpp) that declare types MUST be migrated before .c/.cpp files that include them.
- Group a matching .h + .c pair (same stem) into ONE step so they become a single Rust module.
- Put Cargo.toml / crate scaffolding in the first step if you include it; otherwise the runtime adds it.
- Prefer safe Rust (ownership, Result, Option). Mark risk "high" for pointer graphs, FFI, and threading.
- Use strategy "codemod" ONLY for mechanical 1:1 recipes the runtime knows; otherwise "llm".
- Every source file that must be translated appears in exactly one step.
"""


def _user_prompt(ctx: RunContext) -> str:
    bcs = "\n".join(f"- {b.symbol}: {b.description} -> {b.replacement}" for b in ctx.knowledge.breaking_changes) or (
        "(no verified sources; rely on known C→Rust mappings and say so in summary)"
    )
    manifests = ", ".join(ctx.adapter.manifest_files(ctx.root)) or "none"
    return (
        f"Migration request: {ctx.request.instruction}\nTarget: idiomatic Rust crate at rust-port/\n\n"
        f"C/C++ manifests: {manifests}\n\nDocumented mappings:\n{bcs}\n\nCode graph:\n{summarize(ctx.graph)}"
    )


def _group_units(ctx: RunContext) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for rel in ctx.graph.files:
        target = ctx.adapter.target_path(rel)
        groups.setdefault(target, []).append(rel)
    return groups


async def build_plan(ctx: RunContext) -> tuple[Plan, list[str]]:
    existing = set(ctx.graph.files) | set(ctx.adapter.manifest_files(ctx.root))
    feedback = ""
    last_err: Exception | None = None
    notes: list[str] = []
    for attempt in range(2):
        raw = await ctx.llm.complete(Tier.DEEP, PLAN_SYSTEM, _user_prompt(ctx) + feedback, json_mode=True)
        try:
            plan = Plan(**extract_json(raw))
            notes = validate_and_repair(plan, existing, ctx.graph.edges)
            break
        except Exception as e:
            last_err = e
            feedback = f"\n\nYour previous answer was invalid ({e}). Return valid JSON matching the schema."
    else:
        raise PlanError(f"planner failed twice: {last_err}")

    covered = {f for s in plan.steps for f in s.files}
    missing = [n.path for n in ctx.graph.files.values() if n.path not in covered]
    if missing:
        plan.steps.append(PlanStep(
            id="auto-uncovered", title="Translate remaining translation units", files=missing, risk="medium",
        ))
        notes.append(f"added auto-uncovered for {len(missing)} file(s)")
        notes += validate_and_repair(plan, existing, ctx.graph.edges)

    # Fill target_files from the C adapter mapping so the executor writes a Rust crate, not over C.
    for s in plan.steps:
        s.target_files = sorted({ctx.adapter.target_path(f) for f in s.files if Path(f).suffix in ctx.adapter.extensions})
    return plan, notes
