"""Branch, push and open a PR. The GitHub token is used only here, never inside the sandbox."""
from __future__ import annotations

import re
from pathlib import Path

import httpx

from polyglot.vcs import repo as git


async def open_pull_request(root: Path, repo_url: str, base: str, branch: str, title: str, body: str, token: str) -> str:
    m = re.search(r"github\.com[/:]([^/]+)/([^/.]+)", repo_url)
    if not m:
        raise ValueError("PR creation supports github.com repos")
    owner, name = m.groups()
    await git.git(root, "checkout", "-B", branch)
    remote = f"https://x-access-token:{token}@github.com/{owner}/{name}.git"
    await git.git(root, "push", remote, f"HEAD:refs/heads/{branch}")
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"https://api.github.com/repos/{owner}/{name}/pulls",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            json={"title": title, "head": branch, "base": base, "body": body},
        )
        r.raise_for_status()
        return r.json()["html_url"]
