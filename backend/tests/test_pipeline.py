"""End-to-end C→Rust pipeline with a scripted LLM (no network)."""
import json
import subprocess
from pathlib import Path

import pytest

from polyglot.config import Settings
from polyglot.events import EventBus
from polyglot.models import MigrationRequest
from polyglot.orchestrator import run_migration
from tests.fakes import FailThenOkSandbox, OkSandbox, ScriptedLLM

HEADER = """#ifndef SATADD_H
#define SATADD_H
int add(int a, int b);
#endif
"""
SOURCE = """#include "satadd.h"
int add(int a, int b) { return a + b; }
"""
MAKE = "test:\n\t@echo PASS test_add\n"

RUST_OK = """
pub fn add(a: i32, b: i32) -> i32 { a + b }

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn add_works() { assert_eq!(add(2, 2), 4); }
}
"""

PLAN = {
    "summary": "Translate satadd C library to Rust",
    "steps": [
        {
            "id": "s1",
            "title": "satadd module",
            "files": ["src/satadd.h", "src/satadd.c"],
            "risk": "medium",
            "allowed_symbol_changes": [],
        }
    ],
}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "origin"
    (r / "src").mkdir(parents=True)
    (r / "src" / "satadd.h").write_text(HEADER)
    (r / "src" / "satadd.c").write_text(SOURCE)
    (r / "Makefile").write_text(MAKE)
    for c in (
        ["init", "-q"],
        ["add", "."],
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"],
    ):
        subprocess.run(["git", *c], cwd=r, check=True)
    return r


def handler_ok(tier, system, user):
    if "planning" in system:
        return json.dumps(PLAN)
    if "repair" in system:
        return f"```rust\n{RUST_OK}```"
    if "satadd" in user or "File:" in user or "Write Rust" in user or "translation unit" in user:
        return f"```rust\n{RUST_OK}```"
    raise AssertionError(system[:60] + " | " + user[:80])


def settings(tmp_path) -> Settings:
    return Settings(workdir=str(tmp_path / "work"), tavily_api_key="", nebius_api_key="test")


async def test_happy_path_writes_rust_crate(repo, tmp_path):
    llm = ScriptedLLM(handler_ok)
    report, ctx = await run_migration(
        MigrationRequest(repo_url=str(repo), ref="", instruction="C to Rust"),
        settings(tmp_path), llm, EventBus(), sandbox=OkSandbox(),
    )
    assert report.status == "success", report.notes
    assert (ctx.root / "rust-port" / "Cargo.toml").exists()
    rust = (ctx.root / "rust-port" / "src" / "satadd.rs").read_text()
    assert "pub fn add" in rust
    assert report.files_changed >= 2
    assert any(s.source_sig.startswith("add") or "add(" in s.source_sig for s in report.signatures)


async def test_repair_loop_on_cargo_failure(repo, tmp_path):
    llm = ScriptedLLM(handler_ok)
    report, ctx = await run_migration(
        MigrationRequest(repo_url=str(repo), ref="", instruction="C to Rust", max_repair_iters=3),
        settings(tmp_path), llm, EventBus(), sandbox=FailThenOkSandbox(),
    )
    assert report.status == "success", report.notes
    assert report.repair_iterations >= 1
