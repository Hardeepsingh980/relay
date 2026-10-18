"""Relay API routes for Account Health, Sales Assist, live ingest and "under the hood".

Mounted by relay.api. Every route runs inside the signed-in session's workspace
graph (set by the auth middleware), so tenants never see each other's data.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from . import db, tenants
from .health import investigator, plan, risk, tools
from .sales import brief, live

router = APIRouter(prefix="/api")


def _actor(request: Request, persona: str | None) -> str:
    user = request.state.user
    who = db.rows("MATCH (p:Person {id: $p}) RETURN p.name AS n", {"p": persona}, readonly=True) if persona else []
    return f"{user['name']}" + (f" (as {who[0]['n']})" if who else "")


def _events(obj, request: Request, after: int = -1) -> EventSourceResponse:
    """SSE over an in-memory event log (investigations and call sessions)."""
    last = request.headers.get("last-event-id")
    start = int(last) if last and last.isdigit() else after

    async def gen():
        i = start + 1
        while True:
            async with obj.cond:
                while i >= len(obj.events):
                    try:
                        await asyncio.wait_for(obj.cond.wait(), timeout=15)
                    except asyncio.TimeoutError:
                        break
                batch = obj.events[i:]
            for ev in batch:
                yield {"id": str(ev["id"]), "event": "message", "data": json.dumps(ev, default=str)}
                i = ev["id"] + 1
            # Stay open after completion: follow-ups and approvals keep adding events.
            if await request.is_disconnected():
                break
    return EventSourceResponse(gen(), ping=15)


def _has_accounts() -> bool:
    return db.rows("MATCH (a:Account) WHERE a.crmHealthScore IS NOT NULL RETURN count(a) AS n", readonly=True)[0]["n"] > 0


# ------------------------------------------------------------------ accounts

@router.get("/accounts")
def accounts() -> dict:
    if not _has_accounts():
        return {"asOf": risk.as_of(), "accounts": [], "silent": {"count": 0, "arr": 0, "arrLabel": "₹0"},
                "note": "This sample company has no customer data."}
    return investigator.radar()


@router.get("/accounts/{aid}")
def account(aid: str) -> dict:
    ctx = tools.default_ctx()
    try:
        ov = tools.account_overview(ctx, aid)
    except ValueError:
        raise HTTPException(404, "No such account")
    breakdown = risk.account_risk(aid)
    contacts = db.rows("""MATCH (c:Contact)-[w:WORKS_AT]->(:Account {id: $a})
                          OPTIONAL MATCH (c)-[:SUCCEEDED]->(prev:Contact)
                          RETURN c.id AS id, c.name AS name, c.title AS title, c.role AS role, c.isChampion AS champion,
                                 c.active AS active, w.from AS since, w.to AS left, c.email AS email,
                                 c.emailStatus AS emailStatus, prev.name AS replaced
                          ORDER BY c.active DESC, c.isChampion DESC""", {"a": aid}, readonly=True)
    meetings = db.rows("""MATCH (m:Meeting)-[:WITH]->(:Account {id: $a})
                          OPTIONAL MATCH (m)-[:PRODUCED]->(p:Promise)
                          RETURN m.id AS id, m.title AS title, m.date AS date, m.status AS status, m.recording AS recording,
                                 count(p) AS promises ORDER BY m.date DESC""", {"a": aid}, readonly=True)
    last = investigator.latest_for(aid)
    past = db.rows("""MATCH (i:Investigation)-[:INVESTIGATED]->(:Account {id: $a})
                      RETURN i.id AS id, i.completedAt AS at, i.risk AS risk, i.headline AS headline
                      ORDER BY i.completedAt DESC LIMIT 5""", {"a": aid}, readonly=True)
    tickets = tools.ticket_root_causes(ctx, aid).data
    usage = tools.usage_trend(ctx, aid).data
    return {
        "account": {**ov.data["account"], "arrLabel": tools.inr(ov.data["account"]["arr"]),
                    "walletLabel": tools.inr(ov.data["account"].get("walletBalance")),
                    "renewalInDays": ov.data["renewalInDays"], "csm": ov.data["csm"], "ae": ov.data["ae"],
                    "features": ov.data["features"]},
        "risk": breakdown, "contacts": contacts, "meetings": meetings,
        "promises": tools.promises(ctx, aid).data["promises"],
        "owners": tools.internal_owners(ctx, aid).data,
        "issues": tickets["clusters"], "usage": usage,
        "timeline": tools.timeline(ctx, aid).data["events"],
        "memory": tools.memory(ctx, aid).data["episodes"],
        "investigation": last and {"id": last.id, "status": last.status, "createdAt": last.created_at},
        "pastInvestigations": past,
        "actions": [a for a in plan.log(200) if a["accountId"] == aid],
    }


class Investigate(BaseModel):
    mode: str = "guided"


@router.post("/accounts/{aid}/investigate")
async def investigate(aid: str, body: Investigate, request: Request, x_relay_persona: str | None = Header(None)) -> dict:
    inv = investigator.start(aid, body.mode, actor=_actor(request, x_relay_persona))
    return {"id": inv.id, "mode": inv.mode, "modeDetail": inv.mode_detail}


@router.get("/investigations/{iid}")
def investigation(iid: str) -> dict:
    try:
        return investigator.get(iid).snapshot()
    except KeyError:
        raise HTTPException(404, "Investigation not found. A demo reset removes old investigations.")


@router.get("/investigations/{iid}/events")
def investigation_events(iid: str, request: Request):
    try:
        inv = investigator.get(iid)
    except KeyError:
        raise HTTPException(404, "Investigation not found")
    return _events(inv, request)


class FollowUp(BaseModel):
    question: str


@router.post("/investigations/{iid}/followups")
async def follow_up(iid: str, body: FollowUp) -> dict:
    return await investigator.get(iid).follow_up(body.question[:500])


class EditAction(BaseModel):
    payload: dict[str, Any]


@router.patch("/investigations/{iid}/actions/{action_id}")
def edit_action(iid: str, action_id: str, body: EditAction) -> dict:
    try:
        return investigator.get(iid).update_action(action_id, body.payload)
    except ValueError as e:
        raise HTTPException(409, str(e))


class ApproveActions(BaseModel):
    actionIds: list[str]


@router.post("/investigations/{iid}/approve")
async def approve(iid: str, body: ApproveActions, request: Request, x_relay_persona: str | None = Header(None)) -> list[dict]:
    return await investigator.get(iid).approve(body.actionIds, _actor(request, x_relay_persona))


@router.get("/health/costliest-bugs")
def costliest() -> dict:
    return tools.costliest_bugs(tools.default_ctx(), 8).data


@router.get("/health/actions")
def action_log() -> list[dict]:
    return plan.log()


@router.post("/health/scan")
def rescan() -> dict:
    t0 = time.perf_counter()
    out = risk.scan()
    return {"accounts": len(out), "silent": sum(1 for v in out.values() if v["silent"]),
            "ms": round((time.perf_counter() - t0) * 1000)}


@router.get("/home/overview")
def home_overview(x_relay_persona: str | None = Header(None)) -> dict:
    """What a Head of CS / CSM sees first: silent risks, people leaving, today's calls, the costliest bug."""
    from datetime import date, timedelta

    from .health import handoff
    today = date.fromisoformat(risk.as_of())
    soon = (today + timedelta(days=21)).isoformat()
    leaving_rows = db.rows("""MATCH (p:Person) WHERE (p.endDate IS NOT NULL AND p.endDate >= $today AND p.endDate <= $soon)
                                                   OR p.leaving = true
                              OPTIONAL MATCH (h:Handover {leaverId: p.id}) WHERE h.status <> 'closed'
                              RETURN p.id AS id, p.name AS name, p.role AS role, coalesce(p.lastDay, p.endDate) AS lastDay,
                                     h.id AS handoverId, h.status AS handoverStatus""",
                           {"today": today.isoformat(), "soon": soon}, readonly=True)
    leaving = []
    for r in leaving_rows:
        deps = handoff.dependent_accounts(r["id"]) if _has_accounts() else []
        unique = db.rows("MATCH (:Person {id: $p})-[k:KNOWS]->(x) WHERE k.score > 0.4 RETURN count(x) AS n", {"p": r["id"]},
                         readonly=True)[0]["n"]
        leaving.append({**r, "accounts": deps, "knows": unique})
    out = {"asOf": today.isoformat(), "leaving": leaving}
    if not _has_accounts():
        return out
    rad = investigator.radar()
    mine = [a for a in rad["accounts"] if a["csmId"] == x_relay_persona]
    bugs = tools.costliest_bugs(tools.default_ctx(), 3).data["bugs"]
    out.update({
        "silent": rad["silent"], "silentAccounts": [a for a in rad["accounts"] if a["silent"]][:6],
        "topRisks": rad["accounts"][:8], "mine": mine[:8],
        "renewing": sorted([a for a in rad["accounts"] if 0 <= a["renewalInDays"] <= 45], key=lambda a: -a["risk"])[:6],
        "meetings": brief.upcoming(None)[:6], "myMeetings": brief.upcoming(x_relay_persona)[:6],
        "costliestBug": bugs[0] if bugs else None, "actions": plan.log(8),
        "portfolio": {"accounts": len(rad["accounts"]), "arr": sum(a["arr"] for a in rad["accounts"]),
                      "arrLabel": tools.inr(sum(a["arr"] for a in rad["accounts"])),
                      "atRisk": sum(1 for a in rad["accounts"] if a["risk"] >= 60)},
    })
    return out


