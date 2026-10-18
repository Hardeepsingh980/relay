"""Team sign-in: one click signs you in as a Cheerio teammate, inside your own copy of the workspace.

Each browser gets a sandbox: a hidden owner account and its own workspace graph, kept by a long-lived
cookie. Switching teammates keeps the same workspace, so a handover Priya starts shows up for Arnav, and
two visitors never see each other's changes. Idle sandboxes are deleted after a day.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import threading
import time
import uuid

from . import auth, db, tenants, workspaces
from .config import now

log = logging.getLogger("relay.team")

SANDBOX_COOKIE = "relay_team"
SANDBOX_DAYS = 7
IDLE_HOURS = 24
MAX_SANDBOXES = 150
TENANT = "cheerio"

# What each teammate does first, shown on the sign-in page.
TASKS = {
    "head_cs": "See which customers are about to leave, and why.",
    "csm": "Prepare for today's renewal call, then run it with live help.",
    "manager": "Run Rahul's handover before his last day on Friday.",
    "leaver": "Answer a few questions so what you know stays.",
    "joiner": "Start your first day with everything Rahul knew.",
}
ROLE = {"head_cs": "Head of Customer Success", "csm": "Customer Success Manager", "manager": "Engineering Manager",
        "leaver": "Senior Engineer · leaving Friday", "joiner": "Engineer · joined today"}


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def members() -> list[dict]:
    """The teammates you can sign in as, in the order of the story."""
    from .ingest.pipeline import demo_graph
    t = tenants.get(TENANT)
    people = t.world.PERSONAS
    rows = db.rows("MATCH (p:Person) WHERE p.id IN $ids RETURN p.id AS id, p.name AS name, p.team AS team",
                   {"ids": [p["id"] for p in people]}, g=db.graph(demo_graph(t) + "_base"), readonly=True)
    by_id = {r["id"]: r for r in rows}
    out = []
    for p in people:
        r = by_id.get(p["id"])
        if not r:
            continue
        out.append({"id": p["id"], "name": r["name"], "team": r["team"], "persona": p["persona"], "home": p["home"],
                    "role": ROLE.get(p["persona"], ""), "task": TASKS.get(p["persona"], "")})
    return out


def preview() -> dict:
    """Live numbers from the sample workspace's pristine graph, for the sign-in and landing pages."""
    from .ingest.pipeline import demo_graph
    g = db.graph(demo_graph(tenants.get(TENANT)) + "_base")
    t0 = time.perf_counter()
    nodes = db.rows("MATCH (n) RETURN count(n) AS n", g=g, readonly=True)[0]["n"]
    rels = db.rows("MATCH ()-[r]->() RETURN count(r) AS n", g=g, readonly=True)[0]["n"]
    counts = {r["l"]: r["n"] for r in db.rows(
        """MATCH (n) WHERE n:Account OR n:Person OR n:Message OR n:Ticket OR n:Meeting OR n:Doc
           RETURN labels(n)[0] AS l, count(n) AS n""", g=g, readonly=True)}
    silent = db.rows("""MATCH (a:Account) WHERE a.silentRisk = true
                        RETURN a.name AS name, a.crmHealthScore AS crm, a.detectiveRisk AS risk, a.arr AS arr
                        ORDER BY a.detectiveRisk DESC LIMIT 4""", g=g, readonly=True)
    only = db.rows("""MATCH (p:Person {id: 'p-rahul'})-[k:KNOWS|DECIDED]->(i) WHERE k.score > 0.6
                      OPTIONAL MATCH (o:Person)-[k2:KNOWS|DECIDED]->(i)
                      WHERE o.id <> p.id AND o.status IN ['active', 'joining'] AND k2.score > 0.4
                      WITH i, count(o) AS others WHERE others = 0 RETURN count(i) AS n""", g=g, readonly=True)
    return {"nodes": nodes, "relationships": rels, "counts": counts, "silent": silent,
            "onlyRahul": only[0]["n"] if only else 0, "ms": round((time.perf_counter() - t0) * 1000, 1)}


def _sandbox_for(token: str | None) -> tuple[dict, dict] | None:
    """(user, workspace) for a sandbox cookie, if both still exist."""
    if not token:
        return None
    r = db.rows("""MATCH (u:User {sandboxHash: $h})-[:MEMBER_OF]->(w:Workspace) RETURN u, w LIMIT 1""",
                {"h": _hash(token)}, g=auth._g(), readonly=True)
    return (r[0]["u"], r[0]["w"]) if r else None


def _create_sandbox() -> tuple[dict, dict, str]:
    token = secrets.token_urlsafe(24)
    uid = "u-team-" + uuid.uuid4().hex[:12]
    stamp = now().isoformat(timespec="seconds")
    db.run("""CREATE (:User {id: $id, name: 'Cheerio team', email: $email, sandbox: true, sandboxHash: $h,
                             createdAt: $at, onboardedAt: $at, jobRole: 'Cheerio team'})""",
           {"id": uid, "email": f"{uid}@team.relay", "h": _hash(token), "at": stamp}, g=auth._g())
    ws = workspaces.create_workspace(uid, "Cheerio", tenant=TENANT)
    w = workspaces._workspace(ws["id"])
    u = db.rows("MATCH (u:User {id: $id}) RETURN u", {"id": uid}, g=auth._g(), readonly=True)[0]["u"]
    return u, w, token


