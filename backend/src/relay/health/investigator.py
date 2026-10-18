"""The Detective agent: runs graph tools, streams events, assembles the verdict, answers
follow-ups and executes approved actions.

Two planners share the same tools and event stream:
  * guided  - a fixed, repeatable plan (default for the demo; no LLM needed)
  * gemini  - Gemini chooses which tools to call over MCP; falls back to guided steps if it fails

The Detective never messages other agents. It reads what they wrote to the graph
(promises from Sales Assist, owner-leaving risks from Handover) and writes its own
results back (Risk, Investigation and Episode nodes).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid


from .. import db, tenants
from ..config import settings
from . import plan, risk, tools
from . import verdict as verdict_mod

log = logging.getLogger("relay.detective")

GUIDED_PLAN = [
    ("account_overview", "Loading the account"),
    ("memory", "Checking past investigations"),
    ("champion_changes", "Checking contact changes"),
    ("ticket_root_causes", "Grouping recent tickets by cause"),
    ("usage_trend", "Measuring product usage"),
    ("signals", "Checking calls and chats for warning signs"),
    ("promises", "Checking promises made to them"),
    ("internal_owners", "Checking who at Cheerio they depend on"),
    ("billing_events", "Checking billing and wallet"),
    ("risk_breakdown", "Scoring the risk factors"),
    ("causal_chain", "Tracing how the evidence connects"),
]
REQUIRED = [t for t, _ in GUIDED_PLAN]

DONE_TITLES = {
    "account_overview": lambda d: f"Loaded {d['account']['name']}",
    "memory": lambda d: "Found an earlier investigation" if d["episodes"] else "No earlier investigations",
    "champion_changes": lambda d: "Main contact left" if d["championDeparted"] else "Checked contact changes",
    "ticket_root_causes": lambda d: (f"{len(d['clusters'][0]['tickets'])} tickets point to one bug"
                                     if d["clusters"] and d["clusters"][0]["open"] and len(d["clusters"][0]["tickets"]) > 1
                                     else "Grouped recent tickets"),
    "usage_trend": lambda d: (f"Measured {d['featureDeclines'][0]['metric']} usage" if d["featureDeclines"]
                              else "Measured product usage"),
    "signals": lambda d: ("Competitor mention found" if any(s["type"] == "competitor_evaluation" for s in d["signals"])
                          else "Checked calls and chats"),
    "promises": lambda d: (f"{d['atRisk']} promise{'s' if d['atRisk'] != 1 else ''} at risk" if d["atRisk"]
                           else "Promises on track"),
    "internal_owners": lambda d: f"{d['leaving'][0]['name']} is leaving" if d["leaving"] else "No owner is leaving",
    "billing_events": lambda d: "Late payment found" if d["latestLate"] else "Checked billing",
    "risk_breakdown": lambda d: f"Risk scored: {d['risk']}%",
    "causal_chain": lambda d: "Chain of evidence found" if d.get("candidates") else "No chain of evidence found",
}


def now() -> str:
    """Demo clock (DEMO_NOW + time since boot), so records line up with the seeded world."""
    from ..config import now as demo_now
    return demo_now().isoformat(timespec="milliseconds")


def step_delay() -> float:
    return float(os.getenv("RELAY_STEP_DELAY", "0.6"))


class Investigation:
    def __init__(self, account_id: str, mode: str, actor: str | None = None):
        self.id = f"inv-{uuid.uuid4().hex[:10]}"
        self.graph = db.current_graph_name()
        self.workspace = db.current_workspace_id()
        self.account_id = account_id
        self.actor = actor
        self.mode = mode
        self.mode_detail = ""
        self.status = "running"
        self.created_at = now()
        self.completed_at: str | None = None
        self.events: list[dict] = []
        self.cond = asyncio.Condition()
        self.nodes: dict[str, dict] = {}
        self.edges: dict[str, dict] = {}
        self.evidence: dict[str, dict] = {}
        self.steps: list[dict] = []
        self.causal: dict = {"nodeIds": [], "edgeIds": []}
        self.verdict: dict | None = None
        self.actions: dict[str, dict] = {}
        self.followups: list[dict] = []
        self.data: dict[str, dict] = {}
        self.ctx = tools.default_ctx()
        self.task: asyncio.Task | None = None

    # ------------------------------------------------------------ events
    async def emit(self, type_: str, payload: dict) -> None:
        async with self.cond:
            self.events.append({"id": len(self.events), "type": type_, "ts": now(), "payload": payload})
            self.cond.notify_all()

    def snapshot(self) -> dict:
        return {
            "id": self.id, "accountId": self.account_id, "mode": self.mode, "modeDetail": self.mode_detail,
            "status": self.status, "createdAt": self.created_at, "completedAt": self.completed_at,
            "steps": self.steps, "graph": {"nodes": list(self.nodes.values()), "edges": list(self.edges.values())},
            "evidence": self.evidence, "causal": self.causal, "verdict": self.verdict,
            "actions": list(self.actions.values()), "followups": self.followups, "lastEventId": len(self.events) - 1,
        }

    async def pause(self, seconds: float) -> None:
        if step_delay() > 0:
            await asyncio.sleep(seconds * step_delay() / 0.6)

    async def apply(self, result: tools.ToolResult, step_id: str, stagger: float = 0.07) -> None:
        """Stream a tool's graph delta: nodes first (staggered), then edges whose endpoints exist."""
        new_ev = [e for e in result.evidence if e["id"] not in self.evidence]
        for e in result.evidence:
            self.evidence[e["id"]] = {**self.evidence.get(e["id"], {}), **e}
        if new_ev:
            await self.emit("evidence.added", {"stepId": step_id, "items": new_ev})
        for n in result.nodes:
            if n["id"] in self.nodes:
                continue
            self.nodes[n["id"]] = {**n, "stepId": step_id}
            await self.emit("graph.node.added", {"node": self.nodes[n["id"]]})
            await self.pause(stagger)
        for e in result.edges:
            if e["id"] in self.edges or e["source"] not in self.nodes or e["target"] not in self.nodes:
                continue
            self.edges[e["id"]] = {**e, "stepId": step_id}
            await self.emit("graph.edge.added", {"edge": self.edges[e["id"]]})

    async def run_tool(self, name: str, args: dict, title: str | None = None, show_graph: bool = True,
                       origin: str = "planner", executor=None) -> tools.ToolResult | None:
        """Run one graph tool and stream its result. `executor` routes the call elsewhere (e.g. MCP)."""
        step_id = f"s{len(self.steps) + 1}"
        step = {"id": step_id, "tool": name, "args": args, "title": title or name, "status": "running",
                "startedAt": now(), "summary": "", "ms": None, "queries": [], "origin": origin,
                "via": "mcp" if executor is not None else "direct"}
        self.steps.append(step)
        await self.emit("step.started", {"step": step})
        t0 = time.perf_counter()
        try:
            if executor is not None:
                result = await executor(name, args)
            else:
                result = await asyncio.to_thread(tools.call, name, self.ctx, **args)
        except Exception as exc:  # noqa: BLE001 - surface any tool failure as a step state
            log.exception("tool %s failed", name)
            step.update(status="failed", summary=f"{type(exc).__name__}: {exc}"[:200],
                        ms=round((time.perf_counter() - t0) * 1000))
            await self.emit("step.failed", {"step": step})
            return None
        self.data[name] = result.data
        done = DONE_TITLES.get(name)
        step.update(status="completed", summary=result.summary, ms=round((time.perf_counter() - t0) * 1000),
                    queries=result.trace(), title=(done(result.data) if done and origin == "planner" and show_graph
                                                   else step["title"]))
        if show_graph:
            await self.apply(result, step_id)
        else:
            for e in result.evidence:
                self.evidence.setdefault(e["id"], e)
        await self.emit("step.completed", {"step": step})
        if name == "causal_chain" and result.data.get("causal"):
            self.causal = result.data["causal"]
            await self.pause(0.4)
            await self.emit("graph.causal", {**self.causal, "ranking": result.data.get("ranking")})
        return result

    # ------------------------------------------------------------ planners
    async def run(self) -> None:
        try:
            await self.emit("investigation.started", {"investigationId": self.id, "accountId": self.account_id,
                                                      "mode": self.mode})
            if self.mode == "gemini":
                try:
                    from . import gemini
                    await gemini.plan(self)
                    self.mode_detail = f"Gemini ({settings().llm_model}) chose the tools via MCP"
                except Exception as exc:  # noqa: BLE001
                    log.warning("Gemini planner failed, continuing with guided steps: %s", exc)
                    self.mode_detail = f"Gemini was not available ({type(exc).__name__}), so Relay used the fixed steps"
                    await self.emit("mode.changed", {"mode": "guided", "detail": self.mode_detail})
            for name, title in GUIDED_PLAN:
                if name not in self.data:
                    await self.run_tool(name, {"account_id": self.account_id}, title)
                    await self.pause(0.6)
            await self.finish()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.exception("investigation failed")
            self.status = "failed"
            await self.emit("investigation.failed", {"error": f"{type(exc).__name__}: {exc}"[:300]})

    async def finish(self) -> None:
        step = {"id": f"s{len(self.steps) + 1}", "tool": "verdict", "args": {}, "title": "Writing the finding",
                "status": "running", "startedAt": now(), "summary": "", "ms": None, "queries": [], "origin": "planner"}
        self.steps.append(step)
        await self.emit("step.started", {"step": step})
        v = verdict_mod.build(self.data, tenants.for_graph(self.graph).name)
        problems = verdict_mod.validate(v, set(self.evidence))
        if problems:
            log.warning("verdict evidence problems: %s", problems)
            v["chain"] = [s for s in v["chain"] if s["evidenceIds"] and all(e in self.evidence for e in s["evidenceIds"])]
            for i, s in enumerate(v["chain"], 1):
                s["n"] = i
        if self.mode == "gemini" and "Gemini (" in self.mode_detail:
            try:
                from . import gemini
                narrative = await gemini.narrate(self, v)
                if narrative:
                    v.update(narrative)
            except Exception as exc:  # noqa: BLE001
                log.warning("Gemini narrative failed, keeping template: %s", exc)
        v["evidenceProblems"] = problems
        self.verdict = v
        step.update(status="completed", summary=v["headline"], title="Finding ready")
        await self.emit("verdict.updated", {"verdict": v})
        await self.emit("step.completed", {"step": step})

        if v.get("bugId"):
            await self.pause(0.4)
            await self.run_tool("blast_radius", {"bug_id": v["bugId"], "exclude_account_id": self.account_id},
                                f"Checking which other accounts {v['bugId']} hits", show_graph=False)
            br = self.data.get("blast_radius") or {}
            v["blastRadius"] = {"accounts": br.get("accountCount", 0), "arr": br.get("totalArr", 0),
                                "arrLabel": tools.inr(br.get("totalArr", 0)),
                                "names": [a["name"] for a in br.get("accounts", [])]}
        keys = [f["key"] for f in v.get("factors", []) if f["points"] > 0]
        pb = await self.run_tool("playbooks", {"factors": keys}, "Finding playbooks that worked before",
                                 show_graph=False)
        if pb and pb.data["playbooks"]:
            v["playbook"] = pb.data["playbooks"][0]
        await self.emit("verdict.updated", {"verdict": v})
        await self.pause(0.4)
        for a in await asyncio.to_thread(plan.prepare, self.id, v, self.data):
            self.actions[a["id"]] = a
            await self.emit("action.prepared", {"action": a})
            await self.pause(0.15)
        self.status = "completed"
        self.completed_at = now()
        await asyncio.to_thread(self.persist)
        await self.emit("investigation.completed", {"status": self.status, "evidenceCount": len(self.evidence),
                                                    "nodeCount": len(self.nodes), "edgeCount": len(self.edges)})

    def persist(self) -> None:
        """Episodic memory in the graph: (:Investigation)-[:INVESTIGATED]->(Account), -[:CITED]->(evidence),
        plus an (:Episode) the next investigation of this account will recall."""
        v = self.verdict or {}
        cited = sorted({e for s in v.get("chain", []) + v.get("supporting", []) for e in s["evidenceIds"]
                        if not e.startswith("usage:")})
        db.run("""
MATCH (a:Account {id: $accountId})
MERGE (i:Investigation {id: $id})
SET i.accountId = $accountId, i.mode = $mode, i.startedAt = $startedAt, i.completedAt = $completedAt,
    i.risk = $risk, i.headline = $headline, i.verdict = $verdict, i.actor = $actor
MERGE (i)-[:INVESTIGATED]->(a)
CREATE (e:Episode {id: 'ep-' + $id, kind: 'investigation', at: $completedAt, t: $t, risk: $risk,
                   verdict: $headline, outcome: 'Save plan proposed', memory: 'episodic'})
CREATE (e)-[:FOR_ACCOUNT]->(a)
WITH i
UNWIND $cited AS cid
MATCH (n) WHERE n.id = cid AND (n:Contact OR n:Ticket OR n:Conversation OR n:Signal OR n:Invoice OR n:Promise OR n:Person)
MERGE (i)-[:CITED]->(n)
""", {"id": self.id, "accountId": self.account_id, "mode": self.mode, "startedAt": self.created_at,
      "completedAt": self.completed_at, "t": time.time(), "risk": v.get("risk"), "headline": v.get("headline"),
      "verdict": json.dumps(v, default=str), "cited": cited, "actor": self.actor})

    # ------------------------------------------------------------ follow-ups
    async def follow_up(self, question: str) -> dict:
        fid = f"f{len(self.followups) + 1}"
        await self.emit("followup.started", {"followupId": fid, "question": question})
        intent = route(question)
        try:
            if intent == "blast_radius":
                answer = await self._fu_blast_radius(question)
            elif intent == "timeline":
                answer = await self._fu_timeline()
            elif intent == "costliest_bugs":
                answer = await self._fu_costliest()
            elif intent == "experts":
                answer = await self._fu_experts()
            elif settings().llm_enabled:
                from . import gemini
                answer = await gemini.answer(self, question)
            else:
                answer = {"answer": "I can answer questions like “Who else is hit by this bug?”, “What changed in "
                                    "the last 90 days?”, “Which bug puts the most yearly revenue at risk?” and “Who can fix "
                                    "this?”. Other questions need Gemini, and no GEMINI_API_KEY is set.",
                          "observed": [], "inferred": [], "evidenceIds": [], "tool": None}
        except Exception as exc:  # noqa: BLE001
            log.exception("follow-up failed")
            answer = {"answer": f"That question failed ({type(exc).__name__}). The case graph did not change.",
                      "observed": [], "inferred": [], "evidenceIds": [], "tool": None, "error": True}
        fu = {"id": fid, "question": question, "intent": intent, "askedAt": now(), **answer}
        self.followups.append(fu)
        await self.emit("followup.completed", {"followup": fu})
        return fu

    async def _fu_blast_radius(self, question: str) -> dict:
        bug = (self.verdict or {}).get("bugId")
        m = re.search(r"CHEER-\d+|LUM-\d+", question, flags=re.IGNORECASE)
        if m:
            bug = m.group(0).upper()
        if not bug:
            return {"answer": "No open bug is linked to this account, so no other accounts are hit.",
                    "observed": [], "inferred": [], "evidenceIds": [], "tool": "blast_radius"}
        r = await self.run_tool("blast_radius", {"bug_id": bug, "exclude_account_id": self.account_id},
                                f"Tracing who else {bug} hits", origin="followup")
        d = r.data
        if not d["accounts"]:
            return {"answer": f"No other account has tickets that clearly point to {bug}.",
                    "observed": [], "inferred": [], "evidenceIds": [bug], "tool": "blast_radius", "data": d}
        own = self.data["account_overview"]["account"]
        lines = [f"{a['name']}: {tools.inr(a['arr'])} ARR, {len(a['tickets'])} ticket{'s' if len(a['tickets']) > 1 else ''}, "
                 f"renews in {a['renewalInDays']} days" for a in d["accounts"]]
        answer = (f"{bug} also hits {d['accountCount']} other accounts, with {tools.inr(d['totalArr'])} in yearly revenue "
                  f"({tools.inr(d['totalArr'] + own['arr'])} with {tools.short_name(own['name'])}).")
        await self.emit("graph.focus", {"nodeIds": [bug] + [a["id"] for a in d["accounts"]]})
        return {"answer": answer, "observed": lines,
                "inferred": [f"Each account has tickets linked to {bug} with confidence 0.70 or higher. "
                             f"Relay counts each account's ARR once."],
                "evidenceIds": [bug] + [a["id"] for a in d["accounts"]], "tool": "blast_radius", "data": d}

    async def _fu_timeline(self) -> dict:
        r = await self.run_tool("timeline", {"account_id": self.account_id, "days": 90}, "Building the 90-day timeline",
                                show_graph=False, origin="followup")
        events = r.data["events"]
        key = [e for e in events if e["kind"] in ("contact", "bug", "usage", "invoice", "meeting")
               or (e["kind"] == "ticket" and "→" in e["label"]) or e.get("signals")]
        return {"answer": f"{len(events)} events in the last 90 days. The key changes are below, oldest first.",
                "observed": [f"{e['date']}: {e['label']}" for e in key],
                "inferred": [], "evidenceIds": [e["nodeId"] for e in key if e["nodeId"] in self.evidence],
                "tool": "timeline", "data": r.data}

    async def _fu_costliest(self) -> dict:
        r = await self.run_tool("costliest_bugs", {"limit": 5}, "Ranking open bugs by ARR at risk", origin="followup")
        bugs = r.data["bugs"]
        if not bugs:
            return {"answer": "No open bugs have customer tickets.", "observed": [], "inferred": [],
                    "evidenceIds": [], "tool": "costliest_bugs"}
        top = bugs[0]
        return {"answer": f"{top['bugId']} puts the most yearly revenue at risk: {tools.inr(top['arr'])} across "
                          f"{top['accounts']} accounts. It is still {top['priority']}.",
                "observed": [f"{b['bugId']} ({b['title']}): {tools.inr(b['arr'])} ARR, {b['accounts']} accounts, "
                             f"{b['tickets']} tickets, {b['priority']}, owner {b['owner'] or '—'}" for b in bugs],
                "inferred": ["Ranked by the ARR of all accounts hit. Each account counts once."],
                "evidenceIds": [b["bugId"] for b in bugs[:3]], "tool": "costliest_bugs", "data": r.data}

    async def _fu_experts(self) -> dict:
        bug = (self.verdict or {}).get("bugId")
        r = await self.run_tool("experts", {"bug_id": bug} if bug else {}, "Finding who can fix it", origin="followup")
        ex = r.data["experts"]
        if not ex:
            return {"answer": "Nobody in the graph is clearly connected to this.", "observed": [], "inferred": [],
                    "evidenceIds": [], "tool": "experts"}
        why = ex[0]["why"]
        return {"answer": f"Ask {ex[0]['name']}. {ex[0]['name'].split()[0]} {why[:1].lower()}{why[1:]}.",
                "observed": [f"{e['name']} ({e['role']}): {e['why']}" + (" · leaving" if e["leaving"] else "") for e in ex],
                "inferred": [], "evidenceIds": [e["id"] for e in ex], "tool": "experts", "data": r.data}

    # ------------------------------------------------------------ actions
    def update_action(self, action_id: str, payload: dict) -> dict:
        a = self.actions[action_id]
        if a["status"] not in ("proposed", "failed", "needs_attention"):
            raise ValueError(f"This action is {a['status']}, so you can no longer edit it")
        a["payload"] = {**a["payload"], **{k: v for k, v in payload.items() if k in a["payload"]}}
        a["edited"] = True
        return a

    async def approve(self, action_ids: list[str], actor: str) -> list[dict]:
        approval_id = f"apr-{uuid.uuid4().hex[:8]}"
        targets = [self.actions[i] for i in action_ids if i in self.actions]
        for a in targets:
            errs = plan.validate_payload(a)
            if errs:
                a.update(status="needs_attention", result={"message": ". ".join(errs) + "."})
                await self.emit("action.failed", {"action": a})
                continue
            if a["status"] not in ("proposed", "failed", "needs_attention"):
                continue
            a.update(status="approved", approvedAt=now(), approvedBy=actor, approvalId=approval_id)
            await self.emit("action.approved", {"action": a})
        await asyncio.gather(*(self._execute(a) for a in targets if a["status"] == "approved"))
        return targets

    async def _execute(self, a: dict) -> None:
        if not a.get("approvalId"):
            raise PermissionError("Refusing to execute an action without an approval id")
        a["status"] = "running"
        await self.emit("action.started", {"action": a})
        try:
            out = await asyncio.to_thread(plan.execute, a)
        except Exception as exc:  # noqa: BLE001
            out = plan.Outcome("failed", f"{type(exc).__name__}: {exc}"[:200])
        a.update(status=out.status, executedAt=now(),
                 result={"message": out.message, "ref": out.ref, "url": out.url, "at": now()})
        await asyncio.to_thread(plan.persist, a)
        await self.emit(f"action.{out.status}", {"action": a})
        if out.status in ("succeeded", "drafted", "simulated"):
            node = {"id": a["id"], "kind": "action", "label": a["title"],
                    "sublabel": {"succeeded": "Done", "drafted": "Draft saved", "simulated": "Simulated, not sent"}[out.status],
                    "status": out.status, "stepId": "actions"}
            self.nodes[node["id"]] = node
            self.evidence[a["id"]] = {"id": a["id"], "kind": "action", "title": a["title"],
                                      "sourceSystem": a["destination"]["system"], "recordId": out.ref or a["id"],
                                      "date": a["executedAt"], "quote": out.message,
                                      "fields": [["Status", out.status], ["Mode", a["destination"]["mode"]],
                                                 ["Approved by", a["approvedBy"]], ["Approved", a["approvedAt"]],
                                                 ["Ran", a["executedAt"]]] + ([["Link", out.url]] if out.url else [])}
            await self.emit("evidence.added", {"stepId": "actions", "items": [self.evidence[a["id"]]]})
            await self.emit("graph.node.added", {"node": node})
            for target in a["addresses"]:
                if target in self.nodes:
                    eid = f"{a['id']}|ADDRESSES|{target}"
                    self.edges[eid] = {"id": eid, "source": a["id"], "target": target, "label": "ADDRESSES"}
                    await self.emit("graph.edge.added", {"edge": self.edges[eid]})


