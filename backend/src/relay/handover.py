"""Handover lifecycle: start -> analyze -> assign/dismiss -> capture -> verify.

Coverage states (PRD 8.3): at_risk, assigned, captured, verified, dismissed,
blocked. Only verified or dismissed items leave the active risk count, so
"zero at risk" never just means "everyone was assigned".
"""

from __future__ import annotations

import contextvars
import hashlib
import json
import threading
import time
from datetime import date
from typing import Any

from . import analysis, db
from .config import DEMO_NOW, now
from .events import bus

STATES = ("at_risk", "assigned", "captured", "verified", "dismissed", "blocked")
RESOLVED = ("verified", "dismissed")
HANDOVER_KNOWS_SCORE = 0.55   # a verified handover makes the successor a credible alternate
EDGE_FOR = {"System": "KNOWS", "Account": "KNOWS", "Decision": "KNOWS", "Workaround": "KNOWS"}


class HandoverError(ValueError):
    pass


def now_iso() -> str:
    return now().isoformat(timespec="seconds")


def handover_id(leaver: str, last_day: str) -> str:
    return f"ho-{leaver.removeprefix('p-')}-{last_day}"


def stream(hid: str) -> str:
    return f"handover:{hid}"


def person(pid: str | None) -> dict | None:
    if not pid:
        return None
    r = db.rows("""MATCH (p:Person {id: $id}) RETURN p.id AS id, p.name AS name, p.role AS role, p.team AS team,
                   p.status AS status, p.startDate AS startDate, p.lastDay AS lastDay, p.email AS email""",
                {"id": pid}, readonly=True)
    return r[0] if r else None


# ------------------------------------------------------------------ create

def create(leaver_id: str, last_day: str, joiner_id: str | None, manager_id: str) -> dict:
    try:
        day = date.fromisoformat(last_day)
    except ValueError as e:
        raise HandoverError("The last day must be a date in YYYY-MM-DD format") from e
    if day < DEMO_NOW.date():
        raise HandoverError("The last day is in the past")
    leaver = person(leaver_id)
    if not leaver or leaver["status"] != "active":
        raise HandoverError("The person leaving must be a current employee")
    existing = db.rows("MATCH (h:Handover {leaverId: $l}) WHERE h.status <> 'closed' RETURN h.id AS id",
                       {"l": leaver_id}, readonly=True)
    if existing:
        return get(existing[0]["id"])
    hid = handover_id(leaver_id, last_day)
    db.run("""MATCH (l:Person {id: $l}), (m:Person {id: $m})
              CREATE (h:Handover {id: $id, leaverId: $l, joinerId: $j, managerId: $m, lastDay: $d,
                                  status: 'created', createdAt: $now, analyses: 0})
              CREATE (h)-[:FOR_LEAVER]->(l), (h)-[:MANAGED_BY]->(m)
              SET l.lastDay = $d, l.leaving = true""",
           {"id": hid, "l": leaver_id, "j": joiner_id, "m": manager_id, "d": last_day, "now": now_iso()})
    if joiner_id:
        db.run("MATCH (h:Handover {id: $id}), (j:Person {id: $j}) CREATE (h)-[:FOR_JOINER]->(j)", {"id": hid, "j": joiner_id})
    bus.emit(stream(hid), "handover.started", {"handoverId": hid, "leaverId": leaver_id, "lastDay": last_day})
    return get(hid)


# ----------------------------------------------------------------- analyze

