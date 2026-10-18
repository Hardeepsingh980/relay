"""Graph tools the Detective (and MCP clients) can call.

Each tool runs Cypher against the tenant's FalkorDB graph and returns a ToolResult with:
  * data         structured output for the agent / verdict,
  * nodes/edges  the case-graph delta the UI animates in,
  * evidence     the exact source records behind each node (evidence drawer),
  * queries      the Cypher + params + latency (Show Cypher).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable

from .. import db
from . import risk
from .model import CURRENT_WEEKS, MIN_LINK_CONFIDENCE, MIN_SIGNAL_CONFIDENCE, SIGNAL_WINDOW_DAYS, WEIGHTS, RiskInputs, score

SIGNAL_LABELS = {
    "competitor_evaluation": "Competitor mention",
    "frustration": "Frustration",
    "budget_pressure": "Budget worry",
    "price_objection": "Price concern",
    "renewal_positive": "Plans to expand",
    "praise": "Praise",
}
RISK_SIGNAL_TYPES = ["competitor_evaluation", "frustration", "budget_pressure"]


# ---------------------------------------------------------------- result types

@dataclass
class ToolResult:
    tool: str
    summary: str
    data: dict = field(default_factory=dict)
    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    queries: list[db.QueryResult] = field(default_factory=list)

    def node(self, **n) -> None:
        if not any(x["id"] == n["id"] for x in self.nodes):
            self.nodes.append(n)

    def edge(self, src: str, rel: str, dst: str, **props) -> str:
        eid = f"{src}|{rel}|{dst}"
        if not any(e["id"] == eid for e in self.edges):
            self.edges.append({"id": eid, "source": src, "target": dst, "label": rel, **props})
        return eid

    def cite(self, **ev) -> None:
        if not any(x["id"] == ev["id"] for x in self.evidence):
            self.evidence.append(ev)

    def query(self, cypher: str, params: dict | None = None, write: bool = False) -> list[dict]:
        res = db.timed(cypher, params, readonly=not write)
        self.queries.append(res)
        return res.rows

    def trace(self) -> list[dict]:
        return [{"cypher": q.cypher, "params": _jsonable(q.params), "ms": q.ms, "rows": len(q.rows), "graph": q.graph}
                for q in self.queries]


def _jsonable(v: Any) -> Any:
    return json.loads(json.dumps(v, default=str))


@dataclass
class Ctx:
    as_of: str

    @property
    def today(self) -> date:
        return date.fromisoformat(self.as_of)

    def days_ago(self, iso: str | None) -> int | None:
        return (self.today - date.fromisoformat(iso[:10])).days if iso else None

    def days_until(self, iso: str) -> int:
        return (date.fromisoformat(iso[:10]) - self.today).days

    def since(self, days: int) -> str:
        return (self.today - timedelta(days=days)).isoformat()


def default_ctx() -> Ctx:
    return Ctx(risk.as_of())


def inr(n: float | int | None) -> str:
    """Indian-style money: ₹38,400 · ₹9.6L · ₹1.2 Cr."""
    if n is None:
        return "—"
    if n >= 10_000_000:
        return f"₹{n / 10_000_000:.2f}".rstrip("0").rstrip(".") + " Cr"
    if n >= 100_000:
        return f"₹{n / 100_000:.1f}".rstrip("0").rstrip(".") + "L"
    return f"₹{n:,.0f}"


def short_name(name: str) -> str:
    words = name.split()
    trailing = {"Foods", "Home", "Threads", "Wellness", "Clinics", "Living", "Beauty", "Finance", "Organics", "Kitchen",
                "Co.", "Candles", "Bakehouse", "Naturals", "Studio", "Tea"}
    while len(words) > 1 and words[-1] in trailing:
        words.pop()
    return " ".join(words)


# ---------------------------------------------------------------- node + evidence builders

def add_account(r: ToolResult, ctx: Ctx, a: dict, role: str = "subject") -> None:
    days = ctx.days_until(a["renewalDate"]) if a.get("renewalDate") else None
    r.node(id=a["id"], kind="account", label=a["name"],
           sublabel=f"{inr(a.get('arr'))} ARR · renews in {days} days" if days is not None else a.get("tier", ""), role=role)
    r.cite(id=a["id"], kind="account", title=a["name"], sourceSystem="HubSpot (CRM)", recordId=a["id"], date=a.get("renewalDate"),
           fields=[["ARR", inr(a.get("arr"))], ["Plan", a.get("plan", "—")],
                   ["Renewal", f"{a.get('renewalDate')} (in {days} days)" if days is not None else "—"],
                   ["Renewal stage", a.get("renewalStage", "—")],
                   ["CRM health score", f"{a.get('crmHealthScore', '—')} ({a.get('crmHealthSource', 'CRM')})"],
                   ["Relay risk", f"{a.get('detectiveRisk', '—')}%"],
                   ["Wallet balance", inr(a.get("walletBalance"))], ["Industry", a.get("industry", "—")],
                   ["Agent seats", a.get("seats", "—")]])


def add_contact(r: ToolResult, ctx: Ctx, c: dict, account_id: str | None, champion_note: str = "") -> None:
    former = not c.get("active", True)
    sub = c.get("title") or c.get("role", "")
    if former:
        sub = f"Former {c.get('role', 'contact').lower()} · left {ctx.days_ago(c.get('leftAt'))} days ago"
    r.node(id=c["id"], kind="contact", label=c["name"], sublabel=sub, status="former" if former else "active")
    fields = [["Role", c.get("role", "—")], ["Title", c.get("title", "—")],
              ["Status", "Left the company" if former else "Active"],
              ["Main contact", "Yes" if c.get("isChampion") else "No"],
              ["Joined", c.get("joinedAt", "—")], ["Left", c.get("leftAt") or "—"],
              ["Email", f"{c.get('email', '—')} ({c.get('emailStatus', 'ok')})"]]
    quote = f"Email to {c.get('email')} bounced on {c['emailBouncedAt']}." if c.get("emailBouncedAt") else None
    r.cite(id=c["id"], kind="contact", title=c["name"], sourceSystem="HubSpot (CRM)", recordId=c["id"],
           date=c.get("leftAt") or c.get("joinedAt"), quote=quote, fields=fields, note=champion_note or None)
    if account_id:
        r.edge(c["id"], "WORKED_AT" if former else "WORKS_AT", account_id)


def add_person(r: ToolResult, p: dict, note: str | None = None) -> None:
    leaving = bool(p.get("leaving"))
    r.node(id=p["id"], kind="person", label=p["name"], sublabel=p.get("role", ""), status="leaving" if leaving else "active")
    fields = [["Role", p.get("role", "—")], ["Team", p.get("team", "—")]]
    if leaving:
        fields.append(["Last day", p.get("lastDay") or p.get("endDate") or "—"])
    r.cite(id=p["id"], kind="person", title=p["name"], sourceSystem="HR system", recordId=p["id"], fields=fields, note=note)


def add_ticket(r: ToolResult, ctx: Ctx, t: dict) -> None:
    r.node(id=t["id"], kind="ticket", label=f"“{t['title']}”", sublabel=f"{t['id']} · {ctx.days_ago(t['createdAt'])} days ago",
           status=t.get("status"))
    r.cite(id=t["id"], kind="ticket", title=t["title"], sourceSystem="Support desk", recordId=t["id"], date=t["createdAt"][:10],
           quote=t.get("description"), url=t.get("url"),
           fields=[["Status", t.get("status", "—")], ["Priority", t.get("priority", "—")],
                   ["Channel", t.get("channel", "—")], ["Created", t["createdAt"][:16].replace("T", " ")]])


def add_bug(r: ToolResult, ctx: Ctx, b: dict, owner: dict | None = None) -> None:
    age = ctx.days_ago(b["createdAt"])
    r.node(id=b["id"], kind="bug", label=b["id"], sublabel=b["title"], status=b.get("status"))
    fields = [["Title", b["title"]], ["Status", f"{b.get('jiraStatus') or b.get('status')} ({b.get('status')})"],
              ["Priority", b.get("priority", "—")], ["Opened", f"{b['createdAt'][:10]} ({age} days ago)"],
              ["Fixed", (b.get("resolvedAt") or "")[:10] or "Not fixed"]]
    if b.get("workaround"):
        fields.append(["Workaround", b["workaround"]])
    if owner:
        fields.append(["Owner", f"{owner['name']} ({owner.get('team', '')})"])
    r.cite(id=b["id"], kind="bug", title=f"{b['id']}: {b['title']}", sourceSystem="Jira · Cheerio Dev", recordId=b["id"],
           date=b["createdAt"][:10], quote=b.get("description"), fields=fields, url=b.get("url"))


def add_feature(r: ToolResult, f: dict) -> None:
    r.node(id=f["id"], kind="feature", label=f["name"], sublabel="Product feature")
    r.cite(id=f["id"], kind="feature", title=f["name"], sourceSystem="Product catalog", recordId=f["id"],
           fields=[["Feature", f["name"]]])


def add_promise(r: ToolResult, ctx: Ctx, p: dict, at_risk: str | None) -> None:
    status = "at_risk" if at_risk else p.get("status")
    r.node(id=p["id"], kind="promise", label=f"Promise: {p['text']}", sublabel=f"due {p['due']}", status=status)
    r.cite(id=p["id"], kind="promise", title=p["text"], sourceSystem="Meeting notes (found by Relay)", recordId=p["id"],
           date=(p.get("madeAt") or "")[:10], quote=p.get("quote"),
           fields=[["Due", p["due"]], ["Status", "At risk" if at_risk else p.get("status", "open")],
                   ["Why", at_risk or "On track"], ["Found by", p.get("extraction", "seed")]])


def add_roadmap(r: ToolResult, i: dict) -> None:
    r.node(id=i["id"], kind="roadmap", label=i["title"], sublabel=f"{i['status']} · {i.get('etaLabel') or '—'}",
           status=i["status"])
    r.cite(id=i["id"], kind="roadmap", title=i["title"], sourceSystem="Product roadmap", recordId=i["id"],
           date=(i.get("updatedAt") or "")[:10], quote=i.get("internalNote"), url=i.get("url"),
           fields=[["Status", i["status"]], ["Expected", i.get("etaLabel") or "—"],
                   ["Originally", i.get("originalLabel") or "—"], ["Public note", i.get("publicNote") or "—"]])


# ---------------------------------------------------------------- tools

def account_overview(ctx: Ctx, account_id: str) -> ToolResult:
    r = ToolResult("account_overview", "")
    rows = r.query("""
