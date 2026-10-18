"""Day One for a joiner: inherited area, five people, inherited answers, first week."""

from __future__ import annotations

from datetime import date

from . import analysis, db, graphviews, handover
from .analysis import fmt_day, source_ref
from .config import DEMO_NOW

KIND_WEIGHT = {"onboarding": 4, "runbook": 3, "rfc": 3, "design": 2, "postmortem": 1}


def _inherited_ids(h: dict) -> tuple[list[str], list[str]]:
    """(item ids from the handover, plus adjacent systems).

    Adjacent systems share a decision or workaround with a directly inherited
    system or customer (e.g. ledger-service, via the ledger replay workaround).
    """
    items = [r["itemId"] for r in handover.risks(h["id"])]
    direct = [i for i in items if i.startswith(("sys-", "cust-"))]
    systems = set(i for i in items if i.startswith("sys-"))
    for r in db.rows("""MATCH (d)<-[:ABOUT]-(k)-[:ABOUT]->(s:System) WHERE d.id IN $direct
                        RETURN DISTINCT s.id AS id""", {"direct": direct}, readonly=True):
        systems.add(r["id"])
    return items, sorted(systems)


def _direct(h: dict) -> list[str]:
    return [r["itemId"] for r in handover.risks(h["id"]) if r["type"] in ("System", "Account")]


def meet_five(joiner: str, h: dict) -> list[dict]:
    items, systems = _inherited_ids(h)
    scope = sorted(set(items) | set(systems))
    leaver = h["leaverId"]
    rows = db.rows(f"""MATCH (c:Person)-[k:{analysis.KNOWLEDGE_EDGES}|OWNS]->(i)
                       WHERE i.id IN $scope AND c.status = 'active' AND c.id <> $j AND c.id <> $m
                       RETURN c.id AS id, c.name AS name, c.role AS role, c.team AS team, c.lastDay AS lastDay,
                              i.id AS item, coalesce(i.name, i.summary) AS itemName, labels(i)[0] AS label,
                              type(k) AS rel, coalesce(k.score, 0.5) AS score, k.source AS source""",
                   {"scope": scope, "j": joiner, "m": h["managerId"]}, readonly=True)
    people: dict[str, dict] = {}
    for r in rows:
        p = people.setdefault(r["id"], {"id": r["id"], "name": r["name"], "role": r["role"], "team": r["team"],
                                        "lastDay": r["lastDay"], "centrality": 0.0, "links": [], "taking": []})
        weight = 1.0 if r["item"] in items else 0.5
        p["centrality"] += weight * r["score"]
        if r["rel"] == "OWNS" and r["source"] == "handover":
            p["taking"].append({"name": r["itemName"], "label": r["label"]})
        else:
            p["links"].append({"id": r["item"], "name": r["itemName"], "label": r["label"], "rel": r["rel"],
                               "score": r["score"]})
    ranked = sorted(people.values(), key=lambda p: -p["centrality"])
    out = []
    for p in ranked:
        p["links"].sort(key=lambda link: -link["score"])
        strong = [link for link in p["links"] if link["score"] > analysis.ALTERNATE]
        if p["id"] == leaver:
            last = date.fromisoformat(h["lastDay"])
            p["leaving"] = True
            open_items = len([r for r in handover.risks(h["id"]) if r["state"] not in ("verified", "dismissed")])
            p["reason"] = (f"Leaves {last:%a} {last.day} {last:%b}. Still the only one who knows {open_items} things you take over. "
                           f"Meet this week."
                           if open_items else
                           f"Leaves {last:%a} {last.day} {last:%b}. Everything is handed over, but a short hello before then still helps.")
            p["urgent"] = last >= DEMO_NOW.date()
        elif p["taking"]:
            named = [t["name"] for t in p["taking"] if t["label"] in ("System", "Account")]
            rest = len(p["taking"]) - len(named[:2])
            more = f" and {rest} related decision{'s' if rest != 1 else ''} or workaround{'s' if rest != 1 else ''}" if named and rest else ""
            p["reason"] = (f"Taking over {_join(named[:2])}{more} from {h_first(leaver)}." if named
                           else f"Taking over {len(p['taking'])} of {h_first(leaver)}'s decisions and workarounds.")
            p["taking"] = [t["name"] for t in p["taking"]]
        elif strong:
            names = list(dict.fromkeys(s["name"] for s in strong if s["label"] in ("System", "Account")))[:2] \
                or [strong[0]["name"]]
            p["reason"] = f"Knows {_join(names)} well" + (", next to the systems you take over." if p["team"] != "Payments" else ".")
        elif p["links"]:
            p["reason"] = f"Worked on {_join(list(dict.fromkeys(link['name'] for link in p['links']))[:2])}."
        else:
            continue
        p["centrality"] = round(p["centrality"], 2)
        out.append(p)
        if len(out) == 5:
            break
    return out