def _leaver_activity(pid: str) -> dict:
    q = {
        "commits": "MATCH (:Person {id: $p})-[:AUTHORED]->(c:Commit) RETURN count(c) AS n",
        "repos": "MATCH (:Person {id: $p})-[:AUTHORED]->(:Commit)-[:IN_REPO]->(s) RETURN count(DISTINCT s) AS n",
        "messages": "MATCH (:Person {id: $p})-[:SENT]->(m:Message) RETURN count(m) AS n",
        "docs": "MATCH (:Person {id: $p})-[:AUTHORED]->(d:Doc) RETURN count(d) AS n",
        "tickets": "MATCH (t:Ticket)-[:OWNED_BY]->(:Person {id: $p}) RETURN count(t) AS n",
        "meetings": "MATCH (:Person {id: $p})-[:ATTENDED]->(m:Meeting) RETURN count(m) AS n",
        "reviews": "MATCH (:Person {id: $p})-[r:REVIEWED]->() RETURN count(r) AS n",
    }
    return {k: db.rows(v, {"p": pid}, readonly=True)[0]["n"] for k, v in q.items()}


def start_analysis(hid: str) -> str:
    h = _handover(hid)
    n = (h.get("analyses") or 0) + 1
    db.run("MATCH (h:Handover {id: $id}) SET h.analyses = $n, h.status = 'analyzing'", {"id": hid, "n": n})
    aid = f"an-{hid}-{n}"
    bus.reopen(aid)
    return aid


def analyze(hid: str, aid: str, delay: float = 0.25) -> None:
    """Run the remove-person analysis, streaming progress to `aid`."""
    h = _handover(hid)
    leaver, joiner = h["leaverId"], h.get("joinerId")
    lp = person(leaver)
    first = lp["name"].split()[0]

    def step(label: str, pause: float = 1.0) -> None:
        bus.emit(aid, "analysis.step", {"label": label})
        time.sleep(delay * pause * 2)

    try:
        act = _leaver_activity(leaver)
        step(f"Loading {first}'s work history")
        step(f"Reading {act['commits']} commits across {act['repos']} repos…")
        step(f"Reading {act['messages']} Slack messages and {act['reviews']} code reviews…")
        step(f"Checking {act['docs']} docs, {act['tickets']} tickets and {act['meetings']} meetings…")
        step(f"Taking {first} out of the graph to see who else knows each item…", 1.5)
        bus.emit(aid, "graph.node.updated", {"id": leaver, "state": "departing"})
        items = analysis.unique_knowledge(leaver)
        items.sort(key=lambda i: analysis.TYPE_ORDER[i["type"]])
        enriched = []
        for i in items:
            ev = analysis.evidence(i["id"], leaver)
            pr = analysis.priority(i["id"], leaver)
            enriched.append((i, ev, pr))
        enriched.sort(key=lambda x: (analysis.TYPE_ORDER[x[0]["type"]], -x[2]))
        for order, (i, ev, pr) in enumerate(enriched):
            sugg = analysis.suggest_successors(i["id"], leaver, joiner)
            risk = _upsert_risk(hid, i, ev, pr, sugg, order)
            bus.emit(aid, "risk.detected", {"riskItem": risk})
            bus.emit(aid, "graph.node.updated", {"id": i["id"], "state": "orphaned"})
            if sugg:
                bus.emit(aid, "successor.suggested", {"riskId": risk["id"], "successor": sugg[0]})
            time.sleep(delay)
        thin = analysis.thin_coverage(leaver)
        db.run("MATCH (h:Handover {id: $id}) SET h.status = 'active', h.analyzedAt = $now, h.thin = $thin",
               {"id": hid, "now": now_iso(), "thin": json.dumps(thin)})
        # Hand-off to the Detective through the graph: accounts that depend on the leaver get an
        # owner-leaving risk and are rescanned (PRD: customer impact raises the account's risk).
        impact = customer_impact(leaver)
        if impact:
            step(f"Checking customers: {len(impact)} account{'s depend' if len(impact) != 1 else ' depends'} on {first}", 0.5)
            for acc in impact:
                bus.emit(aid, "account.risk.updated", acc)
                bus.emit(stream(hid), "account.risk.updated", acc)
        cov = coverage(hid)
        bus.emit(aid, "coverage.updated", cov)
        counts = {t: sum(1 for i, _, _ in enriched if i["type"] == t) for t in analysis.ITEM_LABELS}
        bus.emit(aid, "analysis.completed", {"handoverId": hid, "total": len(enriched), "byType": counts,
                                             "thinCoverage": thin})
        bus.emit(stream(hid), "coverage.updated", cov)
        # Write the leaver's questions now (live Gemini calls), so the interview opens without a wait.
        import contextvars
        import threading

        from . import interview
        ctx = contextvars.copy_context()
        threading.Thread(target=ctx.run, args=(interview.ensure_questions, hid), name="questions", daemon=True).start()
    except Exception as e:  # report the failure; keep partial results
        bus.emit(aid, "analysis.failed", {"error": str(e)})
        db.run("MATCH (h:Handover {id: $id}) SET h.status = 'active'", {"id": hid})
        raise
    finally:
        bus.close(aid)


