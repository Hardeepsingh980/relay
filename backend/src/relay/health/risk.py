"""Graph-derived account risk (the Detective agent's portfolio scan).

Every factor is a Cypher traversal over the live graph. The same queries back the
portfolio scan (Risk Radar) and the per-account `risk_breakdown` tool, so the
number on the card and the investigation can never disagree. The scan writes the
score back to the account and one (:Risk)-[:ON]->(:Account) node per factor, with
CAUSED_BY edges to the evidence, so other agents read it from the graph.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from .. import db
from ..config import DEMO_NOW, now
from .model import (
    BASELINE_WEEKS,
    CURRENT_WEEKS,
    DEPARTURE_WINDOW_DAYS,
    MIN_LINK_CONFIDENCE,
    MIN_SIGNAL_CONFIDENCE,
    SIGNAL_WINDOW_DAYS,
    SILENT_RISK_CRM_MIN,
    SILENT_RISK_RISK_MIN,
    RiskInputs,
    band,
    factors_as_dicts,
    hint,
    score,
)
from .signals import POSITIVE_TYPES

Q_CHAMPION = """
MATCH (c:Contact)-[w:WORKS_AT]->(a:Account)
WHERE ($accountId IS NULL OR a.id = $accountId)
  AND c.isChampion = true AND w.to IS NOT NULL AND w.to >= $departureSince
OPTIONAL MATCH (s:Contact)-[:SUCCEEDED]->(c)
RETURN a.id AS accountId, c.id AS contactId, c.name AS name, w.to AS leftAt, s.id AS successorId, s.name AS successor
"""

Q_BUG_TICKETS = """
MATCH (a:Account)<-[:CONCERNS]-(t:Ticket {source: 'support'})-[s:SYMPTOM_OF]->(b:Bug)
WHERE ($accountId IS NULL OR a.id = $accountId) AND t.createdAt >= $signalSince
RETURN a.id AS accountId, b.id AS bugId, b.keyword AS keyword, b.status AS bugStatus, count(t) AS tickets,
       sum(CASE WHEN s.confidence >= $minLink AND b.status <> 'Done' AND t.status <> 'solved' THEN 1 ELSE 0 END) AS unresolved
"""

Q_WAU = """
MATCH (u:UsageWeek)-[:OF_ACCOUNT]->(a:Account)
WHERE ($accountId IS NULL OR a.id = $accountId) AND u.metric = 'active_users' AND u.weekIndex >= $baseFrom
RETURN a.id AS accountId,
       avg(CASE WHEN u.weekIndex <= $baseTo THEN u.value END) AS baseline,
       avg(CASE WHEN u.weekIndex >= $curFrom THEN u.value END) AS current
"""

Q_FEATURE_USAGE = """
MATCH (a:Account)<-[:OF_ACCOUNT]-(u:UsageWeek)-[:OF_FEATURE]->(f:Feature)
WHERE ($accountId IS NULL OR a.id = $accountId) AND u.weekIndex >= $baseFrom
RETURN a.id AS accountId, f.id AS featureId, f.name AS feature,
       avg(CASE WHEN u.weekIndex <= $baseTo THEN u.value END) AS baseline,
       avg(CASE WHEN u.weekIndex >= $curFrom THEN u.value END) AS current
