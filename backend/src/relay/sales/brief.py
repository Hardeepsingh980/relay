"""Before the call: a one-page brief for a scheduled customer meeting.

Everything comes from the graph: attendees and their history, account health and
risks (from the Detective), prior promises and their status, open bugs behind
their tickets, roadmap guidance, and the internal experts to pull in.
"""

from __future__ import annotations

import json
from datetime import datetime

from .. import db, tenants
from ..config import now
from ..health import risk, tools


def _meeting(meeting_id: str) -> dict:
    r = db.rows("""MATCH (m:Meeting {id: $id})-[:WITH]->(a:Account)
                   OPTIONAL MATCH (host:Person)-[:HOSTS]->(m)
                   RETURN m, a, host""", {"id": meeting_id}, readonly=True)
    if not r:
        raise KeyError(meeting_id)
    return r[0]


def upcoming(person_id: str | None = None, days: int = 7) -> list[dict]:
    """Scheduled customer meetings, soonest first (optionally the ones a person is invited to)."""
    rows = db.rows("""MATCH (m:Meeting {status: 'scheduled'})-[:WITH]->(a:Account)
                      WHERE $p IS NULL OR (:Person {id: $p})-[:INVITED_TO]->(m)
                      OPTIONAL MATCH (x)-[:INVITED_TO]->(m)
                      RETURN m.id AS id, m.title AS title, m.date AS start, m.end AS end, m.meetingType AS kind,
                             m.recording AS recording, a.id AS accountId, a.name AS account, a.detectiveRisk AS risk,
                             a.crmHealthScore AS crm, a.silentRisk AS silent, a.arr AS arr,
                             collect(DISTINCT {id: x.id, name: x.name, internal: x:Person}) AS attendees
                      ORDER BY start""", {"p": person_id}, readonly=True)
    for r in rows:
        r["arrLabel"] = tools.inr(r["arr"])
        r["startsIn"] = _mins_until(r["start"])
    return rows


def recent(account_id: str | None = None, limit: int = 10) -> list[dict]:
    rows = db.rows("""MATCH (m:Meeting {kind: 'customer'})-[:WITH]->(a:Account)
                      WHERE m.status = 'held' AND ($a IS NULL OR a.id = $a)
                      OPTIONAL MATCH (m)-[:PRODUCED]->(p:Promise)
                      RETURN m.id AS id, m.title AS title, m.date AS start, a.id AS accountId, a.name AS account,
                             count(p) AS promises, m.summarySource AS summarySource
                      ORDER BY start DESC LIMIT $n""", {"a": account_id, "n": limit}, readonly=True)
    return rows


