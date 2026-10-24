from __future__ import annotations

from pathlib import Path

from polyglot.adapters.base import LanguageAdapter
from polyglot.models import CodeGraph, Knowledge


def build_graph(root: Path, adapter: LanguageAdapter) -> CodeGraph:
    files = {rel: adapter.index_file(root, rel) for rel in adapter.source_files(root)}
    return CodeGraph(files=files, edges=adapter.resolve_imports(files))


def mark_deprecated(graph: CodeGraph, knowledge: Knowledge) -> None:
    symbols = {bc.symbol for bc in knowledge.breaking_changes}
    for node in graph.files.values():
        node.deprecated_hits = sorted(symbols & set(node.used_names))


def summarize(graph: CodeGraph, limit: int = 120) -> str:
    hits = [n for n in graph.files.values() if n.deprecated_hits] or list(graph.files.values())
    lines = [f"files={len(graph.files)} edges={len(graph.edges)} units={len(hits)}"]
    for n in hits[:limit]:
        sigs = ", ".join(s.signature or s.name for s in n.symbols[:8]) or "(no symbols)"
        extra = f" uses {', '.join(n.deprecated_hits)}" if n.deprecated_hits else ""
        lines.append(f"- {n.path} → {n.target_path}: {sigs}{extra}")
    lines.append("include edges (dependent -> dependency):")
    for a, b in graph.edges[:80]:
        lines.append(f"  {a} -> {b}")
    return "\n".join(lines)
