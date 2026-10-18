"""Expertise scoring: derive scored KNOWS edges (to systems and accounts) from evidence in the graph.

Each signal is a Cypher traversal over raw evidence (commits, reviews, docs,
thread answers, tickets, customer conversations). Python combines them with
the policy in scoring.py and writes one scored edge per (person, item), keeping
the component counts so the UI can say *why* ("214 commits, 9 threads answered").
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from falkordb import Graph

from .. import db
from ..config import DEMO_NOW
from ..scoring import HALF_LIFE_DAYS, OWNER_BONUS, SIGNAL_WEIGHTS, STALE_DAYS, squash

DECAY = "pow(0.5, ($now - {t}) / $hl)"

AGGREGATE_SIGNALS = {
    "commit": f"""MATCH (p:Person)-[:AUTHORED]->(c:Commit)-[:IN_REPO]->(x:System)
                 RETURN p.id AS p, x.id AS x, 'System' AS label, count(c) AS n,
                        sum({DECAY.format(t='c.t')}) AS w, max(c.t) AS last, min(c.t) AS first""",
    "review": f"""MATCH (p:Person)-[rv:REVIEWED]->(:PullRequest)-[:IN_REPO]->(x:System)
                 RETURN p.id AS p, x.id AS x, 'System' AS label, count(rv) AS n,
                        sum({DECAY.format(t='rv.t')}) AS w, max(rv.t) AS last, min(rv.t) AS first""",
    "doc": f"""MATCH (p:Person)-[:AUTHORED]->(d:Doc)-[:DOCUMENTS]->(x)
              RETURN p.id AS p, x.id AS x, labels(x)[0] AS label, count(d) AS n,
                     sum({DECAY.format(t='d.t')}) AS w, max(d.t) AS last, min(d.t) AS first""",
}

# Per-thread rows; a person answering several times in one thread counts once.
THREAD_SIGNALS = {
    "answer": [
        """MATCH (p:Person)-[:SENT]->(r:Message {substantive: true})-[:REPLY_TO]->(root:Message)-[:MENTIONS]->(x)
           WHERE NOT (p)-[:SENT]->(root)
           RETURN p.id AS p, x.id AS x, labels(x)[0] AS label, root.id AS thread, max(r.t) AS t""",
        """MATCH (p:Person)-[:SENT]->(r:Message {substantive: true})-[:REPLY_TO]->(root:Message), (r)-[:MENTIONS]->(x)
           WHERE NOT (p)-[:SENT]->(root)
           RETURN p.id AS p, x.id AS x, labels(x)[0] AS label, root.id AS thread, max(r.t) AS t""",
    ],
    "contact": [
        """MATCH (c:Contact)-[:WORKS_AT]->(x:Account), (c)-[:SENT]->(root:Message)<-[:REPLY_TO]-(r:Message {substantive: true})<-[:SENT]-(p:Person)
           RETURN p.id AS p, x.id AS x, 'Account' AS label, root.id AS thread, max(r.t) AS t""",
        """MATCH (c:Contact)-[:WORKS_AT]->(x:Account), (c)-[:SENT]->(:Message)-[:REPLY_TO]->(root:Message)<-[:SENT]-(p:Person)
           RETURN p.id AS p, x.id AS x, 'Account' AS label, root.id AS thread, max(root.t) AS t""",
    ],
}

TICKETS = """MATCH (t:Ticket)-[:OWNED_BY]->(p:Person), (t)-[:CONCERNS]->(x)
             RETURN p.id AS p, x.id AS x, labels(x)[0] AS label, t.status AS status, t.t AS t"""
OWNERS = "MATCH (p:Person)-[:OWNS]->(x) RETURN p.id AS p, x.id AS x, labels(x)[0] AS label"


def _decay(t: float, now: float) -> float:
    return 0.5 ** ((now - t) / (HALF_LIFE_DAYS * 86400))


def compute(g: Graph, now: datetime = DEMO_NOW) -> list[dict]:
    nowt = now.timestamp()
    params = {"now": nowt, "hl": HALF_LIFE_DAYS * 86400}
    acc: dict[tuple[str, str], dict] = defaultdict(lambda: {"raw": 0.0, "last": 0.0, "first": None, "label": None,
                                                            "counts": defaultdict(int)})

    def add(p, x, label, signal, n, w, last, first):
        a = acc[(p, x)]
        a["label"] = label
        a["raw"] += SIGNAL_WEIGHTS[signal] * w
        a["counts"][signal] += n
        if last:
            a["last"] = max(a["last"], last)
        if first:
            a["first"] = first if a["first"] is None else min(a["first"], first)

    for signal, q in AGGREGATE_SIGNALS.items():
        for r in db.rows(q, params, g=g, readonly=True):
            add(r["p"], r["x"], r["label"], signal, r["n"], r["w"], r["last"], r["first"])
    for signal, queries in THREAD_SIGNALS.items():
        threads: dict[tuple[str, str, str], tuple[str, float]] = {}
        for q in queries:
            for r in db.rows(q, params, g=g, readonly=True):
                key = (r["p"], r["x"], r["thread"])
                if key not in threads or r["t"] > threads[key][1]:
                    threads[key] = (r["label"], r["t"])
        for (p, x, _), (label, t) in threads.items():
            add(p, x, label, signal, 1, _decay(t, nowt), t, t)
    for r in db.rows(TICKETS, g=g, readonly=True):
        signal = "ticket" if r["status"] == "Done" else "ticket_open"
        if r["t"]:
            add(r["p"], r["x"], r["label"], signal, 1, _decay(r["t"], nowt), r["t"], r["t"])
    owners = {(r["p"], r["x"]): r["label"] for r in db.rows(OWNERS, g=g, readonly=True)}
    for (p, x), label in owners.items():
        acc[(p, x)]["label"] = label
        acc[(p, x)]["raw"] += OWNER_BONUS

    out = []
    for (p, x), a in acc.items():
        score = squash(a["raw"])
        if score < 0.05:
            continue
        c = a["counts"]
        out.append({
            "p": p, "x": x, "label": a["label"], "score": round(score, 3), "raw": round(a["raw"], 2),
            "commits": c["commit"], "reviews": c["review"], "docs": c["doc"], "answers": c["answer"],
            "tickets": c["ticket"], "openTickets": c["ticket_open"], "contacts": c["contact"],
            "owner": (p, x) in owners, "lastSeen": a["last"] or None, "firstSeen": a["first"],
            "stale": bool(a["last"]) and (nowt - a["last"]) > STALE_DAYS * 86400,
        })
    return out


def write(g: Graph, edges: list[dict]) -> dict:
    props = """score: r.score, raw: r.raw, commits: r.commits, reviews: r.reviews, docs: r.docs, answers: r.answers,
               tickets: r.tickets, openTickets: r.openTickets, contacts: r.contacts, owner: r.owner,
               lastSeen: r.lastSeen, firstSeen: r.firstSeen, stale: r.stale, basis: 'activity'"""
    db.batched(f"""UNWIND $rows AS r MATCH (p:Person {{id: r.p}}), (x:System {{id: r.x}})
                   CREATE (p)-[:KNOWS {{{props}}}]->(x)""", [e for e in edges if e["label"] == "System"], g=g)
    db.batched(f"""UNWIND $rows AS r MATCH (p:Person {{id: r.p}}), (x:Account {{id: r.x}})
                   CREATE (p)-[:KNOWS {{{props}}}]->(x)""", [e for e in edges if e["label"] == "Account"], g=g)
    return {"knows": sum(e["label"] == "System" for e in edges), "accounts": sum(e["label"] == "Account" for e in edges)}