def _mins_until(iso: str) -> int:
    return int((datetime.fromisoformat(iso) - now()).total_seconds() // 60)


def build(meeting_id: str) -> dict:
    row = _meeting(meeting_id)
    m, a = row["m"], row["a"]
    ctx = tools.default_ctx()
    aid = a["id"]
    attendees = db.rows("""MATCH (x)-[:INVITED_TO|ATTENDED]->(:Meeting {id: $m})
                           OPTIONAL MATCH (x)-[w:WORKS_AT]->(:Account)
                           OPTIONAL MATCH (x)-[:SUCCEEDED]->(prev:Contact)
                           RETURN DISTINCT x.id AS id, x.name AS name, coalesce(x.title, x.role) AS title, x:Person AS internal,
                                  x.leaving AS leaving, w.from AS since, prev.name AS replaced""", {"m": meeting_id}, readonly=True)
    health = risk.account_risk(aid)
    proms = tools.promises(ctx, aid).data["promises"]
    owners = tools.internal_owners(ctx, aid).data
    tickets = tools.ticket_root_causes(ctx, aid).data
    past = db.rows("""MATCH (pm:Meeting {status: 'held'})-[:WITH]->(:Account {id: $a})
                      RETURN pm.id AS id, pm.title AS title, pm.date AS date, pm.notes AS notes
                      ORDER BY pm.date DESC LIMIT 3""", {"a": aid}, readonly=True)
    sigs = tools.signals(ctx, aid).data["signals"]
    open_bugs = [c for c in tickets["clusters"] if c["open"]]

    # Roadmap items that touch this account: promised features plus anything they asked about.
    roadmap = []
    for p in proms:
        dep = p.get("dependsOn") or {}
        if dep.get("kind") == "RoadmapItem":
            item = db.rows("MATCH (i:RoadmapItem {id: $i}) RETURN i", {"i": dep["id"]}, readonly=True)[0]["i"]
            roadmap.append({"id": item["id"], "title": item["title"], "status": item["status"], "eta": item.get("etaLabel"),
                            "originally": item.get("originalLabel"), "guidance": item.get("internalNote")})

    experts = []
    for c in open_bugs[:2]:
        ex = tools.experts(ctx, bug_id=c["bugId"]).data["experts"]
        if ex:
            experts.append({**ex[0], "about": f"{c['bugId']} ({c['bugKeyword']})"})
    for r in roadmap[:1]:
        owner = db.rows("MATCH (:RoadmapItem {id: $i})-[:OWNED_BY]->(p:Person) RETURN p.id AS id, p.name AS name, p.role AS role",
                        {"i": r["id"]}, readonly=True)
        if owner:
            experts.append({**owner[0], "why": f"Owns {r['title']}", "about": r["title"], "leaving": False})
    tech = [p for p in owners["people"] if "technical contact" in p["relations"]]
    if tech:
        p = tech[0]
        experts.append({"id": p["id"], "name": p["name"], "role": p["role"], "about": "technical contact",
                        "why": "Technical contact" + (f", leaves {p['lastDay']}" if p["leaving"] else ""),
                        "leaving": p["leaving"]})

    # Goals and questions, from what the graph says matters for this account.
    goals, questions, dont = [], [], []
    renewal_in = ctx.days_until(a["renewalDate"])
    if m.get("meetingType") == "renewal" or renewal_in <= 45:
        goals.append(f"Secure the renewal ({a['renewalDate']}, {tools.inr(a['arr'])} ARR, {a.get('plan')} plan)")
    for c in open_bugs[:1]:
        goals.append(f"Acknowledge {c['bugId']} ({c['bugKeyword']}) and say when they will get a fix date")
        questions.append(f"Which reports does the team rebuild by hand while {c['bugKeyword']} is broken?")
    for p in proms:
        if p["atRisk"]:
            dep = p.get("dependsOn") or {}
            now_ = f"planned for {dep['eta']}" if dep.get("eta") else dep.get("status")
            goals.append(f"Reset the promise “{p['text']}”: {dep.get('title', 'it')} is now {now_}")
            dont.append(f"Do not commit to the original date for {dep.get('title', 'this')}. Give the new quarter and offer "
                        f"to confirm it in writing.")
    for r in roadmap:
        if r["guidance"] and r["guidance"] not in dont:
            dont.append(r["guidance"])
    comp = [s for s in sigs if s["type"] == "competitor_evaluation"]
    if comp:
        questions.append(f"What makes the other tools you are looking at a better fit than {tenants.current().name}?")
        goals.append(f"Show the revenue {tenants.current().name} brought them before you talk about price")
    successor = next((x for x in attendees if x.get("replaced")), None)
    if successor:
        questions.append(f"Now that {successor['name'].split()[0]} owns the account, what does success look like this quarter?")
    questions.append("What is one workflow you want to add next quarter?")

    return {
        "meeting": {"id": m["id"], "title": m["title"], "start": m["date"], "end": m.get("end"), "kind": m.get("meetingType"),
                    "recording": m.get("recording"), "url": m.get("url"), "startsIn": _mins_until(m["date"]),
                    "host": row["host"] and {"id": row["host"]["id"], "name": row["host"]["name"]}},
        "account": {"id": aid, "name": a["name"], "arr": a["arr"], "arrLabel": tools.inr(a["arr"]), "plan": a.get("plan"),
                    "renewalDate": a["renewalDate"], "renewalInDays": renewal_in, "stage": a.get("renewalStage"),
                    "crm": a["crmHealthScore"], "risk": health.get("risk"), "silent": health.get("silent"),
                    "factors": health.get("factors", []), "wallet": tools.inr(a.get("walletBalance"))},
        "attendees": [{**x, "leaving": bool(x["leaving"])} for x in attendees],
        "history": [{"id": p["id"], "title": p["title"], "date": p["date"][:10],
                     "summary": [ln[2:] for ln in (p["notes"] or "").splitlines() if ln.startswith("- ")][:3]} for p in past],
        "openIssues": [{"bugId": c["bugId"], "title": c["bugTitle"], "status": c.get("jiraStatus") or c["bugStatus"],
                        "priority": c["bugPriority"], "owner": c["owner"], "tickets": len(c["tickets"]),
                        "workaround": c.get("bugWorkaround")} for c in open_bugs],
        "promises": proms, "roadmap": roadmap, "experts": experts, "goals": goals[:4], "questions": questions[:3],
        "dont": dont[:3], "signals": [{"type": s["type"], "quote": s["quote"], "speaker": s["speaker"], "date": s["date"]}
                                      for s in sigs][:4],
        "generatedAt": now().isoformat(timespec="seconds"),
        "sources": sorted({"HubSpot", "Support desk", "Jira", "Meeting notes", "Product roadmap", "Product analytics"}),
    }


def as_json(meeting_id: str) -> str:
    return json.dumps(build(meeting_id), default=str)
