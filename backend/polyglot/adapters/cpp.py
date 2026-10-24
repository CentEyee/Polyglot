"""C/C++ source adapter: include graph, function/struct signatures, gcc/make tests."""
from __future__ import annotations

import re
from pathlib import Path

from polyglot.adapters.base import LanguageAdapter
from polyglot.models import Failure, FileNode, Symbol, TestSummary

C_KEYWORDS = {
    "auto", "break", "case", "char", "const", "continue", "default", "do", "double",
    "else", "enum", "extern", "float", "for", "goto", "if", "inline", "int", "long",
    "register", "restrict", "return", "short", "signed", "sizeof", "static", "struct",
    "switch", "typedef", "union", "unsigned", "void", "volatile", "while", "bool",
    "true", "false", "class", "namespace", "template", "typename", "public", "private",
    "protected", "virtual", "override", "this", "new", "delete", "try", "catch",
    "throw", "using", "nullptr", "constexpr", "nullptr_t",
}

IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
INCLUDE_QUOTE = re.compile(r'#\s*include\s+"([^"]+)"')
INCLUDE_ANGLE = re.compile(r"#\s*include\s+<([^>]+)>")
STRUCT = re.compile(r"\b(?:typedef\s+)?struct\s+(\w+)\s*\{")
ENUM = re.compile(r"\benum\s+(?:class\s+)?(\w+)\s*\{")
FUNC = re.compile(
    r"^(?:static\s+|inline\s+|extern\s+|constexpr\s+)*"
    r"[\w:\s\*&<>,]+?\s+(\w+)\s*\(([^;{]*)\)\s*(?:const\s*)?\{",
    re.M,
)
FUNC_DECL = re.compile(
    r"^(?:static\s+|inline\s+|extern\s+|constexpr\s+)*"
    r"[\w:\s\*&<>,]+?\s+(\w+)\s*\(([^;{]*)\)\s*;",
    re.M,
)
COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.S)
COMMENT_LINE = re.compile(r"//.*?$", re.M)
STRING = re.compile(r'"(?:\\.|[^"\\])*"')


def strip_noise(source: str) -> str:
    source = COMMENT_BLOCK.sub(" ", source)
    source = COMMENT_LINE.sub(" ", source)
    return STRING.sub('""', source)


def rust_target(rel: str) -> str:
    stem = Path(rel).stem.replace("-", "_")
    if not stem.isidentifier():
        stem = "mod_" + re.sub(r"[^A-Za-z0-9_]", "_", stem)
    return f"rust-port/src/{stem}.rs"


class CppAdapter(LanguageAdapter):
    key = "cpp"
    extensions = (".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx")
    manifests = ("Makefile", "makefile", "CMakeLists.txt", "meson.build")

    def target_path(self, rel: str) -> str:
        return rust_target(rel)

    def index_source(self, source: str, rel: str) -> FileNode:
        text = strip_noise(source)
        symbols: list[Symbol] = []
        for m in STRUCT.finditer(text):
            symbols.append(Symbol(name=m.group(1), kind="struct", line=text[: m.start()].count("\n") + 1,
                                  signature=f"struct {m.group(1)}"))
        for m in ENUM.finditer(text):
            symbols.append(Symbol(name=m.group(1), kind="enum", line=text[: m.start()].count("\n") + 1,
                                  signature=f"enum {m.group(1)}"))
        seen_fn: set[str] = set()
        for m in list(FUNC.finditer(text)) + list(FUNC_DECL.finditer(text)):
            name, args = m.group(1), re.sub(r"\s+", " ", m.group(2)).strip()
            if name in {"if", "for", "while", "switch", "catch"} or name in seen_fn:
                continue
            seen_fn.add(name)
            symbols.append(Symbol(
                name=name, kind="function", line=text[: m.start()].count("\n") + 1,
                signature=f"{name}({args})",
            ))
        includes = INCLUDE_QUOTE.findall(source)
        used = sorted({t for t in IDENT.findall(text) if t not in C_KEYWORDS and len(t) > 1})
        return FileNode(
            path=rel, language="cpp", imports=includes, symbols=symbols, used_names=used,
            target_path=rust_target(rel),
        )

    def resolve_imports(self, files: dict[str, FileNode]) -> list[tuple[str, str]]:
        by_name: dict[str, list[str]] = {}
        for path in files:
            by_name.setdefault(Path(path).name, []).append(path)
            by_name.setdefault(Path(path).stem, []).append(path)
        edges: list[tuple[str, str]] = []
        for path, node in files.items():
            parent = str(Path(path).parent)
            for inc in node.imports:
                candidates = [
                    str(Path(parent) / inc),
                    inc,
                ]
                hit = next((c for c in candidates if c in files), None)
                if not hit:
                    alts = by_name.get(Path(inc).name, [])
                    hit = alts[0] if len(alts) == 1 else None
                if hit and hit != path:
                    edges.append((path, hit))
            # .c depends on sibling .h of the same stem
            stem_h = str(Path(path).with_suffix(".h"))
            if path.endswith((".c", ".cc", ".cpp")) and stem_h in files:
                edges.append((path, stem_h))
        return list(dict.fromkeys(edges))

    def check_syntax(self, source: str, rel: str) -> list[str]:
        # Brace-depth check is the portable guard; gcc is used in the sandbox test loop.
        depth = 0
        for ch in strip_noise(source):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth < 0:
                    return [f"{rel}: unmatched closing brace"]
        if depth != 0:
            return [f"{rel}: unmatched braces (depth {depth})"]
        return []

    def setup_commands(self, root: Path) -> list[list[str]]:
        return []

    def test_command(self) -> list[str]:
        return ["make", "test"]

    def parse_test_output(self, output: str, root: Path) -> tuple[TestSummary, list[Failure]]:
        failures: list[Failure] = []
        passed = failed = errors = 0
        for line in output.splitlines():
            if re.search(r"\bPASS\b|\bok\b", line) and "FAIL" not in line.upper():
                passed += 1
            m = re.search(r"FAIL[:\s]+(.+)", line)
            if m:
                failed += 1
                failures.append(Failure(id=m.group(1)[:80], message=line, trace=output[-3000:]))
            if "error:" in line.lower() or "undefined reference" in line:
                errors += 1
                failures.append(Failure(id=line[:80], message=line, files=[], trace=output[-3000:]))
        if "Error" in output and not failures:
            errors += 1
            failures.append(Failure(id="<make>", message="make test failed", trace=output[-4000:]))
        ok = not failures and "Error" not in output
        if passed == 0 and failed == 0 and errors == 0:
            ok = "error:" not in output.lower() and "FAIL" not in output
        return TestSummary(passed=passed, failed=failed, errors=errors, ok=ok,
                           failing_ids=[f.id for f in failures]), failures
