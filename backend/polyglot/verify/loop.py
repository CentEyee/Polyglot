"""Phase 3: cargo test + self-correction.

Baseline C tests are recorded first. After translation we run the Rust crate.
Only NEW failures drive repairs. Super handles the first round, Ultra the rest.
On exhaustion, implicated steps are reverted instead of shipping a red PR.
"""
from __future__ import annotations

from polyglot.context import RunContext
from polyglot.llm.client import Tier, extract_code
from polyglot.models import Failure, TestSummary
from polyglot.vcs import repo as git

REPAIR_SYSTEM = """You repair a Rust file after a C/C++ → Rust migration broke `cargo test` or the build.
Fix the root cause in the file shown. Keep the migration intent (do not revert to C).
Do not weaken or delete tests. Prefer safe Rust. Return the COMPLETE updated file in one fenced rust block.
"""

MAX_FILES_PER_ITER = 3


async def run_tests(ctx: RunContext, *, rust: bool = False) -> tuple[TestSummary, list[Failure], str, int]:
    adapter = ctx.target_adapter if rust else ctx.adapter
    cmd = adapter.test_command()
    res = await ctx.sandbox.run(cmd, ctx.root, timeout=900)
    summary, failures = adapter.parse_test_output(res.output, ctx.root)
    if res.code != 0 and not failures:
        failures = [Failure(id="<unparsed>", message="test command failed", trace=res.output[-4000:])]
        summary.ok = False
    return summary, failures, res.output, res.code


def repair_targets(ctx: RunContext, failure: Failure) -> list[str]:
    src = [f for f in failure.files if f.endswith(".rs")]
    if src:
        return src
    # Map failing ids back to rust-port modules from the plan
    return list(dict.fromkeys(
        t for s in (ctx.plan.steps if ctx.plan else []) for t in s.target_files
    ))[:MAX_FILES_PER_ITER]


def _new_failures(ctx: RunContext, failures: list[Failure]) -> list[Failure]:
    # After language switch, every rust failure is "new"
    return failures


async def _repair_file(ctx: RunContext, rel: str, failure: Failure, tier: Tier) -> bool:
    path = ctx.root / rel
    if not path.exists():
        return False
    source = path.read_text(errors="replace")
    prompt = (
        f"Migration: {ctx.request.instruction}\n"
        f"Failing: {failure.id}\n{failure.message}\n\nTrace:\n{failure.trace}\n\n"
        f"File: {rel}\n```rust\n{source}```"
    )
    new = extract_code(await ctx.llm.complete(tier, REPAIR_SYSTEM, prompt))
    if ctx.target_adapter.check_syntax(new, rel) or new == source:
        return False
    path.write_text(new)
    return True


async def verify_and_repair(ctx: RunContext) -> tuple[TestSummary, int]:
    max_iters = ctx.request.max_repair_iters
    summary, failures, _, _ = await run_tests(ctx, rust=True)
    iters = 0
    while True:
        new = _new_failures(ctx, failures)
        ctx.bus.emit(
            "tests.run", iteration=iters, passed=summary.passed, failed=summary.failed,
            errors=summary.errors, new_failures=[f.id for f in new], rust=True,
        )
        if not new and summary.ok:
            return summary, iters
        if not new:
            return summary, iters
        if iters >= max_iters:
            break
        iters += 1
        tier = Tier.BALANCED if iters == 1 else Tier.DEEP
        touched: list[str] = []
        for failure in new:
            for rel in repair_targets(ctx, failure)[:MAX_FILES_PER_ITER]:
                if rel in touched or len(touched) >= MAX_FILES_PER_ITER:
                    continue
                if await _repair_file(ctx, rel, failure, tier):
                    touched.append(rel)
                    ctx.bus.emit("repair.applied", iteration=iters, path=rel, tier=tier.value, failure=failure.id)
        if not touched:
            break
        await git.commit_paths(ctx.root, touched, f"repair: iteration {iters}")
        summary, failures, _, _ = await run_tests(ctx, rust=True)

    by_id = {s.id: s for s in ctx.plan.steps} if ctx.plan else {}
    implicated = set()
    for fl in _new_failures(ctx, failures):
        for f in repair_targets(ctx, fl):
            for sid, step in by_id.items():
                if f in step.target_files:
                    implicated.add(sid)
    to_revert: set[str] = set()
    stack = list(implicated)
    while stack:
        sid = stack.pop()
        if sid in to_revert or sid not in by_id:
            continue
        to_revert.add(sid)
        stack += by_id[sid].depends_on
    for sid in sorted(to_revert):
        await git.restore_paths(ctx.root, by_id[sid].target_files, ctx.base_sha)
        ctx.flagged_steps.add(sid)
        reason = "tests still failing after repairs; reverted" if sid in implicated else "reverted with a dependent step"
        ctx.bus.emit("step.flagged", step=sid, reason=[reason])
    if to_revert:
        paths = [f for sid in to_revert for f in by_id[sid].target_files]
        await git.commit_paths(ctx.root, paths, "revert: steps that could not be verified")
        summary, failures, _, _ = await run_tests(ctx, rust=True)
        ctx.bus.emit(
            "tests.run", iteration=iters, passed=summary.passed, failed=summary.failed,
            errors=summary.errors, new_failures=[f.id for f in _new_failures(ctx, failures)], rust=True,
        )
    return summary, iters