def h_first(pid: str) -> str:
    return analysis.leaver_first(pid)


def _join(xs: list[str]) -> str:
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def from_leaver(h: dict) -> list[dict]:
    rows = db.rows("""MATCH (k:Knowledge {handoverId: $h})-[e:EXPLAINS {primary: true}]->(i)
                      OPTIONAL MATCH (k)-[:EXPLAINS {primary: false}]->(s:System)
                      RETURN k, i, labels(i)[0] AS label, collect(s.name) AS systems ORDER BY k.capturedAt""",
                   {"h": h["id"]}, readonly=True)
    cards = []
    for r in rows:
        k, i = r["k"], r["i"]
        anchor = i.get("name") if r["label"] in ("System", "Account") else (r["systems"][0] if r["systems"] else None)
        sources = [source_ref({**k, "_labels": ["Knowledge"]})]
        kv = handover.knowledge_view(k)
        if kv.get("context"):
            sources.append(kv["context"])
        cards.append({"id": k["id"], "system": anchor, "itemId": i["id"], "itemType": r["label"],
                      "itemTitle": i.get("name") or i.get("summary"), "question": k.get("question"),
                      "answer": k.get("answer"), "author": k.get("authorName"), "capturedAt": k.get("capturedAt"),
                      "capturedLabel": fmt_day(k.get("capturedAt")), "verified": bool(k.get("verifiedAt")),
                      "verifiedBy": k.get("verifiedByName"), "sources": [s for s in sources if s]})
    return cards


def services(h: dict) -> list[dict]:
    out = []
    for r in handover.risks(h["id"]):
        if r["type"] != "System":
            continue
        s = db.rows("""MATCH (s:System {id: $id})
                       OPTIONAL MATCH (k:Knowledge)-[:EXPLAINS]->(s)
                       WITH s, count(DISTINCT k) AS knowledge
                       RETURN s.name AS name, s.summary AS summary, s.criticality AS criticality, s.repo AS repo,
                              knowledge""", {"id": r["itemId"]}, readonly=True)[0]
        tickets = db.rows("""MATCH (t:Ticket)-[:CONCERNS]->(:System {id: $id}) WHERE t.status IN ['To Do', 'In Progress']
                             OPTIONAL MATCH (t)-[:OWNED_BY]->(p:Person)
                             RETURN t.id AS id, t.title AS title, t.status AS status, p.name AS owner
                             ORDER BY t.id DESC LIMIT 3""", {"id": r["itemId"]}, readonly=True)
        out.append({"id": r["itemId"], **s, "state": r["state"], "successor": r["successor"], "openTickets": tickets})
    return out


def decisions(h: dict) -> list[dict]:
    systems = _direct(h)
    risky = {r["itemId"]: r for r in handover.risks(h["id"])}
    rows = db.rows("""MATCH (d:Decision)-[:ABOUT]->(s) WHERE s.id IN $ids
                      OPTIONAL MATCH (k:Knowledge)-[:EXPLAINS]->(d)
                      RETURN d.id AS id, d.summary AS summary, d.decidedAt AS decidedAt, d.rationaleStatus AS rationaleStatus,
                             collect(DISTINCT s.name) AS systems, count(DISTINCT k) AS knowledge
                      ORDER BY d.decidedAt DESC""", {"ids": systems}, readonly=True)
    for r in rows:
        risk = risky.get(r["id"])
        r["inherited"] = bool(risk)
        r["state"] = risk["state"] if risk else None
        r["decidedLabel"] = fmt_day(r["decidedAt"] + "T00:00:00+05:30") if r["decidedAt"] else None
    return rows