# ------------------------------------------------------------------ meetings

@router.get("/meetings")
def meetings(x_relay_persona: str | None = Header(None), mine: bool = False) -> dict:
    return {"upcoming": brief.upcoming(x_relay_persona if mine else None), "recent": brief.recent()}


@router.get("/meetings/{mid}/brief")
def meeting_brief(mid: str) -> dict:
    try:
        return brief.build(mid)
    except KeyError:
        raise HTTPException(404, "No such meeting")


@router.get("/meetings/{mid}")
def meeting(mid: str) -> dict:
    r = db.rows("""MATCH (m:Meeting {id: $id}) OPTIONAL MATCH (m)-[:WITH]->(a:Account)
                   OPTIONAL MATCH (m)-[:PRODUCED]->(p:Promise)
                   RETURN m, a.id AS accountId, a.name AS account, collect(p {.*}) AS promises""", {"id": mid}, readonly=True)
    if not r:
        raise HTTPException(404, "No such meeting")
    m = r[0]["m"]
    call = live.for_meeting(mid)
    transcript = json.loads(m["transcript"]) if m.get("transcript") else []
    names = {x["id"]: x["name"] for x in db.rows("MATCH (x) WHERE x:Person OR x:Contact RETURN x.id AS id, x.name AS name",
                                                 readonly=True)}
    for line in transcript:
        line.setdefault("speakerName", names.get(line.get("speaker"), "Speaker"))
    return {"meeting": {**{k: v for k, v in m.items() if k not in ("_labels",)}, "transcript": transcript},
            "accountId": r[0]["accountId"], "account": r[0]["account"], "promises": r[0]["promises"],
            "call": call and call.snapshot()}


