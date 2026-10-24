"""Append-only run event log with live fan-out. The UI renders from this stream (SSE)."""
from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator

from pydantic import BaseModel, Field


class Event(BaseModel):
    type: str
    ts: float = Field(default_factory=time.time)
    data: dict = Field(default_factory=dict)


class EventBus:
    def __init__(self) -> None:
        self.history: list[Event] = []
        self._subs: set[asyncio.Queue[Event]] = set()
        self.finished = False

    def emit(self, type: str, **data) -> None:
        ev = Event(type=type, data=data)
        self.history.append(ev)
        for q in self._subs:
            q.put_nowait(ev)
        if type == "run.finished":
            self.finished = True

    async def stream(self) -> AsyncIterator[Event]:
        q: asyncio.Queue[Event] = asyncio.Queue()
        snapshot = list(self.history)
        self._subs.add(q)
        try:
            for ev in snapshot:
                yield ev
                if ev.type == "run.finished":
                    return
            while True:
                ev = await q.get()
                yield ev
                if ev.type == "run.finished":
                    return
        finally:
            self._subs.discard(q)
