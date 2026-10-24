from __future__ import annotations

from pathlib import Path

from polyglot.adapters.rust import RustAdapter
from polyglot.models import CodeGraph, SignatureChange


def collect_signatures(root: Path, graph: CodeGraph | None) -> list[SignatureChange]:
    if not graph:
        return []
    rust = RustAdapter()
    by_target: dict[str, list[str]] = {}
    for node in graph.files.values():
        target = node.target_path or rust.target_path(node.path)
        by_target.setdefault(target, [])
        for s in node.symbols:
            by_target[target].append(s.signature or s.name)

    out: list[SignatureChange] = []
    for target, src_sigs in by_target.items():
        path = root / target
        if not path.exists():
            continue
        indexed = rust.index_source(path.read_text(errors="replace"), target)
        rust_sigs = {s.name: s.signature or s.name for s in indexed.symbols}
        used = set()
        for src in src_sigs:
            name = src.split("(")[0].split()[-1]
            dest = rust_sigs.get(name, "")
            used.add(name)
            out.append(SignatureChange(
                source_file=next((n.path for n in graph.files.values() if n.target_path == target), ""),
                source_sig=src,
                target_file=target,
                target_sig=dest or "(not found)",
                notes="" if dest else "no matching Rust item",
            ))
        for name, sig in rust_sigs.items():
            if name not in used and not name.startswith("test_"):
                out.append(SignatureChange(
                    source_file="", source_sig="(new)", target_file=target, target_sig=sig, notes="Rust-only helper",
                ))
    return out