MATCH (a:Account {id: $accountId})
OPTIONAL MATCH (csm:Person)-[:MANAGES {role: 'cs_owner'}]->(a)
OPTIONAL MATCH (ae:Person)-[:MANAGES {role: 'sales_poc'}]->(a)
OPTIONAL MATCH (a)-[:USES]->(f:Feature)
RETURN a, csm, ae, collect(f.name) AS features
""", {"accountId": account_id})
    if not rows:
        raise ValueError(f"Unknown account {account_id}")
    a, csm, ae, features = rows[0]["a"], rows[0]["csm"], rows[0]["ae"], rows[0]["features"]
    add_account(r, ctx, a)
    days = ctx.days_until(a["renewalDate"])
    r.data = {"account": {k: a.get(k) for k in ("id", "name", "arr", "renewalDate", "crmHealthScore", "detectiveRisk",
                                                "industry", "plan", "seats", "renewalStage", "walletBalance", "country")},
              "renewalInDays": days, "csm": csm and {"id": csm["id"], "name": csm["name"]},
              "ae": ae and {"id": ae["id"], "name": ae["name"]}, "features": features}
    r.summary = f"{a['name']}: {inr(a['arr'])} ARR, renews in {days} days, CRM health {a['crmHealthScore']}"
    return r


def champion_changes(ctx: Ctx, account_id: str, window_days: int = 120) -> ToolResult:
    r = ToolResult("champion_changes", "")
    rows = r.query("""
MATCH (c:Contact)-[w:WORKS_AT]->(a:Account {id: $accountId})
WHERE (w.to IS NOT NULL AND w.to >= $since) OR w.from >= $since OR c.isChampion = true
OPTIONAL MATCH (successor:Contact)-[h:SUCCEEDED]->(c)
RETURN c, w.from AS joined, w.to AS left, successor, h.at AS handoverAt
ORDER BY c.isChampion DESC, w.to DESC
""", {"accountId": account_id, "since": ctx.since(window_days)})
    departures, arrivals = [], []
    for row in rows:
        c, succ = row["c"], row["successor"]
        if row["left"]:
            add_contact(r, ctx, c, account_id, champion_note="Former main contact" if c.get("isChampion") else "")
            dep = {"id": c["id"], "name": c["name"], "role": c.get("role"), "champion": bool(c.get("isChampion")),
                   "leftAt": row["left"], "daysAgo": ctx.days_ago(row["left"]), "emailStatus": c.get("emailStatus")}
            if succ:
                add_contact(r, ctx, succ, account_id)
                r.edge(succ["id"], "SUCCEEDED", c["id"], detail=f"took over as {c.get('role', 'admin')} on {row['handoverAt']}")
                dep["successor"] = {"id": succ["id"], "name": succ["name"], "title": succ.get("title")}
            departures.append(dep)
        elif c.get("isChampion"):
            add_contact(r, ctx, c, account_id, champion_note="Current main contact")
        if row["joined"] and row["joined"] >= ctx.since(window_days):
            arrivals.append({"id": c["id"], "name": c["name"], "joinedAt": row["joined"]})
    champs = [d for d in departures if d["champion"]]
    r.data = {"departures": departures, "arrivals": arrivals, "championDeparted": bool(champs)}
    if champs:
        d = champs[0]
        succ = f"{d['successor']['name']} took over." if d.get("successor") else "Nobody is recorded as taking over."
        r.summary = f"Main contact {d['name']} left {d['daysAgo']} days ago. {succ}"
    elif departures:
        n = len(departures)
        r.summary = f"{n} contact{'s' if n != 1 else ''} left. The main contact is still there."
    else:
        r.summary = f"No main contact or admin changes in the last {window_days} days"
    return r


def ticket_root_causes(ctx: Ctx, account_id: str, window_days: int = SIGNAL_WINDOW_DAYS) -> ToolResult:
    r = ToolResult("ticket_root_causes", "")
    rows = r.query("""
