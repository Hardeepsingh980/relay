"""During the call: trigger detection and card building.

Pipeline per transcript segment (what a meeting bot would stream):
    segment -> detect triggers (rules, ~1 ms) -> graph lookup (Cypher) -> card

Cards are neutral (answers, roadmap status, bug status, experts), amber (a promise
the rep just made) or red (a risk). Every card carries its source and the Cypher
that produced it. When the evidence doesn't answer a question the card says
"Not sure" and names who to ask, instead of guessing.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date, timedelta

from .. import db
from ..health import signals as sig_rules
from ..health import tools

FEATURE_TERMS = {
    "F-REPORTS": ["report", "reports", "export", "exports", "csv", "download"],
    "F-ACCESS": ["login", "log in", "otp", "sso", "single sign-on", "password", "2fa"],
    "F-INBOX": ["inbox", "chats", "agents"],
    "F-CAMPAIGNS": ["campaign", "campaigns", "broadcast", "broadcasts"],
    "F-TEMPLATES": ["template", "templates", "carousel", "carousels"],
    "F-WORKFLOWS": ["workflow", "workflows", "chatbot", "flow"],
    "F-SHOPIFY": ["shopify", "cod", "cart", "abandoned"],
    "F-AI": ["ai assistant", "assistant", "hindi"],
    "F-VOICE": ["voice", "calls"],
    "F-API": ["api", "webhook", "webhooks", "developer"],
    "F-ADS": ["ads", "click-to-whatsapp"],
}
COMPLAINT_RE = re.compile(r"\b(keep(s)? failing|broken|not working|doesn'?t work|can'?t|cannot|fail(s|ing|ed)?|stuck|"
                          r"error|empty|by hand|headache)\b", re.I)
QUESTION_RE = re.compile(r"\?|\b(can we|can i|is there|does it|do you|how do)\b", re.I)
ROADMAP_RE = re.compile(r"\b(coming(?! back)|roadmap|planned|release|launch|available|when will|by (january|february|march|"
                        r"april|may|june|july|august|september|october|november|december)|in (january|february|march|"
                        r"april|may|june|july|august|september|october|november|december|q[1-4]))\b", re.I)
OBJECTION_RE = re.compile(r"\b(cheaper|too expensive|expensive|pricing|price|budget|competitor|other platforms?|"
                          r"platforms? we looked at|alternatives?)\b", re.I)
FIX_WHEN_RE = re.compile(r"\b(when will (that|this|it) (actually )?be fixed|fix date|when.*fixed|eta)\b", re.I)
PROMISE_RE = re.compile(r"\b(I'?ll|I will|we'?ll|we will|I'?m going to)\b\s+(?P<what>[^.?!]+)", re.I)
DUE_RE = re.compile(r"\b(by|before|on|this|next)\s+(?P<when>monday|tuesday|wednesday|thursday|friday|week|month|"
                    r"tomorrow|eod|end of (?:the )?week|end of (?:the )?month)\b|\b(?P<q>q[1-4])\b|\btomorrow\b", re.I)
CONSENT_RE = re.compile(r"\b(recorded|recording|takes notes|note-?taker)\b", re.I)
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


@dataclass
class CallContext:
    account_id: str
    account_name: str
    call_day: date
    internal_emails: set[str]
    rep_id: str | None = None
    last_complaint: dict | None = None
    seen: set[str] = field(default_factory=set)
    promises: list[dict] = field(default_factory=list)


def due_date(text: str, call_day: date) -> str | None:
    """Resolve "by Friday", "this week", "tomorrow" (preferred) or "Q1" relative to the call date."""
    found = list(DUE_RE.finditer(text))
    if not found:
        return None
    m = next((x for x in found if not x.group("q")), found[0])
    if m.group("q"):
        q = int(m.group("q")[1])
        year = call_day.year + (1 if q * 3 < call_day.month else 0)
        end = date(year, q * 3, 31 if q in (1, 4) else 30)
        return end.isoformat()
    w = (m.group("when") or "tomorrow").lower()
    if w == "tomorrow":
        return (call_day + timedelta(days=1)).isoformat()
    if w in WEEKDAYS:
        delta = (WEEKDAYS.index(w) - call_day.weekday()) % 7 or 7
        return (call_day + timedelta(days=delta)).isoformat()
    if w in ("week", "end of week", "end of the week", "eod"):
        nxt = m.group(1).lower() == "next"
        return (call_day + timedelta(days=(4 - call_day.weekday()) % 7 + (7 if nxt else 0))).isoformat()
    if "month" in w:
        nxt = (call_day.replace(day=28) + timedelta(days=4))
        return (nxt - timedelta(days=nxt.day)).isoformat()
    return None


def _features(text: str) -> list[str]:
    t = text.lower()
    return [f for f, terms in FEATURE_TERMS.items() if any(re.search(rf"(?<![\w-]){re.escape(x)}(?![\w-])", t) for x in terms)]


def _card(kind: str, tone: str, title: str, body: str, source: dict | None, queries: list, **extra) -> dict:
    return {"kind": kind, "tone": tone, "title": title, "body": body, "source": source,
            "queries": [{"cypher": q.cypher, "ms": q.ms, "rows": len(q.rows)} for q in queries], **extra}


def _q(cypher: str, params: dict, log: list) -> list[dict]:
    r = db.timed(cypher, params)
    log.append(r)
    return r.rows


# ------------------------------------------------------------ card builders

def bug_card(ctx: CallContext, feature: str) -> dict | None:
    log: list = []
    rows = _q("""MATCH (a:Account {id: $a})<-[:CONCERNS]-(t:Ticket {source: 'support'})-[:SYMPTOM_OF]->(b:Bug)-[:AFFECTS]->(:Feature {id: $f})
                 WHERE b.status <> 'Done'
                 OPTIONAL MATCH (b)-[:OWNED_BY]->(o:Person)
                 RETURN b.id AS id, b.title AS title, b.jiraStatus AS status, b.priority AS priority, b.url AS url,
                        b.workaround AS workaround, o.id AS ownerId, o.name AS owner, count(t) AS tickets
                 ORDER BY tickets DESC LIMIT 1""", {"a": ctx.account_id, "f": feature}, log)
    if not rows:
        return None
    b = rows[0]
    others = _q("""MATCH (:Bug {id: $b})<-[:SYMPTOM_OF]-(:Ticket)-[:CONCERNS]->(x:Account) WHERE x.id <> $a
                   RETURN count(DISTINCT x) AS n, sum(DISTINCT x.arr) AS arr""", {"b": b["id"], "a": ctx.account_id}, log)[0]
    ctx.last_complaint = b
    body = (f"{b['title']}. Jira: {b['status']} · {b['priority']} · owner {b['owner']}. {ctx.account_name.split()[0]} raised "
            f"{b['tickets']} ticket{'s' if b['tickets'] != 1 else ''}. {others['n']} other accounts "
            f"({tools.inr(others['arr'] or 0)} ARR) have the same bug.")
    if b["workaround"]:
        body += f" Workaround: {b['workaround']}"
    return _card("bug", "neutral", f"{b['id']}: known bug, no fix date yet", body,
                 {"label": f"Jira {b['id']}", "kind": "bug", "id": b["id"], "url": b["url"]}, log,
                 entity={"bugId": b["id"], "ownerId": b["ownerId"], "owner": b["owner"]})


def _question(text: str) -> str:
    """The sentence(s) that carry the question, so context words don't steer retrieval."""
    qs = [p for p in re.split(r"(?<=[.!?])\s+", text) if "?" in p]
    return " ".join(qs) or text


