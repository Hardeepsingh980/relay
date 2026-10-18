"""Alias matching against the live graph (for answers and questions typed in Relay)."""

from __future__ import annotations

from functools import lru_cache

from . import db
from .ingest.resolve import Alias, AliasMatcher


def matcher() -> AliasMatcher:
    return _matcher(db.current_graph_name())


@lru_cache(maxsize=64)
def _matcher(graph_name: str) -> AliasMatcher:
    """Aliases per graph (tenants and workspaces have different systems and accounts)."""
    g = db.graph(graph_name)
    aliases = []
    for r in db.rows("MATCH (s:System) RETURN s.id AS id, s.name AS name, s.aliases AS aliases", g=g, readonly=True):
        for a in {r["name"], *(r["aliases"] or [])}:
            aliases.append(Alias(r["id"], "System", a.lower()))
    for r in db.rows("MATCH (c:Account) RETURN c.id AS id, c.name AS name, c.aliases AS aliases", g=g, readonly=True):
        for a in {r["name"], *(r["aliases"] or [])}:
            aliases.append(Alias(r["id"], "Account", a.lower()))
    return AliasMatcher(aliases)


def mentions(text: str) -> list[dict]:
    seen, out = set(), []
    for a, surface in matcher().find(text or ""):
        if a.entity_id not in seen:
            seen.add(a.entity_id)
            out.append({"id": a.entity_id, "label": a.label, "surface": surface})
    return out
