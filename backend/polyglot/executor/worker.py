"""Phase 2: wave-parallel C/C++ → Rust translation.

Steps in a wave run concurrently. Waves follow the include DAG so dependents
see already-translated Rust modules (the contract they must stay consistent with).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from polyglot.context import RunContext
from polyglot.executor.codemods import REGISTRY, ensure_rust_crate
from polyglot.llm.client import ESCALATE, TIER_BY_RISK, extract_code
from polyglot.models import PlanStep, StepOutcome
from polyglot.planner.dag import waves
from polyglot.vcs import repo as git

REWRITE_SYSTEM = """You are a senior engineer translating C/C++ translation units into SAFE idiomatic Rust.
Rules:
- Translate the given C/C++ file(s) into ONE complete Rust module.
- Preserve observable behavior. Prefer ownership, Option, Result, iterators. Avoid unsafe unless FFI or raw hardware requires it; if you use unsafe, wrap it in a tiny documented block.
- Match already-translated dependency modules (names and types shown below).
- Include `#[cfg(test)]` tests that lock the original C behavior when you can infer it.
- Return the COMPLETE Rust module in a single fenced rust code block and nothing else.
"""


@dataclass
class FileResult:
    path: str
    ok: bool
    errors: list[str] = field(default_factory=list)
    used_codemod: bool = False
    target: str = ""


def _prompt(ctx: RunContext, step: PlanStep, sources: dict[str, str], target: str, feedback: list[str]) -> str:
    bcs = "\n".join(
        f"- {b.symbol}: {b.description} -> {b.replacement}" for b in ctx.knowledge.breaking_changes[:20]
    ) or "(none listed)"
    dep_files = sorted({b for a, b in ctx.graph.edges if a in sources})
    contract_parts = []
    for d in dep_files:
        t = ctx.adapter.target_path(d)
        p = ctx.root / t
        if p.exists():
            contract_parts.append(f"// {t}\n" + p.read_text(errors="replace")[:2500])
        elif d in ctx.graph.files:
            contract_parts.append(f"{d}: " + ", ".join(s.signature or s.name for s in ctx.graph.files[d].symbols[:20]))
    contract = "\n\n".join(contract_parts) or "(no in-repo dependencies translated yet)"
    blobs = "\n\n".join(f"--- {rel} ---\n```c\n{src}```" for rel, src in sources.items())
    fb = ("\n\nYour previous attempt was rejected:\n" + "\n".join(f"- {e}" for e in feedback)) if feedback else ""
    return (
        f"Migration: {ctx.request.instruction}\nStep: {step.title}\nNotes: {step.breaking_change}\n"
        f"Write Rust module: {target}\n\nMappings:\n{bcs}\n\nAlready-migrated dependencies:\n{contract}\n\n"
        f"Source translation unit:\n{blobs}{fb}"
    )


async def migrate_unit(ctx: RunContext, step: PlanStep, files: list[str], target: str) -> FileResult:
    sources = {rel: (ctx.root / rel).read_text(errors="replace") for rel in files}
    dest: Path = ctx.root / target
    dest.parent.mkdir(parents=True, exist_ok=True)

    if step.strategy == "codemod" and step.codemod in REGISTRY and dest.exists():
        new = REGISTRY[step.codemod](dest.read_text(errors="replace"), step.codemod_args)
        if new is not None and not ctx.target_adapter.check_syntax(new, target):
            dest.write_text(new)
            return FileResult(files[0], True, used_codemod=True, target=target)

    old_symbols = set()
    for rel in files:
        if rel in ctx.graph.files:
            old_symbols |= {s.name for s in ctx.graph.files[rel].symbols}
    allowed = set(step.allowed_symbol_changes)
    tier = TIER_BY_RISK[step.risk]
    feedback: list[str] = []
    for _ in range(3):
        raw = await ctx.llm.complete(tier, REWRITE_SYSTEM, _prompt(ctx, step, sources, target, feedback))
        new = extract_code(raw)
        errors = ctx.target_adapter.check_syntax(new, target)
        if not errors:
            indexed = ctx.target_adapter.index_source(new, target)
            rust_names = {s.name for s in indexed.symbols}
            # C macros/types may vanish; only flag public functions that disappeared with no rename allowance.
            lost = {n for n in old_symbols if n not in rust_names and n not in allowed}
            # Don't fail the whole unit for lost names on first try — record and escalate once.
            if lost and tier != TIER_BY_RISK["high"] and not feedback:
                errors = [f"C symbol `{n}` has no Rust counterpart (rename it or list it in allowed_symbol_changes)"
                          for n in sorted(lost)[:8]]
        if not errors:
            dest.write_text(new)
            return FileResult(files[0], True, target=target)
        feedback = errors
        tier = ESCALATE[tier]
    return FileResult(files[0], False, errors=feedback, target=target)


async def _run_step(ctx: RunContext, step: PlanStep, sem: asyncio.Semaphore) -> tuple[PlanStep, list[FileResult]]:
    ctx.bus.emit("step.started", step=step.id, title=step.title, files=step.files, risk=step.risk)
    groups: dict[str, list[str]] = {}
    for rel in step.files:
        if Path(rel).suffix not in ctx.adapter.extensions:
            continue
        groups.setdefault(ctx.adapter.target_path(rel), []).append(rel)
    if not groups and step.target_files:
        groups = {t: step.files for t in step.target_files}

    async def one(target: str, rels: list[str]) -> FileResult:
        async with sem:
            r = await migrate_unit(ctx, step, rels, target)
            ctx.bus.emit("file.migrated", step=step.id, path=",".join(rels), target=target, ok=r.ok,
                         codemod=r.used_codemod, errors=r.errors)
            return r

    return step, list(await asyncio.gather(*(one(t, rels) for t, rels in groups.items())))


async def execute_plan(ctx: RunContext) -> list[StepOutcome]:
    modules = [ctx.adapter.target_path(f) for f in ctx.graph.files]
    scaffold = ensure_rust_crate(ctx.root, modules)
    if scaffold:
        await git.commit_paths(ctx.root, scaffold, "chore: scaffold rust-port crate")
        ctx.bus.emit("crate.scaffolded", files=scaffold)

    sem = asyncio.Semaphore(ctx.settings.max_parallel_workers)
    outcomes: list[StepOutcome] = []
    failed: set[str] = set()
    for wave_idx, wave in enumerate(waves(ctx.plan)):
        ctx.bus.emit("wave.started", index=wave_idx, steps=[s.id for s in wave])
        runnable = [s for s in wave if not (set(s.depends_on) & failed)]
        for s in wave:
            if s not in runnable:
                failed.add(s.id)
                outcomes.append(StepOutcome(step_id=s.id, title=s.title, status="skipped",
                                            notes=["a dependency step was flagged"]))
        for step, results in await asyncio.gather(*(_run_step(ctx, s, sem) for s in runnable)):
            bad = [r for r in results if not r.ok]
            targets = [r.target for r in results if r.target]
            if bad:
                await git.restore_paths(ctx.root, targets, ctx.base_sha)
                # restore_paths no-ops missing files; delete failed targets so we don't keep half a module
                for r in bad:
                    p = ctx.root / r.target
                    if p.exists():
                        p.unlink()
                ctx.flagged_steps.add(step.id)
                failed.add(step.id)
                outcomes.append(StepOutcome(step_id=step.id, title=step.title, status="flagged",
                                            notes=[e for r in bad for e in r.errors][:6]))
                ctx.bus.emit("step.flagged", step=step.id, reason=[r.path for r in bad])
                continue
            ensure_rust_crate(ctx.root, modules)
            sha = await git.commit_paths(ctx.root, targets + ["rust-port/src/lib.rs"], f"migrate: {step.title}")
            outcomes.append(StepOutcome(step_id=step.id, title=step.title, status="done",
                                        files_changed=targets))
            ctx.bus.emit("step.done", step=step.id, commit=sha, files=targets)
    return outcomes
