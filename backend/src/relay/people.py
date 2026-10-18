"""People directory and profiles."""

from __future__ import annotations

from . import analysis, db, handover


def list_people() -> list[dict]:
    risk = {p["id"]: p for p in analysis.company_risk()["people"]}
    rows = db.rows("""MATCH (p:Person) WHERE p.status IN ['active', 'joining']
                      RETURN p.id AS id, p.name AS name, p.role AS role, p.team AS team, p.status AS status,
                             p.lastDay AS lastDay, p.startDate AS startDate ORDER BY p.team, p.name""", readonly=True)
    for r in rows:
        r["unique"] = risk.get(r["id"], {}).get("unique", 0)
        r["byType"] = risk.get(r["id"], {}).get("byType", {})
    return rows


def profile(pid: str) -> dict | None:
    p = handover.person(pid)
    if not p:
        return None
    mgr = db.rows("MATCH (:Person {id: $p})-[:REPORTS_TO]->(m:Person) RETURN m.id AS id, m.name AS name",
                  {"p": pid}, readonly=True)
    links = db.rows(f"""MATCH (:Person {{id: $p}})-[k:{analysis.KNOWLEDGE_EDGES}]->(i)
                        WHERE k.score > $alt AND (i:System OR i:Account OR i:Decision OR i:Workaround)
                        RETURN i.id AS id, coalesce(i.name, i.summary) AS name, labels(i)[0] AS type, k.score AS score,
                               k.basis AS basis ORDER BY k.score DESC""", {"p": pid, "alt": analysis.ALTERNATE}, readonly=True)
    unique = {u["id"] for u in analysis.unique_knowledge(pid)}
    for link in links:
        link["unique"] = link["id"] in unique
    h = handover.for_leaver(pid)
    incoming = db.rows("""MATCH (p:Person) WHERE p.status = 'joining' AND p.team = $team
                          RETURN p.id AS id, p.name AS name, p.role AS role, p.startDate AS startDate""",
                       {"team": p["team"]}, readonly=True)
    return {"person": p, "manager": mgr[0] if mgr else None, "knowsAbout": links, "uniqueCount": len(unique),
            "handover": handover.payload_summary(h) if h else None, "incomingJoiners": incoming}
