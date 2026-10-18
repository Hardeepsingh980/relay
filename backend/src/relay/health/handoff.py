"""Agent hand-offs through the graph (agents never message each other directly).

  Handover -> Detective   When a departure is analysed, the Handover agent writes
                          (:Risk {kind: 'internal_owner_leaving'})-[:ON]->(Account) for every
                          account that depends on the leaver; the Detective rescans those accounts.
  Sales Assist -> Detective  Promises logged on a call land as (:Promise)-[:TO]->(Account);
                          the next scan scores them (see relay.health.risk).
"""

from __future__ import annotations

from .. import db
from ..config import now
from . import risk

REL_LABEL = {"TECH_CONTACT_FOR": "technical contact", "MANAGES": None, "KNOWS": "only person who knows it"}


def dependent_accounts(leaver: str) -> list[dict]:
    """Accounts that depend on this person: technical contact, CS owner / sales POC, or sole knower."""
    rows = db.rows("""
MATCH (p:Person {id: $p})-[x:TECH_CONTACT_FOR|MANAGES|KNOWS]->(a:Account)
WHERE a.crmHealthScore IS NOT NULL
RETURN a.id AS id, a.name AS name, type(x) AS rel, x.role AS role, x.score AS score, p.name AS person,
       p.lastDay AS lastDay, p.endDate AS endDate
""", {"p": leaver}, readonly=True)
    out: dict[str, dict] = {}
    for r in rows:
        if r["rel"] == "KNOWS":
            others = db.rows("""MATCH (o:Person)-[k:KNOWS]->(:Account {id: $a}) WHERE o.id <> $p AND k.score > 0.4
                                RETURN count(o) AS n""", {"a": r["id"], "p": leaver}, readonly=True)[0]["n"]
            if others:
                continue
            why = "only person who knows the account"
        elif r["rel"] == "MANAGES":
            why = "CS owner" if r["role"] == "cs_owner" else "sales contact"
        else:
            why = "technical contact"
        e = out.setdefault(r["id"], {"id": r["id"], "name": r["name"], "person": r["person"],
                                     "lastDay": r["lastDay"] or r["endDate"], "why": []})
        if why not in e["why"]:
            e["why"].append(why)
    return list(out.values())


def owner_leaving(leaver: str, source: str = "handover") -> list[dict]:
    """Write owner-leaving risks for the leaver's accounts and rescan them. Returns before/after risk."""
    deps = dependent_accounts(leaver)
    impact = []
    for d in deps:
        detail = f"{d['person']} ({', '.join(d['why'])}) leaves {d['lastDay']}"
        before = db.rows("MATCH (a:Account {id: $a}) RETURN a.detectiveRisk AS r", {"a": d["id"]}, readonly=True)[0]["r"]
        db.run("""MATCH (a:Account {id: $a}), (p:Person {id: $p})
                  MERGE (k:Risk {id: $rid})
                  SET k.kind = 'internal_owner_leaving', k.label = $label, k.detail = $detail, k.points = 6,
                      k.source = $source, k.open = true, k.createdAt = $at
                  MERGE (k)-[:ON]->(a)
                  MERGE (k)-[:CAUSED_BY]->(p)""",
               {"a": d["id"], "p": leaver, "rid": f"risk-{d['id']}-owner-{leaver}", "label": f"{d['person']} is leaving",
                "detail": detail, "source": source, "at": now().isoformat(timespec="seconds")})
        after = risk.scan(d["id"])[d["id"]]["risk"]
        impact.append({**d, "before": before, "after": after, "detail": detail})
    return impact


def resolve_owner_leaving(leaver: str, account_id: str | None = None) -> list[dict]:
    """A successor took over (handover verified or closed): close the risk and rescan."""
    rows = db.rows("""MATCH (k:Risk {kind: 'internal_owner_leaving', open: true})-[:CAUSED_BY]->(:Person {id: $p}),
                             (k)-[:ON]->(a:Account) WHERE $a IS NULL OR a.id = $a
                      SET k.open = false, k.closedAt = $at RETURN a.id AS id""",
                   {"p": leaver, "a": account_id, "at": now().isoformat(timespec="seconds")})
    return [{"id": r["id"], "after": risk.scan(r["id"])[r["id"]]["risk"]} for r in rows]
