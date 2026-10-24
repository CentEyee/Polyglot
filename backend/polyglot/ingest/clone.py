from __future__ import annotations

import asyncio
import shutil
from pathlib import Path


async def clone_repo(repo_url: str, ref: str, dest: Path) -> Path:
    """Shallow-clone into dest. Local paths work too (tests, the bundled example)."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    args = ["git", "clone", "--depth", "1"]
    if ref and "://" in repo_url:
        args += ["--branch", ref]
    args += [repo_url, str(dest)]
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    out, _ = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"clone failed: {out.decode(errors='replace')}")
    return dest
