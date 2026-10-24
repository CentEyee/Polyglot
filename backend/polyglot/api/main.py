from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from polyglot.config import get_settings
from polyglot.context import RunContext
from polyglot.events import EventBus
from polyglot.llm.client import TokenFactoryLLM
from polyglot.models import MigrationRequest, RunReport
from polyglot.orchestrator import run_migration
from polyglot.vcs import repo as git
from polyglot.store import list_runs, load_report

app = FastAPI(
    title="PolyGlot Refactor AI",
    description="Autonomous C/C++ → Rust migration agent on Nebius Token Factory + NVIDIA Nemotron",
    version="0.1.0",
)


def _cors():
    origins = [o.strip() for o in get_settings().cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )


_cors()


@dataclass
class Run:
    bus: EventBus = field(default_factory=EventBus)
    report: RunReport | None = None
    ctx: RunContext | None = None
    task: asyncio.Task | None = None
    request: MigrationRequest | None = None


RUNS: dict[str, Run] = {}


@app.get("/demo")
async def demo():
    root = Path(__file__).resolve().parents[3]
    example = root / "examples" / "c-satadd"
    return {
        "repo_url": str(example),
        "ref": "",
        "instruction": (
            "Migrate this C saturating-arithmetic library to safe idiomatic Rust. "
            "Keep INT_MAX/INT_MIN clamp behavior. Generate cargo tests equivalent to the C harness."
        ),
    }


@app.get("/health")
async def health():
    s = get_settings()
    return {
        "ok": True,
        "token_factory": bool(s.nebius_api_key),
        "tavily": bool(s.tavily_api_key),
        "github": bool(s.github_token),
        "models": {"fast": s.model_fast, "balanced": s.model_balanced, "deep": s.model_deep},
    }


@app.post("/runs")
async def create_run(req: MigrationRequest):
    settings = get_settings()
    if not settings.nebius_api_key:
        raise HTTPException(500, "NEBIUS_API_KEY is missing. Put it in .env at the repo root.")
    run_id = uuid.uuid4().hex[:8]
    run = Run(request=req)
    RUNS[run_id] = run

    async def go():
        run.report, run.ctx = await run_migration(
            req, settings, TokenFactoryLLM(settings), run.bus, run_id=run_id
        )

    run.task = asyncio.create_task(go())
    return {"run_id": run_id}


@app.get("/runs")
async def list_runs_endpoint():
    """List past migrations (newest-first) persisted to disk."""
    return {"runs": list_runs(get_settings())}


def _get(run_id: str) -> Run:
    if run_id not in RUNS:
        raise HTTPException(404, "unknown run")
    return RUNS[run_id]


@app.get("/runs/{run_id}/events")
async def events(run_id: str):
    from sse_starlette.sse import EventSourceResponse

    run = _get(run_id)

    async def gen():
        async for ev in run.bus.stream():
            yield {"event": ev.type, "data": ev.model_dump_json()}

    return EventSourceResponse(gen())


@app.get("/runs/{run_id}/diff")
async def get_diff(run_id: str):
    run = _get(run_id)
    if not run.ctx:
        raise HTTPException(409, "run not ready")
    return {"diff": await git.diff(run.ctx.root, run.ctx.base_sha)}


@app.get("/runs/{run_id}/pairs")
async def get_pairs(run_id: str):
    """Original C/C++ next to generated Rust, for the side-by-side UI."""
    run = _get(run_id)
    if not run.ctx:
        raise HTTPException(409, "run not ready")
    ctx = run.ctx
    pairs = []
    seen_targets = set()
    for rel, src in ctx.originals.items():
        target = ctx.adapter.target_path(rel)
        if target in seen_targets:
            # merge additional source (the .c after the .h) into the existing pair
            for p in pairs:
                if p["target"] == target:
                    p["source"] += f"\n\n/* ---- {rel} ---- */\n" + src
                    p["source_files"].append(rel)
                    break
            continue
        seen_targets.add(target)
        rust = ""
        p = ctx.root / target
        if p.exists():
            rust = p.read_text(errors="replace")
        pairs.append({
            "source_files": [rel],
            "source": src,
            "target": target,
            "rust": rust,
        })
    return {"pairs": pairs}


@app.get("/runs/{run_id}/report")
async def get_report(run_id: str):
    run = RUNS.get(run_id)
    if run and run.report:
        return run.report
    disk = load_report(get_settings(), run_id)
    if disk is None:
        raise HTTPException(404, "unknown run or report not available")
    return disk


@app.get("/runs/{run_id}")
async def get_run(run_id: str):
    run = _get(run_id)
    return {
        "run_id": run_id,
        "finished": run.bus.finished,
        "request": run.request.model_dump() if run.request else None,
        "report": run.report.model_dump() if run.report else None,
    }