def customer_impact(leaver: str) -> list[dict]:
    """Accounts whose risk rises because they depend on the leaver (no-op for tenants without accounts)."""
    has_accounts = db.rows("MATCH (a:Account) WHERE a.crmHealthScore IS NOT NULL RETURN count(a) AS n", readonly=True)[0]["n"]
    if not has_accounts:
        return []
    from .health import handoff
    return handoff.owner_leaving(leaver)


def customer_impact_view(hid: str) -> list[dict]:
    h = _handover(hid)
    return db.rows("""MATCH (k:Risk {kind: 'internal_owner_leaving'})-[:CAUSED_BY]->(:Person {id: $p}), (k)-[:ON]->(a:Account)
                      RETURN a.id AS id, a.name AS name, a.detectiveRisk AS after, a.previousRisk AS before,
                             k.detail AS detail, k.open AS open, a.arr AS arr ORDER BY a.arr DESC""",
                   {"p": h["leaverId"]}, readonly=True)


def _upsert_risk(hid: str, item: dict, ev: dict, pr: float, sugg: list[dict], order: int) -> dict:
    rid = f"{hid}:{item['id']}"
    existing = db.rows("MATCH (r:RiskItem {id: $id}) RETURN r.state AS state", {"id": rid}, readonly=True)
    state = "dismissed" if item.get("dismissals") else "at_risk"
    props = {"id": rid, "hid": hid, "item": item["id"], "type": item["type"], "title": item["title"],
             "priority": pr, "evidence": json.dumps(ev), "suggestions": json.dumps(sugg),
             "suggested": sugg[0]["id"] if sugg else None, "order": order, "now": now_iso(), "state": state,
             "note": "Dismissed in an earlier review" if item.get("dismissals") else None}
    if existing:
        db.run("""MATCH (r:RiskItem {id: $id}) SET r.priority = $priority, r.evidence = $evidence,
                  r.suggestions = $suggestions, r.suggestedId = $suggested, r.order = $order, r.updatedAt = $now""", props)
    else:
        db.run("""MATCH (h:Handover {id: $hid}), (i {id: $item})
                  WHERE i:System OR i:Account OR i:Decision OR i:Workaround
                  CREATE (h)-[:HAS_RISK]->(r:RiskItem {id: $id, handoverId: $hid, itemId: $item, type: $type,
                          title: $title, state: $state, priority: $priority, evidence: $evidence,
                          suggestions: $suggestions, suggestedId: $suggested, successorId: null, skipped: false,
                          order: $order, createdAt: $now, updatedAt: $now, note: $note})-[:CONCERNS]->(i)""", props)
    return risk(rid)


# ------------------------------------------------------------------- reads

def _handover(hid: str) -> dict:
    r = db.rows("MATCH (h:Handover {id: $id}) RETURN h", {"id": hid}, readonly=True)
    if not r:
        raise HandoverError(f"No handover found with id {hid}")
    return r[0]["h"]


def risk(rid: str) -> dict:
    r = db.rows("""MATCH (r:RiskItem {id: $id})-[:CONCERNS]->(i)
                   OPTIONAL MATCH (k:Knowledge {riskId: $id})
                   RETURN r, i, k""", {"id": rid}, readonly=True)
    if not r:
        raise HandoverError(f"No item found with id {rid}")
    return _risk_view(r[0]["r"], r[0]["i"], r[0]["k"])