MATCH (a:Account {id: $accountId})<-[:CONCERNS]-(t:Ticket {source: 'support'})<-[:RAISED]-(c:Contact)
WHERE t.createdAt >= $since
OPTIONAL MATCH (t)-[s:SYMPTOM_OF]->(b:Bug)
OPTIONAL MATCH (b)-[:AFFECTS]->(f:Feature)
OPTIONAL MATCH (b)-[:OWNED_BY]->(e:Person)
RETURN c, t, s, b, f, e
ORDER BY t.createdAt
""", {"accountId": account_id, "since": ctx.since(window_days)})
    groups: dict[str, dict] = {}
    unlinked = []
    for row in rows:
        c, t, s, b, f, e = (row[k] for k in ("c", "t", "s", "b", "f", "e"))
        if b is None:
            unlinked.append({"id": t["id"], "title": t["title"], "createdAt": t["createdAt"], "status": t.get("status")})
            continue
        g = groups.setdefault(b["id"], {"bug": b, "feature": f, "owner": e, "tickets": [], "reporters": {}})
        g["tickets"].append({"ticket": t, "link": s, "contact": c})
        g["reporters"][c["id"]] = c
    clusters = []
    for bug_id, g in groups.items():
        b = g["bug"]
        confident = [x for x in g["tickets"] if x["link"]["confidence"] >= MIN_LINK_CONFIDENCE]
        is_open = b.get("status") != "Done"
        add_bug(r, ctx, b, g["owner"])
        if g["feature"]:
            add_feature(r, g["feature"])
            r.edge(b["id"], "AFFECTS", g["feature"]["id"])
        if g["owner"]:
            add_person(r, g["owner"], note=f"Owns {bug_id}")
            r.edge(b["id"], "OWNED_BY", g["owner"]["id"])
        for c in g["reporters"].values():
            add_contact(r, ctx, c, account_id)
        for x in g["tickets"]:
            t, link = x["ticket"], x["link"]
            add_ticket(r, ctx, t)
            r.edge(x["contact"]["id"], "RAISED", t["id"])
            r.edge(t["id"], "SYMPTOM_OF", b["id"], confidence=link["confidence"], method=link.get("method"),
                   possible=link["confidence"] < MIN_LINK_CONFIDENCE)
            ev = next(e for e in r.evidence if e["id"] == t["id"])
            ev["relationship"] = (f"Points to {b['id']} · confidence {link['confidence']:.2f} · linked by "
                                  f"{link.get('linkedBy', 'unknown')} ({link.get('method')}) on {link.get('linkedAt', '—')}")
        dates = [x["ticket"]["createdAt"][:10] for x in g["tickets"]]
        span = (date.fromisoformat(max(dates)) - date.fromisoformat(min(dates))).days
        clusters.append({
            "bugId": bug_id, "bugTitle": b["title"], "bugStatus": b.get("status"), "jiraStatus": b.get("jiraStatus"),
            "bugPriority": b.get("priority"), "bugKeyword": b.get("keyword"), "bugAgeDays": ctx.days_ago(b["createdAt"]),
            "bugWorkaround": b.get("workaround"),
            "feature": g["feature"]["name"] if g["feature"] else None,
            "featureId": g["feature"]["id"] if g["feature"] else None,
            "owner": g["owner"]["name"] if g["owner"] else None, "ownerId": g["owner"]["id"] if g["owner"] else None,
            "tickets": [{"id": x["ticket"]["id"], "title": x["ticket"]["title"], "createdAt": x["ticket"]["createdAt"][:10],
                         "status": x["ticket"].get("status"), "confidence": x["link"]["confidence"],
                         "method": x["link"].get("method"), "raisedBy": x["contact"]["name"]} for x in g["tickets"]],
            "confidentLinks": len(confident), "spanDays": span, "open": is_open,
            "distinctWordings": len({x["ticket"]["title"].lower() for x in g["tickets"]}),
            "reporters": [c["name"] for c in g["reporters"].values()],
        })
    clusters.sort(key=lambda c: (not c["open"], -c["confidentLinks"]))
    r.data = {"clusters": clusters, "unlinkedTickets": unlinked, "windowDays": window_days}
    top = clusters[0] if clusters else None
    if top and top["open"] and top["confidentLinks"] >= 2:
        r.summary = (f"{len(top['tickets'])} tickets with different wording point to one bug: {top['bugId']} "
                     f"({top['bugKeyword']}), open {top['bugAgeDays']} days")
    elif top:
        n = len(top["tickets"])
        r.summary = f"{n} recent ticket{'s point' if n != 1 else ' points'} to {top['bugId']} ({top['bugStatus']})"
    else:
        r.summary = f"No tickets point to a bug in the last {window_days} days ({len(unlinked)} how-to tickets)"
    return r


def usage_trend(ctx: Ctx, account_id: str, feature_id: str | None = None) -> ToolResult:
    r = ToolResult("usage_trend", "")
    p = risk.window_params(ctx.as_of, account_id)
    rows = r.query("""
MATCH (a:Account {id: $accountId})<-[:OF_ACCOUNT]-(u:UsageWeek)
OPTIONAL MATCH (u)-[:OF_FEATURE]->(f:Feature)
WITH u, f WHERE $featureId IS NULL OR f IS NULL OR f.id = $featureId
RETURN coalesce(f.id, 'wau') AS metricKey, coalesce(f.name, 'Active users') AS metric,
       collect({week: u.week, i: u.weekIndex, value: u.value}) AS series,
       avg(CASE WHEN u.weekIndex >= $baseFrom AND u.weekIndex <= $baseTo THEN u.value END) AS baseline,
       avg(CASE WHEN u.weekIndex >= $curFrom THEN u.value END) AS current
""", {**{k: p[k] for k in ("accountId", "baseFrom", "baseTo", "curFrom")}, "featureId": feature_id})
    metrics = []
    for row in rows:
        pct = risk.decline_pct(row["baseline"], row["current"])
        series = sorted(row["series"], key=lambda x: x["i"])
        present = {x["i"] for x in series}
        missing = [i for i in range(series[0]["i"], series[-1]["i"] + 1) if i not in present] if series else []
        metrics.append({"key": row["metricKey"], "metric": row["metric"], "baseline": round(row["baseline"] or 0, 1),
                        "current": round(row["current"] or 0, 1), "declinePct": pct,
                        "series": [{"week": x["week"], "value": x["value"]} for x in series], "missingWeeks": missing})
    wau = next((m for m in metrics if m["key"] == "wau"), None)
    features = sorted((m for m in metrics if m["key"] != "wau"), key=lambda m: -m["declinePct"])
    top = features[0] if features else None
    window = (f"Before: weeks {p['baseFrom']}-{p['baseTo']} of 26 (8 weeks). Now: weeks "
              f"{p['curFrom']}-{CURRENT_WEEKS[1]} (the last 4 full weeks).")
    for m in ([wau] if wau else []) + ([top] if top else []):
        nid = f"usage:{account_id}:{m['key']}"
        trend = "down" if m["declinePct"] > 0 else "up"
        label = f"{'Active users' if m['key'] == 'wau' else m['metric'] + ' usage'} {trend} {abs(m['declinePct'])}%"
        r.node(id=nid, kind="usage", label=label, sublabel="last 4 weeks vs before",
               status="declining" if m["declinePct"] >= 20 else "stable")
        gap = (f" Weeks missing from the source data: {m['missingWeeks']}. The chart shows them as gaps and does not "
               f"fill them in." if m["missingWeeks"] else "")
        r.cite(id=nid, kind="usage", title=label, sourceSystem="Product analytics", recordId=nid,
               date=m["series"][-1]["week"] if m["series"] else None,
               fields=[["Before, average per week", m["baseline"]], ["Now, average per week", m["current"]],
                       ["Change", f"{-m['declinePct']:+d}%"], ["Weeks compared", window]],
               series=m["series"], note=gap.strip() or None)
        if m["key"] == "wau":
            r.edge(account_id, "USAGE_TREND", nid)
        else:
            r.node(id=m["key"], kind="feature", label=m["metric"], sublabel="Product feature")
            r.cite(id=m["key"], kind="feature", title=m["metric"], sourceSystem="Product catalog", recordId=m["key"],
                   fields=[["Feature", m["metric"]]])
            r.edge(account_id, "USES", m["key"])
            r.edge(m["key"], "USAGE_TREND", nid)
    r.data = {"weeklyActiveUsers": wau, "featureDeclines": features, "window": window}
    def change(pct: int) -> str:
        return "unchanged" if pct == 0 else f"{'down' if pct > 0 else 'up'} {abs(pct)}%"

    parts = []
    if wau:
        parts.append(f"active users {change(wau['declinePct'])}")
    if top:
        parts.append(f"{top['metric']} {change(top['declinePct'])}")
    r.summary = ("Usage: " + ", ".join(parts)) if parts else "No usage data"
    return r


def signals(ctx: Ctx, account_id: str, window_days: int = SIGNAL_WINDOW_DAYS) -> ToolResult:
    r = ToolResult("signals", "")
    rows = r.query("""
