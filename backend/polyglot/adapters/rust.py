"""Rust target adapter: cargo test parsing, module/fn indexing, syntax guard."""
from __future__ import annotations

import re
from pathlib import Path

from polyglot.adapters.base import LanguageAdapter
from polyglot.models import Failure, FileNode, Symbol, TestSummary

FN = re.compile(r"^\s*(?:pub(?:\([^)]+\))?\s+)?(?:async\s+)?fn\s+(\w+)\s*(?:<[^>]*>)?\s*(\([^)]*\))", re.M)
STRUCT = re.compile(r"^\s*(?:pub\s+)?(?:struct|enum)\s+(\w+)", re.M)
USE = re.compile(r"^\s*use\s+([^;]+);", re.M)
UNSAFE = re.compile(r"\bunsafe\b")
TEST_FAIL = re.compile(r"^test\s+(\S+)\s+\.\.\.\s+FAILED", re.M)
TEST_OK = re.compile(r"^test\s+(\S+)\s+\.\.\.\s+ok", re.M)
SUMMARY = re.compile(r"test result:.*?(\d+) passed;\s*(\d+) failed")


class RustAdapter(LanguageAdapter):
    key = "rust"
    extensions = (".rs",)
    manifests = ("Cargo.toml", "rust-port/Cargo.toml")

    def source_files(self, root: Path):
        out = []
        for p in root.rglob("*.rs"):
            rel = p.relative_to(root)
            if "target" in rel.parts:
                continue
            out.append(rel.as_posix())
        return sorted(out)

    def index_source(self, source: str, rel: str) -> FileNode:
        symbols: list[Symbol] = []
        for m in STRUCT.finditer(source):
            kind = "enum" if "enum" in m.group(0) else "struct"
            symbols.append(Symbol(name=m.group(1), kind=kind, line=source[: m.start()].count("\n") + 1,
                                  signature=m.group(0).strip()))
        for m in FN.finditer(source):
            symbols.append(Symbol(name=m.group(1), kind="function", line=source[: m.start()].count("\n") + 1,
                                  signature=f"fn {m.group(1)}{m.group(2)}"))
        uses = [u.strip() for u in USE.findall(source)]
        used = sorted({s.name for s in symbols})
        return FileNode(path=rel, language="rust", imports=uses, symbols=symbols, used_names=used, target_path=rel)

    def resolve_imports(self, files: dict[str, FileNode]) -> list[tuple[str, str]]:
        edges = []
        mods = {Path(p).stem: p for p in files}
        for path, node in files.items():
            for u in node.imports:
                name = u.split("::")[0].split(" as ")[0].strip()
                if name in mods and mods[name] != path:
                    edges.append((path, mods[name]))
        return edges

    def check_syntax(self, source: str, rel: str) -> list[str]:
        depth = 0
        for ch in source:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth < 0:
                    return [f"{rel}: unmatched closing brace"]
        if depth != 0:
            return [f"{rel}: unmatched braces (depth {depth})"]
        if "fn " not in source and "struct " not in source and "enum " not in source and "mod " not in source:
            if "Cargo.toml" not in rel:
                return [f"{rel}: generated Rust looks empty"]
        return []

    def test_command(self) -> list[str]:
        return ["cargo", "test", "--manifest-path", "rust-port/Cargo.toml", "--color", "never"]

    def parse_test_output(self, output: str, root: Path) -> tuple[TestSummary, list[Failure]]:
        ok_names = TEST_OK.findall(output)
        fail_names = TEST_FAIL.findall(output)
        failures = [
            Failure(id=n, message=f"test {n} FAILED", files=_files_from_trace(output, root), trace=output[-4000:])
            for n in fail_names
        ]
        compile_errors = [ln for ln in output.splitlines() if "error[" in ln or ln.strip().startswith("error:")]
        if compile_errors and not failures:
            failures.append(Failure(
                id="cargo-build",
                message=compile_errors[0],
                files=_files_from_trace(output, root),
                trace=output[-4000:],
            ))
        m = SUMMARY.search(output)
        passed = int(m.group(1)) if m else len(ok_names)
        failed = int(m.group(2)) if m else len(fail_names)
        errors = 1 if compile_errors and failed == 0 else 0
        ok = failed == 0 and errors == 0 and "error:" not in output
        if m and m.group(0).startswith("test result: ok"):
            ok = failed == 0
        return TestSummary(passed=passed, failed=failed, errors=errors, ok=ok,
                           failing_ids=[f.id for f in failures]), failures


def count_unsafe(root: Path) -> int:
    n = 0
    port = root / "rust-port"
    if not port.exists():
        return 0
    for p in port.rglob("*.rs"):
        if "target" in p.parts:
            continue
        n += len(UNSAFE.findall(p.read_text(errors="replace")))
    return n


def _files_from_trace(output: str, root: Path) -> list[str]:
    found = []
    for m in re.finditer(r"(rust-port/src/\S+\.rs|\S+\.rs):(\d+)", output):
        rel = m.group(1)
        if (root / rel).exists() or rel.startswith("src/") or rel.startswith("rust-port/"):
            found.append(rel if rel.startswith("rust-port/") else f"rust-port/{rel}" if (root / "rust-port" / rel).exists() else rel)
    return list(dict.fromkeys(found))
