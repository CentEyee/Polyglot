"""Shared data contracts. Everything the pipeline passes around is defined here."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class MigrationRequest(BaseModel):
    repo_url: str
    ref: str = "main"
    instruction: str = "Migrate this C/C++ codebase to safe idiomatic Rust"
    language: str | None = None  # force an adapter key; otherwise auto-detected
    target_language: str = "rust"
    max_repair_iters: int = 4
    open_pr: bool = False


class Symbol(BaseModel):
    name: str
    kind: Literal["function", "class", "method", "struct", "enum", "const", "macro", "other"] = "other"
    line: int = 0
    signature: str = ""


class FileNode(BaseModel):
    path: str
    language: str
    imports: list[str] = Field(default_factory=list)
    symbols: list[Symbol] = Field(default_factory=list)
    used_names: list[str] = Field(default_factory=list)
    parse_error: bool = False
    deprecated_hits: list[str] = Field(default_factory=list)
    target_path: str = ""


class CodeGraph(BaseModel):
    files: dict[str, FileNode]
    edges: list[tuple[str, str]] = Field(default_factory=list)


class BreakingChange(BaseModel):
    symbol: str
    description: str
    replacement: str = ""
    source_url: str = ""


class Knowledge(BaseModel):
    breaking_changes: list[BreakingChange] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class PlanStep(BaseModel):
    id: str
    title: str
    files: list[str]
    depends_on: list[str] = Field(default_factory=list)
    breaking_change: str = ""
    strategy: Literal["codemod", "llm"] = "llm"
    codemod: str | None = None
    codemod_args: dict[str, str] = Field(default_factory=dict)
    risk: Literal["low", "medium", "high"] = "medium"
    allowed_symbol_changes: list[str] = Field(default_factory=list)
    target_files: list[str] = Field(default_factory=list)


class Plan(BaseModel):
    summary: str
    steps: list[PlanStep]


class Failure(BaseModel):
    id: str
    message: str = ""
    files: list[str] = Field(default_factory=list)
    trace: str = ""


class TestSummary(BaseModel):
    passed: int = 0
    failed: int = 0
    errors: int = 0
    ok: bool = False
    failing_ids: list[str] = Field(default_factory=list)


class StepOutcome(BaseModel):
    step_id: str
    title: str
    status: Literal["done", "flagged", "skipped"]
    files_changed: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SignatureChange(BaseModel):
    source_file: str
    source_sig: str
    target_file: str
    target_sig: str
    kind: str = "function"
    notes: str = ""


class RunReport(BaseModel):
    status: Literal["success", "partial", "failed"] = "failed"
    tests_before: TestSummary | None = None
    tests_after: TestSummary | None = None
    steps: list[StepOutcome] = Field(default_factory=list)
    signatures: list[SignatureChange] = Field(default_factory=list)
    repair_iterations: int = 0
    files_changed: int = 0
    wall_seconds: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    llm_calls: int = 0
    calls_by_tier: dict[str, int] = Field(default_factory=dict)
    unsafe_blocks: int = 0
    pr_url: str | None = None
    notes: list[str] = Field(default_factory=list)
    plan_summary: str = ""
