"""Command execution for untrusted repo code.

LocalSandbox: run inside the current process/container. On Nebius Serverless Jobs the
job container is the isolation boundary. DockerSandbox is for local development.
Secrets (GitHub token, API keys) are never passed into the sandbox env.
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

MAX_OUTPUT = 40_000


@dataclass
class ExecResult:
    code: int
    output: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.code == 0 and not self.timed_out


class Sandbox(Protocol):
    async def run(self, cmd: list[str], cwd: Path, timeout: int = 600) -> ExecResult: ...


def _clip(s: str) -> str:
    return s if len(s) <= MAX_OUTPUT else "...[truncated]...\n" + s[-MAX_OUTPUT:]


async def _exec(argv: list[str], cwd: Path, timeout: int, env: dict[str, str]) -> ExecResult:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return ExecResult(proc.returncode or 0, _clip(out.decode(errors="replace")))
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return ExecResult(124, "command timed out", timed_out=True)


class LocalSandbox:
    SAFE_ENV = (
        "PATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "CARGO_HOME",
        "RUSTUP_HOME",
        "RUSTFLAGS",
        "CC",
        "CXX",
    )

    async def run(self, cmd: list[str], cwd: Path, timeout: int = 600) -> ExecResult:
        env = {k: v for k, v in os.environ.items() if k in self.SAFE_ENV}
        env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
        env["CI"] = "1"
        env["CARGO_TERM_COLOR"] = "never"
        return await _exec(cmd, cwd, timeout, env)


class DockerSandbox:
    def __init__(self, image: str = "polyglot-sandbox:latest", network: str = "bridge"):
        self.image, self.network = image, network

    async def run(self, cmd: list[str], cwd: Path, timeout: int = 600) -> ExecResult:
        argv = [
            "docker",
            "run",
            "--rm",
            f"--network={self.network}",
            "--memory=4g",
            "--cpus=2",
            "-v",
            f"{cwd}:/work",
            "-w",
            "/work",
            self.image,
            *cmd,
        ]
        return await _exec(argv, cwd, timeout, dict(os.environ))


def make_sandbox(kind: str) -> Sandbox:
    return DockerSandbox() if kind == "docker" else LocalSandbox()
