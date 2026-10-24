"""Run eval/cases.json headlessly and emit eval/results.md for the demo video."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from polyglot.config import get_settings
from polyglot.events import EventBus
from polyglot.llm.client import TokenFactoryLLM
from polyglot.models import MigrationRequest
from polyglot.orchestrator import run_migration

ROOT = Path(__file__).resolve().parents[1]


async def main() -> None:
    settings = get_settings()
    rows = [
        "| Case | Status | Files | Tests after | Repair | Calls | Tokens | Time (s) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for case in json.loads((ROOT / "eval" / "cases.json").read_text()):
        name = case.pop("name")
        if case.get("repo_url", "").startswith("examples/"):
            case["repo_url"] = str(ROOT / case["repo_url"])
        llm = TokenFactoryLLM(settings)
        report, _ = await run_migration(MigrationRequest(**case), settings, llm, EventBus())
        a = report.tests_after
        after = "n/a" if a is None else f"{a.passed}p/{a.failed}f"
        rows.append(
            f"| {name} | {report.status} | {report.files_changed} | {after} | "
            f"{report.repair_iterations} | {report.llm_calls} | "
            f"{report.prompt_tokens + report.completion_tokens} | {report.wall_seconds:.0f} |"
        )
        print(rows[-1], flush=True)
    (ROOT / "eval" / "results.md").write_text("\n".join(rows) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
