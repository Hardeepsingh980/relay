"""Gemini planner over MCP.

Gemini discovers the graph tools from the Relay MCP server (list_tools), decides which to
call (function calling), and every call is executed through MCP (call_tool). The MCP result carries
the case-graph delta, which the investigator streams to the UI. Gemini never sees secrets and never
executes actions: approve_action and investigate are not offered to it.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from google import genai
from google.genai import types
from mcp import Client

from .. import db
from ..config import settings
from . import tools
from .mcp_server import PLANNER_TOOLS
from .mcp_server import server as mcp_server

if TYPE_CHECKING:
    from .investigator import Investigation

MAX_TURNS = 8

SYSTEM = """You are the Detective agent in Relay, a customer-success investigator working over a FalkorDB graph of
Cheerio, a WhatsApp marketing platform (people and customers are fictional). Investigate why an account may churn
by calling the graph tools.
Rules:
- Start with account_overview, then gather evidence from contacts, tickets, usage, conversation signals, promises,
  internal owners and billing.
- Always call causal_chain before you finish; it performs the multi-hop traversal that connects the evidence.
- Call tools in parallel when they are independent.
- Never invent facts. Only use what tools return. When you have enough evidence, reply with a one-line summary."""


def _client() -> genai.Client:
    return genai.Client(api_key=settings().gemini_api_key)


def _compact(data: dict, limit: int = 6000) -> dict:
    """Trim tool data for the model: drop weekly series and weights, cap list lengths."""
    def strip(v):
        if isinstance(v, dict):
            return {k: strip(x) for k, x in v.items() if k not in ("series", "weights")}
        if isinstance(v, list):
            return [strip(x) for x in v[:25]]
        return v
    text = json.dumps(strip(data), default=str)
    if len(text) > limit:
        return {"truncated": True, "json": text[:limit]}
    return json.loads(text)


def result_from_mcp(name: str, payload: dict) -> tools.ToolResult:
    """Rebuild a ToolResult (graph delta + evidence + Cypher trace) from an MCP tool response."""
    r = tools.ToolResult(name, payload.get("summary", ""), payload.get("data", {}))
    r.nodes = payload.get("graph", {}).get("nodes", [])
    r.edges = payload.get("graph", {}).get("edges", [])
    r.evidence = payload.get("evidence", [])
    r.queries = [db.QueryResult(cypher=q["cypher"], params=q.get("params", {}), rows=[{}] * q.get("rows", 0),
                                ms=q.get("ms", 0.0), graph=q.get("graph", "")) for q in payload.get("queries", [])]
    return r


def mcp_executor(client: Client):
    async def run(name: str, args: dict) -> tools.ToolResult:
        res = await client.call_tool(name, args)
        if res.is_error:
            raise RuntimeError(res.content[0].text if res.content else f"MCP tool {name} failed")
        return result_from_mcp(name, json.loads(res.content[0].text))
    return run


async def _tool_loop(inv: "Investigation", prompt: str, origin: str) -> str:
    final = ""
    async with Client(mcp_server) as mcp:
        listed = await mcp.list_tools()
        offered = [t for t in listed.tools if t.name in PLANNER_TOOLS]
        decls = [types.FunctionDeclaration(name=t.name, description=t.description or "",
                                           parameters_json_schema=t.input_schema) for t in offered]
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM, temperature=0.1,
            tools=[types.Tool(function_declarations=decls)],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        run = mcp_executor(mcp)
        client = _client()
        contents: list[types.Content] = [types.Content(role="user", parts=[types.Part(text=prompt)])]
        for _ in range(MAX_TURNS):
            resp = await client.aio.models.generate_content(model=settings().llm_model, contents=contents,
                                                            config=config)
            calls = resp.function_calls or []
            if not calls:
                final = (resp.text or "").strip()
                break
            contents.append(resp.candidates[0].content)
            parts = []
            for call in calls:
                args = dict(call.args or {})
                if call.name not in PLANNER_TOOLS:
                    parts.append(types.Part.from_function_response(name=call.name, response={"error": "not allowed"}))
                    continue
                result = await inv.run_tool(call.name, args, f"Gemini → {call.name}", origin=origin, executor=run)
                payload = {"summary": result.summary, "data": _compact(result.data)} if result else {"error": "tool failed"}
                parts.append(types.Part.from_function_response(name=call.name, response=payload))
            contents.append(types.Content(role="user", parts=parts))
    return final


async def plan(inv: "Investigation") -> None:
    await _tool_loop(inv, f"Investigate churn risk for account_id={inv.account_id}. Use the tools; finish with "
                          f"causal_chain.", "planner")


NARRATIVE_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "story": {"type": "array", "items": {"type": "object", "properties": {
            "text": {"type": "string"}, "evidenceIds": {"type": "array", "items": {"type": "string"}}},
            "required": ["text", "evidenceIds"]}},
    },
    "required": ["headline", "story"],
}


async def narrate(inv: "Investigation", verdict: dict) -> dict | None:
    """Ask Gemini to phrase the verdict. Every sentence must cite evidence ids we hold; otherwise rejected."""
    client = _client()
    facts = {"chain": verdict["chain"], "supporting": verdict["supporting"], "counterEvidence": verdict["counterEvidence"],
             "risk": verdict["risk"], "renewalInDays": verdict["renewalInDays"], "account": verdict["accountName"]}
    prompt = ("Write a verdict for a Head of Customer Success.\n"
              "- headline: one sentence under 22 words in the form '<Account short name> is at risk because ...' "
              "(or '... looks lower-risk than the CRM suggests because ...' when risk is below 25).\n"
              "- story: exactly three short sentences: what changed with people, what broke, and the commercial "
              "consequence.\n"
              "Calm, specific language: state numbers, never dramatise (no 'abandonment', 'collapse', 'crisis'). "
              "Don't claim causation stronger than the evidence; use 'likely' for inferred links such as "
              "ticket-to-bug triage. Cite evidenceIds from the facts for every sentence. Use only these facts:\n"
              + json.dumps(facts, default=str))
    resp = await client.aio.models.generate_content(
        model=settings().llm_model, contents=prompt,
        config=types.GenerateContentConfig(temperature=0.2, response_mime_type="application/json",
                                           response_json_schema=NARRATIVE_SCHEMA))
    out = json.loads(resp.text)
    story = out.get("story") or []
    if len(story) < 2 or any(not s.get("evidenceIds") or any(e not in inv.evidence for e in s["evidenceIds"]) for s in story):
        return None  # unsupported claims: keep the template
    return {"headline": out["headline"], "story": [s["text"] for s in story],
            "storyEvidence": [s["evidenceIds"] for s in story], "narrativeSource": f"gemini ({settings().llm_model})"}


async def answer(inv: "Investigation", question: str) -> dict:
    summary = await _tool_loop(
        inv, f"Account under investigation: {inv.account_id}. Question: {question}\n"
             "Answer in two or three sentences using only tool results; say what is observed vs inferred.",
        "followup")
    return {"answer": summary or "Gemini did not return an answer.", "observed": [], "inferred": [],
            "evidenceIds": [], "tool": "gemini via MCP"}
