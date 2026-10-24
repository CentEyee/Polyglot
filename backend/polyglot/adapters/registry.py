from __future__ import annotations

from collections import Counter
from pathlib import Path

from polyglot.adapters.base import IGNORE_DIRS, LanguageAdapter
from polyglot.adapters.cpp import CppAdapter
from polyglot.adapters.rust import RustAdapter

ADAPTERS: dict[str, LanguageAdapter] = {a.key: a for a in (CppAdapter(), RustAdapter())}


def get_adapter(key: str) -> LanguageAdapter:
    if key not in ADAPTERS:
        raise KeyError(f"unknown language adapter {key}; have {list(ADAPTERS)}")
    return ADAPTERS[key]


def detect_adapter(root: Path, forced: str | None = None) -> LanguageAdapter:
    if forced:
        return get_adapter(forced)
    counts: Counter[str] = Counter()
    for p in root.rglob("*"):
        if p.is_file() and not (set(p.relative_to(root).parts) & IGNORE_DIRS):
            for a in ADAPTERS.values():
                if p.suffix in a.extensions:
                    counts[a.key] += 1
    if not counts:
        raise ValueError("no supported C/C++ or Rust source files found")
    # Prefer C/C++ when both exist: this agent migrates *from* C.
    if "cpp" in counts:
        return ADAPTERS["cpp"]
    return ADAPTERS[counts.most_common(1)[0][0]]
