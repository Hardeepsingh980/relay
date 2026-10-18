"""After the call: summary, promises and signals written to the graph, a follow-up
email draft, internal tasks, and the account's health re-scored.

Promises are written as (:Meeting)-[:PRODUCED]->(:Promise)-[:TO]->(:Account). A
promise that resets an older one on the same roadmap item supersedes it, which
is how the Detective learns the old promise is no longer at risk.
"""

from __future__ import annotations

import json
import re
import time
import uuid

from .. import db, tenants
from ..config import now
from ..health import plan, risk
from ..health import signals as sig_rules
from ..health.tools import inr
from ..ingest.accounts import write_promise, write_signals

COMM_VERBS = re.compile(r"^(confirm|share|send|get you|follow up|set up|put|email|update)\b", re.I)


def _first(name: str) -> str:
    return name.split()[0]


def _promise_rows(session) -> list[dict]:
    rows = []
    for n, p in enumerate(session.ctx.promises, 1):
        communication = bool(COMM_VERBS.search(p["text"]))
        rows.append({"id": f"prm-{session.id}-{n}", "kind": "promise", "text": p["text"], "due": p["due"],
                     "made_by_email": None, "madeById": p["madeById"], "madeBy": p["madeBy"],
                     "account": session.account["name"], "source_id": session.meeting["id"],
                     "made_at": session.meeting["date"], "status": "open", "quote": p["quote"],
                     "depends_on": None if communication else p["dependsOn"], "about": p["dependsOn"],
                     "extraction": "live-call rules-v1"})
    return rows


def _notes(session, promises: list[dict]) -> tuple[str, list[str]]:
    cards = session.cards
    acct = session.account["name"]
    bullets = []
    bug = next((c for c in cards if c["kind"] == "bug"), None)
    if bug:
        owner = (bug.get("entity") or {}).get("owner")
        bullets.append(("Exports", f"{bug['speaker']} raised {bug['entity']['bugId']} again. The team is rebuilding reports "
                                   f"by hand. {owner + ' owns the fix.' if owner else ''}".strip()))
    road = next((c for c in cards if c["kind"] == "roadmap"), None)
    if road:
        bullets.append(("Roadmap", f"{road['title']}. The team reset the earlier expectation on the call."))
    ans = next((c for c in cards if c["kind"] == "answer"), None)
    if ans:
        src = f" (from {ans['source']['label']})" if ans.get("source") else ""
        bullets.append(("Product question", f"{ans['title']}. The team answered it on the call{src}."))
    obj = next((c for c in cards if c["kind"] == "objection"), None)
    if obj:
        company = tenants.current().name
        bullets.append(("Pricing", f"{obj['speaker']} compared {company} with a cheaper platform. The team showed the revenue "
                                   f"{company} brought them before talking about price."))
    risks = [c for c in cards if c["kind"] == "risk" and c["title"] != "Promise at risk"]
    if risks:
        bullets.append(("Risk", ". ".join(r["title"].removeprefix("Risk: ").capitalize() for r in risks) + "."))
    if promises:
        n = len(promises)
        bullets.append(("Commitments", f"{n} promise{'s' if n != 1 else ''} logged for {acct}."))
    by_owner: dict[str, list[str]] = {}
    for p in promises:
        seg = next((s for s in session.transcript if s["text"] == p["quote"]), None)
        stamp = f" ({int(seg['t']) // 60:02d}:{int(seg['t']) % 60:02d})" if seg else ""
        by_owner.setdefault(p["madeBy"], []).append(f"{p['text']}, due {p['due']}{stamp}")
    lines = ["Overview"] + [f"- **{k}:** {v}" for k, v in bullets]
    if by_owner:
        lines += ["", "Action Items"]
        for owner, items in by_owner.items():
            lines.append(f"**{owner}**")
            lines += [f"- {i}" for i in items]
    return "\n".join(lines), [f"{k}: {v}" for k, v in bullets]