def roadmap_cards(ctx: CallContext, text: str) -> list[dict]:
    log: list = []
    terms = [w for w in re.findall(r"[A-Za-z][A-Za-z-]{1,}", _question(text)) if w.lower() not in STOP_WORDS]
    if not terms:
        return []
    rows = _q("""CALL db.idx.fulltext.queryNodes('RoadmapItem', $q) YIELD node, score
                 OPTIONAL MATCH (node)-[:OWNED_BY]->(o:Person)
                 RETURN node AS i, o.name AS owner, score ORDER BY score DESC LIMIT 5""",
              {"q": " | ".join(terms)}, log)
    if not rows:
        return []
    low = [t.lower() for t in terms]
    rows.sort(key=lambda r: -(r["score"] + 2 * sum(t in r["i"]["title"].lower() for t in low)))
    i, owner = rows[0]["i"], rows[0]["owner"]
    out = []
    if i["status"] in ("delayed", "cut"):
        title = f"{i['title'].split(' (')[0].split(' and ')[0]} moved to {i.get('etaLabel')}"
        guidance = i.get("internalNote") or ""
        dont = re.search(r"Don't commit[^.]*\.", guidance)
        body = (f"Originally {i.get('originalLabel')}, now {i.get('etaLabel')}. "
                f"{dont.group(0) if dont else ''} Owner: {owner}.").strip()
        tone = "amber"
    elif i["status"] == "shipped":
        title, body, tone = f"{i['title']}: shipped", f"{i.get('etaLabel')}. {i.get('publicNote') or ''}".strip(), "neutral"
    else:
        title = f"{i['title']}: {i['status'].replace('_', ' ')}, {i.get('etaLabel')}"
        body, tone = f"{i.get('publicNote') or ''} Owner: {owner}.".strip(), "neutral"
    out.append(_card("roadmap", tone, title, body, {"label": "Product roadmap", "kind": "roadmap", "id": i["id"],
                                                     "url": i.get("url")}, log, entity={"roadmapId": i["id"]}))
    prom = _q("""MATCH (p:Promise {status: 'open'})-[:DEPENDS_ON]->(:RoadmapItem {id: $i}), (p)-[:TO]->(:Account {id: $a})
                 OPTIONAL MATCH (x:Person)-[:MADE]->(p)
                 OPTIONAL MATCH (m:Meeting)-[:PRODUCED]->(p)
                 RETURN p.id AS id, p.text AS text, p.due AS due, x.name AS by, m.title AS meeting, m.date AS at""",
              {"i": i["id"], "a": ctx.account_id}, log)
    for p in prom:
        if i["status"] in ("delayed", "cut") and (i.get("eta") or "9999") > p["due"]:
            out.append(_card("risk", "red", "Promise at risk",
                             f"{p['by']} promised “{p['text']}” at {p['meeting'].split(':')[-1].strip()} "
                             f"({p['at'][:10]}). The roadmap now says {i.get('etaLabel')}.",
                             {"label": "Meeting notes", "kind": "promise", "id": p["id"]}, log,
                             entity={"promiseId": p["id"], "roadmapId": i["id"]}))
    return out


