"""Graph-first answers for Ask: account risk, promises, bug fix dates and roadmap questions.

Each handler answers in 2-4 sentences from graph facts, returns its sources as
pills and the path it walked ("How I found this"). The newest evidence wins: a
Slack message ingested a minute ago outranks a ticket from last month.
"""

from __future__ import annotations

import re
from datetime import datetime

from . import db, textmatch
from .analysis import fmt_day, source_ref
from .config import now
from .health import risk, tools

RISK_RE = re.compile(r"\b(why|risk|risky|churn|health|healthy|happening|going on|worried|status)\b", re.I)
PROMISE_RE = re.compile(r"\b(promis\w*|commit\w*|owe|agreed|told them)\b", re.I)
FIX_RE = re.compile(r"\b(fix|fixed|fixing|bug|broken|eta|timeline)\b", re.I)
WHEN_RE = re.compile(r"\b(when (will|is|does|do)|eta|fix date|timeline|status of|any update|still broken|getting fixed)\b|"
                     r"\b(?:CHEER|LUM)-\d+\b", re.I)
ROADMAP_RE = re.compile(r"\b(coming|roadmap|planned|ship|shipping|launch|release|when (is|will)|available)\b", re.I)


def _pill(tag: str, ref: dict) -> dict:
    return {"tag": tag, **ref}


def _result(answer: str, sources: list[dict], path: list[dict], followups: list[str], mode: str = "graph") -> dict:
    segs = []
    for piece in re.split(r"(\[E\d+\])", answer):
        if not piece:
            continue
        m = re.fullmatch(r"\[(E\d+)\]", piece)
        segs.append({"source": m.group(1)} if m else {"text": piece})
    newest = max((s.get("at") or "" for s in sources), default=None) or None
    return {"answer": answer, "segments": segs, "sources": sources, "path": path, "mode": mode, "confidence": "high",
            "supported": True, "conflicts": [], "freshness": {"newest": newest, "label": fmt_day(newest) if newest else None},
            "followups": followups}


def _accounts(question: str) -> list[dict]:
    return [m for m in textmatch.mentions(question) if m["label"] == "Account"]


