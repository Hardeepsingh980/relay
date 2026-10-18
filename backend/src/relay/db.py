"""Thin FalkorDB access layer: one graph per tenant, parameterized queries only."""

from __future__ import annotations

import threading
import time
from collections import deque
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Iterable

from falkordb import FalkorDB, Graph

from .config import settings

# One graph per workspace (tenant). The API sets this per request from the session;
# CLI tools and tests fall back to the configured graph.
_current_graph: ContextVar[str | None] = ContextVar("relay_graph", default=None)
_current_workspace: ContextVar[str | None] = ContextVar("relay_workspace", default=None)


def current_workspace_id() -> str | None:
    return _current_workspace.get()


def use_workspace(wid: str | None, graph_name: str | None):
    return _current_workspace.set(wid), _current_graph.set(graph_name)


@lru_cache
def _client() -> FalkorDB:
    s = settings()
    return FalkorDB(host=s.falkor_host, port=s.falkor_port)


def current_graph_name() -> str:
    return _current_graph.get() or settings().graph_name


def use_graph(name: str | None):
    """Select the workspace graph for the current context. Returns a token for reset()."""
    return _current_graph.set(name)


def reset_graph(token) -> None:
    _current_graph.reset(token)


def graph(name: str | None = None) -> Graph:
    return _client().select_graph(name or current_graph_name())


def exists(name: str) -> bool:
    return name in _client().list_graphs()


def _plain(value: Any) -> Any:
    """Convert falkordb Node/Edge/Path objects into plain dicts."""
    if hasattr(value, "labels") and hasattr(value, "properties"):
        return {"_labels": list(value.labels), **value.properties}
    if hasattr(value, "relation") and hasattr(value, "properties"):
        return {"_type": value.relation, **value.properties}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    return value


class _Meter:
    """Process-wide query counter per graph, for the throughput view (queries/second, p50 latency)."""

    def __init__(self, window: float = 10.0):
        self.window = window
        self.lock = threading.Lock()
        self.events: dict[str, deque] = {}
        self.totals: dict[str, int] = {}

    def record(self, graph_name: str, ms: float) -> None:
        now = time.time()
        with self.lock:
            q = self.events.setdefault(graph_name, deque())
            q.append((now, ms))
            self.totals[graph_name] = self.totals.get(graph_name, 0) + 1
            while q and q[0][0] < now - self.window:
                q.popleft()

    def snapshot(self) -> dict[str, dict]:
        now = time.time()
        out = {}
        with self.lock:
            for name, q in self.events.items():
                recent = [ms for t, ms in q if t >= now - self.window]
                recent.sort()
                out[name] = {"qps": round(len(recent) / self.window, 1), "total": self.totals.get(name, 0),
                             "p50ms": round(recent[len(recent) // 2], 1) if recent else None,
                             "p95ms": round(recent[int(len(recent) * 0.95)], 1) if recent else None}
        return out


meter = _Meter()


@dataclass
class QueryResult:
    cypher: str
    params: dict
    rows: list[dict] = field(default_factory=list)
    ms: float = 0.0
    graph: str = ""


def rows(query: str, params: dict[str, Any] | None = None, *, g: Graph | None = None,
         readonly: bool = False, timeout: int | None = None) -> list[dict[str, Any]]:
    """Run a query and return rows as dicts keyed by the RETURN aliases."""
    return timed(query, params, g=g, readonly=readonly, timeout=timeout).rows


def timed(query: str, params: dict[str, Any] | None = None, *, g: Graph | None = None,
          readonly: bool = True, timeout: int | None = None) -> QueryResult:
    """Run a query and keep the Cypher, params, rows and latency (for "Show Cypher")."""
    g = g or graph()
    fn = g.ro_query if readonly else g.query
    t0 = time.perf_counter()
    res = fn(query, params or {}, timeout=timeout)
    ms = (time.perf_counter() - t0) * 1000
    meter.record(g.name, ms)
    header = [h[1] if isinstance(h, (list, tuple)) else h for h in (res.header or [])]
    out = [{header[i]: _plain(v) for i, v in enumerate(r)} for r in res.result_set]
    return QueryResult(cypher=query.strip(), params=params or {}, rows=out, ms=round(ms, 1), graph=g.name)


def run(query: str, params: dict[str, Any] | None = None, *, g: Graph | None = None,
        timeout: int | None = None) -> None:
    g = g or graph()
    t0 = time.perf_counter()
    g.query(query, params or {}, timeout=timeout)
    meter.record(g.name, (time.perf_counter() - t0) * 1000)


def batched(query: str, items: Iterable[dict[str, Any]], *, size: int = 500,
            g: Graph | None = None, key: str = "rows") -> int:
    """UNWIND-style bulk write: `query` must reference `$rows`."""
    g = g or graph()
    buf: list[dict[str, Any]] = []
    n = 0
    for item in items:
        buf.append(item)
        if len(buf) >= size:
            g.query(query, {key: buf}, timeout=60000)
            n += len(buf)
            buf = []
    if buf:
        g.query(query, {key: buf}, timeout=60000)
        n += len(buf)
    return n
