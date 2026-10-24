from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from polyglot.adapters.base import LanguageAdapter
from polyglot.config import Settings
from polyglot.events import EventBus
from polyglot.llm.client import LLM
from polyglot.models import CodeGraph, Knowledge, MigrationRequest, Plan, SignatureChange, TestSummary
from polyglot.sandbox.base import Sandbox


@dataclass
class RunContext:
    request: MigrationRequest
    root: Path
    adapter: LanguageAdapter
    target_adapter: LanguageAdapter
    sandbox: Sandbox
    llm: LLM
    bus: EventBus
    settings: Settings
    base_sha: str = ""
    graph: CodeGraph | None = None
    knowledge: Knowledge = field(default_factory=Knowledge)
    plan: Plan | None = None
    baseline: TestSummary = field(default_factory=TestSummary)
    file_to_step: dict[str, str] = field(default_factory=dict)
    flagged_steps: set[str] = field(default_factory=set)
    originals: dict[str, str] = field(default_factory=dict)
    signatures: list[SignatureChange] = field(default_factory=list)