def _risk_view(r: dict, item: dict, k: dict | None) -> dict:
    succ = person(r.get("successorId"))
    systems = analysis.item_systems(r["itemId"]) if r["type"] != "System" else []
    return {
        "id": r["id"], "itemId": r["itemId"], "type": r["type"], "title": r["title"], "state": r["state"],
        "priority": r["priority"], "order": r.get("order", 0),
        "subtitle": item.get("summary") if r["type"] in ("System", "Account") else None,
        "criticality": item.get("criticality"), "about": [s["name"] for s in systems],
        "evidence": json.loads(r["evidence"] or "{}"), "suggestions": json.loads(r["suggestions"] or "[]"),
        "suggestedId": r.get("suggestedId"),
        "successor": {"id": succ["id"], "name": succ["name"], "role": succ["role"]} if succ else None,
        "skipped": bool(r.get("skipped")), "dismissReason": r.get("dismissReason"), "dismissedBy": r.get("dismissedBy"),
        "note": r.get("note"), "question": json.loads(r["question"]) if r.get("question") else None,
        "knowledge": knowledge_view(k) if k else None, "updatedAt": r.get("updatedAt"),
    }


def knowledge_view(k: dict) -> dict:
    return {"id": k["id"], "question": k.get("question"), "answer": k.get("answer"),
            "originalAnswer": k.get("originalAnswer"), "capturedAt": k.get("capturedAt"),
            "editedAt": k.get("editedAt"), "verifiedAt": k.get("verifiedAt"), "verifiedBy": k.get("verifiedByName"),
            "authorId": k.get("authorId"), "authorName": k.get("authorName"), "itemId": k.get("itemId"),
            "context": json.loads(k["context"]) if k.get("context") else None}


def risks(hid: str) -> list[dict]:
    rows = db.rows("""MATCH (:Handover {id: $id})-[:HAS_RISK]->(r:RiskItem)-[:CONCERNS]->(i)
                      OPTIONAL MATCH (k:Knowledge {riskId: r.id})
                      RETURN r, i, k ORDER BY r.order""", {"id": hid}, readonly=True)
    return [_risk_view(x["r"], x["i"], x["k"]) for x in rows]


def coverage(hid: str) -> dict:
    rows = db.rows("""MATCH (:Handover {id: $id})-[:HAS_RISK]->(r:RiskItem)
                      RETURN r.state AS state, count(r) AS n""", {"id": hid}, readonly=True)
    by = {s: 0 for s in STATES}
    for r in rows:
        by[r["state"]] = r["n"]
    total = sum(by.values())
    at_risk = total - by["verified"] - by["dismissed"]
    return {"handoverId": hid, "total": total, "atRisk": at_risk, "byState": by,
            "complete": total > 0 and at_risk == 0,
            "assignedOrBetter": by["assigned"] + by["captured"] + by["verified"]}


def get(hid: str) -> dict:
    h = _handover(hid)
    return {
        "handover": {k: h.get(k) for k in ("id", "leaverId", "joinerId", "managerId", "lastDay", "status",
                                           "createdAt", "analyzedAt", "analyses", "closedAt")},
        "leaver": person(h["leaverId"]), "joiner": person(h.get("joinerId")), "manager": person(h["managerId"]),
        "riskItems": risks(hid), "coverage": coverage(hid),
        "thinCoverage": json.loads(h["thin"]) if h.get("thin") else [],
    }


def list_handovers() -> list[dict]:
    rows = db.rows("MATCH (h:Handover) RETURN h.id AS id ORDER BY h.createdAt DESC", readonly=True)
    out = []
    for r in rows:
        h = _handover(r["id"])
        out.append({"id": h["id"], "status": h["status"], "lastDay": h["lastDay"], "leaver": person(h["leaverId"]),
                    "joiner": person(h.get("joinerId")), "coverage": coverage(h["id"])})
    return out


