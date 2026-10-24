"""A LanguageAdapter is the only place language-specific knowledge lives."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from polyglot.models import FileNode, Failure, TestSummary

IGNORE_DIRS = {
    ".git",
    "node_modules",
    "venv",
    ".venv",
    "__pycache__",
    "target",
    "build",
    "dist",
    ".tox",
    "rust-port",
}


class LanguageAdapter(ABC):
    key: str = ""
    extensions: tuple[str, ...] = ()
    manifests: tuple[str, ...] = ()

    def source_files(self, root: Path) -> list[str]:
        out = []
        for p in root.rglob("*"):
            if p.is_file() and p.suffix in self.extensions and not (set(p.relative_to(root).parts) & IGNORE_DIRS):
                out.append(p.relative_to(root).as_posix())
        return sorted(out)

    def manifest_files(self, root: Path) -> list[str]:
        return sorted(m for m in self.manifests if (root / m).exists())

    @abstractmethod
    def index_source(self, source: str, rel: str) -> FileNode: ...

    def index_file(self, root: Path, rel: str) -> FileNode:
        return self.index_source((root / rel).read_text(errors="replace"), rel)

    @abstractmethod
    def resolve_imports(self, files: dict[str, FileNode]) -> list[tuple[str, str]]:
        """Return (dependent, dependency) edges between repo files."""

    @abstractmethod
    def check_syntax(self, source: str, rel: str) -> list[str]:
        """Return a list of syntax errors ([] if the file parses)."""

    def is_test_file(self, rel: str) -> bool:
        low = rel.lower()
        return "test" in Path(low).name or "/tests/" in f"/{low}" or "/test/" in f"/{low}"

    def setup_commands(self, root: Path) -> list[list[str]]:
        return []

    @abstractmethod
    def test_command(self) -> list[str]: ...

    @abstractmethod
    def parse_test_output(self, output: str, root: Path) -> tuple[TestSummary, list[Failure]]: ...

    def target_path(self, rel: str) -> str:
        """Where a migrated file should land. Default: same path."""
        return rel