STOP_WORDS = set("""is are was the a an to of for in on at do does did we our you your it this that can could would
will be by with from and or not coming december january february march april may june july august september october
november q1 q2 q3 q4 last time mentioned also have has there any""".split())


def answer_card(ctx: CallContext, text: str) -> dict | None:
    """Product question: answer from release notes / FAQ / roadmap, with the source. Never guess."""
    log: list = []
    terms = [w for w in re.findall(r"[A-Za-z][A-Za-z-]{2,}", _question(text)) if w.lower() not in STOP_WORDS | {"send", "push", "wants", "straight"}]
    if not terms:
        return None
    shipped = _q("""CALL db.idx.fulltext.queryNodes('RoadmapItem', $q) YIELD node, score
                    WHERE node.status = 'shipped' RETURN node AS i, score ORDER BY score DESC LIMIT 1""",
                 {"q": " | ".join(terms)}, log)
    docs = _q("""CALL db.idx.fulltext.queryNodes('Doc', $q) YIELD node, score
                 WHERE node.kind IN ['release-notes', 'faq'] RETURN node AS d, score ORDER BY score DESC LIMIT 1""",
              {"q": " | ".join(terms)}, log)
    if docs:
        d = docs[0]["d"]
        sentence = _best_sentence(d["body"], terms)
        title = "Yes: shipped" if shipped else "From the product FAQ"
        if shipped:
            i = shipped[0]["i"]
            when = i.get("etaLabel") or "Shipped"
            title = f"Yes: {i['title']}, {when[0].lower()}{when[1:]}"
        return _card("answer", "neutral", title, sentence, {"label": d["title"], "kind": "doc", "id": d["id"], "url": d.get("url")},
                     log, copy=sentence)
    owner = _q("""MATCH (f:Feature)-[:OWNED_BY]->(p:Person) WHERE toLower(f.name) CONTAINS toLower($t)
                  RETURN p.name AS name LIMIT 1""", {"t": terms[0]}, log)
    who = owner[0]["name"] if owner else "the product team"
    return _card("answer", "neutral", "Not sure", f"Nothing in the docs answers this. Ask {who} before you promise anything.",
                 None, log)


def _best_sentence(body: str, terms: list[str]) -> str:
    """The FAQ answer or release-note bullet that best matches the question (answer text only)."""
    parts = [p.strip(" -#") for p in re.split(r"\n\s*\n|\n(?=- )", body) if len(p.strip()) > 20 and not p.startswith("# ")]
    lows = [t.lower() for t in terms]
    best = max(parts, key=lambda p: sum(t in p.lower() for t in lows)) if parts else body[:200]
    qa = re.match(r"\*\*(?P<q>[^*]+\?)\*\*\s*(?P<a>.+)", best, re.S)
    text = qa.group("a") if qa else best
    return re.sub(r"\*\*", "", text).strip()[:300]


