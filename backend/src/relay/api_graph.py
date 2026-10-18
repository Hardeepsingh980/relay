"""Knowledge graph explorer: the workspace graph as nodes and edges for the WebGL view.

Mounted by relay.api. Every route runs inside the signed-in session's workspace graph.
Cypher picks the nodes, computes their degree and the per-account aggregates, and
filters the relationships; Python only stitches the rows into one compact payload.
"""

from __future__ import annotations

import gzip
import json
import re
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from . import db

router = APIRouter(prefix="/api/graph")

# FalkorDB caps a result set (RESULTSET_SIZE), so relationship reads are paged below it.
PAGE = 10_000
MESSAGE_CAP = 3000
TEXT_CAP = 400
NEIGHBOUR_CAP = 60

# Bulk time series: summarised on their Account, never drawn.
SKIP = ("UsageWeek", "Invoice")

# A readable name for any node, whatever its label.
NAME = """left(CASE
  WHEN {v}:Ticket THEN {v}.id + coalesce(' · ' + {v}.title, '')
  WHEN {v}:Risk THEN coalesce({v}.label, {v}.kind, 'Risk') + coalesce(': ' + {v}.detail, '')
  WHEN {v}:Signal THEN coalesce({v}.type, 'Signal') + coalesce(': ' + {v}.phrase, '')
  WHEN {v}:Commit THEN coalesce({v}.message, {v}.id)
  WHEN {v}:Message THEN coalesce({v}.text, {v}.id)
  WHEN {v}:Episode THEN coalesce({v}.outcome, {v}.kind, {v}.id)
  WHEN {v}:Promise THEN coalesce({v}.text, {v}.id)
  ELSE coalesce({v}.name, {v}.title, {v}.summary, {v}.label, {v}.text, {v}.id)
END, 90)"""

# Connections that matter for sizing: everything except the usage and invoice time series.
DEGREE = "indegree(n) + outdegree(n) - indegree(n, 'OF_ACCOUNT', 'OF_FEATURE', 'BILLED_TO')"

# type -> (namespace label, colour, display label, legend group)
TYPES: dict[str, tuple[str, str, str, str]] = {
    "Person": ("Person", "#7ee8ff", "People", "people"),
    "Team": ("Team", "#b9a7ff", "Teams", "people"),
    "System": ("System", "#8b7bff", "Systems", "product"),
    "Feature": ("Feature", "#4ade9b", "Features", "product"),
    "RoadmapItem": ("RoadmapItem", "#b4e86a", "Roadmap items", "product"),
    "Bug": ("Ticket", "#ff6b81", "Bugs", "product"),
    "Account": ("Account", "#ffb547", "Accounts", "customers"),
    "Contact": ("Contact", "#ffd08a", "Contacts", "customers"),
    "Promise": ("Promise", "#ffe066", "Promises", "customers"),
    "Risk": ("Risk", "#ff8a5c", "Risks", "customers"),
    "Ticket": ("Ticket", "#e8879c", "Support tickets", "customers"),
    "Conversation": ("Conversation", "#d9a77a", "Conversations", "customers"),
    "Signal": ("Signal", "#f08bd0", "Signals", "customers"),
    "Decision": ("Decision", "#e98bff", "Decisions", "knowledge"),
    "Workaround": ("Workaround", "#ff9de2", "Workarounds", "knowledge"),
    "Playbook": ("Playbook", "#3fe0c5", "Playbooks", "knowledge"),
    "Episode": ("Episode", "#5fd4d0", "Past saves", "knowledge"),
    "Knowledge": ("Knowledge", "#c9a3ff", "Knowledge", "knowledge"),
    "Doc": ("Doc", "#7fb2ff", "Docs", "knowledge"),
    "Meeting": ("Meeting", "#5a9cff", "Meetings", "knowledge"),
    "Channel": ("Channel", "#46c3f0", "Slack channels", "knowledge"),
    "Message": ("Message", "#4f6b8f", "Slack messages", "activity"),
    "Task": ("Ticket", "#9b8fb8", "Jira tasks", "activity"),
    "PullRequest": ("PullRequest", "#8796b0", "Pull requests", "activity"),
    "Commit": ("Commit", "#5d6b82", "Commits", "activity"),
    "Bot": ("Bot", "#8a93a6", "Bots", "activity"),
}

