"""MCP server exposing Relay's agent tools to any MCP client (Claude Desktop, Gemini CLI, ...).

    uv run relay --tenant cheerio mcp                     # stdio
    uv run python -m relay.health.mcp_server --http       # streamable HTTP on :8721 (/mcp)

Every agent's tools read the same company graph:
  Detective (Account Health)   risk_radar, account_overview, causal_chain, blast_radius, ...
  Handover (Knowledge)         unique_knowledge, who_knows
  Sales Assist                 meeting_brief, roadmap_status, experts
  Ask                          ask
Actions are two-step: `investigate` proposes a save plan; `approve_action` executes ONE
proposed action, and the MCP host asks the human before calling it.
"""

from __future__ import annotations

import argparse
import json

from mcp.server.mcpserver import MCPServer

from .. import db
from . import investigator, tools

server = MCPServer(
    name="relay",
    title="Relay",
    description="Company brain over one FalkorDB graph per company: account health, knowledge continuity, sales assist.",
    instructions=(
        "Use risk_radar to find silent-risk accounts, investigate for a full evidence-grounded investigation, and the "
        "graph tools (causal_chain, blast_radius, promises, experts, ...) for follow-ups. unique_knowledge shows what "
        "only one person knows. Only call approve_action after the user explicitly approved that specific action."
    ),
    version="0.2.0",
)


def _out(r: tools.ToolResult) -> dict:
    """Summary, structured data, the Cypher that produced it, and the case-graph delta."""
    return json.loads(json.dumps({
        "summary": r.summary, "data": r.data, "queries": r.trace(),
        "graph": {"nodes": r.nodes, "edges": r.edges}, "evidence": r.evidence,
    }, default=str))


def _ctx() -> tools.Ctx:
    return tools.default_ctx()


@server.tool(description="Accounts ranked by graph-derived risk, flagging 'silent risk' (CRM healthy, graph risky).")
def risk_radar(limit: int = 10) -> dict:
    return investigator.radar(limit)


@server.tool(description="ARR, plan, renewal, CRM health, CSM, AE and features for an account.")
def account_overview(account_id: str) -> dict:
    return _out(tools.account_overview(_ctx(), account_id))


@server.tool(description="Contacts who left or joined recently and who succeeded whom (WORKS_AT / SUCCEEDED).")
def champion_changes(account_id: str) -> dict:
    return _out(tools.champion_changes(_ctx(), account_id))


@server.tool(description="Recent support tickets grouped by the Jira bug they are a SYMPTOM_OF, with link confidence.")
def ticket_root_causes(account_id: str) -> dict:
    return _out(tools.ticket_root_causes(_ctx(), account_id))


@server.tool(description="Active users and per-feature usage, last 4 weeks vs an 8-week baseline.")
def usage_trend(account_id: str, feature_id: str | None = None) -> dict:
    return _out(tools.usage_trend(_ctx(), account_id, feature_id))


@server.tool(description="Competitor, frustration, budget and positive signals from conversations, with exact quotes.")
def signals(account_id: str) -> dict:
    return _out(tools.signals(_ctx(), account_id))


@server.tool(description="Recent invoices, payment delays and wallet balance.")
def billing_events(account_id: str) -> dict:
    return _out(tools.billing_events(_ctx(), account_id))


@server.tool(description="The transparent demo risk score and each graph-derived factor behind it.")
def risk_breakdown(account_id: str) -> dict:
    return _out(tools.risk_breakdown(_ctx(), account_id))


@server.tool(description="Multi-hop causal chain: contact -> tickets -> shared open bug -> affected feature, plus the "
                         "former champion and risk signals. Ranked candidates with the ranking formula.")
def causal_chain(account_id: str) -> dict:
    return _out(tools.causal_chain(_ctx(), account_id))


@server.tool(description="Every account hit by a bug (bug <- tickets -> accounts) with deduplicated ARR.")
def blast_radius(bug_id: str, exclude_account_id: str | None = None) -> dict:
    return _out(tools.blast_radius(_ctx(), bug_id, exclude_account_id))


@server.tool(description="Open bugs ranked by affected ARR across the portfolio.")
def costliest_bugs(limit: int = 5) -> dict:
    return _out(tools.costliest_bugs(_ctx(), limit))


@server.tool(description="Chronological events (departures, tickets, bugs, conversations, meetings, invoices, usage).")
def timeline(account_id: str, days: int = 90) -> dict:
    return _out(tools.timeline(_ctx(), account_id, days))