INTENTS = [
    ("blast_radius", r"\b(who else|other accounts?|blast|affected|hit by|impact(ed)? (by|of)|same bug)\b"),
    ("costliest_bugs", r"\b(which bug|most arr|costliest|worst bug|biggest bug|bugs? .*(risk|cost))\b"),
    ("timeline", r"\b(what changed|timeline|last \d+ days|history|when did|chronolog)\b"),
    ("experts", r"\b(who (should|can|knows|owns)|owner|who to ask|fix (it|this))\b"),
]


def route(question: str) -> str:
    q = question.lower()
    for intent, pattern in INTENTS:
        if re.search(pattern, q):
            return intent
    return "open"


INVESTIGATIONS: dict[str, Investigation] = {}


def start(account_id: str, mode: str = "guided", actor: str | None = None) -> Investigation:
    """Start an investigation in the current workspace context (the task inherits the graph via contextvars)."""
    if mode == "gemini" and not settings().llm_enabled:
        mode = "guided"
    inv = Investigation(account_id, mode, actor)
    if mode == "guided":
        inv.mode_detail = "Guided plan: the same fixed steps every time"
    INVESTIGATIONS[inv.id] = inv
    inv.task = asyncio.create_task(inv.run())
    return inv


def get(inv_id: str) -> Investigation:
    inv = INVESTIGATIONS.get(inv_id)
    if not inv or inv.graph != db.current_graph_name():
        raise KeyError(inv_id)
    return inv


