"""Load tool exports into the FalkorDB graph: people, systems, and raw evidence.

Identity is resolved by email (Slack, GitHub, Jira, Confluence and meetings all
carry one). Mentions of systems/customers in free text are resolved with the
catalog/CRM aliases and kept with their original surface form.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterator

from falkordb import Graph

from .. import db
from ..config import IST
from .resolve import Alias, AliasMatcher, is_substantive


def _jsonl(path: Path, optional: bool = False) -> list[dict]:
    if optional and not path.exists():
        return []
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def _t(iso: str | None) -> float | None:
    return datetime.fromisoformat(iso).timestamp() if iso else None


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


@dataclass
class Exports:
    root: Path
    employees: list[dict] = field(default_factory=list)
    systems: list[dict] = field(default_factory=list)
    accounts: list[dict] = field(default_factory=list)
    users: list[dict] = field(default_factory=list)
    channels: list[dict] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    pages: list[dict] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)
    meetings: list[dict] = field(default_factory=list)
    commits: list[dict] = field(default_factory=list)
    pulls: list[dict] = field(default_factory=list)
    # Customer-facing exports (absent for tenants without a commercial dataset).
    features: list[dict] = field(default_factory=list)
    support: list[dict] = field(default_factory=list)
    usage: list[dict] = field(default_factory=list)
    invoices: list[dict] = field(default_factory=list)
    wallets: list[dict] = field(default_factory=list)
    conversations: list[dict] = field(default_factory=list)
    roadmap: list[dict] = field(default_factory=list)
    calendar: list[dict] = field(default_factory=list)
    episodes: list[dict] = field(default_factory=list)
    tenant: str = "relay"

    @classmethod
    def read(cls, root: Path) -> "Exports":
        ex = cls._read(root)
        for i in ex.issues:
            # Custom Jira workflows ("On Prod", "PR REQUESTED") map onto status categories.
            i["jira_status"] = i["status"]
            i["status"] = i.get("status_category") or i["status"]
        return ex

    @classmethod
    def _read(cls, root: Path) -> "Exports":
        return cls(
            root=root, tenant=root.name,
            features=_jsonl(root / "catalog" / "features.jsonl", True),
            support=_jsonl(root / "support" / "tickets.jsonl", True),
            usage=_jsonl(root / "product" / "usage.jsonl", True),
            invoices=_jsonl(root / "billing" / "invoices.jsonl", True),
            wallets=_jsonl(root / "billing" / "wallets.jsonl", True),
            conversations=_jsonl(root / "conversations" / "customer.jsonl", True),
            roadmap=_jsonl(root / "roadmap" / "items.jsonl", True),
            calendar=_jsonl(root / "calendar" / "events.jsonl", True),
            episodes=_jsonl(root / "memory" / "episodes.jsonl", True),
            employees=_jsonl(root / "hr" / "employees.jsonl"),
            systems=_jsonl(root / "catalog" / "systems.jsonl"),
            accounts=_jsonl(root / "crm" / "accounts.jsonl"),
            users=_jsonl(root / "slack" / "users.jsonl"),
            channels=_jsonl(root / "slack" / "channels.jsonl"),
            messages=_jsonl(root / "slack" / "messages.jsonl"),
            pages=_jsonl(root / "confluence" / "pages.jsonl"),
            issues=_jsonl(root / "jira" / "issues.jsonl"),
            meetings=_jsonl(root / "meetings" / "transcripts.jsonl"),
            commits=_jsonl(root / "github" / "commits.jsonl"),
            pulls=_jsonl(root / "github" / "pulls.jsonl"),
        )


class Resolver:
    """Email -> actor id, names -> entity ids, text -> mentions."""

    def __init__(self, ex: Exports):
        self.person_by_email = {e["email"]: e["employee_id"] for e in ex.employees}
        self.system_by_name = {s["name"]: "sys-" + slug(s["name"]) for s in ex.systems}
        self.system_by_repo = {s["repo"]: self.system_by_name[s["name"]] for s in ex.systems if s.get("repo")}
        self.customer_by_name = {a["name"]: "cust-" + slug(a["name"]) for a in ex.accounts}
        self.contact_by_email = {}
        for a in ex.accounts:
            for c in a["contacts"]:
                self.contact_by_email[c["email"]] = "contact-" + slug(c["name"])
        self.feature_by_name = {f["name"]: f["id"] for f in ex.features}
        self.slack_user = {u["id"]: u for u in ex.users}
        aliases = []
        for s in ex.systems:
            for al in {s["name"], *s["aliases"]}:
                aliases.append(Alias(self.system_by_name[s["name"]], "System", al.lower()))
        for a in ex.accounts:
            for al in {a["name"], *a.get("aliases", [])}:
                aliases.append(Alias(self.customer_by_name[a["name"]], "Account", al.lower()))
        self.matcher = AliasMatcher(aliases)

    def actor(self, email: str | None) -> tuple[str | None, str | None]:
        """(label, id) for an email: a Person, an external Contact, or nothing."""
        if not email:
            return None, None
        if email in self.person_by_email:
            return "Person", self.person_by_email[email]
        if email in self.contact_by_email:
            return "Contact", self.contact_by_email[email]
        return None, None

    def slack_actor(self, user_id: str) -> tuple[str | None, str | None]:
        u = self.slack_user.get(user_id)
        if not u or u.get("is_bot"):
            return ("Bot", user_id) if u else (None, None)
        return self.actor(u.get("email"))

    def entity(self, name: str) -> tuple[str, str] | None:
        if name in self.system_by_name:
            return "System", self.system_by_name[name]
        if name in self.customer_by_name:
            return "Account", self.customer_by_name[name]
        return None

    def mentions(self, text: str) -> list[dict]:
        seen, out = set(), []
        for a, surface in self.matcher.find(text):
            if a.entity_id not in seen:
                seen.add(a.entity_id)
                out.append({"id": a.entity_id, "label": a.label, "surface": surface})
        return out


LABELS_WITH_ID = ["Person", "Contact", "Team", "System", "Account", "Channel", "Message", "Doc", "Ticket",
                  "Meeting", "Commit", "PullRequest", "Decision", "Workaround", "Knowledge", "Handover",
                  "RiskItem", "Action", "ChecklistItem", "DocProposal", "Bot",
                  "Feature", "Bug", "UsageWeek", "Invoice", "Conversation", "Signal", "RoadmapItem", "Promise",
                  "Playbook", "Episode", "Risk", "Investigation", "Card"]


def create_indexes(g: Graph) -> None:
    for label in LABELS_WITH_ID:
        try:
            g.query(f"CREATE INDEX FOR (n:{label}) ON (n.id)")
        except Exception:
            pass  # already exists


def create_fulltext(g: Graph) -> None:
    specs = {
        "Message": ["text"], "Doc": ["title", "body"], "Ticket": ["title", "description"],
        "Meeting": ["title", "text"], "Decision": ["summary", "rationale"], "Workaround": ["summary"],
        "Knowledge": ["question", "answer"], "Commit": ["message"],
        "Conversation": ["text"], "RoadmapItem": ["title", "internalNote"], "Promise": ["text"],
    }
    existing = {r[0] for r in g.query("CALL db.indexes()").result_set if "FULLTEXT" in str(r[2])}
    for label, props in specs.items():
        if label in existing:
            continue
        on = ", ".join(f"n.{p}" for p in props)
        g.query(f"CREATE FULLTEXT INDEX FOR (n:{label}) ON ({on})")


def _mention_rows(src_label: str, src_id: str, mentions: list[dict]) -> Iterator[dict]:
    for m in mentions:
        yield {"src": src_id, "dst": m["id"], "surface": m["surface"], "label": m["label"], "slabel": src_label}


def _write_mentions(g: Graph, rows: list[dict]) -> None:
    by_pair: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        by_pair.setdefault((r["slabel"], r["label"]), []).append(r)
    for (sl, dl), rs in by_pair.items():
        db.batched(f"""UNWIND $rows AS r MATCH (s:{sl} {{id: r.src}}), (d:{dl} {{id: r.dst}})
                       CREATE (s)-[:MENTIONS {{surface: r.surface}}]->(d)""", rs, g=g)


def load(g: Graph, ex: Exports) -> Resolver:
    rv = Resolver(ex)
    create_indexes(g)

    # --- org --------------------------------------------------------------
    teams = sorted({e["team"] for e in ex.employees})
    db.batched("UNWIND $rows AS r CREATE (:Team {id: r.id, name: r.name})",
               [{"id": "team-" + slug(t), "name": t} for t in teams], g=g)
    slack_by_email = {u["email"]: u["id"] for u in ex.users if u.get("email")}
    db.batched("""UNWIND $rows AS r CREATE (p:Person {id: r.id, name: r.name, email: r.email, role: r.role,
                  team: r.team, startDate: r.start, endDate: r.end, status: r.status, slackId: r.slack})""",
               [{"id": e["employee_id"], "name": e["name"], "email": e["email"], "role": e["title"],
                 "team": e["team"], "start": e["start_date"], "end": e["end_date"], "status": e["status"],
                 "slack": slack_by_email.get(e["email"])} for e in ex.employees], g=g)
    db.batched("""UNWIND $rows AS r MATCH (p:Person {id: r.id}), (t:Team {id: r.team}) CREATE (p)-[:MEMBER_OF]->(t)""",
               [{"id": e["employee_id"], "team": "team-" + slug(e["team"])} for e in ex.employees], g=g)
    db.batched("""UNWIND $rows AS r MATCH (p:Person {id: r.id}), (m:Person {email: r.mgr}) CREATE (p)-[:REPORTS_TO]->(m)""",
               [{"id": e["employee_id"], "mgr": e["manager_email"]} for e in ex.employees if e["manager_email"]], g=g)

    # --- catalog + CRM ----------------------------------------------------
    db.batched("""UNWIND $rows AS r CREATE (s:System {id: r.id, name: r.name, aliases: r.aliases, team: r.team,
                  criticality: r.crit, repo: r.repo, summary: r.summary})""",
               [{"id": rv.system_by_name[s["name"]], "name": s["name"], "aliases": s["aliases"], "team": s["team"],
                 "crit": s["criticality"], "repo": s["repo"], "summary": s["summary"]} for s in ex.systems], g=g)
    db.batched("""UNWIND $rows AS r MATCH (s:System {id: r.id}), (t:Team {id: r.team}) CREATE (s)-[:OWNED_BY_TEAM]->(t)""",
               [{"id": rv.system_by_name[s["name"]], "team": "team-" + slug(s["team"])} for s in ex.systems], g=g)
    db.batched("""UNWIND $rows AS r MATCH (p:Person {email: r.email}), (s:System {id: r.id})
                  CREATE (p)-[:OWNS {source: 'service-catalog'}]->(s)""",
               [{"id": rv.system_by_name[s["name"]], "email": s["owner_email"]} for s in ex.systems], g=g)
    db.batched("""UNWIND $rows AS r CREATE (:Account {id: r.id, name: r.name, aliases: r.aliases, tier: r.tier,
                  summary: r.summary})""",
               [{"id": rv.customer_by_name[a["name"]], "name": a["name"], "aliases": a.get("aliases", []), "tier": a["tier"],
                 "summary": a["summary"]} for a in ex.accounts], g=g)
    db.batched("""UNWIND $rows AS r MATCH (p:Person {email: r.email}), (c:Account {id: r.id})
                  CREATE (p)-[:OWNS {source: 'crm'}]->(c)""",
               [{"id": rv.customer_by_name[a["name"]], "email": a["integration_owner_email"]} for a in ex.accounts
                if a.get("integration_owner_email")], g=g)
    db.batched("""UNWIND $rows AS r MATCH (c:Account {id: r.cust})
                  CREATE (k:Contact {id: r.id, name: r.name, email: r.email, role: r.role, org: r.org, title: r.title,
                          isChampion: r.champ, active: r.left IS NULL, joinedAt: r.joined, leftAt: r.left,
                          emailStatus: r.estatus, emailBouncedAt: r.bounced})
                  CREATE (k)-[:WORKS_AT {from: r.joined, to: r.left, role: r.role, source: 'CRM'}]->(c)""",
               [{"id": rv.contact_by_email[c["email"]], "name": c["name"], "email": c["email"], "role": c["role"],
                 "org": a["name"], "cust": rv.customer_by_name[a["name"]], "title": c.get("title") or c["role"],
                 "champ": bool(c.get("is_champion")), "joined": c.get("joined"), "left": c.get("left"),
                 "estatus": c.get("email_status", "ok"), "bounced": c.get("email_bounced_at")}
                for a in ex.accounts for c in a["contacts"]], g=g)
    db.batched("""UNWIND $rows AS r MATCH (s:Contact {email: r.s}), (p:Contact {email: r.p})
                  CREATE (s)-[:SUCCEEDED {at: p.leftAt, role: 'Admin', source: 'CRM'}]->(p)""",
               [{"s": c["email"], "p": c["successor_of"]} for a in ex.accounts for c in a["contacts"]
                if c.get("successor_of")], g=g)
    db.batched("UNWIND $rows AS r CREATE (:Bot {id: r.id, name: r.name})",
               [{"id": u["id"], "name": u["real_name"]} for u in ex.users if u.get("is_bot")], g=g)

    # --- Slack ------------------------------------------------------------
    db.batched("""UNWIND $rows AS r CREATE (:Channel {id: r.id, name: r.name, purpose: r.purpose,
                  isShared: r.shared, isIm: r.im})""",
               [{"id": c["id"], "name": c["name"] or "Direct message", "purpose": c["purpose"],
                 "shared": c["is_shared"], "im": c["is_im"]} for c in ex.channels], g=g)
    chan_name = {c["id"]: c["name"] or "Direct message" for c in ex.channels}
    msgs, senders, replies, ments = [], [], [], []
    for m in ex.messages:
        mid = f"{m['channel']}:{m['ts']}"
        root = f"{m['channel']}:{m['thread_ts']}" if m.get("thread_ts") else None
        label, actor = rv.slack_actor(m["user"])
        msgs.append({"id": mid, "channel": m["channel"], "channelName": chan_name.get(m["channel"]),
                     "t": float(m["ts"]), "at": datetime.fromtimestamp(float(m["ts"]), IST).isoformat(),
                     "text": m["text"], "threadId": root or mid, "isReply": bool(root),
                     "substantive": bool(root) and is_substantive(m["text"]),
                     "url": f"https://{ex.tenant}.slack.example/archives/{m['channel']}/p{m['ts'].replace('.', '')}"})
        if label:
            senders.append({"label": label, "actor": actor, "id": mid})
        if root:
            replies.append({"id": mid, "root": root})
        ments.extend(_mention_rows("Message", mid, rv.mentions(m["text"])))
    db.batched("""UNWIND $rows AS r CREATE (:Message {id: r.id, channel: r.channel, channelName: r.channelName, t: r.t,
                  at: r.at, text: r.text, threadId: r.threadId, isReply: r.isReply, substantive: r.substantive,
                  url: r.url})""", msgs, g=g)
    db.batched("UNWIND $rows AS r MATCH (m:Message {id: r.id}), (c:Channel {id: split(r.id, ':')[0]}) CREATE (m)-[:IN_CHANNEL]->(c)",
               [{"id": m["id"]} for m in msgs], g=g)
    for label in ("Person", "Contact", "Bot"):
        db.batched(f"""UNWIND $rows AS r MATCH (a:{label} {{id: r.actor}}), (m:Message {{id: r.id}}) CREATE (a)-[:SENT]->(m)""",
                   [s for s in senders if s["label"] == label], g=g)
    db.batched("UNWIND $rows AS r MATCH (m:Message {id: r.id}), (root:Message {id: r.root}) CREATE (m)-[:REPLY_TO]->(root)",
               replies, g=g)

    # --- Confluence -------------------------------------------------------
    docs, doc_rows = [], []
    for p in ex.pages:
        docs.append({"id": p["id"], "title": p["title"], "kind": p["kind"], "space": p["space"], "url": p["url"],
                     "createdAt": p["created"], "updatedAt": p["updated"], "t": _t(p["updated"]), "body": p["body"]})
        _, author = rv.actor(p["author_email"])
        doc_rows.append({"id": p["id"], "author": author})
        for name in p["labels"] + p["customers"]:
            ent = rv.entity(name)
            if ent:
                ments.append({"src": p["id"], "dst": ent[1], "surface": name, "label": ent[0], "slabel": "Doc", "documents": True})
        ments.extend(_mention_rows("Doc", p["id"], rv.mentions(p["title"] + "\n" + p["body"])))
    db.batched("""UNWIND $rows AS r CREATE (:Doc {id: r.id, title: r.title, kind: r.kind, space: r.space, url: r.url,
                  createdAt: r.createdAt, updatedAt: r.updatedAt, t: r.t, body: r.body})""", docs, g=g)
    db.batched("UNWIND $rows AS r MATCH (p:Person {id: r.author}), (d:Doc {id: r.id}) CREATE (p)-[:AUTHORED]->(d)",
               [d for d in doc_rows if d["author"]], g=g)
    documents = [m for m in ments if m.get("documents")]
    ments = [m for m in ments if not m.get("documents")]
    for dl in ("System", "Account"):
        db.batched(f"""UNWIND $rows AS r MATCH (d:Doc {{id: r.src}}), (x:{dl} {{id: r.dst}}) CREATE (d)-[:DOCUMENTS]->(x)""",
                   [m for m in documents if m["label"] == dl], g=g)

    # --- Jira -------------------------------------------------------------
    tickets, owned, reported, concerns = [], [], [], []
    for i in ex.issues:
        text = " ".join([i["summary"], i["description"], *[c["body"] for c in i["comments"]]])
        tickets.append({"id": i["key"], "title": i["summary"], "status": i["status"], "description": i["description"],
                        "createdAt": i["created"], "updatedAt": i["updated"], "resolvedAt": i["resolved"],
                        "t": _t(i["resolved"] or i["updated"]), "labels": i["labels"],
                        "comments": json.dumps(i["comments"]), "jiraStatus": i.get("jira_status"),
                        "issueType": i.get("issuetype", "Task"), "source": "jira",
                        "url": f"https://{ex.tenant}.atlassian.example/browse/{i['key']}"})
        _, a = rv.actor(i["assignee_email"])
        if a:
            owned.append({"id": i["key"], "p": a})
        _, r = rv.actor(i["reporter_email"])
        if r:
            reported.append({"id": i["key"], "p": r})
        for name in i["components"] + ([i["customer"]] if i["customer"] else []):
            ent = rv.entity(name)
            if ent:
                concerns.append({"id": i["key"], "x": ent[1], "label": ent[0]})
        ments.extend(_mention_rows("Ticket", i["key"], rv.mentions(text)))
    db.batched("""UNWIND $rows AS r CREATE (:Ticket {id: r.id, title: r.title, status: r.status, description: r.description,
                  createdAt: r.createdAt, updatedAt: r.updatedAt, resolvedAt: r.resolvedAt, t: r.t, labels: r.labels,
                  comments: r.comments, url: r.url, jiraStatus: r.jiraStatus, issueType: r.issueType, source: r.source})""",
               tickets, g=g)
    db.batched("UNWIND $rows AS r MATCH (t:Ticket {id: r.id}), (p:Person {id: r.p}) CREATE (t)-[:OWNED_BY]->(p)", owned, g=g)
    db.batched("UNWIND $rows AS r MATCH (t:Ticket {id: r.id}), (p:Person {id: r.p}) CREATE (t)-[:REPORTED_BY]->(p)", reported, g=g)
    for dl in ("System", "Account"):
        db.batched(f"UNWIND $rows AS r MATCH (t:Ticket {{id: r.id}}), (x:{dl} {{id: r.x}}) CREATE (t)-[:CONCERNS]->(x)",
                   [c for c in concerns if c["label"] == dl], g=g)

    # --- Meetings ---------------------------------------------------------
    meetings, attended = [], []
    for m in ex.meetings:
        lines = []
        for x in m["transcript"]:
            _, sp = rv.actor(x["speaker_email"])
            lines.append({"speaker": sp, "text": x["text"]})
        text = "\n".join(x["text"] for x in m["transcript"]) + "\n" + (m["notes"] or "")
        meetings.append({"id": m["id"], "title": m["title"], "date": m["start"], "t": _t(m["start"]),
                         "notes": m["notes"], "transcript": json.dumps(lines), "text": text,
                         "kind": m.get("kind", "internal"), "status": "held", "durationMin": m.get("duration_min"),
                         "url": f"https://meet.{ex.tenant}.example/notes/{m['id']}"})
        for e in m["attendees"]:
            label, p = rv.actor(e)
            if p:
                attended.append({"id": m["id"], "p": p, "label": label})
        ments.extend(_mention_rows("Meeting", m["id"], rv.mentions(text)))
    db.batched("""UNWIND $rows AS r CREATE (:Meeting {id: r.id, title: r.title, date: r.date, t: r.t, notes: r.notes,
                  transcript: r.transcript, text: r.text, url: r.url, kind: r.kind, status: r.status,
                  durationMin: r.durationMin})""", meetings, g=g)
    for label in ("Person", "Contact"):
        db.batched(f"UNWIND $rows AS r MATCH (p:{label} {{id: r.p}}), (m:Meeting {{id: r.id}}) CREATE (p)-[:ATTENDED]->(m)",
                   [a for a in attended if a["label"] == label], g=g)
    db.batched("UNWIND $rows AS r MATCH (m:Meeting {id: r.id}), (a:Account {id: r.a}) CREATE (m)-[:WITH]->(a)",
               [{"id": m["id"], "a": rv.customer_by_name[m["account"]]} for m in ex.meetings
                if m.get("account") in rv.customer_by_name], g=g)

    # --- GitHub -----------------------------------------------------------
    commits, cauth = [], []
    for c in ex.commits:
        commits.append({"id": c["sha"], "repo": c["repo"], "message": c["message"], "at": c["date"], "t": _t(c["date"]),
                        "sys": rv.system_by_repo.get(c["repo"]),
                        "url": f"https://github.example/{c['repo']}/commit/{c['sha']}"})
        _, a = rv.actor(c["author_email"])
        if a:
            cauth.append({"id": c["sha"], "p": a})
    db.batched("""UNWIND $rows AS r CREATE (c:Commit {id: r.id, repo: r.repo, message: r.message, at: r.at, t: r.t, url: r.url})
                  WITH c, r MATCH (s:System {id: r.sys}) CREATE (c)-[:IN_REPO]->(s)""", commits, g=g)
    db.batched("UNWIND $rows AS r MATCH (p:Person {id: r.p}), (c:Commit {id: r.id}) CREATE (p)-[:AUTHORED]->(c)", cauth, g=g)
    prs, pauth, parts, reviews = [], [], [], []
    for p in ex.pulls:
        pid = f"{p['repo']}#{p['number']}"
        prs.append({"id": pid, "repo": p["repo"], "number": p["number"], "title": p["title"],
                    "createdAt": p["created_at"], "mergedAt": p["merged_at"], "t": _t(p["merged_at"]),
                    "sys": rv.system_by_repo.get(p["repo"]), "reviewCount": len(p["reviews"]),
                    "url": f"https://github.example/{p['repo']}/pull/{p['number']}"})
        _, a = rv.actor(p["author_email"])
        if a:
            pauth.append({"id": pid, "p": a})
        parts.extend({"sha": s, "pr": pid} for s in p["commit_shas"])
        for r in p["reviews"]:
            _, rvw = rv.actor(r["reviewer_email"])
            if rvw:
                reviews.append({"id": pid, "p": rvw, "at": r["submitted_at"], "t": _t(r["submitted_at"]), "state": r["state"]})
    db.batched("""UNWIND $rows AS r CREATE (pr:PullRequest {id: r.id, repo: r.repo, number: r.number, title: r.title,
                  createdAt: r.createdAt, mergedAt: r.mergedAt, t: r.t, reviewCount: r.reviewCount, url: r.url})
                  WITH pr, r MATCH (s:System {id: r.sys}) CREATE (pr)-[:IN_REPO]->(s)""", prs, g=g)
    db.batched("UNWIND $rows AS r MATCH (p:Person {id: r.p}), (pr:PullRequest {id: r.id}) CREATE (p)-[:AUTHORED]->(pr)", pauth, g=g)
    db.batched("UNWIND $rows AS r MATCH (c:Commit {id: r.sha}), (pr:PullRequest {id: r.pr}) CREATE (c)-[:PART_OF]->(pr)", parts, g=g)
    db.batched("""UNWIND $rows AS r MATCH (p:Person {id: r.p}), (pr:PullRequest {id: r.id})
                  CREATE (p)-[:REVIEWED {at: r.at, t: r.t, state: r.state}]->(pr)""", reviews, g=g)

    _write_mentions(g, ments)
    return rv
