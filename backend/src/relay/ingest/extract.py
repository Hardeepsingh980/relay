"""Decisions and workarounds: extraction backends and the shared graph writer.

Two backends produce the same records:
  * seed:   reads the generator's annotations (deterministic, no API key)
  * gemini: asks the LLM to read each knowledge-bearing source (see llm_extract.py)

The writer turns them into Decision/Workaround nodes with ABOUT and
SOURCED_FROM edges, plus DECIDED/KNOWS edges scored by the role each person
played across all sources.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from falkordb import Graph

from datetime import datetime

from .. import db
from ..config import IST
from ..scoring import role_score
from .load import Exports, Resolver

SOURCE_LABEL = {"slack_thread": "Message", "meeting": "Meeting", "doc": "Doc", "commit": "Commit", "ticket": "Ticket"}


@dataclass
class ItemDef:
    id: str
    kind: str                    # "decision" | "workaround"
    summary: str
    rationale: str | None = None
    decided_at: str | None = None
    about: list[tuple[str, str]] = field(default_factory=list)   # (label, id)


@dataclass
class Extraction:
    source_label: str
    source_id: str
    kind: str                    # "decision" | "workaround" | "obsoletes"
    item: str
    roles: dict[str, str]        # person id -> role
    quote: str | None = None


@dataclass
class ExtractionResult:
    items: list[ItemDef]
    links: list[Extraction]
    version: str


def seed_extract(ex: Exports, rv: Resolver) -> ExtractionResult:
    root: Path = ex.root / "annotations"
    items = []
    for r in (json.loads(x) for x in (root / "items.jsonl").read_text().splitlines() if x.strip()):
        if r["kind"] not in ("decision", "workaround"):
            continue  # promises and playbooks are loaded by ingest.accounts
        about = [e for e in (rv.entity(n) for n in r["about"]) if e]
        items.append(ItemDef(r["id"], r["kind"], r["summary"], r.get("rationale"), r.get("decidedAt"), about))
    links = []
    for r in (json.loads(x) for x in (root / "extractions.jsonl").read_text().splitlines() if x.strip()):
        for a in r["annotations"]:
            roles = {}
            for email, role in a["roles"].items():
                label, pid = rv.actor(email)
                if label == "Person":
                    roles[pid] = role
            links.append(Extraction(SOURCE_LABEL[r["source_type"]], r["source_id"], a["kind"], a["item"], roles))
    return ExtractionResult(items, links, "seed-annotations@1")


def write(g: Graph, res: ExtractionResult) -> dict:
    labels = {"decision": "Decision", "workaround": "Workaround"}
    db.batched("""UNWIND $rows AS r CREATE (d:Decision {id: r.id, summary: r.summary, rationale: r.rationale,
                  decidedAt: r.decidedAt, extraction: r.v})""",
               [{"id": i.id, "summary": i.summary, "rationale": i.rationale, "decidedAt": i.decided_at, "v": res.version}
                for i in res.items if i.kind == "decision"], g=g)
    db.batched("""UNWIND $rows AS r CREATE (w:Workaround {id: r.id, summary: r.summary, status: 'active', extraction: r.v})""",
               [{"id": i.id, "summary": i.summary, "v": res.version} for i in res.items if i.kind == "workaround"], g=g)
    for i in res.items:
        for label, eid in i.about:
            db.run(f"MATCH (i:{labels[i.kind]} {{id: $i}}), (x:{label} {{id: $x}}) CREATE (i)-[:ABOUT]->(x)",
                   {"i": i.id, "x": eid}, g=g)

    kind_of = {i.id: i.kind for i in res.items}
    # Source timestamps, so each link knows when it was last seen.
    times: dict[tuple[str, str], float] = {}
    for label in {l.source_label for l in res.links}:
        ids = sorted({l.source_id for l in res.links if l.source_label == label})
        for r in db.rows(f"UNWIND $ids AS id MATCH (s:{label} {{id: id}}) RETURN s.id AS id, s.t AS t", {"ids": ids}, g=g):
            times[(label, r["id"])] = r["t"]

    per_person: dict[tuple[str, str], dict] = defaultdict(lambda: {"roles": [], "sources": [], "last": 0.0, "first": None})
    item_span: dict[str, list[float]] = defaultdict(list)
    sourced = []
    for l in res.links:
        t = times.get((l.source_label, l.source_id))
        if t is None:
            continue
        if l.kind == "obsoletes":
            db.run("""MATCH (t:Ticket {id: $t}), (w:Workaround {id: $w})
                      CREATE (t)-[:OBSOLETES]->(w) SET w.status = 'possibly-obsolete', w.obsoleteHint = t.title""",
                   {"t": l.source_id, "w": l.item}, g=g)
            continue
        if l.item not in kind_of:
            continue
        sourced.append({"item": l.item, "src": l.source_id, "label": l.source_label, "kind": labels[kind_of[l.item]],
                        "roles": json.dumps(l.roles), "quote": l.quote})
        item_span[l.item].append(t)
        for pid, role in l.roles.items():
            agg = per_person[(pid, l.item)]
            agg["roles"].append(role)
            agg["sources"].append(f"{l.source_label}:{l.source_id}")
            agg["last"] = max(agg["last"], t)
            agg["first"] = t if agg["first"] is None else min(agg["first"], t)

    for (kind, label), rows in _group(sourced, ("kind", "label")).items():
        db.batched(f"""UNWIND $rows AS r MATCH (i:{kind} {{id: r.item}}), (s:{label} {{id: r.src}})
                       CREATE (i)-[:SOURCED_FROM {{roles: r.roles, quote: r.quote}}]->(s)""", rows, g=g)
    for item, ts in item_span.items():
        label = labels[kind_of[item]]
        first_day = datetime.fromtimestamp(min(ts), IST).date().isoformat()
        db.run(f"""MATCH (i:{label} {{id: $id}}) SET i.firstSeen = $f, i.lastSeen = $l, i.sourceCount = $n,
                   i.decidedAt = CASE WHEN i:Decision THEN coalesce(i.decidedAt, $day) ELSE null END""",
               {"id": item, "f": min(ts), "l": max(ts), "n": len(ts), "day": first_day}, g=g)

    edges = defaultdict(list)
    for (pid, item), agg in per_person.items():
        best = max(agg["roles"], key=lambda r: role_score([r]))
        edges[kind_of[item]].append({"p": pid, "i": item, "score": round(role_score(agg["roles"]), 3),
                                     "role": best, "roles": agg["roles"], "sources": agg["sources"],
                                     "last": agg["last"], "first": agg["first"]})
    db.batched("""UNWIND $rows AS r MATCH (p:Person {id: r.p}), (d:Decision {id: r.i})
                  CREATE (p)-[:DECIDED {score: r.score, role: r.role, roles: r.roles, sources: r.sources,
                                        lastSeen: r.last, firstSeen: r.first}]->(d)""", edges["decision"], g=g)
    db.batched("""UNWIND $rows AS r MATCH (p:Person {id: r.p}), (w:Workaround {id: r.i})
                  CREATE (p)-[:KNOWS {score: r.score, role: r.role, roles: r.roles, sources: r.sources,
                                      lastSeen: r.last, firstSeen: r.first, basis: 'role'}]->(w)""",
               edges["workaround"], g=g)

    # A decision whose reasoning only lives in conversation is riskier than one in a doc.
    db.run("""MATCH (d:Decision) OPTIONAL MATCH (d)-[:SOURCED_FROM]->(doc:Doc)
              WITH d, count(doc) AS docs SET d.rationaleStatus = CASE WHEN docs > 0 THEN 'documented' ELSE 'conversation-only' END""",
           g=g)
    return {"items": len(res.items), "links": len(sourced), "people_edges": sum(len(v) for v in edges.values()),
            "version": res.version}


def _group(rows: list[dict], keys: tuple[str, ...]) -> dict[tuple, list[dict]]:
    out: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        out[tuple(r[k] for k in keys)].append(r)
    return out