MATCH (a:Account {id: $accountId})<-[:WITH_ACCOUNT]-(cv:Conversation)<-[:PARTICIPATED_IN]-(c:Contact)
WHERE cv.occurredAt >= $since
OPTIONAL MATCH (cv)-[x:EXPRESSES]->(s:Signal)
WHERE s.confidence >= $minSignal
RETURN cv, c, collect({signal: s, link: x}) AS found
ORDER BY cv.occurredAt DESC
""", {"accountId": account_id, "since": ctx.since(window_days), "minSignal": MIN_SIGNAL_CONFIDENCE})
    out = []
    for row in rows:
        cv, c = row["cv"], row["c"]
        found = [f for f in row["found"] if f["signal"]]
        if not found:
            continue
        add_contact(r, ctx, c, account_id)
        r.node(id=cv["id"], kind="conversation", label=f"{cv['channel']} · {ctx.days_ago(cv['occurredAt'])} days ago",
               sublabel=cv.get("summary", ""))
        r.cite(id=cv["id"], kind="conversation", title=cv.get("summary") or cv["channel"], sourceSystem=cv["channel"],
               recordId=cv["id"], date=cv["occurredAt"][:10], quote=cv["text"],
               fields=[["Channel", cv["channel"]], ["Participant", c["name"]], ["Date", cv["occurredAt"][:10]]])
        r.edge(c["id"], "PARTICIPATED_IN", cv["id"])
        for f in found:
            s = f["signal"]
            r.node(id=s["id"], kind="signal", label=SIGNAL_LABELS.get(s["type"], s["type"]),
                   sublabel=f"“{s['phrase']}”", status="risk" if s["type"] in RISK_SIGNAL_TYPES else "positive")
            r.cite(id=s["id"], kind="signal", title=SIGNAL_LABELS.get(s["type"], s["type"]),
                   sourceSystem=f"{cv['channel']} (found by Relay)", recordId=s["id"], date=s.get("extractedAt"),
                   quote=s.get("quote"), fields=[["Type", SIGNAL_LABELS.get(s["type"], s["type"])],
                                                 ["Words that matched", s["phrase"]],
                                                 ["Confidence", s["confidence"]], ["Method", s.get("method")],
                                                 ["How Relay knows", "Relay found this in the text with fixed rules"]],
                   relationship=f"Said in {cv['id']} · confidence {s['confidence']:.2f} · {s.get('method')}")
            r.edge(cv["id"], "EXPRESSES", s["id"], confidence=s["confidence"])
            out.append({"signalId": s["id"], "type": s["type"], "quote": s.get("quote"), "phrase": s["phrase"],
                        "confidence": s["confidence"], "conversationId": cv["id"], "date": cv["occurredAt"][:10],
                        "speaker": c["name"], "speakerId": c["id"]})
    risky = [s for s in out if s["type"] in RISK_SIGNAL_TYPES]
    positive = [s for s in out if s["type"] not in RISK_SIGNAL_TYPES]
    r.data = {"signals": out, "riskSignals": len(risky), "positiveSignals": len(positive)}
    comp = [s for s in out if s["type"] == "competitor_evaluation"]
    if comp:
        r.summary = (f"Competitor mention: “{comp[0]['quote']}” ({comp[0]['speaker']}, "
                     f"{ctx.days_ago(comp[0]['date'])} days ago)")
    elif risky:
        r.summary = (f"{len(risky)} warning sign{'s' if len(risky) != 1 else ''}: "
                     + ", ".join(sorted({SIGNAL_LABELS[s['type']] for s in risky})))
    elif positive:
        r.summary = f"{len(positive)} positive sign{'s' if len(positive) != 1 else ''}, no warning signs"
    else:
        r.summary = f"No warning signs or positive signs in the last {window_days} days"
    return r


def billing_events(ctx: Ctx, account_id: str) -> ToolResult:
    r = ToolResult("billing_events", "")
    rows = r.query("""
MATCH (i:Invoice)-[:BILLED_TO]->(a:Account {id: $accountId})
RETURN i, a.walletBalance AS wallet ORDER BY i.issuedAt DESC LIMIT 4
""", {"accountId": account_id})
    invoices = [row["i"] for row in rows]
    wallet = rows[0]["wallet"] if rows else None
    latest = invoices[0] if invoices else None
    late = latest and (latest.get("daysLate") or 0) > 7
    if latest and late:
        label = f"Invoice paid {latest['daysLate']} days late"
        r.node(id=latest["id"], kind="invoice", label=label, sublabel=latest["id"], status="late")
        r.cite(id=latest["id"], kind="invoice", title=label, sourceSystem="Billing (GST invoices)", recordId=latest["id"],
               date=latest.get("paidDate"), fields=[["Amount (incl. GST)", inr(latest["amount"])], ["Issued", latest["issuedAt"]],
                                                    ["Due", latest["dueDate"]], ["Paid", latest.get("paidDate") or "Unpaid"],
                                                    ["Days late", latest.get("daysLate", 0)]])
        r.edge(latest["id"], "BILLED_TO", account_id)
    r.data = {"invoices": [{k: i.get(k) for k in ("id", "issuedAt", "dueDate", "paidDate", "daysLate", "amount", "status")}
                           for i in invoices], "latestLate": bool(late), "walletBalance": wallet}
    parts = [f"Latest invoice paid {latest['daysLate']} days late" if late else ("Invoices paid on time" if latest else "No invoices")]
    if wallet is not None:
        parts.append(f"wallet balance {inr(wallet)}")
    r.summary = ", ".join(parts)
    return r


def risk_breakdown(ctx: Ctx, account_id: str) -> ToolResult:
    r = ToolResult("risk_breakdown", "")
    inputs, res = risk.compute_inputs(account_id, ctx.as_of)
    for name, q in risk.QUERIES.items():
        r.queries.append(db.QueryResult(cypher=q.strip(), params={"accountId": account_id}, rows=res[name], ms=0.0))
    acc = db.rows("MATCH (a:Account {id: $id}) RETURN a.walletBalance AS w", {"id": account_id}, readonly=True)
    ri = inputs.get(account_id, RiskInputs())
    ri.wallet_balance = acc[0]["w"] if acc else None
    total, factors = score(ri)
    r.data = {"risk": total, "base": WEIGHTS["base"], "factors": [f.__dict__ for f in factors],
              "label": "risk of leaving", "weights": WEIGHTS}
    r.summary = (f"Risk of leaving: {total}%, from {len(factors)} "
                 f"factor{'s' if len(factors) != 1 else ''} in the graph")
    return r


Q_CAUSAL_CHAIN = """
MATCH (a:Account {id: $accountId})<-[:CONCERNS]-(t:Ticket {source: 'support'})<-[:RAISED]-(reporter:Contact),
      (t)-[s:SYMPTOM_OF]->(b:Bug)-[:AFFECTS]->(f:Feature)<-[:USES]-(a)
WHERE t.createdAt >= $since AND b.status <> 'Done' AND s.confidence >= $minLink
OPTIONAL MATCH (reporter)-[h:SUCCEEDED]->(former:Contact)-[w:WORKS_AT]->(a)
WHERE w.to >= $departureSince
OPTIONAL MATCH (a)<-[:WITH_ACCOUNT]-(cv:Conversation)-[:EXPRESSES]->(sig:Signal)
WHERE cv.occurredAt >= $since AND sig.type IN $riskSignals AND sig.confidence >= $minSignal
OPTIONAL MATCH (speaker:Contact)-[:PARTICIPATED_IN]->(cv)
RETURN b.id AS bugId, f.id AS featureId, f.name AS feature,
       collect(DISTINCT reporter.id) AS reporters, collect(DISTINCT t.id) AS tickets,
       avg(s.confidence) AS linkConfidence, min(t.createdAt) AS firstTicket, max(t.createdAt) AS lastTicket,
       collect(DISTINCT former.id) AS formerChampions, collect(DISTINCT h.at) AS handovers,
       collect(DISTINCT {signal: sig.id, type: sig.type, conversation: cv.id, speaker: speaker.id}) AS signals
