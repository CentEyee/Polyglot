"""Nebius Serverless Job entrypoint: one isolated container per migration.

    python -m polyglot.jobs.entrypoint request.json out/

Streams events as JSON lines on stdout and writes report.json + migration.diff to out/.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from polyglot.config import get_settings
from polyglot.events import EventBus
from polyglot.llm.client import TokenFactoryLLM
from polyglot.models import MigrationRequest
from polyglot.orchestrator import run_migration
from polyglot.vcs import repo as git


async def main(request_path: str, out_dir: str) -> int:
    settings = get_settings()
    req = MigrationRequest(**json.loads(Path(request_path).read_text()))
    bus = EventBus()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    async def pump():
        async for ev in bus.stream():
            print(ev.model_dump_json(), flush=True)

    pump_task = asyncio.create_task(pump())
    report, ctx = await run_migration(req, settings, TokenFactoryLLM(settings), bus)
    await pump_task
    (out / "report.json").write_text(report.model_dump_json(indent=2))
    if ctx:
        (out / "migration.diff").write_text(await git.diff(ctx.root, ctx.base_sha))
    return 0 if report.status in ("success", "partial") else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1], sys.argv[2])))