SUPPORT = "n.source = 'support'"
LINKED_TO_BUG = "(n)-[:SYMPTOM_OF]->(:Bug)"

# (type, MATCH ... WHERE ..., extra map or None, layer, ORDER BY/LIMIT tail)
SPECS: list[tuple[str, str, str | None, str, str]] = [
    ("Person", "MATCH (n:Person)", "{role: n.role, team: n.team, status: n.status}", "knowledge", ""),
    ("Team", "MATCH (n:Team)", None, "knowledge", ""),
    ("System", "MATCH (n:System)", "{criticality: n.criticality, team: n.team}", "knowledge", ""),
    ("Account", "MATCH (n:Account)",
     ("{arr: n.arr, plan: coalesce(n.plan, n.tier), health: n.crmHealthScore, risk: n.detectiveRisk,"
      " renewal: n.renewalDate, usageWeeks: size([(n)<-[:OF_ACCOUNT]-(:UsageWeek) | 1]),"
      " invoices: size([(n)<-[:BILLED_TO]-(:Invoice) | 1]),"
      " unpaid: size([(n)<-[:BILLED_TO]-(i:Invoice) WHERE i.status <> 'paid' | 1])}"), "knowledge", ""),
    ("Contact", "MATCH (n:Contact)", "{title: n.title, org: n.org, champion: n.isChampion, active: n.active}",
     "knowledge", ""),
    ("Feature", "MATCH (n:Feature)", None, "knowledge", ""),
    ("Bug", "MATCH (n:Bug)", "{status: n.status, priority: n.priority}", "knowledge", ""),
    ("RoadmapItem", "MATCH (n:RoadmapItem)", "{status: n.status, eta: n.etaLabel}", "knowledge", ""),
    ("Promise", "MATCH (n:Promise)", "{status: n.status, due: n.due}", "knowledge", ""),
    ("Playbook", "MATCH (n:Playbook)", None, "knowledge", ""),
    ("Decision", "MATCH (n:Decision)", "{decidedAt: n.decidedAt}", "knowledge", ""),
    ("Workaround", "MATCH (n:Workaround)", "{status: n.status}", "knowledge", ""),
    ("Doc", "MATCH (n:Doc)", "{freshness: n.freshness, kind: n.kind}", "knowledge", ""),
    ("Meeting", "MATCH (n:Meeting)", "{date: n.date, kind: n.kind}", "knowledge", ""),
    ("Channel", "MATCH (n:Channel)", None, "knowledge", ""),
    ("Risk", "MATCH (n:Risk)", "{kind: n.kind, points: n.points}", "knowledge", ""),
    ("Knowledge", "MATCH (n:Knowledge)", None, "knowledge", ""),
    ("Episode", "MATCH (n:Episode)", None, "knowledge", ""),
    # Support tickets that are symptoms of a known bug belong to the knowledge layer.
    ("Ticket", f"MATCH (n:Ticket) WHERE NOT n:Bug AND {SUPPORT} AND {LINKED_TO_BUG}",
     "{status: n.status}", "knowledge", ""),
    # Everything else is activity: the full layer.
    ("Ticket", f"MATCH (n:Ticket) WHERE NOT n:Bug AND {SUPPORT} AND NOT {LINKED_TO_BUG}",
     "{status: n.status}", "full", ""),
    ("Task", f"MATCH (n:Ticket) WHERE NOT n:Bug AND NOT coalesce({SUPPORT}, false)", "{status: n.status}", "full", ""),
    ("Conversation", "MATCH (n:Conversation)", None, "full", ""),
    ("Signal", "MATCH (n:Signal)", None, "full", ""),
    ("PullRequest", "MATCH (n:PullRequest)", None, "full", ""),
    ("Commit", "MATCH (n:Commit)", None, "full", ""),
    ("Message", "MATCH (n:Message)", None, "full", f"ORDER BY n.t DESC LIMIT {MESSAGE_CAP}"),
    ("Bot", "MATCH (n:Bot)", None, "full", ""),
]

LABELS = sorted({ns for ns, *_ in TYPES.values()})
SECRET = re.compile(r"secret|token|passw|credential|api_?key|private_?key|cookie|authorization|salt|hash|embedding|vector",
                    re.IGNORECASE)
HIDDEN = {"planted", "riskHint", "obsoleteHint", "t"}


def _ns(labels: list[str]) -> str:
    """The namespace label for a node: the first label the explorer knows, else its first label."""
    for label in labels:
        if label in LABELS and label != "Bug":
            return label
    return labels[0] if labels else "Node"


