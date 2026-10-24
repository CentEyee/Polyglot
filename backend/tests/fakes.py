from __future__ import annotations

from pathlib import Path

from polyglot.llm.client import Usage
from polyglot.sandbox.base import ExecResult


class ScriptedLLM:
    def __init__(self, handler):
        self.handler = handler
        self.usage = Usage()
        self.calls: list[tuple[str, str]] = []

    async def complete(self, tier, system, user, *, json_mode=False, temperature=0.0):
        self.calls.append((tier.value, system[:40]))
        self.usage.add(tier, 10, 10)
        return self.handler(tier, system, user)


class OkSandbox:
    """Pretend make/cargo succeeded so pipeline tests don't need a toolchain."""

    async def run(self, cmd: list[str], cwd: Path, timeout: int = 600) -> ExecResult:
        if cmd and cmd[0] == "make":
            return ExecResult(0, "PASS test_add\nPASS test_sat\n")
        if cmd and cmd[0] == "cargo":
            return ExecResult(
                0,
                "test satadd::tests::add_works ... ok\n"
                "test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out\n",
            )
        return ExecResult(0, "")


class FailThenOkSandbox:
    def __init__(self):
        self.cargo_runs = 0

    async def run(self, cmd: list[str], cwd: Path, timeout: int = 600) -> ExecResult:
        if cmd and cmd[0] == "make":
            return ExecResult(0, "PASS test_add\n")
        if cmd and cmd[0] == "cargo":
            self.cargo_runs += 1
            if self.cargo_runs == 1:
                return ExecResult(
                    101,
                    "error[E0425]: cannot find value `oops` in this scope\n"
                    "  --> rust-port/src/satadd.rs:1:1\n"
                    "test satadd::tests::add_works ... FAILED\n"
                    "test result: FAILED. 0 passed; 1 failed; 0 ignored; 0 measured; 0 filtered out\n",
                )
            return ExecResult(
                0,
                "test satadd::tests::add_works ... ok\n"
                "test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out\n",
            )
        return ExecResult(0, "")