"""


def causal_chain(ctx: Ctx, account_id: str, usage: dict | None = None) -> ToolResult:
    """Multi-hop: contact -> tickets -> shared bug -> affected feature the account uses, plus the former
    champion they replaced and risk signals in the same window. Ranks candidate chains."""
    r = ToolResult("causal_chain", "")
    rows = r.query(Q_CAUSAL_CHAIN, {
        "accountId": account_id, "since": ctx.since(SIGNAL_WINDOW_DAYS),
        "departureSince": ctx.since(90), "minLink": MIN_LINK_CONFIDENCE,
        "minSignal": MIN_SIGNAL_CONFIDENCE, "riskSignals": RISK_SIGNAL_TYPES,
    })
    if usage is None:
        usage = usage_trend(ctx, account_id).data
    declines = {m["key"]: m["declinePct"] for m in usage.get("featureDeclines", [])}
    candidates = []
    for row in rows:
        sigs = [s for s in row["signals"] if s.get("signal")]
        decline = max(0, declines.get(row["featureId"], 0))
        recency = max(0.0, 1 - ctx.days_ago(row["lastTicket"]) / SIGNAL_WINDOW_DAYS)
        consistency = sum([bool(row["formerChampions"]), decline >= 20, bool(sigs), len(row["tickets"]) >= 2])
        score_ = round(row["linkConfidence"] * (0.4 + 0.6 * min(decline, 100) / 100) * (0.5 + 0.5 * recency)
                       * (1 + 0.25 * consistency), 3)
        candidates.append({**row, "signals": sigs, "featureDeclinePct": decline, "recency": round(recency, 2),
                           "consistency": consistency, "score": score_})
    candidates.sort(key=lambda c: -c["score"])
    r.data = {"candidates": candidates,
              "ranking": "score = linkConfidence × (0.4 + 0.6 × featureDecline) × (0.5 + 0.5 × recency) × "
                         "(1 + 0.25 × corroborating sources)"}
    if not candidates:
        r.summary = "No chain found from tickets to an open bug to a feature this account uses"
        r.data["causal"] = {"nodeIds": [], "edgeIds": []}
        return r
    best = candidates[0]
    node_ids, edge_ids = [], []
    for t in best["tickets"]:
        node_ids.append(t)
        edge_ids.append(f"{t}|SYMPTOM_OF|{best['bugId']}")
    for rep in best["reporters"]:
        node_ids.append(rep)
        edge_ids.extend(f"{rep}|RAISED|{t}" for t in best["tickets"])
    for former in best["formerChampions"]:
        node_ids.append(former)
        edge_ids.extend(f"{rep}|SUCCEEDED|{former}" for rep in best["reporters"])
    node_ids += [best["bugId"], best["featureId"]]
    edge_ids.append(f"{best['bugId']}|AFFECTS|{best['featureId']}")
    if best["featureDeclinePct"] >= 20:
        feature_usage = usage_trend(ctx, account_id, best["featureId"])
        r.queries.extend(feature_usage.queries)
        for n in feature_usage.nodes:
            if n["id"] != f"usage:{account_id}:wau":
                r.node(**n)
        r.evidence.extend(e for e in feature_usage.evidence if e["id"] != f"usage:{account_id}:wau")
        for e in feature_usage.edges:
            if e["target"] != f"usage:{account_id}:wau":
                r.edges.append(e)
        uid = f"usage:{account_id}:{best['featureId']}"
        node_ids.append(uid)
        edge_ids.append(f"{best['featureId']}|USAGE_TREND|{uid}")
    for s in best["signals"]:
        node_ids += [s["conversation"], s["signal"]]
        edge_ids.append(f"{s['conversation']}|EXPRESSES|{s['signal']}")
        if s.get("speaker"):
            node_ids.append(s["speaker"])
            edge_ids.append(f"{s['speaker']}|PARTICIPATED_IN|{s['conversation']}")
    r.data["causal"] = {"nodeIds": list(dict.fromkeys(node_ids)), "edgeIds": list(dict.fromkeys(edge_ids))}
    lead = "former main contact → " if best["formerChampions"] else ""
    decline = f" (−{best['featureDeclinePct']}%)" if best["featureDeclinePct"] else ""
    competitor = " → competitor mention" if any(s["type"] == "competitor_evaluation" for s in best["signals"]) else ""
    r.summary = (f"How it connects: {lead}{len(best['tickets'])} tickets → {best['bugId']} → "
                 f"{best['feature']}{decline}{competitor}")
    return r


def blast_radius(ctx: Ctx, bug_id: str, exclude_account_id: str | None = None) -> ToolResult:
    r = ToolResult("blast_radius", "")
    rows = r.query("""
MATCH (b:Bug {id: $bugId})<-[s:SYMPTOM_OF]-(t:Ticket)-[:CONCERNS]->(a:Account)
WHERE s.confidence >= $minLink
OPTIONAL MATCH (c:Contact)-[:RAISED]->(t)
WITH b, a, collect(DISTINCT {id: t.id, title: t.title, createdAt: t.createdAt, status: t.status,
                             confidence: s.confidence, raisedBy: c.name}) AS tickets
RETURN b, a, tickets
ORDER BY a.arr DESC
""", {"bugId": bug_id, "minLink": MIN_LINK_CONFIDENCE})
    if not rows:
        r.summary = f"No accounts have tickets that point to {bug_id}"
        r.data = {"bugId": bug_id, "accounts": [], "totalArr": 0}
        return r
    bug = rows[0]["b"]
    add_bug(r, ctx, bug)
    accounts = []
    for row in rows:
        a = row["a"]
        if a["id"] == exclude_account_id:
            continue
        add_account(r, ctx, a, role="affected")
        n = len(row["tickets"])
        ev = next(e for e in r.evidence if e["id"] == a["id"])
        ev["fields"] = ev["fields"] + [[f"{t['id']} ({t['createdAt'][:10]})",
                                        f"“{t['title']}” · {t['raisedBy']} · confidence {t['confidence']:.2f}"]
                                       for t in row["tickets"]]
        ev["relationship"] = f"{n} ticket{'s' if n > 1 else ''} from {a['name']} point{'' if n > 1 else 's'} to {bug_id}"
        node = next(x for x in r.nodes if x["id"] == a["id"])
        node["sublabel"] = f"{inr(a['arr'])} ARR · {n} ticket{'s' if n > 1 else ''}"
        r.edge(bug_id, "IMPACTS", a["id"], detail=f"{n} ticket{'s' if n > 1 else ''}")
        accounts.append({"id": a["id"], "name": a["name"], "arr": a["arr"], "renewalDate": a["renewalDate"],
                         "renewalInDays": ctx.days_until(a["renewalDate"]), "crmHealthScore": a["crmHealthScore"],
                         "detectiveRisk": a.get("detectiveRisk"), "tickets": row["tickets"]})
    total = sum(a["arr"] for a in {a["id"]: a for a in accounts}.values())
    r.data = {"bugId": bug_id, "bugTitle": bug["title"], "accounts": accounts, "totalArr": total,
              "accountCount": len(accounts), "excluded": exclude_account_id,
              "dedup": "Each account's ARR is counted once"}
    who = "other " if exclude_account_id else ""
    r.summary = f"{bug_id} also hits {len(accounts)} {who}accounts · {inr(total)} ARR in total"
    return r


def costliest_bugs(ctx: Ctx, limit: int = 5) -> ToolResult:
    r = ToolResult("costliest_bugs", "")
    rows = r.query("""
MATCH (b:Bug)<-[s:SYMPTOM_OF]-(t:Ticket)-[:CONCERNS]->(a:Account)
WHERE s.confidence >= $minLink AND b.status <> 'Done'
WITH b, a, count(t) AS tickets
OPTIONAL MATCH (b)-[:OWNED_BY]->(o:Person)
WITH b, o, count(a) AS accounts, sum(a.arr) AS arr, sum(tickets) AS tickets,
     collect({id: a.id, name: a.name, arr: a.arr}) AS hit
RETURN b.id AS bugId, b.title AS title, b.priority AS priority, b.status AS status, b.jiraStatus AS jiraStatus,
       b.createdAt AS createdAt, o.name AS owner, o.id AS ownerId, accounts, arr, tickets, hit