class StartCall(BaseModel):
    speed: float = 1.0
    live: bool = False


class Say(BaseModel):
    text: str
    who: str = "customer"   # customer | rep


@router.post("/meetings/{mid}/call")
async def start_call(mid: str, body: StartCall, request: Request, x_relay_persona: str | None = Header(None)) -> dict:
    existing = live.for_meeting(mid)
    if existing and existing.status in ("live", "ready"):
        return existing.snapshot()
    try:
        s = live.start(mid, body.speed, actor=_actor(request, x_relay_persona), live=body.live)
    except KeyError:
        raise HTTPException(404, "No such meeting")
    except ValueError as e:
        raise HTTPException(409, str(e))
    return s.snapshot()


@router.get("/calls/{cid}")
def call(cid: str) -> dict:
    try:
        return live.get(cid).snapshot()
    except KeyError:
        raise HTTPException(404, "Call not found")


@router.get("/calls/{cid}/events")
def call_events(cid: str, request: Request):
    try:
        s = live.get(cid)
    except KeyError:
        raise HTTPException(404, "Call not found")
    return _events(s, request)


@router.post("/calls/{cid}/say")
async def say(cid: str, body: Say) -> dict:
    try:
        s = live.get(cid)
    except KeyError:
        raise HTTPException(404, "No such call") from None
    try:
        return await s.say(body.text, body.who)
    except ValueError as e:
        raise HTTPException(409, str(e)) from None


@router.post("/calls/{cid}/end")
async def end_call(cid: str) -> dict:
    s = live.get(cid)
    if s.task and not s.task.done():
        s.task.cancel()
    return await s.end()


@router.post("/calls/{cid}/cards/{card_id}/ping")
async def ping(cid: str, card_id: str, request: Request, x_relay_persona: str | None = Header(None)) -> dict:
    return await live.get(cid).ping(card_id, _actor(request, x_relay_persona))