# --------------------------------------------------------------- mutations

def _require(hid: str, rid: str) -> dict:
    r = risk(rid)
    if not rid.startswith(hid + ":"):
        raise HandoverError("This item is not part of this handover")
    return r


def _emit_change(hid: str, type_: str, payload: dict) -> None:
    bus.emit(stream(hid), type_, payload)
    bus.emit(stream(hid), "coverage.updated", coverage(hid))


def assign(hid: str, rid: str, successor_id: str, actor: str) -> dict:
    r = _require(hid, rid)
    h = _handover(hid)
    if actor != h["managerId"]:
        raise HandoverError("Only the handover's manager can pick next owners")
    succ = person(successor_id)
    if not succ or succ["status"] not in analysis.ACTIVE or successor_id == h["leaverId"]:
        raise HandoverError("The next owner must be a current teammate, not the person leaving")
    db.run("""MATCH (:Person)-[o:OWNS {handoverId: $hid, itemId: $item}]->() DELETE o""", {"hid": hid, "item": r["itemId"]})
    db.run("""MATCH (:Person)-[s:SUCCEEDS {handoverId: $hid, itemId: $item}]->() DELETE s""", {"hid": hid, "item": r["itemId"]})
    db.run("""MATCH (s:Person {id: $s}), (l:Person {id: $l}), (i {id: $item})
              WHERE i:System OR i:Account OR i:Decision OR i:Workaround
              CREATE (s)-[:OWNS {source: 'handover', handoverId: $hid, itemId: $item, since: $now}]->(i)
              CREATE (s)-[:SUCCEEDS {handoverId: $hid, itemId: $item, at: $now}]->(l)""",
           {"s": successor_id, "l": h["leaverId"], "item": r["itemId"], "hid": hid, "now": now_iso()})
    new_state = "assigned" if r["state"] in ("at_risk", "blocked") else r["state"]
    db.run("MATCH (r:RiskItem {id: $id}) SET r.successorId = $s, r.state = $st, r.updatedAt = $now",
           {"id": rid, "s": successor_id, "st": new_state, "now": now_iso()})
    out = risk(rid)
    _emit_change(hid, "risk.assigned", {"riskItem": out})
    return out


def dismiss(hid: str, rid: str, reason: str, actor: str) -> dict:
    r = _require(hid, rid)
    h = _handover(hid)
    if actor != h["managerId"]:
        raise HandoverError("Only the handover's manager can dismiss a risk")
    reason = (reason or "").strip() or "Not a real knowledge risk"
    db.run("""MATCH (m:Person {id: $m}), (i {id: $item}) WHERE i:System OR i:Account OR i:Decision OR i:Workaround
              CREATE (m)-[:DISMISSED {reason: $reason, at: $now, handoverId: $hid}]->(i)""",
           {"m": actor, "item": r["itemId"], "reason": reason, "now": now_iso(), "hid": hid})
    db.run("""MATCH (r:RiskItem {id: $id}) SET r.state = 'dismissed', r.dismissReason = $reason,
              r.dismissedBy = $by, r.prevState = $prev, r.updatedAt = $now""",
           {"id": rid, "reason": reason, "by": person(actor)["name"], "prev": r["state"], "now": now_iso()})
    out = risk(rid)
    _emit_change(hid, "risk.dismissed", {"riskItem": out})
    return out


def restore(hid: str, rid: str, actor: str) -> dict:
    r = _require(hid, rid)
    h = _handover(hid)
    if actor != h["managerId"]:
        raise HandoverError("Only the handover's manager can restore a risk")
    db.run("MATCH (:Person)-[d:DISMISSED {handoverId: $hid}]->(i {id: $item}) DELETE d", {"hid": hid, "item": r["itemId"]})
    db.run("""MATCH (r:RiskItem {id: $id}) SET r.state = coalesce(r.prevState, 'at_risk'), r.dismissReason = null,
              r.dismissedBy = null, r.updatedAt = $now""", {"id": rid, "now": now_iso()})
    out = risk(rid)
    _emit_change(hid, "risk.restored", {"riskItem": out})
    return out