def objection_card(ctx: CallContext) -> dict:
    log: list = []
    rows = _q("""MATCH (b:Playbook) WHERE b.trigger CONTAINS 'competitor'
                 OPTIONAL MATCH (b)-[:WORKED_FOR]->(a:Account)
                 OPTIONAL MATCH (b)-[:SOURCED_FROM]->(d:Doc)
                 RETURN b.name AS name, b.steps AS steps, b.outcome AS outcome, collect(a.name) AS won, d.id AS doc,
                        d.title AS docTitle, d.url AS url LIMIT 1""", {}, log)
    import json
    if not rows:
        return _card("objection", "neutral", "Price concern", "No sales guide found for this. Ask the account executive.", None, log)
    r = rows[0]
    steps = json.loads(r["steps"])
    return _card("objection", "neutral", "Price concern: what worked before",
                 " · ".join(steps) + f". Result: {r['outcome']} (for example {', '.join(r['won'][:2])}).",
                 {"label": r["docTitle"], "kind": "doc", "id": r["doc"], "url": r["url"]}, log, copy="\n".join(steps))


def warm_path(rep_id: str | None, expert_id: str, log: list) -> dict | None:
    """Shortest path through work the rep and the expert share, so the ping can say how they're connected."""
    if not rep_id or rep_id == expert_id:
        return None
    rows = _q(tools.WARM_PATH, {"a": rep_id, "b": expert_id}, log)
    if not rows or not rows[0]["hops"]:
        return None
    hops = rows[0]["hops"]
    middle = hops[1:-1]
    first = hops[-1]["name"].split()[0]
    if len(middle) == 1 and middle[0]["label"] == "Ticket":
        summary = f"You both worked on “{middle[0]['name']}”. Mention it when you message {first}."
    elif len(middle) == 1 and middle[0]["label"] == "Team":
        summary = f"You are both on the {middle[0]['name']} team."
    elif len(middle) == 1 and middle[0]["label"] == "Person":
        summary = f"{middle[0]['name']} works with you both and can ask {first} for you."
    else:
        summary = "Closest link through shared work: " + " → ".join(h["id"] if h["label"] == "Ticket" else h["name"] for h in hops) + "."
    return {"hops": hops, "length": len(hops) - 1, "summary": summary}


def expert_card(ctx: CallContext) -> dict | None:
    b = ctx.last_complaint
    if not b or not b.get("ownerId"):
        return None
    log: list = []
    p = _q("MATCH (p:Person {id: $p}) RETURN p.name AS name, p.role AS role, p.slackId AS slack, p.leaving AS leaving",
           {"p": b["ownerId"]}, log)[0]
    first = p["name"].split()[0]
    path = warm_path(ctx.rep_id, b["ownerId"], log)
    via = f" {path['summary']}" if path else ""
    return _card("expert", "neutral", f"Ask {first}: owns {b['id']}",
                 f"{p['name']} ({p['role']}) owns {b['id']}. Ask {first} for a fix date. Do not guess on the call.{via}",
                 {"label": "Jira assignee", "kind": "person", "id": b["ownerId"]}, log, path=path,
                 action={"kind": "ping", "to": p["name"], "toId": b["ownerId"], "slack": p["slack"],
                         "message": f"Hi {first}, I am on a call with {ctx.account_name} about {b['id']} ({b['title']}). "
                                    f"Can you share a fix date by Thursday? Then I can update them by Friday."})


def ask_card(ctx: CallContext, text: str) -> dict | None:
    """A typed or spoken question no rule matched: answer it with Ask (graph retrieval, then Gemini)."""
    from ..ask import ask as ask_relay
    t0 = time.perf_counter()
    a = ask_relay(text, ctx.rep_id)
    if not a.get("answer") or a.get("mode") in ("empty", "no-evidence"):
        return None
    body = re.sub(r"\s*\[E\d+\]", "", a["answer"]).strip()
    src = (a.get("sources") or [None])[0]
    by = "Gemini, from the graph" if a.get("mode") == "llm" else "the graph"
    card = _card("answer", "neutral", "Answer from Relay", body,
                 {"label": src.get("label") or src.get("title") or "Relay graph", "kind": src.get("kind", "doc"),
                  "id": src.get("id")} if src else {"label": "Relay graph", "kind": "graph", "id": None}, [],
                 copy=body, answeredBy=by)
    card["queries"] = [{"cypher": f"ask({text!r}) via {by}", "ms": round((time.perf_counter() - t0) * 1000, 1), "rows": len(a.get("sources") or [])}]
    return card


