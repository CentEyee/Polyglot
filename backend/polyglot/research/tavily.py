"""Research stage: pull C→Rust / cxx / bindgen / unsafe guides, then extract structured mappings.

This grounds the planner in documentation instead of model memory (and targets Best Use of Tavily).
"""
from __future__ import annotations

import httpx

from polyglot.llm.client import LLM, Tier, extract_json
from polyglot.models import BreakingChange, Knowledge

TAVILY_URL = "https://api.tavily.com/search"

EXTRACT_SYSTEM = (
    "You extract C/C++ → Rust translation mappings from the provided documentation. "
    "Return ONLY JSON: {\"breaking_changes\":[{\"symbol\":str,\"description\":str,\"replacement\":str,\"source_url\":str}]}. "
    "`symbol` must be a single C/C++ identifier (malloc, free, strcpy, NULL, unique_ptr, new, delete, ...). "
    "Do not invent entries the text does not support."
)


async def tavily_search(query: str, api_key: str, max_results: int = 5) -> list[dict]:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            TAVILY_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"query": query, "max_results": max_results, "search_depth": "advanced", "include_answer": False},
        )
        r.raise_for_status()
        return r.json().get("results", [])


async def gather_knowledge(instruction: str, llm: LLM, tavily_key: str) -> Knowledge:
    results: list[dict] = []
    queries = (
        f"{instruction} C to Rust migration guide ownership malloc free",
        "C++ to Rust bindgen cxx crate unsafe equivalences changelog",
        "Rustonomicon translating C pointers to references and Box Vec",
    )
    if tavily_key:
        for q in queries:
            try:
                results += await tavily_search(q, tavily_key)
            except Exception:
                continue
    if not results:
        return Knowledge(sources=[])
    seen: set[str] = set()
    unique = []
    for r in results:
        url = r.get("url", "")
        if url in seen:
            continue
        seen.add(url)
        unique.append(r)
    corpus = "\n\n".join(f"SOURCE {r.get('url','')}\n{r.get('content','')[:2500]}" for r in unique[:8])
    raw = await llm.complete(Tier.BALANCED, EXTRACT_SYSTEM, f"Migration: {instruction}\n\n{corpus}", json_mode=True)
    try:
        data = extract_json(raw)
        changes = [BreakingChange(**c) for c in data.get("breaking_changes", []) if c.get("symbol")]
    except Exception:
        changes = []
    return Knowledge(breaking_changes=changes, sources=sorted(seen))
