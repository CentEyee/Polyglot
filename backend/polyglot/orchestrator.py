"""Pipeline: ingest → baseline C tests → AST graph → Tavily research → Nemotron Ultra plan
→ parallel C→Rust translation → cargo test/repair → report → PR."""
from __future__ import annotations

import time
import uuid
from pathlib import Path

from polyglot.adapters.registry import detect_adapter, get_adapter
from polyglot.adapters.rust import count_unsafe
from polyglot.analysis.graph import build_graph, mark_deprecated
from polyglot.analysis.signatures import collect_signatures
from polyglot.config import Settings
from polyglot.context import RunContext
from polyglot.events import EventBus
from polyglot.executor.worker import execute_plan
from polyglot.ingest.clone import clone_repo
from polyglot.llm.client import LLM
from polyglot.models import MigrationRequest, RunReport
from polyglot.planner.dag import waves
from polyglot.planner.planner import build_plan
from polyglot.report import pr_body
from polyglot.research.tavily import gather_knowledge
from polyglot.sandbox.base import Sandbox, make_sandbox
from polyglot.store import save_report
from polyglot.vcs import pr as pull_request
from polyglot.vcs import repo as git
from polyglot.verify.loop import run_tests, verify_and_repair


async def run_migration(
    request: MigrationRequest,
    settings: Settings,
    llm: LLM,
    bus: EventBus,
    sandbox: Sandbox | None = None,
    run_id: str | None = None,
) -> tuple[RunReport, RunContext | None]:
    t0 = time.time()
    run_id = run_id or uuid.uuid4().hex[:8]
    report = RunReport()
    ctx: RunContext | None = None
    try:
        bus.emit("run.started", run_id=run_id, instruction=request.instruction, repo=request.repo_url)

        root = await clone_repo(request.repo_url, request.ref, Path(settings.workdir) / run_id)
        adapter = detect_adapter(root, request.language)
        target = get_adapter(request.target_language)
        ctx = RunContext(
            request=request, root=root, adapter=adapter, target_adapter=target, llm=llm, bus=bus,
            settings=settings, sandbox=sandbox or make_sandbox(settings.sandbox),
        )
        ctx.base_sha = await git.head(root)
        for rel in adapter.source_files(root):
            ctx.originals[rel] = (root / rel).read_text(errors="replace")
        bus.emit("ingest.done", language=adapter.key, target=target.key, sha=ctx.base_sha,
                 files=len(ctx.originals))

        for cmd in adapter.setup_commands(root):
            bus.emit("setup.run", cmd=" ".join(cmd))
            await ctx.sandbox.run(cmd, root, timeout=900)

        ctx.baseline, _, _, _ = await run_tests(ctx, rust=False)
        report.tests_before = ctx.baseline
        bus.emit("baseline.done", passed=ctx.baseline.passed, failed=ctx.baseline.failed,
                 errors=ctx.baseline.errors, ok=ctx.baseline.ok)

        ctx.graph = build_graph(root, adapter)
        bus.emit("graph.built", files=len(ctx.graph.files), edges=len(ctx.graph.edges),
                 graph={"files": {k: v.model_dump() for k, v in ctx.graph.files.items()},
                        "edges": ctx.graph.edges})

        ctx.knowledge = await gather_knowledge(request.instruction, llm, settings.tavily_api_key)
        mark_deprecated(ctx.graph, ctx.knowledge)
        bus.emit(
            "research.done",
            breaking_changes=len(ctx.knowledge.breaking_changes),
            sources=ctx.knowledge.sources,
            mappings=[b.model_dump() for b in ctx.knowledge.breaking_changes],
            verified=bool(ctx.knowledge.sources),
        )

        ctx.plan, notes = await build_plan(ctx)
        ctx.file_to_step = {f: s.id for s in ctx.plan.steps for f in s.files}
        report.plan_summary = ctx.plan.summary
        bus.emit(
            "plan.ready", summary=ctx.plan.summary, notes=notes,
            waves=[[s.model_dump() for s in w] for w in waves(ctx.plan)],
        )

        report.steps = await execute_plan(ctx)
        summary, iters = await verify_and_repair(ctx)
        report.tests_after, report.repair_iterations = summary, iters

        for so in report.steps:
            if so.step_id in ctx.flagged_steps and so.status == "done":
                so.status, so.files_changed = "flagged", []
                so.notes.append("reverted: could not be verified against cargo test")

        report.files_changed = len(await git.changed_files(root, ctx.base_sha))
        report.signatures = collect_signatures(root, ctx.graph)
        ctx.signatures = report.signatures
        report.unsafe_blocks = count_unsafe(root)
        flagged = bool(ctx.flagged_steps)
        rust_ok = summary.ok
        if not rust_ok and report.files_changed == 0:
            report.status = "failed"
        elif not rust_ok:
            # Shipped something, but the Rust suite is not clean yet.
            report.status = "partial"
        else:
            # Final Rust suite is green. Reverting an unverified step is a
            # deliberate safety action; what remains builds and tests clean.
            report.status = "success"

        u = llm.usage
        report.prompt_tokens, report.completion_tokens, report.llm_calls = u.prompt_tokens, u.completion_tokens, u.calls
        report.calls_by_tier = dict(u.by_tier)
        report.wall_seconds = time.time() - t0

        if request.open_pr and report.status in ("success", "partial") and settings.github_token:
            body = pr_body(request, ctx.plan, report)
            report.pr_url = await pull_request.open_pull_request(
                root, request.repo_url, request.ref or "main", f"polyglot/{run_id}",
                f"C→Rust: {request.instruction}", body, settings.github_token,
            )
        bus.emit("run.finished", status=report.status, report=report.model_dump())
        save_report(settings, run_id, report.model_dump())
    except Exception as e:
        report.status, report.notes = "failed", [f"{type(e).__name__}: {e}"]
        report.wall_seconds = time.time() - t0
        bus.emit("run.error", error=str(e))
        bus.emit("run.finished", status="failed", report=report.model_dump())
        save_report(settings, run_id, report.model_dump())
    return report, ctx