def _email(session, promises: list[dict], overview: list[str]) -> dict:
    contacts = db.rows("""MATCH (c:Contact)-[:INVITED_TO]->(:Meeting {id: $m}) RETURN c.name AS name, c.email AS email""",
                       {"m": session.meeting["id"]}, readonly=True)
    host = db.rows("MATCH (p:Person)-[:HOSTS]->(:Meeting {id: $m}) RETURN p.name AS name", {"m": session.meeting["id"]},
                   readonly=True)
    sender = host[0]["name"] if host else f"The {tenants.current().name} team"
    names = " and ".join(_first(c["name"]) for c in contacts) or "team"
    ours = [p for p in promises]
    lines = "\n".join(f"- {p['text']} ({_first(p['madeBy'])}, by {p['due']})" for p in ours)
    ans = next((c for c in session.cards if c["kind"] == "answer" and c.get("source")), None)
    docs = f"\n\nCarousel templates via the API: {ans['body']}" if ans else ""
    body = (f"Hi {names},\n\nThank you for your time today. Here is what we agreed:\n\n{lines}{docs}\n\n"
            f"I will keep you updated on the export fix and send you the date by Friday.\n\nBest,\n{sender}")
    return {"to": [c["email"] for c in contacts], "subject": f"Recap: {session.meeting['title']}", "body": body,
            "send": False}


def _tasks(session, promises: list[dict]) -> list[dict]:
    out = []
    bug = next((c for c in session.cards if c["kind"] == "bug"), None)
    if bug and (bug.get("entity") or {}).get("owner"):
        out.append({"assignee": bug["entity"]["owner"], "title": f"Share a fix date for {bug['entity']['bugId']} by Thursday",
                    "description": f"On the renewal call, we promised {session.account['name']} a fix date by Friday.",
                    "addresses": [bug["entity"]["bugId"], bug["entity"]["ownerId"]]})
    road = next((c for c in session.cards if c["kind"] == "roadmap"), None)
    if road:
        owner = db.rows("MATCH (:RoadmapItem {id: $i})-[:OWNED_BY]->(p:Person) RETURN p.name AS name, p.id AS id",
                        {"i": road["entity"]["roadmapId"]}, readonly=True)
        if owner:
            out.append({"assignee": owner[0]["name"], "title": f"Confirm the {road['title'].split(' moved')[0]} timeline for "
                                                             f"{session.account['name']} in writing",
                        "description": "The account executive promised to confirm it in writing this week.",
                        "addresses": [road["entity"]["roadmapId"], owner[0]["id"]]})
    for p in promises:
        if p["madeBy"] and "proposal" in p["text"].lower():
            out.append({"assignee": p["madeBy"], "title": f"{p['text']} ({session.account['name']})",
                        "description": f"Promised on the renewal call, due {p['due']}.", "addresses": [p["id"]]})
    return out