def _type(labels: list[str], source: Any) -> str:
    if "Ticket" in labels:
        return "Bug" if "Bug" in labels else "Ticket" if source == "support" else "Task"
    return next((label for label in labels if label in TYPES), labels[0] if labels else "Node")


def _node_id(label: str, key: Any, internal: int) -> str:
    return f"{label}:{key}" if key is not None else f"{label}:#{internal}"


def overview_data(layer: str = "knowledge") -> dict:
    """Nodes, relationships, stats and the type legend for one layer of the current graph."""
    full = layer == "full"
    t0 = time.perf_counter()
    db_ms = 0.0

    def q(cypher: str, params: dict | None = None) -> list[dict]:
        nonlocal db_ms
        res = db.timed(cypher, params, readonly=True, timeout=15000)
        db_ms += res.ms
        return res.rows

    totals = q("MATCH (n) RETURN count(n) AS n")[0]["n"], q("MATCH ()-[r]->() RETURN count(r) AS n")[0]["n"]

    nodes: list[dict] = []
    by_internal: dict[int, str] = {}
    counts: dict[str, int] = {}
    for typ, match, extra, spec_layer, tail in SPECS:
        if spec_layer == "full" and not full:
            continue
        label = TYPES[typ][0]
        rows = q(f"""{match}
                     RETURN ID(n) AS i, n.id AS k, {NAME.format(v='n')} AS name, {DEGREE} AS d,
                            {extra or 'null'} AS x {tail}""")
        for r in rows:
            if r["i"] in by_internal:  # a node matched by two specs keeps its first type
                continue
            nid = _node_id(label, r["k"], r["i"])
            by_internal[r["i"]] = nid
            x = {k: v for k, v in (r["x"] or {}).items() if v is not None} or None
            nodes.append({"id": nid, "type": typ, "name": r["name"] or nid.split(":", 1)[1],
                          "degree": max(int(r["d"] or 0), 0), "extra": x})
            counts[typ] = counts.get(typ, 0) + 1

    # Relationships among the chosen nodes, read per source label and paged below RESULTSET_SIZE.
    wanted = sorted({TYPES[t][0] for t in counts} | ({"Bug"} if "Bug" in counts else set()))
    target = "NOT b:UsageWeek AND NOT b:Invoice" if full else "any(l IN labels(b) WHERE l IN $labels)"
    edges: list[dict] = []
    for label in sorted({TYPES[t][0] for t in counts}):
        skip = 0
        while True:
            rows = q(f"""MATCH (a:{label})-[r]->(b) WHERE {target}
                         RETURN ID(a) AS a, type(r) AS t, ID(b) AS b SKIP $skip LIMIT $page""",
                     {"labels": wanted, "skip": skip, "page": PAGE})
            for r in rows:
                s, t = by_internal.get(r["a"]), by_internal.get(r["b"])
                if s and t:
                    edges.append({"s": s, "t": t, "type": r["t"]})
            if len(rows) < PAGE:
                break
            skip += PAGE

    order = list(TYPES)
    types = [{"type": t, "label": TYPES[t][2], "group": TYPES[t][3], "color": TYPES[t][1], "count": counts[t]}
             for t in order if counts.get(t)]
    return {
        "layer": "full" if full else "knowledge",
        "graph": db.current_graph_name(),
        "nodes": nodes,
        "edges": edges,
        "types": types,
        "stats": {"totalNodes": totals[0], "totalRelationships": totals[1], "shownNodes": len(nodes),
                  "shownEdges": len(edges), "ms": round((time.perf_counter() - t0) * 1000),
                  "dbMs": round(db_ms)},
    }


@router.get("/overview")
def overview(request: Request, layer: str = Query("knowledge", pattern="^(knowledge|full)$")) -> Response:
    body = json.dumps(overview_data(layer), separators=(",", ":"), default=str).encode()
    headers = {"Cache-Control": "no-store", "Vary": "Accept-Encoding"}
    if "gzip" in request.headers.get("accept-encoding", "") and len(body) > 1024:
        body = gzip.compress(body, compresslevel=5)
        headers["Content-Encoding"] = "gzip"
    return Response(body, media_type="application/json", headers=headers)


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        return value if len(value) <= TEXT_CAP else value[:TEXT_CAP].rstrip() + "…"
    if isinstance(value, list):
        if len(value) > 32 and all(isinstance(v, (int, float)) for v in value):
            return None  # an embedding, not a property worth reading
        return _clean(json.dumps(value, default=str)) if any(isinstance(v, (dict, list)) for v in value) else \
            [_clean(v) for v in value[:20]]
    if isinstance(value, dict):
        return _clean(json.dumps(value, default=str))
    return value