def touch(workspace_id: str) -> None:
    db.run("MATCH (w:Workspace {id: $id}) SET w.lastActiveAt = $t", {"id": workspace_id, "t": time.time()}, g=auth._g())


def sign_in(person_id: str, sandbox_token: str | None) -> tuple[dict, dict, str, dict]:
    """(public user, workspace, sandbox token, teammate) for a one-click sign-in as `person_id`."""
    member = next((m for m in members() if m["id"] == person_id), None)
    if not member:
        raise auth.AuthError("Pick someone from the team", 404)
    found = _sandbox_for(sandbox_token)
    if found:
        u, w = found
        token = sandbox_token
    else:
        prune()
        u, w, token = _create_sandbox()
    touch(w["id"])
    return auth.public(u), w, token, member


def _delete(user_id: str, ws: dict) -> None:
    try:
        if db.exists(ws["graph"]):
            db.graph(ws["graph"]).delete()
    except Exception as e:  # noqa: BLE001 - a missing graph must not block cleanup
        log.warning("could not delete graph %s: %s", ws.get("graph"), e)
    db.run("""MATCH (w:Workspace {id: $w}) OPTIONAL MATCH (c)-[:IN]->(w) DETACH DELETE c, w""", {"w": ws["id"]}, g=auth._g())
    db.run("""MATCH (u:User {id: $u}) OPTIONAL MATCH (s:Session)-[:FOR]->(u) DETACH DELETE s, u""", {"u": user_id}, g=auth._g())


def prune() -> int:
    """Delete sandboxes idle for a day, and the oldest ones beyond the cap."""
    rows = db.rows("""MATCH (u:User {sandbox: true})-[:MEMBER_OF]->(w:Workspace)
                      RETURN u.id AS uid, w AS w, coalesce(w.lastActiveAt, 0) AS seen ORDER BY seen DESC""",
                   g=auth._g(), readonly=True)
    cutoff = time.time() - IDLE_HOURS * 3600
    doomed = [r for i, r in enumerate(rows) if r["seen"] < cutoff or i >= MAX_SANDBOXES - 1]
    for r in doomed:
        _delete(r["uid"], r["w"])
    if doomed:
        log.info("removed %d idle sandboxes", len(doomed))
    return len(doomed)


def start_janitor(every_seconds: int = 1800) -> None:
    def loop() -> None:
        while True:
            time.sleep(every_seconds)
            try:
                prune()
            except Exception as e:  # noqa: BLE001 - keep the janitor alive
                log.warning("sandbox cleanup failed: %s", e)
    threading.Thread(target=loop, name="sandbox-janitor", daemon=True).start()


def ensure_evaluator() -> None:
    """A shared email and password login for evaluators (RELAY_EVAL_EMAIL / RELAY_EVAL_PASSWORD), with a workspace."""
    import os
    email, password = os.getenv("RELAY_EVAL_EMAIL"), os.getenv("RELAY_EVAL_PASSWORD")
    if not email or not password:
        return
    email = email.strip().lower()
    try:
        found = auth._user_by_email(email)
        if not found:
            auth.sign_up("Evaluator", email, password)
            found = auth._user_by_email(email)
        db.run("MATCH (u:User {id: $id}) SET u.onboardedAt = coalesce(u.onboardedAt, $at), u.defaultPersona = 'p-arnav'",
               {"id": found["id"], "at": now().isoformat(timespec="seconds")}, g=auth._g())
        if not workspaces.memberships(found["id"]):
            workspaces.create_workspace(found["id"], "Cheerio", tenant=TENANT)
        log.info("evaluator login ready: %s", email)
    except Exception as e:  # noqa: BLE001 - never block startup on this
        log.warning("could not prepare the evaluator login: %s", e)



_LANDING: dict = {}


