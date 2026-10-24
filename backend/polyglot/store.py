"""Lightweight on-disk run store so migrations survive API restarts.

Each run gets a directory under WORKDIR/runs/<run_id>/ containing:
  report.json   final RunReport (dict)
  events.jsonl  append-only event stream (best-effort; live stream stays in-memory)
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _runs_dir(settings) -> Path:
    return Path(settings.workdir) / "runs"


def run_dir(settings, run_id: str) -> Path:
    d = _runs_dir(settings) / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_report(settings, run_id: str, report: dict[str, Any]) -> None:
    d = run_dir(settings, run_id)
    (d / "report.json").write_text(
        json.dumps(report, default=str, indent=2), encoding="utf-8"
    )


def save_event(settings, run_id: str, event: dict[str, Any]) -> None:
    """Append a single event to the run's JSONL log (best-effort)."""
    try:
        d = run_dir(settings, run_id)
        with open(d / "events.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(event, default=str) + "\n")
    except OSError:
        pass


def list_runs(settings) -> list[dict[str, Any]]:
    """Return past runs newest-first, with a small summary from report.json."""
    root = _runs_dir(settings)
    if not root.exists():
        return []
    out: list[dict[str, Any]] = []
    for d in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        rep = d / "report.json"
        if not rep.is_file():
            continue
        try:
            data = json.loads(rep.read_text(encoding="utf-8"))
        except Exception:
            continue
        ta = data.get("tests_after") or {}
        out.append(
            {
                "run_id": d.name,
                "status": data.get("status"),
                "wall_seconds": data.get("wall_seconds"),
                "files_changed": data.get("files_changed"),
                "tests_passed": ta.get("passed") if isinstance(ta, dict) else None,
                "tests_failed": ta.get("failed") if isinstance(ta, dict) else None,
                "repair_iterations": data.get("repair_iterations"),
                "unsafe_blocks": data.get("unsafe_blocks"),
                "llm_calls": data.get("llm_calls"),
                "pr_url": data.get("pr_url"),
                "plan_summary": data.get("plan_summary"),
                "tokens": (
                    (data.get("prompt_tokens") or 0) + (data.get("completion_tokens") or 0)
                ),
            }
        )
    return out


def load_report(settings, run_id: str) -> dict[str, Any] | None:
    p = _runs_dir(settings) / run_id / "report.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_events(settings, run_id: str) -> list[dict[str, Any]]:
    p = _runs_dir(settings) / run_id / "events.jsonl"
    if not p.is_file():
        return []
    out: list[dict[str, Any]] = []
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out
