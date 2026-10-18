"""Graph analysis: single points of knowledge failure, evidence, successors.

The core question is the PRD's "remove this person" query: which items does
this person know strongly, where no other active person has a credible link?
FalkorDB 6 has no EXISTS {} subqueries, so the alternate check is an OPTIONAL
MATCH plus an aggregate.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from . import db, tenants
from .config import DEMO_NOW, IST
from .scoring import ALTERNATE, STRONG

KNOWLEDGE_EDGES = "KNOWS|DECIDED"
ITEM_LABELS = ("System", "Account", "Decision", "Workaround")
TYPE_ORDER = {"System": 0, "Account": 1, "Decision": 2, "Workaround": 3}
CRITICALITY = {"critical": 1.0, "high": 0.8, "medium": 0.6, "low": 0.4}
ACTIVE = ["active", "joining"]
EIGHT_MONTHS_AGO = DEMO_NOW.replace(month=DEMO_NOW.month - 8, hour=0, minute=0)

UNIQUE_QUERY = f"""
MATCH (r:Person {{id: $pid}})-[k:{KNOWLEDGE_EDGES}]->(item)
WHERE k.score > $strong AND (item:System OR item:Account OR item:Decision OR item:Workaround)
OPTIONAL MATCH (other:Person)-[k2:{KNOWLEDGE_EDGES}]->(item)
WHERE other.id <> r.id AND other.status IN $active AND k2.score > $alt
WITH r, k, item, count(other) AS alternates
WHERE alternates = 0
OPTIONAL MATCH (m:Person)-[dm:DISMISSED]->(item)
RETURN labels(item)[0] AS type, item.id AS id, coalesce(item.name, item.summary) AS title,
       k.score AS score, count(dm) AS dismissals
ORDER BY score DESC
"""

COMPANY_QUERY = f"""
MATCH (r:Person)-[k:{KNOWLEDGE_EDGES}]->(item)
WHERE r.status = 'active' AND k.score > $strong
  AND (item:System OR item:Account OR item:Decision OR item:Workaround)
OPTIONAL MATCH (other:Person)-[k2:{KNOWLEDGE_EDGES}]->(item)
WHERE other.id <> r.id AND other.status IN $active AND k2.score > $alt
WITH r, item, count(other) AS alternates
WHERE alternates = 0
OPTIONAL MATCH (:Person)-[dm:DISMISSED]->(item)
WITH r, item, labels(item)[0] AS lbl, count(dm) AS dismissals
WHERE dismissals = 0
RETURN r.id AS id, r.name AS name, r.role AS role, r.team AS team, count(item) AS unique,
       collect(lbl) AS types