def landing_graph() -> dict:
    """A real slice of the sample company's graph for the landing page, plus three paths the agents walk.

    Everything comes from Cypher on the pristine graph. Node keys are FalkorDB ids, and the result is cached
    for ten minutes.
    """
    from .api_graph import TYPES
    from .ingest.pipeline import demo_graph
    if _LANDING.get("at", 0) > time.time() - 600:
        return _LANDING["data"]
    g = db.graph(demo_graph(tenants.get(TENANT)) + "_base")
    q = lambda c, p=None: db.rows(c, p or {}, g=g, readonly=True)  # noqa: E731
    picks = [
        "MATCH (n:Person) WHERE n.status <> 'left' RETURN ID(n) AS id",
        "MATCH (n) WHERE n:Team OR n:System OR n:Feature OR n:Decision OR n:Workaround OR n:RoadmapItem OR n:Promise RETURN ID(n) AS id",
        "MATCH (n:Account) RETURN ID(n) AS id ORDER BY n.arr DESC LIMIT 40",
        "MATCH (n:Account) WHERE n.silentRisk = true RETURN ID(n) AS id",
        """MATCH (t:Ticket {source: 'support'})-[:SYMPTOM_OF]->(n:Bug) WITH n, count(t) AS c
           RETURN ID(n) AS id ORDER BY c DESC LIMIT 16""",
        "MATCH (n:Contact)-[:WORKS_AT]->(a:Account) WHERE a.silentRisk = true OR a.arr >= 800000 RETURN ID(n) AS id LIMIT 90",
        """MATCH (a:Account)<-[:CONCERNS]-(n:Ticket {source: 'support'})-[:SYMPTOM_OF]->(:Bug)
           WHERE a.silentRisk = true RETURN ID(n) AS id LIMIT 60""",
    ]
    ids = {r["id"] for c in picks for r in q(c)}

    # The three findings. Each path starts where the agent starts and follows the hops it takes.
    stories = []
    chain = q("""MATCH (a:Account {id: 'cust-northwind-foods'})<-[:CONCERNS]-(t:Ticket {source: 'support'})-[:SYMPTOM_OF]->(b:Bug)
                 -[:AFFECTS]->(f:Feature)
                 MATCH (c:Contact)-[:RAISED]->(t)
                 OPTIONAL MATCH (c)-[:SUCCEEDED]->(former:Contact)
                 OPTIONAL MATCH (f)-[:OWNED_BY]->(o:Person)
                 RETURN a.name AS account, a.detectiveRisk AS risk, a.crmHealthScore AS crm, b.id AS bug, ID(a) AS a,
                        collect(DISTINCT ID(former)) AS former, collect(DISTINCT ID(c)) AS raisers, collect(DISTINCT ID(t)) AS tickets,
                        ID(b) AS b, ID(f) AS f, ID(o) AS o
                 LIMIT 1""")
    if chain:
        c = chain[0]
        stories.append({"agent": "Account Health",
                        "path": [c["a"], *c["former"], *c["raisers"], *c["tickets"][:3], c["b"], c["f"], c["o"]],
                        "text": f"{c['account']} looks healthy in HubSpot ({c['crm']}/100). Relay says {c['risk']}% risk: "
                                f"the main contact left, and {len(c['tickets'][:3])} tickets point to one bug, {c['bug']}.",
                        "chip": f"{c['account']} · {c['risk']}% risk · HubSpot says {c['crm']}"})
    pv = preview()
    rahul = q("""MATCH (p:Person {id: 'p-rahul'})-[k:KNOWS]->(i) WHERE k.score > 0.6 AND (i:System OR i:Account)
                 RETURN ID(p) AS p, ID(i) AS i ORDER BY k.score DESC LIMIT 6""")
    if rahul:
        stories.append({"agent": "Handovers", "path": [rahul[0]["p"]] + [r["i"] for r in rahul],
                        "text": f"Rahul Verma leaves on Friday. Remove him from the graph, and {pv['onlyRahul']} things "
                                "have nobody else who knows them.",
                        "chip": f"Rahul Verma · {pv['onlyRahul']} things only he knows"})
    prm = q("""MATCH (m:Person)-[:MADE]->(p:Promise {id: 'prm-northwind-sso'})-[:DEPENDS_ON]->(r:RoadmapItem)
               MATCH (p)-[:TO]->(a:Account)
               RETURN ID(m) AS m, ID(p) AS p, ID(r) AS r, ID(a) AS a, r.etaLabel AS eta, m.name AS who, a.name AS account""")
    if prm:
        p = prm[0]
        stories.append({"agent": "Sales Assist", "path": [p["a"], p["p"], p["m"], p["r"]],
                        "text": f"{p['who']} promised {p['account']} SSO by December. The roadmap now says {p['eta']}, "
                                "so Sales Assist warns before the renewal call.",
                        "chip": f"SSO promised for December · roadmap says {p['eta']}"})
    for s in stories:
        s["path"] = list(dict.fromkeys(x for x in s["path"] if x is not None))
        ids.update(s["path"])

    nodes = q("""MATCH (n) WHERE ID(n) IN $ids
                 RETURN ID(n) AS id, labels(n) AS labels,
                        coalesce(n.name, n.title, n.text, n.summary, n.id) AS name, n.id AS key""", {"ids": list(ids)})
    order = list(TYPES)
    for n in nodes:
        labels = n.pop("labels")
        n["type"] = min((lb for lb in labels if lb in TYPES), key=order.index, default=labels[0] if labels else "Node")
    edges = q("""MATCH (n)-[r]->(m) WHERE ID(n) IN $ids AND ID(m) IN $ids AND ID(n) <> ID(m)
                 RETURN ID(n) AS s, ID(m) AS t, type(r) AS type""", {"ids": list(ids)})
    data = {"nodes": nodes, "edges": edges, "stories": stories,
            "colors": {t: v[1] for t, v in TYPES.items()}, "preview": pv}
    _LANDING.update(at=time.time(), data=data)
    return data