"""

Q_SIGNALS = """
MATCH (a:Account)<-[:WITH_ACCOUNT]-(cv:Conversation)-[:EXPRESSES]->(s:Signal)
WHERE ($accountId IS NULL OR a.id = $accountId) AND cv.occurredAt >= $signalSince AND s.confidence >= $minSignal
RETURN a.id AS accountId, s.type AS type, count(s) AS n
"""

Q_CALL_SIGNALS = """
MATCH (a:Account)<-[:WITH]-(m:Meeting)-[:EXPRESSES]->(s:Signal)
WHERE ($accountId IS NULL OR a.id = $accountId) AND m.date >= $signalSince AND s.confidence >= $minSignal
RETURN a.id AS accountId, s.type AS type, count(s) AS n
"""

Q_LATEST_INVOICE = """
MATCH (i:Invoice)-[:BILLED_TO]->(a:Account)
WHERE ($accountId IS NULL OR a.id = $accountId)
WITH a, i ORDER BY i.issuedAt DESC
WITH a, collect(i)[0] AS latest
RETURN a.id AS accountId, latest.id AS invoiceId, latest.daysLate AS daysLate
"""

# PRD 10.3, "promises at risk": a promise whose dependency slipped past its due date.
Q_PROMISES = """
MATCH (p:Promise)-[:TO]->(a:Account)
WHERE ($accountId IS NULL OR a.id = $accountId) AND p.status = 'open'
OPTIONAL MATCH (p)-[:DEPENDS_ON]->(d)
OPTIONAL MATCH (maker:Person)-[:MADE]->(p)
RETURN a.id AS accountId, p.id AS id, p.text AS text, p.due AS due, labels(d) AS depLabels, d.id AS depId,
       d.status AS depStatus, d.eta AS depEta, d.etaLabel AS depEtaLabel, d.title AS depTitle, maker.name AS maker