def risk_cards(ctx: CallContext, text: str, speaker: str, broad: bool = False) -> list[dict]:
    log: list = []
    out = []
    for s in sig_rules.extract(text, broad=broad):
        if s["type"] not in ("competitor_evaluation", "frustration", "budget_pressure"):
            continue
        prior = _q("""MATCH (:Account {id: $a})<-[:WITH_ACCOUNT]-(c:Conversation)-[:EXPRESSES]->(x:Signal {type: $t})
                      RETURN c.occurredAt AS at, x.quote AS quote ORDER BY at DESC LIMIT 1""",
                   {"a": ctx.account_id, "t": s["type"]}, log)
        label = tools.SIGNAL_LABELS[s["type"]]
        body = f"{speaker}: “{s['quote']}”"
        if prior:
            body += f" Earlier mention: “{prior[0]['quote']}” ({prior[0]['at'][:10]})."
        out.append(_card("risk", "red", f"Risk: {label.lower()}", body, {"label": "This call (extracted)", "kind": "signal",
                                                                       "id": None}, log, signal=s))
    return out


def promise_card(ctx: CallContext, text: str, speaker_name: str, speaker_id: str | None) -> dict | None:
    m = PROMISE_RE.search(text)
    if not m:
        return None
    due = due_date(text, ctx.call_day)
    what = m.group("what").strip().rstrip(",")
    if not due and not re.search(r"\b(send|share|confirm|get you|follow up|set up)\b", what, re.I):
        return None
    log: list = []
    dep = None
    low = text.lower()
    if re.search(r"\b(fix|fixed|export)\b", low) and ctx.last_complaint:
        dep = {"kind": "Bug", "id": ctx.last_complaint["id"]}
    elif re.search(r"\b(sso|q1)\b", low):
        r = _q("""CALL db.idx.fulltext.queryNodes('RoadmapItem', 'SSO') YIELD node RETURN node.id AS id LIMIT 1""", {}, log)
        dep = {"kind": "RoadmapItem", "id": r[0]["id"]} if r else None
    clean = re.sub(r"\s+", " ", what)
    clean = clean[0].upper() + clean[1:]
    p = {"text": clean, "due": due or (ctx.call_day + timedelta(days=4 - ctx.call_day.weekday())).isoformat(),
         "madeBy": speaker_name, "madeById": speaker_id, "dependsOn": dep, "quote": text}
    ctx.promises.append(p)
    return _card("promise", "amber", "Promise logged", f"{speaker_name.split()[0]}: {clean}. Due {p['due']}."
                 + (f" Linked to {dep['id']}." if dep else ""), {"label": "This call", "kind": "promise", "id": None},
                 log, promise=p, copy=clean)


def detect(ctx: CallContext, seg: dict, index: int) -> list[dict]:
    """All cards for one transcript segment, each stamped with its own latency."""
    text, email, name = seg["text"], seg["speaker_email"], seg["speaker_name"]
    internal = email in ctx.internal_emails
    cards: list[tuple[float, dict]] = []

    def add(fn, *args):
        t0 = time.perf_counter()
        res = fn(*args)
        ms = (time.perf_counter() - t0) * 1000
        for c in (res if isinstance(res, list) else [res] if res else []):
            key = f"{c['kind']}:{c['title']}:{c['body'][:80]}"
            if key in ctx.seen:
                continue
            ctx.seen.add(key)
            cards.append((ms, c))

    if internal:
        if index == 0 and CONSENT_RE.search(text):
            cards.append((0.1, _card("consent", "neutral", "Consent noted",
                                     "Your team announced recording and note-taking at the start of the call.", None, [])))
        sp = db.rows("MATCH (p:Person {email: $e}) RETURN p.id AS id", {"e": email}, readonly=True)
        add(promise_card, ctx, text, name, sp[0]["id"] if sp else None)
    else:
        feats = _features(text)
        if QUESTION_RE.search(text) and FIX_WHEN_RE.search(text):
            add(expert_card, ctx)
        elif ROADMAP_RE.search(text) and QUESTION_RE.search(text):
            add(roadmap_cards, ctx, text)
        elif QUESTION_RE.search(text) and feats:
            add(answer_card, ctx, text)
        if COMPLAINT_RE.search(text) and feats:
            for f in feats:
                add(bug_card, ctx, f)
        if OBJECTION_RE.search(text):
            add(objection_card, ctx)
        add(risk_cards, ctx, text, name, bool(seg.get("typed")))
        if seg.get("typed") and not cards and "?" in text:
            add(ask_card, ctx, text)
    out = []
    for ms, c in cards:
        c.update({"segment": index, "t": seg["t"], "speaker": name, "latencyMs": round(ms + 0.5, 1)})
        out.append(c)
    return out