def ensure_checklist(joiner: str, h: dict) -> list[dict]:
    existing = db.rows("MATCH (c:ChecklistItem {personId: $p, handoverId: $h}) RETURN c ORDER BY c.order",
                       {"p": joiner, "h": h["id"]}, readonly=True)
    if existing:
        return [_check_view(r["c"]) for r in existing]
    items, systems = _inherited_ids(h)
    direct = _direct(h)
    docs = db.rows("""MATCH (d:Doc)-[:DOCUMENTS]->(x) WHERE x.id IN $scope
                      OPTIONAL MATCH (a:Person)-[:AUTHORED]->(d)
                      RETURN d.id AS id, d.title AS title, d.kind AS kind, d.t AS t, d.freshness AS freshness,
                             collect(DISTINCT x.id) AS about, a.id AS author""",
                   {"scope": sorted(set(direct) | set(systems))}, readonly=True)

    def rank(d: dict) -> tuple:
        on_direct = any(x in direct for x in d["about"])
        return (-(3 if on_direct else 0) - (2 if d["author"] == h["leaverId"] else 0) - KIND_WEIGHT.get(d["kind"], 0),
                -(d["t"] or 0))
    docs.sort(key=rank)
    chosen = docs[:3]
    onboarding_doc = next((d for d in docs if d["kind"] == "onboarding"), None)
    if onboarding_doc and onboarding_doc not in chosen:
        chosen.append(onboarding_doc)
    else:
        chosen = docs[:4]
    rows = []
    for d in chosen:
        sys_ = db.rows("MATCH (:Doc {id: $d})-[:DOCUMENTS]->(x) RETURN x.id AS id LIMIT 1", {"d": d["id"]}, readonly=True)
        rows.append({"kind": "doc", "label": f"Read “{d['title']}”", "targetId": d["id"], "targetLabel": "Doc",
                     "familiarWith": sys_[0]["id"] if sys_ else None,
                     "note": "Out of date. Read the handover answers with it." if d["freshness"] in ("stale", "aging") else None})
    rows.append({"kind": "people", "label": "Book intros with your five people", "targetId": None, "targetLabel": None,
                 "familiarWith": None, "note": None})
    starter = db.rows("""MATCH (t:Ticket)-[:CONCERNS]->(s:System) WHERE s.id IN $ids AND 'good-first-issue' IN t.labels
                         AND t.status IN ['To Do', 'Backlog'] RETURN t.id AS id, t.title AS title, s.id AS sys LIMIT 1""",
                      {"ids": systems}, readonly=True)
    if starter:
        t = starter[0]
        rows.append({"kind": "ticket", "label": f"Pick up your starter ticket {t['id']}: {t['title']}",
                     "targetId": t["id"], "targetLabel": "Ticket", "familiarWith": t["sys"], "note": None})
    for n, r in enumerate(rows):
        db.run("""CREATE (:ChecklistItem {id: $id, personId: $p, handoverId: $h, order: $n, kind: $kind, label: $label,
                  targetId: $tid, targetLabel: $tl, familiarWith: $fw, note: $note, done: false})""",
               {"id": f"ck-{joiner}-{n}", "p": joiner, "h": h["id"], "n": n, "kind": r["kind"], "label": r["label"],
                "tid": r["targetId"], "tl": r["targetLabel"], "fw": r["familiarWith"], "note": r["note"]})
    return ensure_checklist(joiner, h)


def _check_view(c: dict) -> dict:
    return {k: c.get(k) for k in ("id", "kind", "label", "targetId", "targetLabel", "note", "done", "doneAt", "familiarWith")}


def toggle_check(cid: str, actor: str) -> dict:
    from .handover import now_iso
    r = db.rows("MATCH (c:ChecklistItem {id: $id}) RETURN c", {"id": cid}, readonly=True)
    if not r:
        raise handover.HandoverError("No such checklist item")
    c = r[0]["c"]
    if c["personId"] != actor:
        raise handover.HandoverError("Only the new joiner can tick items on this checklist")
    done = not c.get("done")
    db.run("MATCH (c:ChecklistItem {id: $id}) SET c.done = $d, c.doneAt = $at", {"id": cid, "d": done, "at": now_iso() if done else None})
    if c.get("familiarWith"):
        # A familiarity signal, deliberately weaker than expertise (PRD 11.3).
        if done:
            db.run("""MATCH (p:Person {id: $p}), (x {id: $x}) WHERE x:System OR x:Account
                      CREATE (p)-[:FAMILIAR_WITH {source: 'checklist', checklistId: $c, at: $at}]->(x)""",
                   {"p": actor, "x": c["familiarWith"], "c": cid, "at": now_iso()})
        else:
            db.run("MATCH (:Person {id: $p})-[f:FAMILIAR_WITH {checklistId: $c}]->() DELETE f", {"p": actor, "c": cid})
    return _check_view(db.rows("MATCH (c:ChecklistItem {id: $id}) RETURN c", {"id": cid}, readonly=True)[0]["c"])


def day_one(joiner: str) -> dict:
    me = handover.person(joiner)
    h = handover.for_joiner(joiner)
    if not h:
        return {"person": me, "handover": None}
    leaver = handover.person(h["leaverId"])
    people = meet_five(joiner, h)
    familiar = db.rows("MATCH (:Person {id: $p})-[f:FAMILIAR_WITH]->(x) RETURN DISTINCT x.name AS name",
                       {"p": joiner}, readonly=True)
    return {
        "person": me, "handover": {k: h.get(k) for k in ("id", "status", "lastDay")}, "leaver": leaver,
        "team": me["team"], "services": services(h), "decisions": decisions(h), "meet": people,
        "fromLeaver": from_leaver(h), "checklist": ensure_checklist(joiner, h),
        "familiarWith": [f["name"] for f in familiar],
        "graph": graphviews.day_one_graph(joiner, h["id"], people),
    }