ORDER BY unique DESC, name
"""

THIN_QUERY = f"""
MATCH (r:Person {{id: $pid}})-[k:{KNOWLEDGE_EDGES}]->(item)
WHERE k.score > $alt AND (item:System OR item:Account OR item:Decision OR item:Workaround)
MATCH (other:Person)-[k2:{KNOWLEDGE_EDGES}]->(item)
WHERE other.id <> r.id AND other.status IN $active AND k2.score > $alt
WITH item, collect(other.name) AS others
WHERE size(others) = 1
RETURN labels(item)[0] AS type, item.id AS id, coalesce(item.name, item.summary) AS title, others[0] AS remaining
"""


def _params(**kw) -> dict[str, Any]:
    return {"strong": STRONG, "alt": ALTERNATE, "active": ACTIVE, **kw}


def fmt_day(t: float | str | None) -> str | None:
    if t is None:
        return None
    d = datetime.fromtimestamp(t, IST) if isinstance(t, (int, float)) else datetime.fromisoformat(t)
    return f"{d.day} {d:%b %Y}"


def iso(t: float | None) -> str | None:
    return datetime.fromtimestamp(t, IST).isoformat() if t else None


# ---------------------------------------------------------------- sources

def source_ref(node: dict, highlight: str | None = None) -> dict:
    """A uniform 'source pill' for any evidence node."""
    label = node.get("_labels", [None])[0]
    nid = node.get("id")
    if label == "Message":
        kind, title = "slack", f"#{node.get('channelName')}" if node.get("channelName") != "Direct message" else "Direct message"
        when, excerpt = node.get("t"), node.get("text")
    elif label == "Doc":
        kind, title = "doc", node.get("title")
        when, excerpt = node.get("t"), (node.get("body") or "")[:400]
    elif label == "Ticket" and node.get("source") == "support":
        kind, title = "support", f"{nid} · {node.get('title')}"
        when, excerpt = node.get("t"), node.get("description")
    elif label == "Ticket":
        kind, title = "jira", f"{nid} · {node.get('title')}"
        when, excerpt = node.get("t"), node.get("description")
    elif label == "Conversation":
        kind, title = "conversation", f"{node.get('channel')} · {node.get('summary') or ''}"[:80]
        when, excerpt = node.get("t"), node.get("text")
    elif label == "Contact":
        kind, title = "crm", f"HubSpot · {node.get('name')}"
        when, excerpt = None, f"{node.get('title') or node.get('role')} at {node.get('org')}" + (
            f" · left {node.get('leftAt')}" if node.get("leftAt") else "")
    elif label == "RoadmapItem":
        kind, title = "roadmap", f"Roadmap · {node.get('title')}"
        when, excerpt = node.get("t"), node.get("internalNote") or node.get("publicNote")
    elif label == "Promise":
        kind, title = "promise", f"Promise · {node.get('text')}"
        when, excerpt = node.get("t"), node.get("quote")
    elif label == "Meeting":
        kind, title = "meeting", node.get("title")
        when, excerpt = node.get("t"), node.get("notes")
    elif label == "Commit":
        kind, title = "github", f"{(node.get('repo') or '').split('/')[-1]} · {nid[:7]}"
        when, excerpt = node.get("t"), node.get("message")
    elif label == "PullRequest":
        kind, title = "github", f"{(node.get('repo') or '').split('/')[-1]} #{node.get('number')}"
        when, excerpt = node.get("t"), node.get("title")
    elif label == "Knowledge":
        kind, title = "handover", "Handover answer"
        when, excerpt = node.get("capturedAt"), node.get("answer")
    else:
        kind, title, when, excerpt = "other", nid, None, None
    day = fmt_day(when)
    return {"kind": kind, "id": nid, "nodeLabel": label, "title": title, "label": f"{title} · {day}" if day else title,
            "at": iso(when) if isinstance(when, (int, float)) else when, "excerpt": excerpt, "url": node.get("url"),
            "freshness": node.get("freshness"), "highlight": highlight}


def get_source(label: str, sid: str) -> dict | None:
    """Full content for the source drawer: the original text plus thread/context."""
    if label not in ("Message", "Doc", "Ticket", "Meeting", "Commit", "PullRequest", "Knowledge", "Conversation",
                     "Contact", "RoadmapItem", "Promise"):
        return None
    rows = db.rows(f"MATCH (s:{label} {{id: $id}}) RETURN s", {"id": sid}, readonly=True)
    if not rows:
        return None
    node = rows[0]["s"]
    ref = source_ref(node)
    out = {**ref, "available": False,
           "availability": f"Demo source. The original exists only in Relay's sample {tenants.current().name} workspace."}
    if label == "Message":
        thread = db.rows("""MATCH (m:Message {threadId: $tid}) OPTIONAL MATCH (a)-[:SENT]->(m)
                            RETURN m.id AS id, m.text AS text, m.t AS t, coalesce(a.name, 'Unknown') AS author,
                                   labels(a)[0] AS authorType, coalesce(a.org, '') AS org
                            ORDER BY m.t""", {"tid": node["threadId"]}, readonly=True)
        out["thread"] = [{"id": r["id"], "text": r["text"], "at": iso(r["t"]), "author": r["author"],
                          "external": r["authorType"] == "Contact", "org": r["org"], "focus": r["id"] == sid}
                         for r in thread]
        out["excerpt"] = node.get("text")
    elif label == "Doc":
        a = db.rows("MATCH (p:Person)-[:AUTHORED]->(d:Doc {id: $id}) RETURN p.name AS name, p.status AS status",
                    {"id": sid}, readonly=True)
        out.update({"body": node.get("body"), "author": a[0]["name"] if a else None,
                    "authorStatus": a[0]["status"] if a else None, "staleReason": node.get("staleReason"),
                    "updatedAt": node.get("updatedAt")})
    elif label == "Meeting":
        tr = json.loads(node.get("transcript") or "[]")
        names = {r["id"]: r["name"] for r in db.rows("MATCH (p) WHERE p:Person OR p:Contact RETURN p.id AS id, p.name AS name",
                                                     readonly=True)}
        out.update({"transcript": [{"speaker": x.get("speakerName") or names.get(x["speaker"], "Unknown"), "text": x["text"]}
                                   for x in tr], "notes": node.get("notes")})
    elif label == "Ticket":
        r = db.rows("""MATCH (t:Ticket {id: $id}) OPTIONAL MATCH (t)-[:OWNED_BY]->(a:Person)
                       RETURN t.status AS status, a.name AS assignee, t.comments AS comments""", {"id": sid}, readonly=True)[0]
        out.update({"status": r["status"], "assignee": r["assignee"], "comments": json.loads(r["comments"] or "[]"),
                    "description": node.get("description")})
    elif label == "Commit":
        a = db.rows("MATCH (p:Person)-[:AUTHORED]->(c:Commit {id: $id}) RETURN p.name AS name", {"id": sid}, readonly=True)
        out.update({"author": a[0]["name"] if a else None, "repo": node.get("repo"), "message": node.get("message")})
    elif label == "Knowledge":
        out.update({"available": True, "availability": "Answered in Relay during a handover.",
                    "question": node.get("question"), "answer": node.get("answer")})
    elif label == "Conversation":
        who = db.rows("MATCH (x)-[:PARTICIPATED_IN]->(:Conversation {id: $id}) RETURN x.name AS n", {"id": sid}, readonly=True)
        out.update({"body": node.get("text"), "author": ", ".join(w["n"] for w in who) or None})
    elif label in ("Contact", "RoadmapItem", "Promise"):
        fields = {"Contact": ["title", "role", "org", "email", "emailStatus", "joinedAt", "leftAt"],
                  "RoadmapItem": ["status", "etaLabel", "originalLabel", "publicNote", "internalNote"],
                  "Promise": ["text", "due", "status", "madeAt", "quote", "extraction"]}[label]
        out["body"] = "\n".join(f"{f}: {node.get(f)}" for f in fields if node.get(f) not in (None, ""))
    return out


# ------------------------------------------------------------- unique items

def unique_knowledge(pid: str) -> list[dict]:
    return db.rows(UNIQUE_QUERY, _params(pid=pid), readonly=True)


def thin_coverage(pid: str) -> list[dict]:
    return db.rows(THIN_QUERY, _params(pid=pid), readonly=True)


def company_risk() -> dict:
    people = db.rows(COMPANY_QUERY, _params(), readonly=True)
    total = sum(p["unique"] for p in people)
    by_type: dict[str, int] = {}
    for p in people:
        for t in p["types"]:
            by_type[t] = by_type.get(t, 0) + 1
        p["byType"] = {t: p["types"].count(t) for t in ITEM_LABELS if t in p["types"]}
        del p["types"]
    return {"singlePointsOfFailure": total, "byType": by_type, "people": people}


def _item_node(item_id: str) -> dict | None:
    rows = db.rows("MATCH (i) WHERE i.id = $id AND (i:System OR i:Account OR i:Decision OR i:Workaround) RETURN i",
                   {"id": item_id}, readonly=True)
    return rows[0]["i"] if rows else None


def item_systems(item_id: str) -> list[dict]:
    """Systems an item is about: the system itself, a decision/workaround's ABOUT
    targets, or for a customer the systems its decisions and workarounds touch."""
    node = _item_node(item_id)
    if not node:
        return []
    label = node["_labels"][0]
    if label == "System":
        return [node]
    if label == "Account":
        q = """MATCH (:Account {id: $id})<-[:ABOUT]-(k)-[:ABOUT]->(s:System) RETURN DISTINCT s"""
    else:
        q = """MATCH (i {id: $id})-[:ABOUT]->(s:System) RETURN DISTINCT s"""
    return [r["s"] for r in db.rows(q, {"id": item_id}, readonly=True)]


def evidence(item_id: str, pid: str) -> dict:
    """Why this item depends on `pid`: facts, sources, weak alternates."""
    node = _item_node(item_id)
    if not node:
        return {}
    label = node["_labels"][0]
    person = db.rows("MATCH (p:Person {id: $id}) RETURN p.name AS name", {"id": pid}, readonly=True)[0]["name"]
    first = person.split()[0]
    facts: list[str] = []
    sources: list[dict] = []
    link = db.rows(f"MATCH (:Person {{id: $p}})-[k:{KNOWLEDGE_EDGES}]->(i {{id: $i}}) RETURN k",
                   {"p": pid, "i": item_id}, readonly=True)
    k = link[0]["k"] if link else {}

    if label == "System":
        eight_months = EIGHT_MONTHS_AGO.timestamp()
        if node.get("repo"):
            c = db.rows("""MATCH (p:Person)-[:AUTHORED]->(c:Commit)-[:IN_REPO]->(:System {id: $i}) WHERE c.t > $since
                           RETURN p.id AS id, p.name AS name, p.status AS status, count(c) AS n ORDER BY n DESC""",
                        {"i": item_id, "since": eight_months}, readonly=True)
            mine = next((r["n"] for r in c if r["id"] == pid), 0)
            others = [r for r in c if r["id"] != pid and r["status"] in ACTIVE]
            if mine:
                facts.append(f"{mine} commits to {node['name']} in the last eight months"
                             + (", and nobody else committed to it" if not others else ""))
            prs = db.rows("""MATCH (p:Person {id: $p})-[:AUTHORED]->(pr:PullRequest)-[:IN_REPO]->(:System {id: $i})
                             WHERE pr.t > $since RETURN count(pr) AS n, sum(CASE WHEN pr.reviewCount = 0 THEN 1 ELSE 0 END) AS solo""",
                          {"p": pid, "i": item_id, "since": eight_months}, readonly=True)[0]
            if prs["n"] and prs["solo"] > prs["n"] / 2:
                facts.append(f"{int(prs['solo'])} of {prs['n']} pull requests merged with no other reviewer")
            for r in db.rows("""MATCH (p:Person {id: $p})-[:AUTHORED]->(c:Commit)-[:IN_REPO]->(:System {id: $i})
                                RETURN c ORDER BY c.t DESC LIMIT 1""", {"p": pid, "i": item_id}, readonly=True):
                sources.append(source_ref(r["c"]))
        if k.get("answers"):
            facts.append(f"Answered {k['answers']} Slack threads about it")
        if k.get("owner"):
            facts.append("Listed as the owner in the service catalog")
        if k.get("docs"):
            facts.append(f"Wrote {k['docs']} of its docs")
        sources += [source_ref(r["root"]) for r in db.rows(
            """MATCH (p:Person {id: $p})-[:SENT]->(r:Message {substantive: true})-[:REPLY_TO]->(root:Message)-[:MENTIONS]->(:System {id: $i})
               RETURN DISTINCT root ORDER BY root.t DESC LIMIT 1""", {"p": pid, "i": item_id}, readonly=True)]
        sources += [source_ref(r["d"]) for r in db.rows(
            """MATCH (p:Person {id: $p})-[:AUTHORED]->(d:Doc)-[:DOCUMENTS]->(:System {id: $i})
               RETURN d ORDER BY d.t DESC LIMIT 1""", {"p": pid, "i": item_id}, readonly=True)]
    elif label == "Account":
        dm = db.rows("""MATCH (c:Contact)-[:WORKS_AT]->(:Account {id: $i}), (c)-[:SENT]->(m:Message)-[:IN_CHANNEL]->(ch:Channel {isIm: true})
                        MATCH (ch)<-[:IN_CHANNEL]-(:Message)<-[:SENT]-(:Person {id: $p})
                        RETURN count(DISTINCT m) AS n""", {"i": item_id, "p": pid}, readonly=True)[0]["n"]
        if k.get("contacts"):
            facts.append(f"Had {k['contacts']} conversations with {node['name']}'s own team"
                         + (f", including {dm} direct messages to {first}" if dm else ""))
        if k.get("owner"):
            facts.append("Listed as the integration owner in the CRM")
        if k.get("docs"):
            facts.append(f"Wrote {k['docs']} doc{'s' if k['docs'] != 1 else ''} about the account")
        sources += [source_ref(r["m"]) for r in db.rows(
            """MATCH (c:Contact)-[:WORKS_AT]->(:Account {id: $i}), (c)-[:SENT]->(m:Message)-[:IN_CHANNEL]->(:Channel {isIm: false})
               MATCH (m)<-[:REPLY_TO]-(:Message)<-[:SENT]-(:Person {id: $p})
               RETURN DISTINCT m ORDER BY m.t DESC LIMIT 2""", {"i": item_id, "p": pid}, readonly=True)]
        sources += [source_ref(r["d"]) for r in db.rows(
            """MATCH (p:Person {id: $p})-[:AUTHORED]->(d:Doc)-[:DOCUMENTS]->(c:Account {id: $i})
               RETURN d, CASE WHEN d.title CONTAINS c.name THEN 1 ELSE 0 END AS named
               ORDER BY named DESC, d.t DESC LIMIT 1""", {"p": pid, "i": item_id}, readonly=True)]
    else:
        srcs = db.rows("""MATCH (i {id: $i})-[sf:SOURCED_FROM]->(s) RETURN s, sf.roles AS roles ORDER BY s.t""",
                       {"i": item_id}, readonly=True)
        if label == "Decision":
            first_src = srcs[0]["s"] if srcs else None
            if first_src:
                where = first_src.get("title") or (f"#{first_src.get('channelName')}" if first_src.get("channelName") else "a commit")
                facts.append(f"{first} proposed it in {where} ({fmt_day(first_src.get('t'))})")
            if node.get("rationaleStatus") == "conversation-only":
                facts.append("The reasons exist only in conversations, not in any doc")
            others = db.rows("""MATCH (p:Person)-[d:DECIDED]->(:Decision {id: $i}) WHERE p.id <> $p
                                RETURN p.name AS name, d.role AS role ORDER BY d.score DESC""",
                             {"i": item_id, "p": pid}, readonly=True)
            approvers = [o["name"].split()[0] for o in others if o["role"] == "approver"]
            present = [o["name"].split()[0] for o in others if o["role"] == "ack"]
            if approvers:
                facts.append(f"{' and '.join(approvers)} approved it, but nobody wrote down why")
            if present:
                facts.append(f"{', '.join(present)} heard about it but never explained it")
        else:
            n = len(srcs)
            if n:
                facts.append(f"{first} explained it {n} time{'s' if n > 1 else ''} since {fmt_day(srcs[0]['s'].get('t'))}")
            stale_docs = db.rows("""MATCH (w:Workaround {id: $i})-[:ABOUT]->(:System)<-[:DOCUMENTS]-(d:Doc {freshness: 'stale'})
                                    WHERE d.kind = 'runbook' RETURN d""", {"i": item_id}, readonly=True)
            for r in stale_docs[:1]:
                facts.append(f"The runbook “{r['d']['title']}” does not cover it")
                sources.append(source_ref(r["d"]))
            obs = db.rows("MATCH (t:Ticket)-[:OBSOLETES]->(:Workaround {id: $i}) RETURN t", {"i": item_id}, readonly=True)
            for r in obs:
                facts.append(f"May be obsolete: {r['t']['id']} ({r['t']['status']}) says the fix shipped")
                sources.append(source_ref(r["t"]))
        sources = [source_ref(r["s"], highlight=person) for r in reversed(srcs[-2:])] + sources

    weak = db.rows(f"""MATCH (o:Person)-[k:{KNOWLEDGE_EDGES}]->(i {{id: $i}})
                       WHERE o.id <> $p AND k.score > 0.12
                       RETURN o.id AS id, o.name AS name, o.status AS status, o.endDate AS endDate, k.score AS score,
                              k.commits AS commits, k.answers AS answers, k.reviews AS reviews, k.role AS role,
                              k.basis AS basis
                       ORDER BY k.score DESC LIMIT 4""", {"i": item_id, "p": pid}, readonly=True)
    alternates = []
    for w in weak:
        bits = []
        if w.get("commits"):
            bits.append(f"{w['commits']} commit{'s' if w['commits'] != 1 else ''}")
        if w.get("reviews"):
            bits.append(f"{w['reviews']} review{'s' if w['reviews'] != 1 else ''}")
        if w.get("answers"):
            bits.append(f"{w['answers']} answer{'s' if w['answers'] != 1 else ''}")
        if w.get("role"):
            bits.append({"approver": "approved it", "ack": "was told about it"}.get(w["role"], w["role"]))
        alternates.append({"id": w["id"], "name": w["name"], "score": w["score"], "status": w["status"],
                           "credible": w["score"] > ALTERNATE and w["status"] in ACTIVE,
                           "basis": ", ".join(bits) or w.get("basis") or "activity",
                           "note": f"left {tenants.current().name} {fmt_day(w['endDate'])}" if w["status"] == "left" else None})
    seen, unique_sources = set(), []
    for s in sources:
        if s["id"] not in seen:
            seen.add(s["id"])
            unique_sources.append(s)
    return {"facts": facts, "sources": unique_sources[:4], "alternates": alternates,
            "link": {"score": k.get("score"), "lastSeen": iso(k.get("lastSeen")), "stale": k.get("stale", False)}}


def priority(item_id: str, pid: str) -> float:
    """Rank risk: criticality x uniqueness x recency x documentation x link strength."""
    # Kept as separate queries: an OPTIONAL MATCH after an aggregating WITH drops rows in FalkorDB 6.0.
    base = db.rows("""MATCH (i {id: $i}) OPTIONAL MATCH (i)-[:ABOUT]->(s:System)
                      RETURN i.criticality AS crit, collect(s.criticality) AS crits, i.rationaleStatus AS rs""",
                   {"i": item_id}, readonly=True)[0]
    mine = db.rows(f"""MATCH (:Person {{id: $p}})-[k:{KNOWLEDGE_EDGES}]->(i {{id: $i}})
                       RETURN max(k.score) AS score, max(k.lastSeen) AS last""", {"i": item_id, "p": pid}, readonly=True)[0]
    other = db.rows(f"""MATCH (o:Person)-[k:{KNOWLEDGE_EDGES}]->(i {{id: $i}}) WHERE o.id <> $p AND o.status IN $active
                        RETURN max(k.score) AS best""", {"i": item_id, "p": pid, "active": ACTIVE}, readonly=True)
    crits = [CRITICALITY.get(c, 0.6) for c in ([base["crit"]] if base["crit"] else base["crits"] or ["medium"])]
    best_other = (other[0]["best"] if other else 0) or 0
    unique = 1 - best_other
    last = mine["last"]
    recency = 1.0 if not last else max(0.4, 0.5 ** ((DEMO_NOW.timestamp() - last) / (180 * 86400)))
    doc = 0.85 if base["rs"] == "documented" else 1.0
    return round(max(crits) * unique * recency * doc * (mine["score"] or 0), 3)


# ----------------------------------------------------------------- successors

def suggest_successors(item_id: str, leaver: str, joiner: str | None = None, limit: int = 3) -> list[dict]:
    """Rank credible next owners from graph signals and explain each one."""
    systems = [s["id"] for s in item_systems(item_id)]
    node = _item_node(item_id) or {}
    label = node.get("_labels", ["?"])[0]
    leaver_team = db.rows("MATCH (p:Person {id: $p}) RETURN p.team AS team", {"p": leaver}, readonly=True)[0]["team"]
    rows = db.rows(f"""
        MATCH (c:Person) WHERE c.status IN $active AND c.id <> $leaver
        OPTIONAL MATCH (c)-[d:{KNOWLEDGE_EDGES}]->(:{label} {{id: $item}})
        OPTIONAL MATCH (c)-[k:KNOWS]->(s:System) WHERE s.id IN $systems
        OPTIONAL MATCH (c)-[rv:REVIEWED]->(pr:PullRequest)<-[:AUTHORED]-(:Person {{id: $leaver}})
        WHERE (pr)-[:IN_REPO]->(:System) AND pr.repo IN $repos
        RETURN c.id AS id, c.name AS name, c.role AS role, c.team AS team, c.status AS status,
               max(d.score) AS direct, max(k.score) AS context, collect(DISTINCT s.name) AS ctxSystems,
               count(DISTINCT rv) AS reviews""",
                   {"active": ACTIVE, "leaver": leaver, "item": item_id, "systems": systems,
                    "repos": [r["repo"] for r in db.rows("MATCH (s:System) WHERE s.id IN $ids AND s.repo IS NOT NULL RETURN s.repo AS repo",
                                                          {"ids": systems}, readonly=True)]}, readonly=True)
    out = []
    for r in rows:
        direct, context, reviews = r["direct"] or 0, r["context"] or 0, r["reviews"]
        same_team = r["team"] == leaver_team
        is_joiner = r["id"] == joiner
        if not (direct or context or reviews or is_joiner):
            continue
        score = 0.45 * direct + 0.35 * context + 0.12 * min(reviews / 8, 1) + (0.08 if same_team else 0)
        manager_like = any(w in r["role"] for w in ("Manager", "Head", "CEO", "CTO", "Controller"))
        if manager_like:
            score *= 0.5
        if is_joiner:
            score = max(score, 0.2)
        reasons = []
        if reviews:
            reasons.append(f"reviewed {reviews} of {leaver_first(leaver)}'s pull requests in these repos")
        ctx = [n for n in sorted(r["ctxSystems"]) if n != node.get("name")]
        if direct:
            reasons.append("already knows a little about it" if direct < ALTERNATE else "already knows it")
        if context and ctx:
            reasons.append(f"works on {', '.join(ctx[:2])}")
        if same_team and not reasons:
            reasons.append(f"on the {r['team']} team")
        if is_joiner:
            reasons.append("joining to take over this area")
        out.append({"id": r["id"], "name": r["name"], "role": r["role"], "score": round(score, 3),
                    "reason": _sentence_list(reasons),
                    "signals": {"direct": direct, "context": context, "reviews": reviews, "sameTeam": same_team},
                    "confidence": "high" if score > 0.45 else "medium" if score > 0.25 else "low"})
    out.sort(key=lambda x: -x["score"])
    return out[:limit]


def _sentence_list(parts: list[str]) -> str:
    """'a', 'b', 'c' -> 'A, b and c'."""
    if not parts:
        return ""
    text = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    return text[:1].upper() + text[1:]


def leaver_first(pid: str) -> str:
    return db.rows("MATCH (p:Person {id: $p}) RETURN p.name AS n", {"p": pid}, readonly=True)[0]["n"].split()[0]