def capture(hid: str, rid: str, answer: str, author: str, question: dict | None = None) -> dict:
    from .textmatch import mentions
    r = _require(hid, rid)
    h = _handover(hid)
    if author != h["leaverId"]:
        raise HandoverError("Only the person leaving can answer handover questions")
    answer = (answer or "").strip()
    if len(answer) < 3:
        raise HandoverError("The answer is empty")
    q = question or r.get("question") or {}
    kid = "kn-" + hashlib.sha1(rid.encode()).hexdigest()[:10]
    lp = person(author)
    exists = db.rows("MATCH (k:Knowledge {id: $id}) RETURN k.answer AS a", {"id": kid}, readonly=True)
    params = {"id": kid, "rid": rid, "hid": hid, "item": r["itemId"], "q": q.get("prompt"), "a": answer,
              "now": now_iso(), "author": author, "name": lp["name"], "ctx": json.dumps(q.get("source")) if q else None}
    if exists:
        db.run("""MATCH (k:Knowledge {id: $id}) SET k.answer = $a, k.editedAt = $now, k.verifiedAt = null,
                  k.verifiedByName = null""", params)
    else:
        db.run("""MATCH (l:Person {id: $author}), (i {id: $item})
                  WHERE i:System OR i:Account OR i:Decision OR i:Workaround
                  CREATE (k:Knowledge {id: $id, riskId: $rid, handoverId: $hid, itemId: $item, question: $q,
                          answer: $a, originalAnswer: $a, capturedAt: $now, confidence: 'stated-by-leaver',
                          authorId: $author, authorName: $name, context: $ctx})
                  CREATE (k)-[:EXPLAINS {primary: true}]->(i)
                  CREATE (k)-[:GIVEN_BY]->(l)""", params)
        for s in analysis.item_systems(r["itemId"]):
            if s["id"] != r["itemId"]:
                db.run("MATCH (k:Knowledge {id: $k}), (s:System {id: $s}) CREATE (k)-[:EXPLAINS {primary: false}]->(s)",
                       {"k": kid, "s": s["id"]})
    db.run("MATCH (k:Knowledge {id: $id})-[m:MENTIONS]->() DELETE m", {"id": kid})
    for m in mentions(answer):
        db.run(f"MATCH (k:Knowledge {{id: $k}}), (x:{m['label']} {{id: $x}}) CREATE (k)-[:MENTIONS {{surface: $s}}]->(x)",
               {"k": kid, "x": m["id"], "s": m["surface"]})
    db.run("""MATCH (r:RiskItem {id: $id}) SET r.state = 'captured', r.skipped = false, r.knowledgeId = $k,
              r.updatedAt = $now""", {"id": rid, "k": kid, "now": now_iso()})
    proposal = _propose(hid, rid)
    out = risk(rid)
    _emit_change(hid, "answer.saved", {"riskItem": out, "docProposal": proposal})
    return out


def _propose(hid: str, rid: str) -> dict | None:
    """Template diffs are instant; an LLM rewrite runs in the background and announces itself."""
    from . import llm
    from .proposals import propose_doc_update
    if not llm.available():
        return propose_doc_update(hid, rid)

    def run() -> None:
        try:
            p = propose_doc_update(hid, rid)
            if p:
                bus.emit(stream(hid), "doc.proposed", {"docProposal": p})
        except Exception:  # never let a doc rewrite break answer capture
            import logging
            logging.getLogger("relay.handover").exception("doc proposal failed")

    ctx = contextvars.copy_context()
    threading.Thread(target=ctx.run, args=(run,), daemon=True).start()
    return None