ORDER BY arr DESC LIMIT $limit
""", {"minLink": MIN_LINK_CONFIDENCE, "limit": limit})
    ranked = [{**row, "tickets": int(row["tickets"]), "arr": int(row["arr"]), "ageDays": ctx.days_ago(row["createdAt"]),
               "underPrioritised": row["priority"] in ("P3", "P4") and int(row["arr"]) >= 1_000_000} for row in rows]
    r.data = {"bugs": ranked, "ranking": "Ranked by the ARR of the accounts hit. Each account counts once."}
    for b in ranked[:3]:
        r.node(id=b["bugId"], kind="bug", label=b["bugId"], sublabel=b["title"], status=b["status"])
        r.cite(id=b["bugId"], kind="bug", title=f"{b['bugId']}: {b['title']}", sourceSystem="Jira · Cheerio Dev",
               recordId=b["bugId"], date=(b["createdAt"] or "")[:10],
               fields=[["Affected accounts", b["accounts"]], ["Affected ARR", inr(b["arr"])], ["Tickets", b["tickets"]],
                       ["Priority", b["priority"]], ["Owner", b["owner"] or "—"]])
    if ranked:
        top = ranked[0]
        r.summary = (f"{top['bugId']} puts the most ARR at risk: {inr(top['arr'])} across {top['accounts']} accounts "
                     f"(priority {top['priority']})")
    else:
        r.summary = "No open bugs have customer tickets"
    return r


def timeline(ctx: Ctx, account_id: str, days: int = 90) -> ToolResult:
    r = ToolResult("timeline", "")
    since = ctx.since(days)
    p = {"accountId": account_id, "since": since}
    events = []
    for row in r.query("""
MATCH (c:Contact)-[w:WORKS_AT]->(:Account {id: $accountId}) WHERE w.to >= $since
RETURN c.id AS id, c.name AS name, c.isChampion AS champion, w.to AS date
""", p):
        events.append({"date": row["date"], "kind": "contact", "nodeId": row["id"],
                       "label": f"{row['name']} left" + (" (main contact)" if row["champion"] else "")})
    for row in r.query("""
MATCH (:Account {id: $accountId})<-[:CONCERNS]-(t:Ticket {source: 'support'}) WHERE t.createdAt >= $since
OPTIONAL MATCH (t)-[:SYMPTOM_OF]->(b:Bug)
RETURN t.id AS id, t.title AS title, t.createdAt AS date, b.id AS bug
""", p):
        events.append({"date": row["date"][:10], "kind": "ticket", "nodeId": row["id"],
                       "label": f"Ticket “{row['title']}”" + (f" → {row['bug']}" if row["bug"] else "")})
    for row in r.query("""
MATCH (:Account {id: $accountId})<-[:CONCERNS]-(:Ticket {source: 'support'})-[:SYMPTOM_OF]->(b:Bug)
WHERE b.createdAt >= $since OR b.status <> 'Done'
RETURN DISTINCT b.id AS id, b.title AS title, b.createdAt AS date, b.status AS status
""", p):
        d = row["date"][:10]
        events.append({"date": max(d, since), "kind": "bug", "nodeId": row["id"],
                       "label": f"{row['id']} opened ({row['status']})" if d >= since else f"{row['id']} still {row['status']}"})
    for row in r.query("""
MATCH (:Account {id: $accountId})<-[:WITH_ACCOUNT]-(cv:Conversation) WHERE cv.occurredAt >= $since
OPTIONAL MATCH (cv)-[:EXPRESSES]->(s:Signal)
RETURN cv.id AS id, cv.channel AS channel, cv.occurredAt AS date, cv.summary AS summary, collect(s.type) AS types
""", p):
        events.append({"date": row["date"][:10], "kind": "conversation", "nodeId": row["id"],
                       "label": row["summary"] or row["channel"], "signals": row["types"]})
    for row in r.query("""
MATCH (m:Meeting)-[:WITH]->(:Account {id: $accountId}) WHERE m.date >= $since
RETURN m.id AS id, m.title AS title, m.date AS date, m.status AS status
""", p):
        events.append({"date": row["date"][:10], "kind": "meeting", "nodeId": row["id"],
                       "label": row["title"] + (" (scheduled)" if row["status"] == "scheduled" else "")})
    for row in r.query("""
MATCH (i:Invoice)-[:BILLED_TO]->(:Account {id: $accountId}) WHERE i.dueDate >= $since
RETURN i.id AS id, i.paidDate AS date, i.daysLate AS late
""", p):
        if row["date"]:
            events.append({"date": row["date"], "kind": "invoice", "nodeId": row["id"],
                           "label": f"Invoice paid {row['late']} days late" if row["late"] else "Invoice paid on time"})
    usage = usage_trend(ctx, account_id)
    r.queries.extend(usage.queries)
    wau = usage.data.get("weeklyActiveUsers")
    if wau and wau["declinePct"] >= 15:
        base = wau["baseline"]
        first_drop = next((pt for pt in wau["series"] if pt["week"] >= since and pt["value"] < base * 0.85), None)
        if first_drop:
            events.append({"date": first_drop["week"], "kind": "usage", "nodeId": f"usage:{account_id}:wau",
                           "label": f"Active users drop below 85% of the usual level ({first_drop['value']} vs {base:.0f})"})
    events.sort(key=lambda e: e["date"])
    r.data = {"from": since, "to": ctx.as_of, "events": events}
    r.summary = f"{len(events)} events with dates in the last {days} days"
    return r


# ---------------------------------------------------------------- Relay tools (shared graph)

def promises(ctx: Ctx, account_id: str) -> ToolResult:
    """Promises made to this account, their dependencies, and which are at risk."""
    r = ToolResult("promises", "")
    rows = r.query("""
MATCH (p:Promise)-[:TO]->(a:Account {id: $accountId})
OPTIONAL MATCH (m:Meeting)-[:PRODUCED]->(p)
OPTIONAL MATCH (maker:Person)-[:MADE]->(p)
OPTIONAL MATCH (p)-[:DEPENDS_ON]->(d)
RETURN p, m.id AS meetingId, m.title AS meeting, m.date AS meetingDate, maker, labels(d) AS depLabels, d AS dep
ORDER BY p.madeAt DESC
""", {"accountId": account_id})
    out = []
    for row in rows:
        p, dep, maker = row["p"], row["dep"], row["maker"]
        flat = {"text": p["text"], "due": p["due"], "depLabels": row["depLabels"], "depId": dep and dep.get("id"),
                "depStatus": dep and dep.get("status"), "depEta": dep and dep.get("eta"),
                "depEtaLabel": dep and dep.get("etaLabel"), "depTitle": dep and dep.get("title")}
        why = risk.promise_risk(flat, ctx.as_of) if p["status"] == "open" else None
        add_promise(r, ctx, p, why)
        r.edge(p["id"], "TO", account_id)
        if row["meetingId"]:
            r.node(id=row["meetingId"], kind="meeting", label=row["meeting"], sublabel=(row["meetingDate"] or "")[:10])
            r.cite(id=row["meetingId"], kind="meeting", title=row["meeting"], sourceSystem="Meeting notes",
                   recordId=row["meetingId"], date=(row["meetingDate"] or "")[:10], quote=p.get("quote"))
            r.edge(row["meetingId"], "PRODUCED", p["id"])
        if maker:
            add_person(r, maker)
            r.edge(maker["id"], "MADE", p["id"])
        if dep:
            if "RoadmapItem" in (row["depLabels"] or []):
                add_roadmap(r, dep)
            else:
                add_bug(r, ctx, dep) if "Bug" in (row["depLabels"] or []) else r.node(
                    id=dep["id"], kind="ticket", label=dep["id"], sublabel=dep.get("title", ""), status=dep.get("status"))
            r.edge(p["id"], "DEPENDS_ON", dep["id"])
        out.append({"id": p["id"], "text": p["text"], "due": p["due"], "status": p["status"], "atRisk": bool(why),
                    "why": why, "madeBy": maker and maker["name"], "madeById": maker and maker["id"],
                    "meeting": row["meeting"], "meetingId": row["meetingId"], "quote": p.get("quote"),
                    "dependsOn": dep and {"id": dep["id"], "title": dep.get("title"), "status": dep.get("status"),
                                          "eta": dep.get("etaLabel"), "kind": (row["depLabels"] or ["?"])[0]}})
    at_risk = [p for p in out if p["atRisk"]]
    r.data = {"promises": out, "atRisk": len(at_risk), "open": sum(1 for p in out if p["status"] == "open")}
    if at_risk:
        r.summary = f"{len(at_risk)} promise{'s' if len(at_risk) != 1 else ''} at risk: {at_risk[0]['why']}"
    elif out:
        r.summary = f"{r.data['open']} open promise{'s' if r.data['open'] != 1 else ''}, all on track"
    else:
        r.summary = "No promises recorded"
    return r


def internal_owners(ctx: Ctx, account_id: str) -> ToolResult:
    """The Cheerio people this account depends on (CSM, sales POC, technical contact, people who know it)."""
    r = ToolResult("internal_owners", "")
    rows = r.query("""
