"""Workspaces, teammates, invites, connections and the getting-started journey.

Account data lives in the `<graph>_accounts` FalkorDB graph. Each workspace gets
its own company graph (`<tenant graph>_ws_<id>`), copied from a sample company's
build (Cheerio by default, or Lumen), so teams never see each other's data and a
demo reset only touches one team.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import uuid

import httpx

from . import db, secretbox
from .auth import AuthError, _g, public
from .config import now, settings

ROLES = ("owner", "admin", "member")
PERSONAS = ("p-priya", "p-rahul", "p-aisha", "p-arnav", "p-sneha")

# Sources that feed the company graph. In a workspace they start connected to the
# sample company's exports; live ingestion isn't available yet, and the UI says so.
SOURCES = [
    {"id": "slack", "name": "Slack", "kind": "source", "category": "Conversations",
     "description": "Channels and threads: who answers questions, workarounds, customer contacts.", "demo": "8 channels · 3,000 messages"},
    {"id": "confluence", "name": "Confluence", "kind": "source", "category": "Docs",
     "description": "Runbooks, RFCs and design docs, with freshness checks.", "demo": "62 pages"},
    {"id": "jira", "name": "Jira", "kind": "source", "category": "Tickets",
     "description": "Ownership and resolved work. Live connection also lets Relay move tickets.", "demo": "400 issues"},
    {"id": "meetings", "name": "Google Meet notes", "kind": "source", "category": "Meetings",
     "description": "Transcripts where decisions and their reasons are recorded.", "demo": "50 transcripts"},
    {"id": "github", "name": "GitHub", "kind": "source", "category": "Code",
     "description": "Commits and reviews: the strongest signal of who knows a system.", "demo": "6 repos · 1,181 commits"},
    {"id": "hris", "name": "HR system", "kind": "source", "category": "People",
     "description": "Org chart, start dates and last days.", "demo": "41 people"},
    {"id": "hubspot", "name": "HubSpot", "kind": "source", "category": "CRM",
     "description": "Accounts, ARR, renewal dates and stages, health scores, contacts and champions.", "demo": "120 accounts",
     "commercial": True},
    {"id": "support", "name": "Support desk", "kind": "source", "category": "Customer tickets",
     "description": "Customer tickets, triaged to the Jira bugs they're a symptom of.", "demo": "1,083 tickets", "commercial": True},
    {"id": "amplitude", "name": "Amplitude", "kind": "source", "category": "Product usage",
     "description": "Weekly active users and feature usage per account.", "demo": "26 weeks", "commercial": True},
    {"id": "billing", "name": "Billing & wallet", "kind": "source", "category": "Invoices",
     "description": "GST invoices, payment delays and wallet balances.", "demo": "360 invoices", "commercial": True},
    {"id": "calendar", "name": "Google Calendar + meeting bot", "kind": "source", "category": "Customer calls",
     "description": "Upcoming customer calls; the bot streams transcripts to Sales Assist (with consent).",
     "demo": "6 calls this week", "commercial": True},
    {"id": "roadmap", "name": "Product roadmap", "kind": "source", "category": "Roadmap",
     "description": "Roadmap items with ETAs, slips and internal guidance.", "demo": "10 items", "commercial": True},
]
ACTIONS = [
    {"id": "google", "name": "Google Workspace", "kind": "action", "category": "Calendar & Gmail",
     "description": "Book 30-minute intros on Day One and save customer intro drafts in Gmail."},
    {"id": "jira_live", "name": "Jira (live)", "kind": "action", "category": "Ticket moves",
     "description": "Reassign a leaver's open tickets to their successors after you approve."},
]


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "workspace"


def public_url() -> str:
    return os.getenv("RELAY_PUBLIC_URL", "http://localhost:3025").rstrip("/")


# ------------------------------------------------------------------- users

def update_profile(user_id: str, *, job_role: str | None = None, persona: str | None = None,
                   name: str | None = None) -> dict:
    if persona and persona not in PERSONAS:
        raise AuthError("Unknown persona")
    db.run("""MATCH (u:User {id: $id})
              SET u.jobRole = coalesce($role, u.jobRole), u.defaultPersona = coalesce($persona, u.defaultPersona),
                  u.name = coalesce($name, u.name)""",
           {"id": user_id, "role": job_role, "persona": persona, "name": (name or "").strip() or None}, g=_g())
    return user(user_id)


def user(user_id: str) -> dict:
    r = db.rows("MATCH (u:User {id: $id}) RETURN u", {"id": user_id}, g=_g(), readonly=True)
    if not r:
        raise AuthError("No such user", 404)
    u = r[0]["u"]
    return {**public(u), "jobRole": u.get("jobRole"), "defaultPersona": u.get("defaultPersona"),
            "avatarUrl": u.get("avatarUrl"), "onboardedAt": u.get("onboardedAt"),
            "hasPassword": bool(u.get("passwordHash")), "google": bool(u.get("googleSub"))}


def flags(user_id: str) -> dict:
    r = db.rows("MATCH (u:User {id: $id}) RETURN u.flags AS f", {"id": user_id}, g=_g(), readonly=True)
    return json.loads(r[0]["f"]) if r and r[0]["f"] else {}


def mark(user_id: str, step: str) -> dict:
    f = flags(user_id)
    if step not in f:
        f[step] = now().isoformat(timespec="seconds")
        db.run("MATCH (u:User {id: $id}) SET u.flags = $f", {"id": user_id, "f": json.dumps(f)}, g=_g())
    return f


def complete_onboarding(user_id: str) -> dict:
    db.run("MATCH (u:User {id: $id}) SET u.onboardedAt = coalesce(u.onboardedAt, $at)",
           {"id": user_id, "at": now().isoformat(timespec="seconds")}, g=_g())
    return user(user_id)


# -------------------------------------------------------------- workspaces

def _ws_view(w: dict, role: str | None = None) -> dict:
    from . import tenants
    t = tenants.for_graph(w.get("graph") or "")
    return {"id": w["id"], "name": w["name"], "slug": w.get("slug"), "createdAt": w.get("createdAt"),
            "demoData": True, "role": role, "tenant": t.id, "company": t.name}


def create_workspace(user_id: str, name: str, tenant: str | None = None) -> dict:
    from . import tenants
    from .ingest.pipeline import demo_graph
    name = (name or "").strip()
    if len(name) < 2:
        raise AuthError("Give your workspace a name")
    t = tenants.get(tenant) if tenant in tenants.TENANTS else tenants.for_graph(settings().graph_name)
    base = demo_graph(t) + "_base"
    if not db.exists(base):
        raise AuthError(f"The {t.name} sample graph hasn't been built yet (run `relay --tenant {t.id} build`).", 503)
    wid = "w-" + uuid.uuid4().hex[:10]
    graph_name = f"{demo_graph(t)}_ws_{wid[2:]}"
    db.graph(base).copy(graph_name)
    stamp = now().isoformat(timespec="seconds")
    db.run("""MATCH (u:User {id: $uid})
              CREATE (w:Workspace {id: $id, name: $name, slug: $slug, graph: $graph, createdAt: $at, createdBy: $uid})
              CREATE (u)-[:MEMBER_OF {role: 'owner', joinedAt: $at}]->(w)""",
           {"uid": user_id, "id": wid, "name": name, "slug": _slug(name), "graph": graph_name, "at": stamp}, g=_g())
    for s in SOURCES:
        if s.get("commercial") and t.id != "cheerio":
            continue
        db.run("""MATCH (w:Workspace {id: $w})
                  CREATE (:Connection {id: $cid, provider: $p, status: 'connected', mode: 'demo', connectedAt: $at})-[:IN]->(w)""",
               {"w": wid, "cid": f"{wid}:{s['id']}", "p": s["id"], "at": stamp}, g=_g())
    return _ws_view(_workspace(wid), "owner")


def _workspace(wid: str) -> dict:
    r = db.rows("MATCH (w:Workspace {id: $id}) RETURN w", {"id": wid}, g=_g(), readonly=True)
    if not r:
        raise AuthError("No such workspace", 404)
    return r[0]["w"]


def memberships(user_id: str) -> list[dict]:
    rows = db.rows("""MATCH (:User {id: $u})-[m:MEMBER_OF]->(w:Workspace) RETURN w, m.role AS role
                      ORDER BY m.joinedAt""", {"u": user_id}, g=_g(), readonly=True)
    return [{**r["w"], "role": r["role"]} for r in rows]


def resolve(user_id: str, preferred: str | None) -> dict | None:
    """The workspace a session is acting in: its stored choice if still a member, else the first."""
    ms = memberships(user_id)
    for m in ms:
        if m["id"] == preferred:
            return m
    return ms[0] if ms else None


def graph_for(ws: dict) -> str:
    return ws["graph"]


def role_in(user_id: str, wid: str) -> str | None:
    r = db.rows("MATCH (:User {id: $u})-[m:MEMBER_OF]->(:Workspace {id: $w}) RETURN m.role AS role",
                {"u": user_id, "w": wid}, g=_g(), readonly=True)
    return r[0]["role"] if r else None


def require_admin(user_id: str, wid: str) -> None:
    if role_in(user_id, wid) not in ("owner", "admin"):
        raise AuthError("Only workspace owners and admins can do that", 403)


def rename(user_id: str, wid: str, name: str) -> dict:
    require_admin(user_id, wid)
    if len((name or "").strip()) < 2:
        raise AuthError("Give your workspace a name")
    db.run("MATCH (w:Workspace {id: $w}) SET w.name = $n, w.slug = $s", {"w": wid, "n": name.strip(), "s": _slug(name)}, g=_g())
    return _ws_view(_workspace(wid), role_in(user_id, wid))


# ------------------------------------------------------------ teammates

def members(wid: str) -> dict:
    ms = db.rows("""MATCH (u:User)-[m:MEMBER_OF]->(:Workspace {id: $w})
                    RETURN u.id AS id, u.name AS name, u.email AS email, u.avatarUrl AS avatarUrl,
                           m.role AS role, m.joinedAt AS joinedAt ORDER BY m.joinedAt""", {"w": wid}, g=_g(), readonly=True)
    inv = db.rows("""MATCH (i:Invite {status: 'pending'})-[:TO]->(:Workspace {id: $w})
                     OPTIONAL MATCH (by:User {id: i.invitedBy})
                     RETURN i.id AS id, i.email AS email, i.role AS role, i.createdAt AS createdAt, by.name AS invitedBy
                     ORDER BY i.createdAt DESC""", {"w": wid}, g=_g(), readonly=True)
    return {"members": ms, "invites": inv}


def invite(user_id: str, wid: str, emails: list[str], role: str = "member") -> list[dict]:
    require_admin(user_id, wid)
    if role not in ("admin", "member"):
        raise AuthError("Role must be admin or member")
    clean = []
    for e in emails:
        e = (e or "").strip().lower()
        if not e:
            continue
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", e):
            raise AuthError(f"“{e}” isn't a valid email address")
        clean.append(e)
    if not clean:
        raise AuthError("Add at least one email address")
    if len(clean) > 20:
        raise AuthError("Invite up to 20 people at a time")
    existing = {m["email"] for m in members(wid)["members"]}
    out = []
    for e in dict.fromkeys(clean):
        if e in existing:
            out.append({"email": e, "status": "already-member"})
            continue
        db.run("""MATCH (i:Invite {email: $e, status: 'pending'})-[:TO]->(:Workspace {id: $w}) SET i.status = 'replaced'""",
               {"e": e, "w": wid}, g=_g())
        token = secrets.token_urlsafe(24)
        iid = "i-" + uuid.uuid4().hex[:10]
        db.run("""MATCH (w:Workspace {id: $w})
                  CREATE (:Invite {id: $id, tokenHash: $h, email: $e, role: $r, status: 'pending', invitedBy: $by,
                                   createdAt: $at})-[:TO]->(w)""",
               {"w": wid, "id": iid, "h": _hash(token), "e": e, "r": role, "by": user_id,
                "at": now().isoformat(timespec="seconds")}, g=_g())
        out.append({"id": iid, "email": e, "role": role, "status": "pending", "link": f"{public_url()}/join/{token}"})
    return out


def invite_info(token: str) -> dict:
    r = db.rows("""MATCH (i:Invite {tokenHash: $h})-[:TO]->(w:Workspace) OPTIONAL MATCH (by:User {id: i.invitedBy})
                   RETURN i, w.name AS workspace, w.id AS wid, by.name AS invitedBy""", {"h": _hash(token)}, g=_g(), readonly=True)
    if not r:
        raise AuthError("This invite link isn't valid", 404)
    i = r[0]["i"]
    return {"email": i["email"], "role": i["role"], "status": i["status"], "workspace": r[0]["workspace"],
            "workspaceId": r[0]["wid"], "invitedBy": r[0]["invitedBy"], "valid": i["status"] == "pending"}


def accept_invite(token: str, user_id: str) -> dict:
    info = invite_info(token)
    if not info["valid"]:
        raise AuthError("This invite has already been used or was withdrawn", 410)
    u = user(user_id)
    if u["email"] != info["email"]:
        raise AuthError(f"This invite was sent to {info['email']}. Sign in with that email to accept it.", 403)
    if not role_in(user_id, info["workspaceId"]):
        db.run("""MATCH (u:User {id: $u}), (w:Workspace {id: $w})
                  CREATE (u)-[:MEMBER_OF {role: $r, joinedAt: $at}]->(w)""",
               {"u": user_id, "w": info["workspaceId"], "r": info["role"], "at": now().isoformat(timespec="seconds")}, g=_g())
    db.run("MATCH (i:Invite {tokenHash: $h}) SET i.status = 'accepted', i.acceptedAt = $at",
           {"h": _hash(token), "at": now().isoformat(timespec="seconds")}, g=_g())
    return _ws_view(_workspace(info["workspaceId"]), info["role"])


def revoke_invite(user_id: str, wid: str, invite_id: str) -> None:
    require_admin(user_id, wid)
    db.run("MATCH (i:Invite {id: $i})-[:TO]->(:Workspace {id: $w}) SET i.status = 'revoked'", {"i": invite_id, "w": wid}, g=_g())


def set_role(user_id: str, wid: str, member_id: str, role: str) -> None:
    require_admin(user_id, wid)
    if role not in ROLES:
        raise AuthError("Unknown role")
    if member_id == user_id and role != "owner" and role_in(user_id, wid) == "owner":
        owners = [m for m in members(wid)["members"] if m["role"] == "owner"]
        if len(owners) == 1:
            raise AuthError("A workspace needs at least one owner")
    db.run("MATCH (:User {id: $m})-[r:MEMBER_OF]->(:Workspace {id: $w}) SET r.role = $role",
           {"m": member_id, "w": wid, "role": role}, g=_g())


def remove_member(user_id: str, wid: str, member_id: str) -> None:
    require_admin(user_id, wid)
    if role_in(member_id, wid) == "owner":
        raise AuthError("Owners can't be removed; change their role first")
    db.run("MATCH (:User {id: $m})-[r:MEMBER_OF]->(:Workspace {id: $w}) DELETE r", {"m": member_id, "w": wid}, g=_g())


# ------------------------------------------------------------ connections

def _connection_rows(wid: str) -> dict[str, dict]:
    rows = db.rows("MATCH (c:Connection)-[:IN]->(:Workspace {id: $w}) RETURN c", {"w": wid}, g=_g(), readonly=True)
    return {r["c"]["provider"]: r["c"] for r in rows}


def google_configured() -> bool:
    return bool(os.getenv("GOOGLE_OAUTH_CLIENT_ID") and os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"))


def _demo_counts(tenant) -> dict[str, str]:
    """Source sizes for a sample company, from its export manifest."""
    try:
        c = json.loads((tenant.data_dir / "manifest.json").read_text())["counts"]
    except (OSError, KeyError, ValueError):
        return {}
    out = {"slack": f"{c.get('slack_channels', 0)} channels · {c.get('slack_messages', 0):,} messages",
           "confluence": f"{c.get('docs', 0)} pages", "jira": f"{c.get('jira_issues', c.get('tickets', 0)):,} issues",
           "meetings": f"{c.get('meetings', 0)} transcripts", "github": f"{c.get('commits', 0):,} commits",
           "hris": f"{c.get('people', 0)} people"}
    if c.get("accounts"):
        out |= {"hubspot": f"{c['accounts']} accounts", "support": f"{c['support_tickets']:,} tickets",
                "billing": f"{c['invoices']} invoices", "calendar": f"{c['calendar_events']} calls this week",
                "roadmap": f"{c['roadmap_items']} items", "amplitude": f"{c['usage_rows']:,} weekly data points"}
    return out


def connections(wid: str) -> list[dict]:
    from . import tenants
    rows = _connection_rows(wid)
    t = tenants.for_graph(_workspace(wid)["graph"])
    counts = _demo_counts(t)
    out = []
    for s in SOURCES:
        if s.get("commercial") and "hubspot" not in counts:
            continue
        c = rows.get(s["id"], {})
        out.append({**s, "demo": counts.get(s["id"], s["demo"]), "status": c.get("status", "disconnected"), "mode": c.get("mode", "demo"),
                    "connectedAt": c.get("connectedAt"), "live": False,
                    "liveNote": "Live ingestion isn't available yet. The demo export keeps this source populated."})
    g = rows.get("google", {})
    out.append({**ACTIONS[0], "status": g.get("status", "disconnected"), "mode": "live" if g.get("status") == "connected" else None,
                "connectedAt": g.get("connectedAt"), "account": g.get("account"), "live": True,
                "available": google_configured(),
                "liveNote": None if google_configured() else "Needs a Google OAuth client (GOOGLE_OAUTH_CLIENT_ID / _SECRET) on the server."})
    j = rows.get("jira_live", {})
    out.append({**ACTIONS[1], "status": j.get("status", "disconnected"), "mode": "live" if j.get("status") == "connected" else None,
                "connectedAt": j.get("connectedAt"), "account": j.get("account"), "live": True, "available": True,
                "liveNote": None})
    out.append({"id": "gemini", "name": "Gemini", "kind": "ai", "category": "AI",
                "description": "Writes interview questions, cited answers and runbook updates from retrieved evidence.",
                "status": "connected" if settings().llm_enabled else "disconnected",
                "mode": "server" if settings().llm_enabled else None, "live": True, "available": settings().llm_enabled,
                "liveNote": None if settings().llm_enabled else "Set GEMINI_API_KEY on the server."})
    return out


def _store(wid: str, provider: str, secret: dict, account: str, user_id: str) -> None:
    db.run("MATCH (c:Connection {provider: $p})-[:IN]->(:Workspace {id: $w}) DETACH DELETE c", {"p": provider, "w": wid}, g=_g())
    db.run("""MATCH (w:Workspace {id: $w})
              CREATE (:Connection {id: $id, provider: $p, status: 'connected', mode: 'live', account: $acct,
                                   connectedAt: $at, connectedBy: $by, secret: $s})-[:IN]->(w)""",
           {"w": wid, "id": f"{wid}:{provider}", "p": provider, "acct": account, "at": now().isoformat(timespec="seconds"),
            "by": user_id, "s": secretbox.seal(secret)}, g=_g())


def connect_jira(user_id: str, wid: str, base_url: str, email: str, token: str, project: str) -> dict:
    require_admin(user_id, wid)
    base_url = (base_url or "").strip().rstrip("/")
    if not re.match(r"^https://[\w.-]+$", base_url):
        raise AuthError("Use your Jira site URL, like https://your-team.atlassian.net")
    if not project.strip():
        raise AuthError("Which project should Relay create handover tasks in?")
    try:
        r = httpx.get(f"{base_url}/rest/api/3/myself", auth=(email.strip(), token.strip()), timeout=15)
    except httpx.HTTPError as e:
        raise AuthError(f"Couldn't reach {base_url}: {e}") from e
    if r.status_code != 200:
        raise AuthError("Jira rejected those credentials. Check the email and API token.", 400)
    account = r.json().get("emailAddress") or email
    _store(wid, "jira_live", {"base_url": base_url, "email": email.strip(), "token": token.strip(),
                              "project": project.strip().upper()}, f"{account} · {base_url.removeprefix('https://')}", user_id)
    return next(c for c in connections(wid) if c["id"] == "jira_live")


def connect_google(user_id: str, wid: str, refresh_token: str, account: str) -> None:
    _store(wid, "google", {"refresh_token": refresh_token}, account, user_id)


def disconnect(user_id: str, wid: str, provider: str) -> None:
    require_admin(user_id, wid)
    if provider not in ("google", "jira_live"):
        raise AuthError("Demo sources stay connected so the workspace keeps its data")
    db.run("MATCH (c:Connection {provider: $p})-[:IN]->(:Workspace {id: $w}) DETACH DELETE c", {"p": provider, "w": wid}, g=_g())


def secret(wid: str | None, provider: str) -> dict:
    if not wid:
        return {}
    c = _connection_rows(wid).get(provider)
    return secretbox.open_sealed(c.get("secret")) if c and c.get("status") == "connected" else {}


# --------------------------------------------------------------- journey

def journey(user_id: str, ws: dict) -> dict:
    """The full circle, computed from real state: setup, then one complete handover."""
    f = flags(user_id)
    team = members(ws["id"])
    g = db.graph(ws["graph"])

    def has(q: str) -> bool:
        return bool(db.rows(q, g=g, readonly=True))

    live = [c for c in connections(ws["id"]) if c.get("kind") == "action" and c["status"] == "connected"]
    commercial = has("MATCH (a:Account) WHERE a.crmHealthScore IS NOT NULL RETURN a.id LIMIT 1")
    if commercial:
        steps = [
            {"id": "workspace", "group": "Set up", "label": "Create your workspace", "done": True, "href": "/settings/workspace"},
            {"id": "connections", "group": "Set up", "label": "Review your connections",
             "done": bool(live) or "connections" in f, "href": "/settings/connections"},
            {"id": "teammates", "group": "Set up", "label": "Invite a teammate",
             "done": len(team["members"]) > 1 or bool(team["invites"]), "href": "/settings/team"},
            {"id": "radar", "group": "Account Health", "label": "Find at-risk accounts that look healthy", "done": "radar" in f,
             "href": "/accounts", "persona": "p-arnav"},
            {"id": "investigate", "group": "Account Health", "label": "Investigate Northwind Foods",
             "done": has("MATCH (i:Investigation) RETURN i.id LIMIT 1"), "href": "/accounts/cust-northwind-foods", "persona": "p-arnav"},
            {"id": "handover", "group": "Handovers", "label": "Preview Rahul's departure",
             "done": has("MATCH (h:Handover) WHERE h.analyzedAt IS NOT NULL RETURN h.id LIMIT 1"), "href": "/people/p-rahul",
             "persona": "p-priya"},
            {"id": "capture", "group": "Handovers", "label": "Answer a question as Rahul",
             "done": has("MATCH (k:Knowledge) RETURN k.id LIMIT 1"), "href": "/interview", "persona": "p-rahul"},
            {"id": "call", "group": "Sales Assist", "label": "Run the Northwind renewal call",
             "done": has("MATCH (m:Meeting) WHERE m.callId IS NOT NULL RETURN m.id LIMIT 1"),
             "href": "/meetings/evt-2026-10-19-northwind", "persona": "p-sneha"},
            {"id": "followup", "group": "Sales Assist", "label": "Approve the follow-up steps",
             "done": has("MATCH (x:Action {origin: 'account-health'}) WHERE x.investigationId STARTS WITH 'call-' RETURN x.id LIMIT 1"),
             "href": "/meetings/evt-2026-10-19-northwind", "persona": "p-sneha"},
            {"id": "dayone", "group": "Day One", "label": "Open Aisha's Day One", "done": "dayone" in f,
             "href": "/day-one", "persona": "p-aisha"},
            {"id": "ask", "group": "Day One", "label": "Ask why something works the way it does", "done": "ask" in f,
             "href": "/day-one", "persona": "p-aisha", "ask": "Why does wallet settlement run at 6 AM?"},
            {"id": "close", "group": "Day One", "label": "Close the handover",
             "done": has("MATCH (h:Handover {status: 'closed'}) RETURN h.id LIMIT 1"), "href": "/handovers", "persona": "p-priya"},
        ]
        if user(user_id).get("sandbox"):
            steps = [s for s in steps if s["group"] != "Set up"]   # signed in from the team picker: no setup to do
        done = sum(s["done"] for s in steps)
        nxt = next((s for s in steps if not s["done"]), None)
        return {"steps": steps, "done": done, "total": len(steps), "next": nxt["id"] if nxt else None,
                "dismissed": "journey-dismissed" in f, "title": "Try the full story"}
    from . import tenants
    w = tenants.for_graph(ws["graph"]).world

    def first(pid: str) -> str:
        r = db.rows("MATCH (p:Person {id: $p}) RETURN p.name AS n", {"p": pid}, g=g, readonly=True)
        return r[0]["n"].split()[0] if r else pid

    steps = [
        {"id": "workspace", "group": "Set up", "label": "Create your workspace", "done": True, "href": "/settings/workspace"},
        {"id": "connections", "group": "Set up", "label": "Review your connections",
         "done": bool(live) or "connections" in f, "href": "/settings/connections"},
        {"id": "teammates", "group": "Set up", "label": "Invite a teammate",
         "done": len(team["members"]) > 1 or bool(team["invites"]), "href": "/settings/team"},
        {"id": "risk", "group": "Run a handover", "label": "See where knowledge is at risk", "done": "risk" in f, "href": "/home"},
        {"id": "handover", "group": "Run a handover", "label": f"Start {first(w.LEAVER)}'s handover",
         "done": has("MATCH (h:Handover) RETURN h.id LIMIT 1"), "href": f"/people/{w.LEAVER}"},
        {"id": "capture", "group": "Run a handover", "label": f"Answer a question as {first(w.LEAVER)}",
         "done": has("MATCH (k:Knowledge) RETURN k.id LIMIT 1"), "href": "/interview", "persona": w.LEAVER},
        {"id": "verify", "group": "Run a handover", "label": f"Verify an answer as {first(w.MANAGER)}",
         "done": has("MATCH (k:Knowledge) WHERE k.verifiedAt IS NOT NULL RETURN k.id LIMIT 1"), "href": "/handovers", "persona": w.MANAGER},
        {"id": "dayone", "group": "Welcome the joiner", "label": f"Open {first(w.JOINER)}'s Day One", "done": "dayone" in f,
         "href": "/day-one", "persona": w.JOINER},
        {"id": "ask", "group": "Welcome the joiner", "label": "Ask why something works the way it does", "done": "ask" in f,
         "href": "/day-one", "persona": w.JOINER, "ask": "Why does the settlement job run at 2 AM?"},
        {"id": "close", "group": "Close the loop", "label": "Close the handover and watch company risk drop",
         "done": has("MATCH (h:Handover {status: 'closed'}) RETURN h.id LIMIT 1"), "href": "/handovers", "persona": w.MANAGER},
    ]
    done = sum(s["done"] for s in steps)
    nxt = next((s for s in steps if not s["done"]), None)
    return {"steps": steps, "done": done, "total": len(steps), "next": nxt["id"] if nxt else None,
            "dismissed": "journey-dismissed" in f}