def skip(hid: str, rid: str, author: str) -> dict:
    r = _require(hid, rid)
    h = _handover(hid)
    if author != h["leaverId"]:
        raise HandoverError("Only the person leaving can skip handover questions")
    blocked = date.fromisoformat(h["lastDay"]) < DEMO_NOW.date() and r["state"] in ("at_risk", "assigned")
    db.run("MATCH (r:RiskItem {id: $id}) SET r.skipped = true, r.state = $st, r.updatedAt = $now",
           {"id": rid, "st": "blocked" if blocked else r["state"], "now": now_iso()})
    out = risk(rid)
    _emit_change(hid, "risk.skipped", {"riskItem": out})
    return out


def verify(hid: str, rid: str, actor: str) -> dict:
    r = _require(hid, rid)
    h = _handover(hid)
    if not r["knowledge"]:
        raise HandoverError("Nothing to verify yet. The person leaving did not answer this question yet.")
    if not r["successor"]:
        raise HandoverError("Assign a next owner before you verify")
    if actor not in (h["managerId"], r["successor"]["id"]):
        raise HandoverError("Only the manager or the next owner can verify")
    vp = person(actor)
    edge = EDGE_FOR[r["type"]]
    db.run("""MATCH (k:Knowledge {riskId: $rid}), (v:Person {id: $v})
              SET k.verifiedAt = $now, k.verifiedByName = $name
              CREATE (v)-[:VERIFIED {at: $now}]->(k)""", {"rid": rid, "v": actor, "now": now_iso(), "name": vp["name"]})
    db.run(f"""MATCH (s:Person {{id: $s}})-[e:{edge} {{basis: 'handover-verified', handoverId: $hid}}]->(i {{id: $item}}) DELETE e""",
           {"s": r["successor"]["id"], "hid": hid, "item": r["itemId"]})
    db.run(f"""MATCH (s:Person {{id: $s}}), (i {{id: $item}}) WHERE i:System OR i:Account OR i:Decision OR i:Workaround
               CREATE (s)-[:{edge} {{score: $score, basis: 'handover-verified', handoverId: $hid, at: $now,
                                     lastSeen: $t}}]->(i)""",
           {"s": r["successor"]["id"], "item": r["itemId"], "score": HANDOVER_KNOWS_SCORE, "hid": hid,
            "now": now_iso(), "t": DEMO_NOW.timestamp()})
    db.run("MATCH (r:RiskItem {id: $id}) SET r.state = 'verified', r.updatedAt = $now", {"id": rid, "now": now_iso()})
    out = risk(rid)
    _emit_change(hid, "risk.verified", {"riskItem": out})
    return out


def close(hid: str, actor: str) -> dict:
    h = _handover(hid)
    if actor != h["managerId"]:
        raise HandoverError("Only the manager can close the handover")
    cov = coverage(hid)
    if not cov["complete"]:
        raise HandoverError(f"{cov['atRisk']} items are still at risk. Verify or dismiss them first.")
    db.run("MATCH (h:Handover {id: $id}) SET h.status = 'closed', h.closedAt = $now", {"id": hid, "now": now_iso()})
    if db.rows("MATCH (k:Risk {kind: 'internal_owner_leaving', open: true}) RETURN count(k) AS n", readonly=True)[0]["n"]:
        from .health import handoff
        handoff.resolve_owner_leaving(_handover(hid)["leaverId"])
    bus.emit(stream(hid), "handover.closed", {"handoverId": hid})
    return get(hid)


def for_joiner(pid: str) -> dict | None:
    r = db.rows("MATCH (h:Handover {joinerId: $p}) RETURN h.id AS id ORDER BY h.createdAt DESC LIMIT 1",
                {"p": pid}, readonly=True)
    return _handover(r[0]["id"]) if r else None


def for_leaver(pid: str) -> dict | None:
    r = db.rows("MATCH (h:Handover {leaverId: $p}) RETURN h.id AS id ORDER BY h.createdAt DESC LIMIT 1",
                {"p": pid}, readonly=True)
    return _handover(r[0]["id"]) if r else None


def payload_summary(h: dict[str, Any]) -> dict:
    return {"id": h["id"], "status": h["status"], "lastDay": h["lastDay"]}
