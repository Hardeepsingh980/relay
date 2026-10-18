"""Small, focused subgraphs for the UI (never the whole company hairball).

Each view stays near 25 nodes: the people and items that explain one risk
picture, with risk state on nodes so the client can animate a departure.
"""

from __future__ import annotations

from . import analysis, db, handover

KIND = {"Person": "person", "System": "system", "Account": "customer", "Decision": "decision", "Workaround": "workaround"}
MAX_NODES = 25


def _name(n: dict) -> str:
    return n.get("name") or n.get("summary") or n.get("id")


def handover_graph(hid: str) -> dict:
    h = handover.get(hid)
    leaver = h["leaver"]["id"]
    risks = {r["itemId"]: r for r in h["riskItems"]}
    nodes: dict[str, dict] = {leaver: {"id": leaver, "kind": "person", "name": h["leaver"]["name"], "role": "leaver"}}
    edges: list[dict] = []

    rows = db.rows(f"""MATCH (l:Person {{id: $l}})-[k:{analysis.KNOWLEDGE_EDGES}]->(i)
                       WHERE (i:System OR i:Account OR i:Decision OR i:Workaround) AND k.score > $alt
                       RETURN i, labels(i)[0] AS label, type(k) AS rel, k.score AS score ORDER BY k.score DESC""",
                   {"l": leaver, "alt": analysis.ALTERNATE}, readonly=True)
    thin = {t["id"] for t in h["thinCoverage"]}
    shared_budget = 6
    for r in rows:
        i = r["i"]
        unique = i["id"] in risks
        if not unique:
            if shared_budget == 0:
                continue
            shared_budget -= 1
        risk = risks.get(i["id"])
        nodes[i["id"]] = {"id": i["id"], "kind": KIND[r["label"]], "name": _name(i),
                          "risk": "unique" if unique else ("thin" if i["id"] in thin else "shared"),
                          "state": risk["state"] if risk else None, "riskId": risk["id"] if risk else None}
        edges.append({"source": leaver, "target": i["id"], "type": r["rel"], "score": r["score"], "fromLeaver": True})

    # Who else holds the shared items (why they stay neutral when the leaver goes).
    shared_ids = [n for n, v in nodes.items() if v.get("risk") in ("shared", "thin")]
    others = db.rows(f"""MATCH (o:Person)-[k:{analysis.KNOWLEDGE_EDGES}]->(i) WHERE i.id IN $ids AND o.id <> $l
                         AND o.status IN $active AND k.score > $alt
                         RETURN o.id AS id, o.name AS name, i.id AS item, type(k) AS rel, k.score AS score
                         ORDER BY k.score DESC""",
                     {"ids": shared_ids, "l": leaver, "active": analysis.ACTIVE, "alt": analysis.ALTERNATE}, readonly=True)
    per_item: dict[str, int] = {}
    for o in others:
        if per_item.get(o["item"], 0) >= 2:
            continue
        if o["id"] not in nodes:
            if len(nodes) >= MAX_NODES:
                continue
            nodes[o["id"]] = {"id": o["id"], "kind": "person", "name": o["name"]}
        per_item[o["item"]] = per_item.get(o["item"], 0) + 1
        edges.append({"source": o["id"], "target": o["item"], "type": o["rel"], "score": o["score"], "fromLeaver": False})

    # Successors and verified handover links.
    # Successors appear once their handover is verified: the graph visibly heals.
    for r in h["riskItems"]:
        s = r["successor"]
        if s and r["state"] == "verified" and len(nodes) < MAX_NODES + 4:
            nodes.setdefault(s["id"], {"id": s["id"], "kind": "person", "name": s["name"]})
            edges.append({"source": s["id"], "target": r["itemId"], "type": "VERIFIED", "score": 0.55,
                          "fromLeaver": False, "handover": True})
    # Context: which systems the unique decisions/workarounds are about (only those already shown).
    about = db.rows("""MATCH (i)-[:ABOUT]->(s) WHERE i.id IN $ids AND s.id IN $shown RETURN i.id AS i, s.id AS s""",
                    {"ids": list(risks), "shown": list(nodes)}, readonly=True)
    edges += [{"source": a["i"], "target": a["s"], "type": "ABOUT", "score": None, "fromLeaver": False} for a in about]
    return {"nodes": list(nodes.values()), "edges": edges,
            "relationships": _relationship_text(nodes, edges)}


def day_one_graph(joiner: str, hid: str, people: list[dict]) -> dict:
    h = handover.get(hid)
    nodes: dict[str, dict] = {joiner: {"id": joiner, "kind": "person", "name": h["joiner"]["name"], "role": "you"}}
    edges = []
    systems = [r for r in h["riskItems"] if r["type"] in ("System", "Account")]
    for r in systems:
        nodes[r["itemId"]] = {"id": r["itemId"], "kind": KIND[r["type"]], "name": r["title"],
                              "risk": "covered" if r["state"] == "verified" else ("unique" if r["state"] != "dismissed" else None),
                              "state": r["state"]}
        edges.append({"source": joiner, "target": r["itemId"], "type": "INHERITS", "score": None})
    decisions = db.rows("""MATCH (d:Decision)-[:ABOUT]->(s) WHERE s.id IN $ids
                           RETURN DISTINCT d.id AS id, d.summary AS name, s.id AS s""",
                        {"ids": [r["itemId"] for r in systems]}, readonly=True)
    risky = {r["itemId"]: r for r in h["riskItems"]}
    for d in decisions[:6]:
        if d["id"] not in nodes:
            r = risky.get(d["id"])
            nodes[d["id"]] = {"id": d["id"], "kind": "decision", "name": d["name"],
                              "risk": ("covered" if r["state"] == "verified" else "unique") if r and r["state"] != "dismissed" else None,
                              "state": r["state"] if r else None}
        edges.append({"source": d["id"], "target": d["s"], "type": "ABOUT", "score": None})
    for p in people:
        nodes[p["id"]] = {"id": p["id"], "kind": "person", "name": p["name"], "role": "leaver" if p.get("leaving") else None}
        for link in p.get("links", [])[:3]:
            if link["id"] in nodes:
                edges.append({"source": p["id"], "target": link["id"], "type": link["rel"], "score": link["score"]})
    return {"nodes": list(nodes.values())[:MAX_NODES], "edges": edges, "relationships": _relationship_text(nodes, edges)}


def _relationship_text(nodes: dict, edges: list[dict]) -> list[str]:
    """Accessible text alternative to the graph."""
    verbs = {"KNOWS": "knows", "DECIDED": "decided", "OWNS": "is taking over",
             "VERIFIED": "verified the handover of", "ABOUT": "is about", "INHERITS": "inherits"}
    out = []
    for e in edges:
        a, b = nodes.get(e["source"]), nodes.get(e["target"])
        if a and b:
            s = f"{a['name']} {verbs.get(e['type'], e['type'].lower())} {b['name']}"
            if e.get("score"):
                s += f" (strength {e['score']:.2f})"
            out.append(s)
    return out
