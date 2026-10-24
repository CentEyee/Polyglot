"""Tiered LLM access over Nebius Token Factory (OpenAI-compatible API).

Tiers map to Nemotron sizes: FAST=Nano, BALANCED=Super, DEEP=Ultra.
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from polyglot.config import Settings


class Tier(str, Enum):
    FAST = "fast"
    BALANCED = "balanced"
    DEEP = "deep"


ESCALATE = {Tier.FAST: Tier.BALANCED, Tier.BALANCED: Tier.DEEP, Tier.DEEP: Tier.DEEP}
TIER_BY_RISK = {"low": Tier.FAST, "medium": Tier.BALANCED, "high": Tier.DEEP}


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0
    by_tier: dict[str, int] = field(default_factory=dict)

    def add(self, tier: Tier, prompt: int, completion: int) -> None:
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.calls += 1
        self.by_tier[tier.value] = self.by_tier.get(tier.value, 0) + 1


class LLM(Protocol):
    usage: Usage

    async def complete(
        self, tier: Tier, system: str, user: str, *, json_mode: bool = False, temperature: float = 0.0
    ) -> str: ...


class TokenFactoryLLM:
    def __init__(self, settings: Settings):
        from openai import AsyncOpenAI

        base = settings.nebius_base_url.rstrip("/") + "/"
        self._client = AsyncOpenAI(base_url=base, api_key=settings.nebius_api_key)
        self._models = {
            Tier.FAST: settings.model_fast,
            Tier.BALANCED: settings.model_balanced,
            Tier.DEEP: settings.model_deep,
        }
        self.usage = Usage()

    async def complete(self, tier, system, user, *, json_mode=False, temperature=0.0) -> str:
        kwargs = dict(
            model=self._models[tier],
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=temperature,
        )
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                try:
                    if json_mode:
                        resp = await self._client.chat.completions.create(
                            response_format={"type": "json_object"}, **kwargs
                        )
                    else:
                        resp = await self._client.chat.completions.create(**kwargs)
                except Exception:
                    if not json_mode:
                        raise
                    resp = await self._client.chat.completions.create(**kwargs)
                u = resp.usage
                self.usage.add(tier, getattr(u, "prompt_tokens", 0) or 0, getattr(u, "completion_tokens", 0) or 0)
                return resp.choices[0].message.content or ""
            except Exception as e:
                last_err = e
                await asyncio.sleep(2**attempt)
        raise RuntimeError(f"LLM call failed after retries: {last_err}")


_FENCE = re.compile(r"```[\w+-]*\n(.*?)```", re.S)


def extract_code(text: str) -> str:
    m = _FENCE.search(text)
    return (m.group(1) if m else text).rstrip("\n") + "\n"


def extract_json(text: str) -> dict:
    t = text.strip()
    m = _FENCE.search(t)
    if m:
        t = m.group(1)
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in model output")
    return json.loads(t[start : end + 1])