def finalize(session) -> dict:
    t0 = time.perf_counter()
    m, acc = session.meeting, session.account
    aid = acc["id"]
    before = acc.get("detectiveRisk")
    promises = _promise_rows(session)

    # 1. The meeting record becomes a held meeting with transcript and notes.
    speakers = {r["email"]: r["id"] for r in db.rows("MATCH (x) WHERE x:Person OR x:Contact RETURN x.email AS email, x.id AS id",
                                                     readonly=True)}
    transcript = [{"speaker": speakers.get(s["speaker_email"]), "speakerName": s["speaker_name"], "t": s["t"],
                   "text": s["text"]} for s in session.transcript]
    notes, overview = _notes(session, promises)
    db.run("""MATCH (m:Meeting {id: $id})
              SET m.status = 'held', m.transcript = $tr, m.text = $text, m.notes = $notes, m.summarySource = 'Relay live call',
                  m.callId = $call, m.heldAt = $at""",
           {"id": m["id"], "tr": json.dumps(transcript), "text": "\n".join(s["text"] for s in session.transcript),
            "notes": notes, "call": session.id, "at": now().isoformat(timespec="seconds")})
    db.run("""MATCH (x)-[:INVITED_TO]->(m:Meeting {id: $id}) MERGE (x)-[:ATTENDED]->(m)""", {"id": m["id"]})

    # 2. Promises (and what they supersede).
    superseded = []
    for p in promises:
        write_promise(None, None, p, account_id=aid, maker_id=p["madeById"])
        about = p.get("about")
        if about:
            db.run(f"MATCH (p:Promise {{id: $id}}), (x:{about['kind']} {{id: $x}}) MERGE (p)-[:ABOUT]->(x)",
                   {"id": p["id"], "x": about["id"]})
            if about["kind"] == "RoadmapItem":
                rows = db.rows("""MATCH (old:Promise {status: 'open'})-[:DEPENDS_ON]->(:RoadmapItem {id: $x}),
                                        (old)-[:TO]->(:Account {id: $a}), (new:Promise {id: $id})
                                  SET old.status = 'superseded', old.supersededAt = $at
                                  CREATE (old)-[:SUPERSEDED_BY]->(new)
                                  RETURN old.id AS id, old.text AS text""",
                               {"x": about["id"], "a": aid, "id": p["id"], "at": now().isoformat(timespec="seconds")})
                superseded += rows

    # 3. Signals said on the call (customer side only), for the Detective.
    sigs = []
    for s in session.transcript:
        if s["internal"]:
            continue
        for i, x in enumerate(sig_rules.extract(s["text"])):
            sigs.append({"id": f"SIG-{session.id}-{s['i']}-{i}", "conv": m["id"], **x, "at": m["date"][:10]})
    write_signals(db.graph(), sigs, "Meeting")

    # 4. Follow-through: email draft (customer-facing, needs approval) and internal tasks.
    status = plan.integration_status()
    actions = [plan._action("email.draft", "Follow-up email to the customer", "Recap of the call and every promise, with dates",
                            {"system": "Gmail", "mode": status["gmail"]["mode"], "target": "customer"},
                            _email(session, promises, overview), [aid], session.id, customer_facing=True)]
    for t in _tasks(session, promises):
        actions.append(plan._action("task.create", t["title"], f"Task for {t['assignee']}",
                                    {"system": "Jira", "mode": status["jira"]["mode"], "target": t["assignee"]},
                                    {"assignee": t["assignee"], "title": t["title"], "description": t["description"],
                                     "due": None}, t["addresses"], session.id))
    actions.append(plan._action("crm.note", "Log the call to HubSpot", "Notes and promises on the company record",
                                {"system": "HubSpot", "mode": "simulated", "target": acc["name"]},
                                {"note": notes}, [aid], session.id))

    # 5. Account Health re-scored from the updated graph.
    scanned = risk.scan(aid)[aid]
    db.run("""MATCH (a:Account {id: $a})
              CREATE (e:Episode {id: $id, kind: 'call', at: $at, t: $t, risk: $risk, verdict: $verdict, outcome: $outcome,
                                 memory: 'episodic'})-[:FOR_ACCOUNT]->(a)
              WITH e MATCH (m:Meeting {id: $m}) CREATE (e)-[:FROM_MEETING]->(m)""",
           {"a": aid, "id": f"ep-{session.id}", "at": now().isoformat(timespec="seconds"), "t": time.time(),
            "risk": scanned["risk"], "verdict": overview[0] if overview else m["title"],
            "outcome": f"{len(promises)} promise{'s' if len(promises) != 1 else ''} logged, {len(superseded)} replaced",
            "m": m["id"]})
    return {"meetingId": m["id"], "notes": notes, "overview": overview, "promises": [
                {k: p[k] for k in ("id", "text", "due", "madeBy", "quote")} | {"about": p.get("about")} for p in promises],
            "superseded": superseded, "signals": [{"type": s["type"], "quote": s["quote"]} for s in sigs],
            "actions": actions, "health": {"before": before, "after": scanned["risk"], "factors": scanned["factors"],
                                           "hint": scanned["hint"]},
            "arrLabel": inr(acc.get("arr")), "ms": round((time.perf_counter() - t0) * 1000)}


def ping_expert(card: dict, actor: str) -> dict:
    """Ask-an-expert: an internal Slack DM from the rep (live if Slack is connected, otherwise simulated)."""
    a = card["action"]
    action = plan._action("slack.post", f"Message {a['to']}", a["message"][:120],
                          {"system": "Slack", "mode": plan.integration_status()["slack"]["mode"], "target": a["to"]},
                          {"channel": f"@{a['to']}", "message": a["message"]}, [a["toId"]], f"card:{card['id']}")
    action.update(status="approved", approvedBy=actor, approvedAt=now().isoformat(timespec="seconds"),
                  approvalId=f"apr-{uuid.uuid4().hex[:8]}")
    out = plan.execute(action)
    action.update(status=out.status, executedAt=now().isoformat(timespec="seconds"),
                  result={"message": out.message, "ref": out.ref, "url": out.url})
    plan.persist(action)
    return {"status": out.status, "message": out.message}