def latest_for(account_id: str) -> Investigation | None:
    found = [i for i in INVESTIGATIONS.values() if i.account_id == account_id and i.graph == db.current_graph_name()]
    return found[-1] if found else None


def find_action(action_id: str) -> tuple[Investigation, dict]:
    for inv in INVESTIGATIONS.values():
        if action_id in inv.actions and inv.graph == db.current_graph_name():
            return inv, inv.actions[action_id]
    raise KeyError(action_id)


def reset(graph: str | None = None) -> None:
    """Drop in-memory investigations (all, or one graph's)."""
    for inv_id, inv in list(INVESTIGATIONS.items()):
        if graph is not None and inv.graph != graph:
            continue
        if inv.task and not inv.task.done():
            inv.task.cancel()
        del INVESTIGATIONS[inv_id]


def radar(limit: int = 200) -> dict:
    """Portfolio view for the Risk Radar: CRM health vs Relay risk, silent risks first."""
    rows = db.rows("""
MATCH (a:Account) WHERE a.detectiveRisk IS NOT NULL
OPTIONAL MATCH (csm:Person)-[:MANAGES {role: 'cs_owner'}]->(a)
OPTIONAL MATCH (a)<-[:WITH]-(m:Meeting {status: 'scheduled'})
RETURN a.id AS id, a.name AS name, a.arr AS arr, a.plan AS plan, a.renewalDate AS renewalDate,
       a.crmHealthScore AS crm, a.detectiveRisk AS risk, a.previousRisk AS previousRisk, a.riskHint AS hint,
       a.silentRisk AS silent, a.riskBand AS band, a.industry AS industry, a.planted AS planted,
       a.renewalStage AS stage, csm.name AS csm, csm.id AS csmId, min(m.date) AS nextMeeting
ORDER BY risk DESC LIMIT $limit""", {"limit": limit}, readonly=True)
    today = risk.as_of()
    from datetime import date
    for r in rows:
        r["renewalInDays"] = (date.fromisoformat(r["renewalDate"]) - date.fromisoformat(today)).days
        r["arrLabel"] = tools.inr(r["arr"])
    silent = [r for r in rows if r["silent"]]
    return {"asOf": today, "accounts": rows,
            "silent": {"count": len(silent), "arr": sum(r["arr"] for r in silent), "arrLabel": tools.inr(sum(r["arr"] for r in silent))},
            "note": "Risk is a score built from factors you can see. It is not a measured probability."}