@router.post("/calls/{cid}/approve")
async def approve_call_actions(cid: str, body: ApproveActions, request: Request,
                               x_relay_persona: str | None = Header(None)) -> list[dict]:
    s = live.get(cid)
    if not s.result:
        raise HTTPException(409, "The call does not have a summary yet")
    actor = _actor(request, x_relay_persona)
    done = []
    for a in s.result["actions"]:
        if a["id"] not in body.actionIds or a["status"] not in ("proposed", "failed"):
            continue
        errs = plan.validate_payload(a)
        if errs:
            a.update(status="needs_attention", result={"message": ". ".join(errs) + "."})
            continue
        a.update(status="approved", approvedBy=actor, approvedAt=plan.stamp())
        if a["type"] == "crm.note":
            out = plan.Outcome("simulated", "Saved in Relay on the account timeline. Connect HubSpot to log it there too.")
        else:
            out = await asyncio.to_thread(plan.execute, a)
        a.update(status=out.status, executedAt=plan.stamp(), result={"message": out.message, "ref": out.ref, "url": out.url})
        await asyncio.to_thread(plan.persist, a)
        done.append(a)
    await s.emit("call.actions", {"actions": s.result["actions"]})
    return done


# ------------------------------------------------------------------ live ingest

class SlackMessage(BaseModel):
    channel: str = "cs"
    personId: str
    text: str


@router.post("/ingest/slack")
def ingest_slack(body: SlackMessage) -> dict:
    """The Ingest agent: one new Slack message lands in the graph and is searchable immediately."""
    from .ingest import live as live_ingest
    return live_ingest.slack_message(body.channel, body.personId, body.text)


@router.get("/ingest/recent")
def ingest_recent() -> list[dict]:
    from .ingest import live as live_ingest
    return live_ingest.recent()


# ------------------------------------------------------------------ under the hood

def _graph_stats(name: str) -> dict:
    g = db.graph(name)
    labels = db.rows("MATCH (n) RETURN labels(n)[0] AS label, count(n) AS n ORDER BY n DESC", g=g, readonly=True)
    rels = db.rows("MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS n ORDER BY n DESC", g=g, readonly=True)
    comp = db.rows("MATCH (c:Company) RETURN c.name AS name, c.tagline AS tagline", g=g, readonly=True)
    return {"graph": name, "company": comp[0] if comp else None, "nodes": sum(r["n"] for r in labels),
            "edges": sum(r["n"] for r in rels), "labels": labels, "relationships": rels}


@router.get("/system/graphs")
def graphs(request: Request) -> dict:
    from .ingest.pipeline import base_graph_name
    names = []
    current = db.current_graph_name()
    names.append({"role": "your workspace", "name": current})
    for t in tenants.TENANTS.values():
        if db.exists(t.base_graph) and t.base_graph != base_graph_name(current):
            names.append({"role": f"{t.name} (another tenant)", "name": t.base_graph})
    return {"graphs": [{**n, **_graph_stats(n["name"])} for n in names], "throughput": db.meter.snapshot()}


@router.get("/system/throughput")
def throughput() -> dict:
    return {"meter": db.meter.snapshot()}


@router.get("/system/agents")
def agents() -> dict:
    from .health.mcp_server import PLANNER_TOOLS
    return {"agents": [
        {"id": "ingest", "name": "Ingest", "job": "Reads Slack, Jira, docs, meetings, CRM, support and usage data into the graph. "
                                                 "Finds decisions, workarounds, promises and warning signs.",
         "writes": ["Message", "Ticket", "Decision", "Workaround", "Signal", "Promise"], "tools": ["ingest/slack"]},
        {"id": "detective", "name": "Detective", "job": "Scores every account, finds out why an account is at risk and suggests "
                                                       "a save plan (steps to keep the customer).",
         "writes": ["Risk", "Investigation", "Episode", "Action"], "tools": PLANNER_TOOLS},
        {"id": "handover", "name": "Handover", "job": "Finds what only the person leaving knows, runs the interview and passes "
                                                     "their accounts to the next owner.",
         "writes": ["RiskItem", "Knowledge", "Risk (owner leaving)"], "tools": ["unique_knowledge", "who_knows"]},
        {"id": "onboarding", "name": "Onboarding", "job": "Builds Day One for a new joiner: who to meet, what they take over and "
                                                         "their first tickets.",
         "writes": ["ChecklistItem", "Action"], "tools": ["who_knows", "ask"]},
        {"id": "sales", "name": "Sales Assist", "job": "Gives a brief before the call and cards during it. After the call, it "
                                                     "logs promises and next steps.",
         "writes": ["Meeting (held)", "Promise", "Signal", "Episode", "Action"], "tools": ["meeting_brief", "roadmap_status", "experts"]},
    ], "note": "Agents never message each other. They read and write the same graph and share their tools over MCP."}