MATCH (p:Person)-[x:MANAGES|TECH_CONTACT_FOR|KNOWS]->(a:Account {id: $accountId})
RETURN p, type(x) AS rel, x.role AS role, x.score AS score
ORDER BY coalesce(x.score, 1.0) DESC
""", {"accountId": account_id})
    risks = r.query("""
MATCH (k:Risk {kind: 'internal_owner_leaving', open: true})-[:ON]->(:Account {id: $accountId})
OPTIONAL MATCH (k)-[:CAUSED_BY]->(p:Person)
RETURN k.detail AS detail, p.id AS personId
""", {"accountId": account_id})
    people: dict[str, dict] = {}
    for row in rows:
        p = row["p"]
        e = people.setdefault(p["id"], {"id": p["id"], "name": p["name"], "role": p.get("role"),
                                        "leaving": bool(p.get("leaving")), "lastDay": p.get("lastDay") or p.get("endDate"),
                                        "relations": [], "knows": None})
        if row["rel"] == "KNOWS":
            e["knows"] = row["score"]
        else:
            e["relations"].append({"cs_owner": "CS owner", "sales_poc": "sales contact"}.get(row["role"], row["role"] or "technical contact"))
    for p in people.values():
        rel = ", ".join(p["relations"]) or f"knows the account (score {p['knows']:.2f})"
        add_person(r, {"id": p["id"], "name": p["name"], "role": p["role"], "leaving": p["leaving"], "lastDay": p["lastDay"]},
                   note=rel)
        r.edge(p["id"], "TECH_CONTACT_FOR" if "technical contact" in p["relations"] else
               ("MANAGES" if p["relations"] else "KNOWS"), account_id, detail=rel)
    leaving = [p for p in people.values() if p["leaving"]]
    r.data = {"people": sorted(people.values(), key=lambda p: (not p["relations"], -(p["knows"] or 0))),
              "leaving": leaving, "ownerRisks": risks}
    if leaving:
        p = leaving[0]
        r.summary = f"{p['name']} ({', '.join(p['relations']) or 'knows the account'}) leaves {p['lastDay']}"
    else:
        r.summary = f"{len(people)} people work with this account. Nobody is leaving."
    return r


def roadmap_status(ctx: Ctx, query: str | None = None, feature_id: str | None = None) -> ToolResult:
    """Roadmap items by feature or keyword, with ETA changes and internal guidance."""
    r = ToolResult("roadmap_status", "")
    if query:
        rows = r.query("""
CALL db.idx.fulltext.queryNodes('RoadmapItem', $q) YIELD node, score
OPTIONAL MATCH (node)-[:FOR_FEATURE]->(f:Feature)
OPTIONAL MATCH (node)-[:OWNED_BY]->(o:Person)
RETURN node AS i, f.name AS feature, o.name AS owner, score ORDER BY score DESC LIMIT 5
""", {"q": query})
    else:
        rows = r.query("""
MATCH (i:RoadmapItem) WHERE $featureId IS NULL OR (i)-[:FOR_FEATURE]->(:Feature {id: $featureId})
OPTIONAL MATCH (i)-[:FOR_FEATURE]->(f:Feature)
OPTIONAL MATCH (i)-[:OWNED_BY]->(o:Person)
RETURN i, f.name AS feature, o.name AS owner ORDER BY i.eta
""", {"featureId": feature_id})
    items = []
    for row in rows:
        i = row["i"]
        add_roadmap(r, i)
        items.append({"id": i["id"], "title": i["title"], "status": i["status"], "eta": i.get("etaLabel"),
                      "originally": i.get("originalLabel"), "slipped": i.get("eta") != i.get("originalEta"),
                      "internalNote": i.get("internalNote"), "publicNote": i.get("publicNote"),
                      "feature": row["feature"], "owner": row["owner"]})
    r.data = {"items": items}
    if items:
        top = items[0]
        moved = f" (moved from {top['originally']})" if top["slipped"] and top["originally"] else ""
        r.summary = f"{top['title']}: {top['status']}, {top['eta']}{moved}"
    else:
        r.summary = "No matching roadmap items"
    return r


# Shortest path through shared work. Working links only: a shared all-hands says nothing about who
# can get a quick answer from whom.
WARM_PATH = """
MATCH (a:Person {id: $a}), (b:Person {id: $b})
WITH shortestPath((a)-[:ASSIGNED_TO|OWNED_BY|REPORTED_BY|MEMBER_OF|REPORTS_TO*..4]-(b)) AS p
WHERE p IS NOT NULL
RETURN [n IN nodes(p) | {label: labels(n)[0], id: n.id, name: coalesce(n.name, n.title, n.id)}] AS hops
"""


def experts(ctx: Ctx, feature_id: str | None = None, bug_id: str | None = None, system_id: str | None = None,
            from_person_id: str | None = None) -> ToolResult:
    """Who to ask: the owner of a bug or feature and the people who know the systems behind it.
    With `from_person_id`, each expert also gets the shortest working path from the asker."""
    r = ToolResult("experts", "")
    if bug_id and not feature_id:
        rows = r.query("MATCH (:Bug {id: $b})-[:AFFECTS]->(f:Feature) RETURN f.id AS id", {"b": bug_id})
        feature_id = rows[0]["id"] if rows else None
    owner_rows = r.query("""
OPTIONAL MATCH (b:Bug {id: $b})-[:OWNED_BY]->(bo:Person)
OPTIONAL MATCH (f:Feature {id: $f})-[:OWNED_BY]->(fo:Person)
RETURN bo, fo
""", {"b": bug_id, "f": feature_id})
    knowers = r.query("""