def _props(props: dict) -> dict:
    out = {}
    for k, v in props.items():
        if k in HIDDEN or SECRET.search(k):
            continue
        v = _clean(v)
        if v is not None and v != "":
            out[k] = v
    return out


def node_data(nid: str) -> dict | None:
    label, _, key = nid.partition(":")
    if label not in LABELS or not key:
        return None
    if key.startswith("#") and key[1:].isdigit():
        where, params = "ID(n) = $key", {"key": int(key[1:])}
    else:
        where, params = "n.id = $key", {"key": key}
    found = db.timed(f"""MATCH (n:{label}) WHERE {where}
                         RETURN n, ID(n) AS i, {NAME.format(v='n')} AS name, {DEGREE} AS d""", params, timeout=10000)
    if not found.rows:
        return None
    row = found.rows[0]
    raw = dict(row["n"])
    labels = raw.pop("_labels", [label])
    typ = _type(labels, raw.get("source"))

    ms = found.ms
    groups: list[dict] = []
    for direction, pattern in (("out", "(n)-[r]->(m)"), ("in", "(n)<-[r]-(m)")):
        res = db.timed(f"""MATCH {pattern} WHERE ID(n) = $i AND NOT m:UsageWeek AND NOT m:Invoice
                           WITH type(r) AS rel, m ORDER BY m.t DESC
                           WITH rel, count(m) AS total, collect(m)[..{NEIGHBOUR_CAP}] AS ms
                           UNWIND ms AS m
                           RETURN rel, total, labels(m) AS labels, m.id AS k, ID(m) AS mi, m.source AS source,
                                  {NAME.format(v='m')} AS name""", {"i": row["i"]}, timeout=10000)
        ms += res.ms
        by_rel: dict[str, dict] = {}
        for r in res.rows:
            g = by_rel.setdefault(r["rel"], {"rel": r["rel"], "dir": direction, "total": r["total"], "items": []})
            g["items"].append({"id": _node_id(_ns(r["labels"]), r["k"], r["mi"]),
                               "type": _type(r["labels"], r["source"]), "name": r["name"] or r["k"]})
        groups.extend(by_rel.values())
    # Meaning first (what someone knows, decided, owns, works on), raw activity (commits, messages) last.
    rank = {r: i for i, r in enumerate(("KNOWS", "DECIDED", "OWNS", "TECH_CONTACT_FOR", "MANAGES", "CONTACT_FOR",
                                         "SYMPTOM_OF", "AFFECTS", "DEPENDS_ON", "PRODUCED", "ON", "CAUSED_BY",
                                         "WORKS_AT", "MEMBER_OF", "REPORTS_TO", "ABOUT", "SOURCED_FROM", "USES",
                                         "RAISED", "CONCERNS", "ATTENDED", "HOSTS", "INVITED_TO"))}
    groups.sort(key=lambda g: (rank.get(g["rel"], len(rank)), -g["total"], g["rel"]))

    agg = {}
    if "Account" in labels:
        agg = db.rows("""MATCH (n:Account) WHERE ID(n) = $i
                         RETURN size([(n)<-[:OF_ACCOUNT]-(:UsageWeek) | 1]) AS usageWeeks,
                                size([(n)<-[:BILLED_TO]-(:Invoice) | 1]) AS invoices,
                                size([(n)<-[:BILLED_TO]-(i:Invoice) WHERE i.status <> 'paid' | 1]) AS unpaidInvoices""",
                      {"i": row["i"]}, readonly=True)[0]
    return {"id": _node_id(label, raw.get("id"), row["i"]), "type": typ, "labels": labels,
            "name": row["name"] or key, "degree": max(int(row["d"] or 0), 0),
            "props": _props(raw), "aggregates": agg, "neighbours": groups, "ms": round(ms, 1)}


@router.get("/node/{nid:path}")
def node(nid: str) -> dict:
    out = node_data(nid)
    if out is None:
        raise HTTPException(404, "No such node in this workspace graph")
    return out
