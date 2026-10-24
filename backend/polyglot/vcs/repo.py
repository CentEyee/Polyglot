"""Thin async git wrapper. Git is the source of truth for diffs, per-step commits and revert."""
from __future__ import annotations

import asyncio
from pathlib import Path


async def git(root: Path, *args: str, check: bool = True) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git", "-c", "user.name=PolyGlot Refactor", "-c", "user.email=bot@polyglot.invalid", *args,
        cwd=str(root), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    text = out.decode(errors="replace")
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {text}")
    return text


async def head(root: Path) -> str:
    return (await git(root, "rev-parse", "HEAD")).strip()


async def commit_paths(root: Path, paths: list[str], message: str) -> str | None:
    existing = [p for p in paths if (root / p).exists()]
    if not existing:
        return None
    await git(root, "add", "--", *existing)
    if not (await git(root, "diff", "--cached", "--name-only")).strip():
        return None
    await git(root, "commit", "-m", message)
    return await head(root)


async def restore_paths(root: Path, paths: list[str], sha: str) -> None:
    tracked = []
    for p in paths:
        # new files (rust-port/*) were not in base_sha — delete them instead of checkout
        probe = await git(root, "ls-tree", "-r", "--name-only", sha, "--", p, check=False)
        if probe.strip():
            tracked.append(p)
        else:
            fp = root / p
            if fp.exists() and fp.is_file():
                fp.unlink()
    if tracked:
        await git(root, "checkout", sha, "--", *tracked)


async def diff(root: Path, base_sha: str) -> str:
    return await git(root, "diff", f"{base_sha}..HEAD")


async def changed_files(root: Path, base_sha: str) -> list[str]:
    out = await git(root, "diff", "--name-only", f"{base_sha}..HEAD")
    return [l for l in out.splitlines() if l]