MATCH (s:System)<-[k:KNOWS]-(p:Person)
WHERE s.id = $s OR (s)<-[:SERVED_BY]-(:Feature {id: $f})
RETURN p, s.name AS system, s.id AS systemId, k.score AS score, p.leaving AS leaving
ORDER BY k.score DESC LIMIT 6
""", {"s": system_id, "f": feature_id})
    out = []
    o = owner_rows[0] if owner_rows else {}
    for key, why in (("bo", f"Owns {bug_id}"), ("fo", "Owns the feature")):
        p = o.get(key)
        if p and not any(x["id"] == p["id"] for x in out):
            add_person(r, p, note=why)
            out.append({"id": p["id"], "name": p["name"], "role": p.get("role"), "why": why,
                        "slack": p.get("slackId"), "leaving": bool(p.get("leaving"))})
    for row in knowers:
        p = row["p"]
        if any(x["id"] == p["id"] for x in out):
            continue
        add_person(r, p, note=f"Knows {row['system']} ({row['score']:.2f})")
        r.edge(p["id"], "KNOWS", row["systemId"], score=row["score"])
        r.node(id=row["systemId"], kind="system", label=row["system"], sublabel="System")
        out.append({"id": p["id"], "name": p["name"], "role": p.get("role"),
                    "why": f"Knows {row['system']} ({row['score']:.2f})", "slack": p.get("slackId"),
                    "leaving": bool(row["leaving"])})
    if from_person_id:
        for x in out:
            rows = r.query(WARM_PATH, {"a": from_person_id, "b": x["id"]}) if x["id"] != from_person_id else []
            x["hops"] = rows[0]["hops"] if rows else None
            x["distance"] = len(x["hops"]) - 1 if x["hops"] else None
    r.data = {"experts": out, "featureId": feature_id, "bugId": bug_id}
    r.summary = f"Ask {out[0]['name']} ({out[0]['why']})" if out else "Nobody found who knows this"
    if from_person_id and out and out[0].get("distance"):
        r.summary += f", {out[0]['distance']} steps away through shared work"
    return r


def playbooks(ctx: Ctx, factors: list[str] | None = None) -> ToolResult:
    """Procedural memory: save playbooks whose trigger matches the account's risk factors."""
    r = ToolResult("playbooks", "")
    rows = r.query("""
MATCH (b:Playbook)
OPTIONAL MATCH (b)-[:WORKED_FOR]->(a:Account)
OPTIONAL MATCH (b)-[:SOURCED_FROM]->(d:Doc)
RETURN b, collect(DISTINCT a.name) AS workedFor, d.id AS docId, d.title AS doc
""")
    keys = set(factors or [])
    out = []
    for row in rows:
        b = row["b"]
        trig = set(b["trigger"].split("+"))
        match = trig <= keys if keys else True
        if not match and not (trig & keys):
            continue
        out.append({"id": b["id"], "name": b["name"], "steps": json.loads(b["steps"]), "outcome": b.get("outcome"),
                    "workedFor": row["workedFor"], "doc": row["doc"], "docId": row["docId"], "fullMatch": match,
                    "specificity": len(trig)})
        r.node(id=b["id"], kind="playbook", label=b["name"], sublabel=b.get("outcome", ""))
        r.cite(id=b["id"], kind="playbook", title=b["name"], sourceSystem="Playbooks (what worked before)", recordId=b["id"],
               quote=" · ".join(json.loads(b["steps"])), fields=[["Worked for", ", ".join(row["workedFor"]) or "—"],
                                                                ["Source", row["doc"] or "—"]])
    out.sort(key=lambda p: (not p["fullMatch"], -p["specificity"]))
    r.data = {"playbooks": out}
    r.summary = (f"{len(out)} playbook{'s' if len(out) != 1 else ''} match: " + ", ".join(p["name"] for p in out[:2])
                 if out else "No matching playbooks")
    return r


def memory(ctx: Ctx, account_id: str) -> ToolResult:
    """Episodic memory: past investigations, calls and handovers that touched this account."""
    r = ToolResult("memory", "")
    rows = r.query("""
MATCH (e:Episode)-[:FOR_ACCOUNT]->(:Account {id: $accountId})
OPTIONAL MATCH (p:Person)-[:RAN]->(e)
RETURN e, p.name AS by ORDER BY e.t DESC LIMIT 5
""", {"accountId": account_id})
    out = [{"id": row["e"]["id"], "kind": row["e"]["kind"], "at": row["e"]["at"][:10], "risk": row["e"].get("risk"),
            "verdict": row["e"]["verdict"], "outcome": row["e"].get("outcome"), "by": row["by"]} for row in rows]
    for e in out:
        r.node(id=e["id"], kind="episode", label=f"Past {e['kind']} · {e['at']}", sublabel=e["outcome"] or "")
        r.cite(id=e["id"], kind="episode", title=f"{e['kind'].capitalize()} on {e['at']}", sourceSystem="Relay memory",
               recordId=e["id"], date=e["at"], quote=e["verdict"], fields=[["Outcome", e["outcome"] or "—"], ["By", e["by"] or "—"]])
        r.edge(e["id"], "FOR_ACCOUNT", account_id)
    r.data = {"episodes": out}
    r.summary = (f"Last looked at on {out[0]['at']}: {out[0]['verdict']}" if out
                 else "No earlier investigations or calls for this account")
    return r


# ---------------------------------------------------------------- registry

@dataclass
class ToolSpec:
    name: str
    fn: Callable[..., ToolResult]
    description: str
    params: dict  # JSON schema "properties"
    required: list[str]


REGISTRY: dict[str, ToolSpec] = {}


def _register(name, fn, description, params, required):
    REGISTRY[name] = ToolSpec(name, fn, description, params, required)


_ACC = {"account_id": {"type": "string", "description": "Account id, e.g. cust-northwind-foods"}}
_register("account_overview", account_overview, "ARR, plan, renewal date and stage, CRM health score, CSM, AE and features for an account.", _ACC, ["account_id"])
_register("champion_changes", champion_changes, "Contacts who left or joined recently, champion status and who succeeded whom (WORKS_AT / SUCCEEDED).", _ACC, ["account_id"])
_register("ticket_root_causes", ticket_root_causes, "Recent support tickets grouped by the Jira bug they are a SYMPTOM_OF, with link confidence, provenance and bug owner.", _ACC, ["account_id"])
_register("usage_trend", usage_trend, "Active users and per-feature usage, last 4 weeks vs an 8-week baseline.",
          {**_ACC, "feature_id": {"type": "string", "description": "Optional feature id, e.g. F-REPORTS"}}, ["account_id"])
_register("signals", signals, "Competitor, frustration, budget and positive signals extracted from customer conversations, with exact quotes.", _ACC, ["account_id"])
_register("billing_events", billing_events, "Recent GST invoices, payment delays and wallet balance.", _ACC, ["account_id"])
_register("risk_breakdown", risk_breakdown, "The transparent demo risk score and each graph-derived factor behind it.", _ACC, ["account_id"])
_register("causal_chain", causal_chain, "Multi-hop traversal: contact -> tickets -> shared open bug -> affected feature the account uses, plus the former champion and risk signals. Ranks candidate chains.", _ACC, ["account_id"])
_register("blast_radius", blast_radius, "Every account hit by a bug (bug <- tickets -> accounts) with deduplicated ARR.",
          {"bug_id": {"type": "string", "description": "Jira bug key, e.g. CHEER-2547"},
           "exclude_account_id": {"type": "string", "description": "Account to leave out (the one under investigation)"}}, ["bug_id"])
_register("costliest_bugs", costliest_bugs, "Open bugs ranked by affected ARR across the portfolio.",
          {"limit": {"type": "integer", "description": "How many bugs to return (default 5)"}}, [])
_register("timeline", timeline, "Chronological events (departures, tickets, bugs, conversations, meetings, invoices, usage) for an account.",
          {**_ACC, "days": {"type": "integer", "description": "Look-back window in days (default 90)"}}, ["account_id"])
_register("promises", promises, "Promises made to the account in meetings, what each depends on (roadmap item, bug) and which are at risk.", _ACC, ["account_id"])
_register("internal_owners", internal_owners, "Cheerio people the account depends on (CSM, AE, technical contact, people who know it) and whether any are leaving.", _ACC, ["account_id"])
_register("roadmap_status", roadmap_status, "Roadmap items by keyword or feature, with ETA changes and internal guidance (e.g. don't commit to a date).",
          {"query": {"type": "string", "description": "Keywords, e.g. 'SSO'"},
           "feature_id": {"type": "string", "description": "Feature id, e.g. F-ACCESS"}}, [])
_register("experts", experts, "Who to ask about a bug, feature or system: owners plus people with the strongest KNOWS edges.",
          {"bug_id": {"type": "string"}, "feature_id": {"type": "string"}, "system_id": {"type": "string"},
           "from_person_id": {"type": "string", "description": "Asker; adds the shortest working path to each expert"}}, [])
_register("playbooks", playbooks, "Save playbooks (procedural memory) whose trigger matches the given risk factor keys, with the accounts they worked for.",
          {"factors": {"type": "array", "items": {"type": "string"}, "description": "Risk factor keys, e.g. champion_departed"}}, [])
_register("memory", memory, "Past investigations, calls and handovers for this account (episodic memory).", _ACC, ["account_id"])


def call(name: str, ctx: Ctx, **kwargs) -> ToolResult:
    spec = REGISTRY[name]
    allowed = set(spec.params)
    return spec.fn(ctx, **{k: v for k, v in kwargs.items() if k in allowed and v is not None})