@server.tool(description="Promises made to an account, what each depends on, and which are at risk.")
def promises(account_id: str) -> dict:
    return _out(tools.promises(_ctx(), account_id))


@server.tool(description="Cheerio people an account depends on (CSM, AE, technical contact) and whether any are leaving.")
def internal_owners(account_id: str) -> dict:
    return _out(tools.internal_owners(_ctx(), account_id))


@server.tool(description="Roadmap items by keyword or feature, with ETA changes and internal guidance.")
def roadmap_status(query: str | None = None, feature_id: str | None = None) -> dict:
    return _out(tools.roadmap_status(_ctx(), query, feature_id))


@server.tool(description="Who to ask about a bug, feature or system: owners and the strongest KNOWS edges. "
                         "Pass from_person_id to get the shortest working path (shared tickets, team, manager) to each.")
def experts(bug_id: str | None = None, feature_id: str | None = None, system_id: str | None = None,
            from_person_id: str | None = None) -> dict:
    return _out(tools.experts(_ctx(), feature_id, bug_id, system_id, from_person_id))


@server.tool(description="Past investigations, calls and handovers for an account (episodic memory).")
def memory(account_id: str) -> dict:
    return _out(tools.memory(_ctx(), account_id))


@server.tool(description="What only this person knows (systems, accounts, decisions, workarounds nobody else covers).")
def unique_knowledge(person_id: str) -> dict:
    from .. import analysis
    return {"personId": person_id, "items": analysis.unique_knowledge(person_id)}


@server.tool(description="People who know a system or account, strongest first, with the evidence counts behind each.")
def who_knows(entity_id: str) -> dict:
    rows = db.rows("""MATCH (p:Person)-[k:KNOWS]->(x {id: $id})
                      RETURN p.id AS id, p.name AS name, p.role AS role, k.score AS score, k.commits AS commits,
                             k.answers AS answers, k.docs AS docs, k.tickets AS tickets, p.leaving AS leaving
                      ORDER BY k.score DESC LIMIT 8""", {"id": entity_id}, readonly=True)
    return {"entityId": entity_id, "people": rows}


@server.tool(description="Pre-call brief for a scheduled customer meeting: attendees, history, health, promises, goals, "
                         "questions to ask and internal experts.")
def meeting_brief(meeting_id: str) -> dict:
    from ..sales import brief
    return brief.build(meeting_id)


@server.tool(description="Ask the company brain a question. Returns a short sourced answer with the path it took.")
def ask(question: str) -> dict:
    from .. import ask as ask_mod
    return ask_mod.ask(question, None)


@server.tool(description="Run a full guided investigation. Returns the verdict and the proposed save-plan actions "
                         "(nothing is executed).")
async def investigate(account_id: str) -> dict:
    inv = investigator.start(account_id, "guided", actor="mcp")
    await inv.task
    return {"investigationId": inv.id, "verdict": inv.verdict,
            "proposedActions": [{k: a[k] for k in ("id", "type", "title", "summary", "destination", "payload")}
                                for a in inv.actions.values()]}


@server.tool(description="Execute ONE previously proposed action. Only call after the user explicitly approved it. "
                         "Unconnected integrations run in clearly labelled simulated mode.")
async def approve_action(action_id: str, approver: str) -> dict:
    inv, _ = investigator.find_action(action_id)
    done = await inv.approve([action_id], f"{approver} (via MCP)")
    a = done[0]
    return {"id": a["id"], "status": a["status"], "result": a["result"]}


# Graph tools a planner may call over MCP. Full investigations and actions are deliberately excluded.
PLANNER_TOOLS = ["account_overview", "champion_changes", "ticket_root_causes", "usage_trend", "signals",
                 "billing_events", "risk_breakdown", "causal_chain", "blast_radius", "costliest_bugs", "timeline",
                 "promises", "internal_owners", "roadmap_status", "experts", "memory"]


def main(tenant: str | None = None, http: bool = False, port: int = 8721) -> None:
    from .. import tenants
    from ..ingest.pipeline import demo_graph
    db.use_graph(demo_graph(tenants.get(tenant)))
    if http:
        server.run("streamable-http", host="127.0.0.1", port=port)
    else:
        server.run("stdio")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--http", action="store_true", help="Serve streamable HTTP instead of stdio")
    ap.add_argument("--port", type=int, default=8721)
    ap.add_argument("--tenant", default=None)
    a = ap.parse_args()
    main(a.tenant, a.http, a.port)
