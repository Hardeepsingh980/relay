"""In-process event streams for SSE (analysis progress, live handover updates).

Events carry stable ids (`<stream>:<n>`) so a reconnecting client can resume
from Last-Event-ID without duplicating items.
"""

from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime
from typing import Any, AsyncIterator

from .config import IST


def _scoped(stream: str) -> str:
    """Streams are per workspace: the same handover id in two workspaces never shares events."""
    from .db import current_graph_name
    return f"{current_graph_name()}::{stream}"


class EventBus:
    def __init__(self) -> None:
        self._streams: dict[str, list[dict]] = {}
        self._closed: set[str] = set()
        self._lock = threading.Lock()

    def emit(self, stream: str, type_: str, payload: dict[str, Any] | None = None) -> dict:
        key = _scoped(stream)
        with self._lock:
            events = self._streams.setdefault(key, [])
            ev = {"eventId": f"{stream}:{len(events) + 1}", "type": type_,
                  "timestamp": datetime.now(IST).isoformat(), "payload": payload or {}}
            events.append(ev)
        return ev

    def close(self, stream: str) -> None:
        with self._lock:
            self._closed.add(_scoped(stream))

    def reopen(self, stream: str) -> None:
        with self._lock:
            self._closed.discard(_scoped(stream))

    def events(self, stream: str) -> list[dict]:
        with self._lock:
            return list(self._streams.get(_scoped(stream), []))

    def reset(self, everything: bool = False) -> None:
        """Clear this workspace's streams (or all of them)."""
        with self._lock:
            if everything:
                self._streams.clear()
                self._closed.clear()
                return
            prefix = _scoped("")
            for k in [k for k in self._streams if k.startswith(prefix)]:
                del self._streams[k]
            self._closed = {k for k in self._closed if not k.startswith(prefix)}

    async def subscribe(self, stream: str, last_event_id: str | None = None,
                        follow: bool = True, idle_timeout: float = 600) -> AsyncIterator[dict]:
        key = _scoped(stream)
        sent = 0
        if last_event_id and last_event_id.startswith(stream + ":"):
            try:
                sent = int(last_event_id.rsplit(":", 1)[1])
            except ValueError:
                sent = 0
        idle_since = time.monotonic()
        while True:
            with self._lock:
                events = self._streams.get(key, [])
                fresh = events[sent:]
                closed = key in self._closed
            for ev in fresh:
                yield ev
            if fresh:
                sent += len(fresh)
                idle_since = time.monotonic()
            elif closed or not follow or time.monotonic() - idle_since > idle_timeout:
                return
            await asyncio.sleep(0.1)


bus = EventBus()