def _ago(iso: str | None) -> str:
    if not iso:
        return ""
    mins = int((now() - datetime.fromisoformat(iso)).total_seconds() // 60)
    if mins < 1:
        return "just now"
    if mins < 60:
        return f"{mins} min ago"
    if mins < 60 * 24:
        return f"{mins // 60} hour{'s' if mins // 60 != 1 else ''} ago"
    return fmt_day(iso) or ""


def account_risk(question: str) -> dict | None:
    accs = _accounts(question)
    if not accs or not RISK_RE.search(question) or PROMISE_RE.search(question):
        return None
    aid = accs[0]["id"]
    a = db.rows("MATCH (a:Account {id: $a}) RETURN a", {"a": aid}, readonly=True)
    if not a or a[0]["a"].get("crmHealthScore") is None:
        return None
    a = a[0]["a"]
    br = risk.account_risk(aid)
    ctx = tools.default_ctx()
    tk = tools.ticket_root_causes(ctx, aid).data
    ch = tools.champion_changes(ctx, aid).data
    sg = tools.signals(ctx, aid).data
    sources, bits = [], []
    dep = next((d for d in ch["departures"] if d["champion"]), None)
    if dep:
        c = db.rows("MATCH (c:Contact {id: $c}) RETURN c", {"c": dep["id"]}, readonly=True)[0]["c"]
        sources.append(_pill(f"E{len(sources) + 1}", source_ref(c)))
        succ = f" and {dep['successor']['name']} took over" if dep.get("successor") else ""
        bits.append(f"their main contact {dep['name']} left {dep['daysAgo']} days ago{succ} [E{len(sources)}]")
    cl = next((c for c in tk["clusters"] if c["open"]), None)
    if cl:
        b = db.rows("MATCH (b:Bug {id: $b}) RETURN b", {"b": cl["bugId"]}, readonly=True)[0]["b"]
        sources.append(_pill(f"E{len(sources) + 1}", source_ref(b)))
        bits.append(f"{len(cl['tickets'])} recent tickets point to {cl['bugId']} ({cl['bugKeyword']}), still {cl.get('jiraStatus') or cl['bugStatus']} "
                    f"at {cl['bugPriority']} [E{len(sources)}]")
    comp = next((s for s in sg["signals"] if s["type"] == "competitor_evaluation"), None)
    if comp:
        cv = db.rows("MATCH (c:Conversation {id: $c}) RETURN c", {"c": comp["conversationId"]}, readonly=True)[0]["c"]
        sources.append(_pill(f"E{len(sources) + 1}", source_ref(cv, highlight=comp["quote"])))
        bits.append(f"{comp['speaker'].split()[0]} said “{comp['quote']}” [E{len(sources)}]")
    lead = (f"{a['name']} has a {br['risk']}% risk of leaving, but HubSpot shows a healthy {a['crmHealthScore']}"
            if br.get("silent") else
            f"{a['name']} has a {br['risk']}% risk of leaving. Its HubSpot health is {a['crmHealthScore']}")
    others = [f["label"] for f in br["factors"] if f["key"] in ("promise_at_risk", "internal_owner_leaving", "wallet_low")]
    answer = lead + "." + "".join(f" {b[:1].upper()}{b[1:]}." for b in bits)
    if others:
        answer += " Other warning signs: " + ", ".join(others) + "."
    answer += f" Renewal is on {a['renewalDate']}."
    path = [{"kind": "question", "label": question}, {"kind": "customer", "label": a["name"], "id": aid}]
    if cl:
        path += [{"kind": "ticket", "label": f"{len(cl['tickets'])} tickets", "edge": "raised"},
                 {"kind": "bug", "label": cl["bugId"], "id": cl["bugId"], "nodeLabel": "Ticket", "edge": "points to"}]
        if cl.get("ownerId"):
            path.append({"kind": "person", "label": cl["owner"], "id": cl["ownerId"], "edge": "owned by"})
    return _result(answer, sources, path, [f"Who else is hit by {cl['bugId']}?" if cl else "What changed in the last 90 days?",
                                           f"What did we promise {a['name']}?", f"Who knows {a['name']}?"])


def promises(question: str) -> dict | None:
    accs = _accounts(question)
    if not accs or not PROMISE_RE.search(question):
        return None
    aid = accs[0]["id"]
    ps = tools.promises(tools.default_ctx(), aid).data["promises"]
    if not ps:
        return None
    name = db.rows("MATCH (a:Account {id: $a}) RETURN a.name AS n", {"a": aid}, readonly=True)[0]["n"]
    sources, lines = [], []
    for p in [p for p in ps if p["status"] in ("open", "superseded")][:4]:
        m = db.rows("MATCH (m:Meeting {id: $m}) RETURN m", {"m": p["meetingId"]}, readonly=True)
        sources.append(_pill(f"E{len(sources) + 1}", source_ref(m[0]["m"], highlight=p["quote"]) if m else
                             {"kind": "promise", "label": p["text"], "id": p["id"], "nodeLabel": "Promise", "title": p["text"]}))
        state = "at risk: " + p["why"].split("(")[-1].rstrip(")") if p["atRisk"] else (
            "replaced by a newer promise" if p["status"] == "superseded" else f"due {p['due']}")
        lines.append(f"{(p['madeBy'] or 'Someone').split()[0]} promised “{p['text']}” ({state}) [E{len(sources)}]")
    at_risk = sum(p["atRisk"] for p in ps)
    risk_note = "" if not at_risk else (" That one is at risk." if len(lines) == 1 else f" {at_risk} of them are at risk.")
    answer = f"Here are the open promises to {name}." + "".join(f" {line}." for line in lines) + risk_note
    path = [{"kind": "question", "label": question}, {"kind": "customer", "label": name, "id": aid},
            {"kind": "promise", "label": f"{len(lines)} promises", "edge": "promised to"}]
    return _result(answer, sources, path, [f"Why is {name} at risk?", "Is SSO coming in December?"])


def bug_fix(question: str) -> dict | None:
    if not FIX_RE.search(question) or not WHEN_RE.search(question):
        return None
    keys = re.findall(r"\b(?:CHEER|LUM)-\d+\b", question.upper())
    if keys:
        rows = db.rows("MATCH (b:Bug {id: $k}) RETURN b, 10.0 AS score", {"k": keys[0]}, readonly=True)
    else:
        terms = [w for w in re.findall(r"[a-z0-9]+", question.lower())
                 if len(w) > 2 and w not in {"when", "will", "the", "bug", "fixed", "fix", "be", "get", "for", "what", "is"}]
        if not terms:
            return None
        rows = db.rows("""CALL db.idx.fulltext.queryNodes('Ticket', $q) YIELD node, score
                          WHERE node:Bug RETURN node AS b, score ORDER BY score DESC LIMIT 1""",
                       {"q": "|".join(terms)}, readonly=True)
    if not rows:
        return None
    b = rows[0]["b"]
    owner = db.rows("MATCH (:Bug {id: $b})-[:OWNED_BY]->(p:Person) RETURN p.id AS id, p.name AS name", {"b": b["id"]},
                    readonly=True)
    msgs = db.rows("""MATCH (m:Message)-[:MENTIONS]->(:Ticket {id: $b}) OPTIONAL MATCH (a:Person)-[:SENT]->(m)
                      RETURN m, a.name AS who, a.id AS whoId ORDER BY m.t DESC LIMIT 1""", {"b": b["id"]}, readonly=True)
    sources = [_pill("E1", source_ref(b))]
    who = owner[0]["name"] if owner else "nobody yet"
    answer = (f"{b['id']} ({b['title']}) is in {b.get('jiraStatus') or b['status']} at {b.get('priority')}, owned by {who} [E1].")
    path = [{"kind": "question", "label": question}, {"kind": "bug", "label": b["id"], "id": b["id"], "nodeLabel": "Ticket"}]
    if msgs:
        m = msgs[0]["m"]
        ref = source_ref(m)
        sources.append(_pill("E2", {**ref, "at": m.get("at")}))
        answer = (f"Latest update ({_ago(m.get('at'))}): {msgs[0]['who']} posted in #{m.get('channelName')}: “{m['text']}” [E2]. "
                  + answer)
        path += [{"kind": "message", "label": f"#{m.get('channelName')} · {_ago(m.get('at'))}", "id": m["id"],
                  "nodeLabel": "Message", "edge": "mentioned in"},
                 {"kind": "person", "label": msgs[0]["who"], "id": msgs[0]["whoId"], "edge": "by"}]
    else:
        answer += " No fix date is recorded yet."
        if owner:
            answer += f" Ask {who.split()[0]}, who owns it."
            path.append({"kind": "person", "label": who, "id": owner[0]["id"], "edge": "owned by"})
    if b.get("workaround"):
        answer += f" Workaround: {b['workaround']}"
    return _result(answer, sources, path, [f"Who else is hit by {b['id']}?", "Which bug puts the most ARR at risk?"])


def roadmap(question: str) -> dict | None:
    if not ROADMAP_RE.search(question) or FIX_RE.search(question):
        return None
    terms = [w for w in re.findall(r"[A-Za-z][A-Za-z-]+", question)
             if w.lower() not in {"is", "are", "coming", "in", "the", "when", "will", "be", "available", "it", "we", "a",
                                  "december", "january", "q1", "q2", "q3", "q4", "planned", "roadmap", "on", "for"}]
    if not terms:
        return None
    rows = db.rows("""CALL db.idx.fulltext.queryNodes('RoadmapItem', $q) YIELD node, score
                      OPTIONAL MATCH (node)-[:OWNED_BY]->(o:Person)
                      RETURN node AS i, o.name AS owner, o.id AS ownerId, score ORDER BY score DESC LIMIT 5""",
                   {"q": "|".join(terms)}, readonly=True)
    if not rows:
        return None
    low = [t.lower() for t in terms]
    rows.sort(key=lambda r: -(r["score"] + 2 * sum(t in r["i"]["title"].lower() for t in low)))
    i, owner = rows[0]["i"], rows[0]["owner"]
    ref = source_ref(i)
    moved = (f", moved from {i['originalLabel']}" if i.get("originalLabel") and i["originalLabel"] != i.get("etaLabel") else "")
    if i["status"] == "shipped":
        answer = f"{i['title']} shipped: {i.get('etaLabel')} [E1]."
    else:
        answer = f"{i['title']} is {i['status'].replace('_', ' ')}. Expected: {i.get('etaLabel')}{moved} [E1]."
    if i.get("internalNote"):
        answer += f" Internal note: {i['internalNote']}"
    if owner:
        answer += f" Owner: {owner}."
    path = [{"kind": "question", "label": question}, {"kind": "roadmap", "label": i["title"], "id": i["id"], "nodeLabel": "RoadmapItem"}]
    if owner:
        path.append({"kind": "person", "label": owner, "id": rows[0]["ownerId"], "edge": "owned by"})
    return _result(answer, [_pill("E1", ref)], path, ["What did we promise Northwind Foods?"])


HANDLERS = [promises, account_risk, bug_fix, roadmap]


def try_answer(question: str) -> dict | None:
    for h in HANDLERS:
        try:
            out = h(question)
        except Exception:  # noqa: BLE001 - fall back to general retrieval
            out = None
        if out:
            return out
    return None