"""

# Written by the Handover agent when it analyses a departure (see relay.health.handoff).
Q_OWNER_RISKS = """
MATCH (r:Risk {kind: 'internal_owner_leaving', open: true})-[:ON]->(a:Account)
WHERE ($accountId IS NULL OR a.id = $accountId)
OPTIONAL MATCH (r)-[:CAUSED_BY]->(p:Person)
RETURN a.id AS accountId, r.detail AS detail, p.name AS name, p.id AS personId
"""


def as_of() -> str:
    return now().date().isoformat()


def window_params(as_of_day: str, account_id: str | None = None) -> dict:
    d = date.fromisoformat(as_of_day)
    return {
        "accountId": account_id,
        "signalSince": (d - timedelta(days=SIGNAL_WINDOW_DAYS)).isoformat(),
        "departureSince": (d - timedelta(days=DEPARTURE_WINDOW_DAYS)).isoformat(),
        "minLink": MIN_LINK_CONFIDENCE,
        "minSignal": MIN_SIGNAL_CONFIDENCE,
        "baseFrom": BASELINE_WEEKS[0], "baseTo": BASELINE_WEEKS[1],
        "curFrom": CURRENT_WEEKS[0], "curTo": CURRENT_WEEKS[1],
    }


def decline_pct(baseline: float | None, current: float | None) -> int:
    """Percent decline from baseline to current, rounded. Negative means growth. 0 if no baseline."""
    if not baseline or current is None:
        return 0
    return round((baseline - current) / baseline * 100)


def promise_risk(row: dict, today: str) -> str | None:
    """Why an open promise is at risk, or None if it is on track."""
    labels = row.get("depLabels") or []
    due = row["due"]
    if "RoadmapItem" in labels:
        if row["depStatus"] in ("delayed", "cut") and (row["depEta"] is None or row["depEta"] > due):
            return f"{row['text']} (the roadmap now says {row['depEtaLabel'] or row['depStatus']})"
        if row["depStatus"] != "shipped" and due < today:
            return f"{row['text']} (due {due}, not shipped yet)"
        return None
    if "Bug" in labels or "Ticket" in labels:
        if row["depStatus"] != "Done" and due < today:
            return f"{row['text']} (due {due}, {row['depId']} still open)"
        return None
    if due < today:
        return f"{row['text']} (due {due})"
    return None


QUERIES = {"champion": Q_CHAMPION, "bugTickets": Q_BUG_TICKETS, "activeUsers": Q_WAU, "featureUsage": Q_FEATURE_USAGE,
           "signals": Q_SIGNALS, "callSignals": Q_CALL_SIGNALS, "latestInvoice": Q_LATEST_INVOICE,
           "promises": Q_PROMISES, "ownerRisks": Q_OWNER_RISKS}


def compute_inputs(account_id: str | None = None, as_of_day: str | None = None) -> tuple[dict[str, RiskInputs], dict]:
    as_of_day = as_of_day or as_of()
    p = window_params(as_of_day, account_id)
    res = {k: db.rows(q, p, readonly=True) for k, q in QUERIES.items()}
    inputs: dict[str, RiskInputs] = {}

    def get(acc: str) -> RiskInputs:
        return inputs.setdefault(acc, RiskInputs())

    for r in res["champion"]:
        ri = get(r["accountId"])
        ri.champion_departed = True
        ri.champion_name = r["name"]
    per_bug: dict[str, list[dict]] = {}
    for r in res["bugTickets"]:
        per_bug.setdefault(r["accountId"], []).append(r)
    for acc, rows in per_bug.items():
        ri = get(acc)
        ri.unresolved_bug_tickets = int(sum(r["unresolved"] for r in rows))
        top = max(rows, key=lambda r: r["unresolved"])
        ri.top_bug_keyword = top["keyword"] if top["unresolved"] else None
        ri.fixed_bug_tickets = int(sum(r["tickets"] for r in rows if r["bugStatus"] == "Done"))
    for r in res["activeUsers"]:
        ri = get(r["accountId"])
        ri.wau_decline_pct = max(0, decline_pct(r["baseline"], r["current"]))
        ri.recovered_usage = decline_pct(r["baseline"], r["current"]) <= -3
    per_feat: dict[str, list[dict]] = {}
    for r in res["featureUsage"]:
        per_feat.setdefault(r["accountId"], []).append(r)
    for acc, rows in per_feat.items():
        ri = get(acc)
        top = max(rows, key=lambda r: decline_pct(r["baseline"], r["current"]))
        ri.top_feature = top["feature"]
        ri.top_feature_decline_pct = max(0, decline_pct(top["baseline"], top["current"]))
    sig_counts: dict[tuple[str, str], int] = {}
    for r in res["signals"] + res["callSignals"]:
        sig_counts[(r["accountId"], r["type"])] = sig_counts.get((r["accountId"], r["type"]), 0) + r["n"]
    for (acc, typ), n in sig_counts.items():
        ri = get(acc)
        if typ == "competitor_evaluation":
            ri.competitor_signals += n
        elif typ == "budget_pressure":
            ri.budget_signals += n
        elif typ == "frustration":
            ri.frustration_signals += n
        elif typ in POSITIVE_TYPES:
            ri.positive_signals += n
    for r in res["latestInvoice"]:
        get(r["accountId"]).latest_invoice_days_late = r["daysLate"] or 0
    for r in res["promises"]:
        why = promise_risk(r, as_of_day)
        if why:
            get(r["accountId"]).promises_at_risk.append(why)
    for r in res["ownerRisks"]:
        get(r["accountId"]).owners_leaving.append(r["detail"] or r["name"])
    return inputs, res


def _accounts(account_id: str | None = None) -> list[dict]:
    return db.rows("""MATCH (a:Account) WHERE a.crmHealthScore IS NOT NULL AND ($id IS NULL OR a.id = $id)
                      RETURN a.id AS id, a.crmHealthScore AS crm, a.walletBalance AS wallet, a.detectiveRisk AS prev""",
                   {"id": account_id}, readonly=True)


def scan(account_id: str | None = None, as_of_day: str | None = None) -> dict[str, dict]:
    """Score accounts from the graph and write the result (and its Risk nodes) back."""
    as_of_day = as_of_day or as_of()
    inputs, _ = compute_inputs(account_id, as_of_day)
    out: dict[str, dict] = {}
    rows = []
    for a in _accounts(account_id):
        ri = inputs.get(a["id"], RiskInputs())
        ri.wallet_balance = a["wallet"]
        risk, factors = score(ri)
        h = hint(ri, risk, factors, a["crm"])
        silent = a["crm"] >= SILENT_RISK_CRM_MIN and risk >= SILENT_RISK_RISK_MIN
        fd = factors_as_dicts(factors)
        out[a["id"]] = {"risk": risk, "previous": a["prev"], "factors": fd, "hint": h, "silent": silent, "crm": a["crm"]}
        rows.append({"id": a["id"], "risk": risk, "factors": json.dumps(fd), "hint": h, "silent": silent,
                     "band": band(risk), "risks": [{"rid": f"risk-{a['id']}-{f['key']}", **f} for f in fd
                                                   if f["points"] > 0 and f["key"] != "internal_owner_leaving"]})
    stamp = now().isoformat(timespec="seconds")
    g = db.graph()
    for i in range(0, len(rows), 200):
        g.query("""UNWIND $rows AS r MATCH (a:Account {id: r.id})
                   SET a.previousRisk = a.detectiveRisk, a.detectiveRisk = r.risk, a.riskFactors = r.factors,
                       a.riskHint = r.hint, a.silentRisk = r.silent, a.riskBand = r.band, a.riskScannedAt = $at""",
                {"rows": rows[i:i + 200], "at": stamp})
    _write_risk_nodes(rows, account_id)
    return out


def _write_risk_nodes(rows: list[dict], account_id: str | None) -> None:
    """One Risk node per scored factor, linked to the account (owner-leaving risks belong to the Handover agent)."""
    db.run("""MATCH (r:Risk {source: 'detective'})-[:ON]->(a:Account) WHERE $id IS NULL OR a.id = $id DETACH DELETE r""",
           {"id": account_id})
    flat = [{"aid": r["id"], **k} for r in rows for k in r["risks"]]
    db.batched("""UNWIND $rows AS r MATCH (a:Account {id: r.aid})
                  CREATE (:Risk {id: r.rid, kind: r.key, label: r.label, points: r.points, detail: r.detail,
                          source: 'detective', open: true})-[:ON]->(a)""", flat)
    # Evidence links for the factors that have a natural cause in the graph.
    db.run("""MATCH (r:Risk {kind: 'unresolved_bug_tickets', source: 'detective'})-[:ON]->(a:Account)
              WHERE $id IS NULL OR a.id = $id
              MATCH (a)<-[:CONCERNS]-(:Ticket {source: 'support'})-[:SYMPTOM_OF]->(b:Bug) WHERE b.status <> 'Done'
              WITH DISTINCT r, b CREATE (r)-[:CAUSED_BY]->(b)""", {"id": account_id})
    db.run("""MATCH (r:Risk {kind: 'champion_departed', source: 'detective'})-[:ON]->(a:Account)
              WHERE $id IS NULL OR a.id = $id
              MATCH (c:Contact {isChampion: true})-[w:WORKS_AT]->(a) WHERE w.to IS NOT NULL
              CREATE (r)-[:CAUSED_BY]->(c)""", {"id": account_id})
    db.run("""MATCH (r:Risk {kind: 'promise_at_risk', source: 'detective'})-[:ON]->(a:Account)
              WHERE $id IS NULL OR a.id = $id
              MATCH (p:Promise {status: 'open'})-[:TO]->(a)
              CREATE (r)-[:CAUSED_BY]->(p)""", {"id": account_id})
    db.run("""MATCH (r:Risk {source: 'detective'})-[:ON]->(a:Account)
              WHERE r.kind IN ['competitor_signal', 'budget_signal', 'frustration_signal'] AND ($id IS NULL OR a.id = $id)
              MATCH (a)<-[:WITH_ACCOUNT]-(:Conversation)-[:EXPRESSES]->(s:Signal)
              WHERE (r.kind = 'competitor_signal' AND s.type = 'competitor_evaluation')
                 OR (r.kind = 'budget_signal' AND s.type = 'budget_pressure')
                 OR (r.kind = 'frustration_signal' AND s.type = 'frustration')
              CREATE (r)-[:CAUSED_BY]->(s)""", {"id": account_id})


def account_risk(account_id: str) -> dict:
    """Fresh, uncached breakdown for one account (no write-back)."""
    inputs, res = compute_inputs(account_id)
    a = _accounts(account_id)
    if not a:
        return {}
    ri = inputs.get(account_id, RiskInputs())
    ri.wallet_balance = a[0]["wallet"]
    risk, factors = score(ri)
    return {"risk": risk, "factors": factors_as_dicts(factors), "hint": hint(ri, risk, factors, a[0]["crm"]),
            "crm": a[0]["crm"], "silent": a[0]["crm"] >= SILENT_RISK_CRM_MIN and risk >= SILENT_RISK_RISK_MIN,
            "inputs": ri.__dict__, "asOf": as_of(), "queries": {k: QUERIES[k].strip() for k in QUERIES},
            "demoNow": DEMO_NOW.isoformat()}
