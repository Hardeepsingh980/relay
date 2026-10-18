"""HTTP API (FastAPI) with SSE streams.

Every request carries a session cookie (who is signed in) and acts inside that
session's workspace, whose knowledge graph is selected per request. The demo
persona (Priya / Rahul / Aisha) travels in X-Relay-Persona.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import threading
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import run_in_threadpool

from . import (actions, analysis, ask, auth, db, google_oauth, graphviews, handover, interview, llm, onboarding, people,
               proposals, tenants, workspaces)
from . import team as sandboxes
from .api_connectors import router as connectors_router
from .api_graph import router as graph_router
from .api_relay import router as relay_router
from .api_repos import router as repos_router
from .config import DEMO_NOW, now, settings
from .events import bus

log = logging.getLogger("relay.api")
app = FastAPI(title="Relay", version="0.3.0",
              description="Company brain: account health, knowledge continuity and sales assist on one graph per company")

PUBLIC_PATHS = ("/api/health", "/api/auth/", "/api/public/")
ACCOUNT_PATHS = ("/api/me", "/api/workspaces", "/api/invites/")   # signed in, workspace optional


def _context(token: str | None) -> tuple[dict, dict | None] | None:
    ctx = auth.session_context(token)
    if not ctx:
        return None
    user, preferred = ctx
    return user, workspaces.resolve(user["id"], preferred)


@app.middleware("http")
async def require_session(request: Request, call_next):
    """Signed-in user for every API route (except health/auth), and a workspace for workspace data."""
    path = request.url.path
    if request.method == "OPTIONS" or not path.startswith("/api/") or path.startswith(PUBLIC_PATHS):
        return await call_next(request)
    if path.startswith("/api/invites/") and request.method == "GET":
        return await call_next(request)  # invite preview is public
    ctx = await run_in_threadpool(_context, request.cookies.get(auth.COOKIE))
    if not ctx:
        return JSONResponse({"error": "Sign in to continue"}, status_code=401)
    user, ws = ctx
    request.state.user, request.state.ws = user, ws
    if ws:
        db.use_workspace(ws["id"], ws["graph"])
    elif not path.startswith(ACCOUNT_PATHS):
        return JSONResponse({"error": "Create or join a workspace first", "code": "no_workspace"}, status_code=403)
    return await call_next(request)


# Added after the auth middleware so it wraps it: 401s still carry CORS headers.
app.add_middleware(CORSMiddleware, allow_origins=list(settings().cors_origins), allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

def personas() -> list[dict]:
    """The current tenant's demo personas (falls back to manager / leaver / joiner)."""
    w = tenants.current().world
    return getattr(w, "PERSONAS", None) or [
        {"id": w.MANAGER, "persona": "manager", "home": "/home"},
        {"id": w.LEAVER, "persona": "leaver", "home": "/interview"},
        {"id": w.JOINER, "persona": "joiner", "home": "/day-one"},
    ]


ANALYSIS_DELAY = float(os.getenv("RELAY_ANALYSIS_DELAY", "0.25"))


@app.exception_handler(handover.HandoverError)
@app.exception_handler(actions.ActionError)
async def _bad_request(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"error": str(exc)}, status_code=400)


@app.exception_handler(auth.AuthError)
async def _auth_error(_: Request, exc: auth.AuthError) -> JSONResponse:
    return JSONResponse({"error": str(exc)}, status_code=exc.status)


def _uid(request: Request) -> str:
    return request.state.user["id"]


def _wid(request: Request) -> str:
    ws = getattr(request.state, "ws", None)
    if not ws:
        raise auth.AuthError("Create or join a workspace first", 403)
    return ws["id"]


# --------------------------------------------------------------------- auth

class SignUp(BaseModel):
    name: str
    email: str
    password: str
    invite: str | None = None


class SignIn(BaseModel):
    email: str
    password: str
    invite: str | None = None


def _set_cookie(resp, token: str, ttl: int) -> None:
    resp.set_cookie(auth.COOKIE, token, max_age=ttl, httponly=True, samesite="lax", secure=auth.cookie_secure(), path="/")


def _start_session(user: dict, request: Request, invite: str | None = None, status: int = 200) -> JSONResponse:
    token, ttl = auth.create_session(user["id"], request.headers.get("user-agent"))
    joined = None
    if invite:
        joined = workspaces.accept_invite(invite, user["id"])
        auth.set_session_workspace(token, joined["id"])
    resp = JSONResponse({"user": user, "joined": joined}, status_code=status)
    _set_cookie(resp, token, ttl)
    return resp


@app.get("/api/auth/providers")
def providers() -> dict:
    return {"password": True, "google": google_oauth.configured()}


@app.post("/api/auth/sign-up")
def sign_up(body: SignUp, request: Request) -> JSONResponse:
    if body.invite:
        info = workspaces.invite_info(body.invite)
        if body.email.strip().lower() != info["email"]:
            raise auth.AuthError(f"This invite was sent to {info['email']}. Use that address to accept it.", 403)
    return _start_session(auth.sign_up(body.name, body.email, body.password), request, body.invite, 201)


@app.post("/api/auth/sign-in")
def sign_in(body: SignIn, request: Request) -> JSONResponse:
    return _start_session(auth.sign_in(body.email, body.password), request, body.invite)


class TeamSignIn(BaseModel):
    personId: str


@app.get("/api/public/graph")
def public_graph() -> dict:
    """A real slice of the sample company's graph and three agent paths, for the landing page."""
    return sandboxes.landing_graph()


@app.get("/api/auth/team")
def team_members() -> dict:
    """Who you can sign in as with one click (each browser gets its own copy of the Cheerio workspace)."""
    return {"company": tenants.get(sandboxes.TENANT).name, "members": sandboxes.members(), "preview": sandboxes.preview()}


@app.post("/api/auth/team")
def team_sign_in(body: TeamSignIn, request: Request) -> JSONResponse:
    user, ws, sandbox_token, member = sandboxes.sign_in(body.personId, request.cookies.get(sandboxes.SANDBOX_COOKIE))
    token, ttl = auth.create_session(user["id"], request.headers.get("user-agent"))
    auth.set_session_workspace(token, ws["id"])
    resp = JSONResponse({"user": user, "member": member})
    _set_cookie(resp, token, ttl)
    resp.set_cookie(sandboxes.SANDBOX_COOKIE, sandbox_token, max_age=sandboxes.SANDBOX_DAYS * 86400, httponly=True,
                    samesite="lax", secure=auth.cookie_secure(), path="/")
    return resp


@app.on_event("startup")
def _start_janitor() -> None:
    sandboxes.start_janitor()
    threading.Thread(target=sandboxes.ensure_evaluator, name="evaluator-login", daemon=True).start()


@app.post("/api/auth/sign-out")
def sign_out(request: Request) -> JSONResponse:
    auth.revoke(request.cookies.get(auth.COOKIE))
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE, path="/")
    return resp


@app.get("/api/auth/me")
def auth_me(request: Request) -> dict:
    ctx = _context(request.cookies.get(auth.COOKIE))
    if not ctx:
        raise auth.AuthError("Not signed in", 401)
    user, ws = ctx
    return {"user": workspaces.user(user["id"]), "workspace": workspaces._ws_view(ws, ws["role"]) if ws else None}


def _front(path: str) -> str:
    return f"{workspaces.public_url()}{path}"


@app.get("/api/auth/google/start")
def google_start(next: str = "/home", invite: str | None = None) -> RedirectResponse:
    if not google_oauth.configured():
        return RedirectResponse(_front("/sign-in?error=" + quote("Google sign-in is not set up on this server yet.")))
    nxt = next if next.startswith("/") and not next.startswith("//") else "/home"
    return RedirectResponse(google_oauth.start("sign-in", next=nxt, invite=invite))


@app.get("/api/auth/google/callback")
def google_callback(request: Request, code: str | None = None, state: str | None = None,
                    error: str | None = None) -> RedirectResponse:
    st = google_oauth.take_state(state)
    if not st:
        return RedirectResponse(_front("/sign-in?error=" + quote("That Google sign-in expired. Please try again.")))
    if error or not code:
        back = "/settings/connections" if st["purpose"] == "connect" else "/sign-in"
        return RedirectResponse(_front(f"{back}?error=" + quote("Google sign-in was canceled.")))
    try:
        tokens = google_oauth.exchange(code)
        info = google_oauth.userinfo(tokens["access_token"])
    except Exception as e:
        log.warning("google oauth failed: %s", e)
        return RedirectResponse(_front("/sign-in?error=" + quote("Google did not confirm the sign-in. Please try again.")))
    if st["purpose"] == "connect":
        if not tokens.get("refresh_token"):
            return RedirectResponse(_front("/settings/connections?error=" + quote("Google did not give offline access. Try again.")))
        workspaces.connect_google(st["user"], st["workspace"], tokens["refresh_token"], info.get("email", "Google account"))
        return RedirectResponse(_front("/settings/connections?connected=google"))
    if not info.get("email_verified", True):
        return RedirectResponse(_front("/sign-in?error=" + quote("Your Google email address is not verified.")))
    user = auth.upsert_google_user(info["sub"], info["email"], info.get("name"), info.get("picture"))
    token, ttl = auth.create_session(user["id"], request.headers.get("user-agent"))
    dest = st.get("next") or "/home"
    if st.get("invite"):
        try:
            joined = workspaces.accept_invite(st["invite"], user["id"])
            auth.set_session_workspace(token, joined["id"])
        except auth.AuthError as e:
            dest = "/welcome?error=" + quote(str(e))
    if not workspaces.memberships(user["id"]):
        dest = "/welcome"
    resp = RedirectResponse(_front(dest))
    _set_cookie(resp, token, ttl)
    return resp


# ------------------------------------------------------- account & onboarding

class Profile(BaseModel):
    name: str | None = None
    jobRole: str | None = None
    defaultPersona: str | None = None


@app.get("/api/me")
def get_me(request: Request) -> dict:
    ws = request.state.ws
    return {"user": workspaces.user(_uid(request)),
            "workspace": workspaces._ws_view(ws, ws["role"]) if ws else None,
            "workspaces": [workspaces._ws_view(w, w["role"]) for w in workspaces.memberships(_uid(request))]}


@app.patch("/api/me")
def patch_me(body: Profile, request: Request) -> dict:
    return workspaces.update_profile(_uid(request), job_role=body.jobRole, persona=body.defaultPersona, name=body.name)


@app.post("/api/me/onboarded")
def onboarded(request: Request) -> dict:
    return workspaces.complete_onboarding(_uid(request))


class NewWorkspace(BaseModel):
    name: str
    tenant: str | None = None


@app.post("/api/workspaces")
def create_workspace(body: NewWorkspace, request: Request) -> dict:
    ws = workspaces.create_workspace(_uid(request), body.name, body.tenant)
    auth.set_session_workspace(request.cookies.get(auth.COOKIE), ws["id"])
    return ws


@app.post("/api/workspaces/{wid}/switch")
def switch_workspace(wid: str, request: Request) -> dict:
    if not workspaces.role_in(_uid(request), wid):
        raise auth.AuthError("You are not a member of that workspace", 403)
    auth.set_session_workspace(request.cookies.get(auth.COOKIE), wid)
    return {"ok": True}


@app.patch("/api/workspace")
def rename_workspace(body: NewWorkspace, request: Request) -> dict:
    return workspaces.rename(_uid(request), _wid(request), body.name)


@app.get("/api/invites/{token}")
def invite_preview(token: str) -> dict:
    return workspaces.invite_info(token)


@app.post("/api/invites/{token}/accept")
def invite_accept(token: str, request: Request) -> dict:
    ws = workspaces.accept_invite(token, _uid(request))
    auth.set_session_workspace(request.cookies.get(auth.COOKIE), ws["id"])
    return ws


# ------------------------------------------------------------- teammates

class Invites(BaseModel):
    emails: list[str]
    role: str = "member"


class RoleChange(BaseModel):
    role: str


@app.get("/api/workspace/members")
def team(request: Request) -> dict:
    return workspaces.members(_wid(request))


@app.post("/api/workspace/invites")
def send_invites(body: Invites, request: Request) -> dict:
    return {"invites": workspaces.invite(_uid(request), _wid(request), body.emails, body.role)}


@app.delete("/api/workspace/invites/{iid}")
def revoke_invite(iid: str, request: Request) -> dict:
    workspaces.revoke_invite(_uid(request), _wid(request), iid)
    return {"ok": True}


@app.patch("/api/workspace/members/{mid}")
def change_role(mid: str, body: RoleChange, request: Request) -> dict:
    workspaces.set_role(_uid(request), _wid(request), mid, body.role)
    return {"ok": True}


@app.delete("/api/workspace/members/{mid}")
def remove_member(mid: str, request: Request) -> dict:
    workspaces.remove_member(_uid(request), _wid(request), mid)
    return {"ok": True}


# ----------------------------------------------------------- connections

class JiraConnect(BaseModel):
    baseUrl: str
    email: str
    token: str
    project: str


@app.get("/api/workspace/connections")
def list_connections(request: Request) -> list[dict]:
    workspaces.mark(_uid(request), "connections")
    return workspaces.connections(_wid(request))


@app.post("/api/workspace/connections/jira")
def connect_jira(body: JiraConnect, request: Request) -> dict:
    return workspaces.connect_jira(_uid(request), _wid(request), body.baseUrl, body.email, body.token, body.project)


@app.get("/api/workspace/connections/google/start")
def connect_google(request: Request) -> RedirectResponse:
    workspaces.require_admin(_uid(request), _wid(request))
    if not google_oauth.configured():
        return RedirectResponse(_front("/settings/connections?error=" + quote("Google is not set up on this server yet.")))
    return RedirectResponse(google_oauth.start("connect", user=_uid(request), workspace=_wid(request)))


@app.delete("/api/workspace/connections/{provider}")
def disconnect(provider: str, request: Request) -> dict:
    workspaces.disconnect(_uid(request), _wid(request), provider)
    return {"ok": True}


# --------------------------------------------------------------- journey

@app.get("/api/journey")
def journey(request: Request) -> dict:
    return workspaces.journey(_uid(request), request.state.ws)


@app.post("/api/journey/{step}")
def journey_mark(step: str, request: Request) -> dict:
    if step not in ("connections", "risk", "radar", "dayone", "ask", "journey-dismissed"):
        raise auth.AuthError("Unknown step")
    workspaces.mark(_uid(request), step)
    return workspaces.journey(_uid(request), request.state.ws)


def _persona(x_relay_persona: str | None) -> str:
    ids = [p["id"] for p in personas()]
    pid = x_relay_persona if x_relay_persona in ids else ids[0]
    if not handover.person(pid):
        raise HTTPException(401, "Unknown persona")
    return pid


# ------------------------------------------------------------------ session

@app.get("/api/health")
def health() -> dict:
    try:
        n = db.rows("MATCH (p:Person) RETURN count(p) AS n", readonly=True)[0]["n"]
        return {"ok": n > 0, "people": n}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/session")
def session(request: Request) -> dict:
    ws = request.state.ws
    if request.state.user.get("sandbox"):
        sandboxes.touch(ws["id"])
    t = tenants.current()
    has_accounts = db.rows("MATCH (a:Account) WHERE a.crmHealthScore IS NOT NULL RETURN count(a) AS n",
                           readonly=True)[0]["n"] > 0
    return {
        "user": workspaces.user(_uid(request)),
        "workspace": workspaces._ws_view(ws, ws["role"]),
        "personas": [{**handover.person(p["id"]), **p} for p in personas()],
        "demo": {"synthetic": True, "company": t.name, "tenant": t.id, "tagline": t.tagline,
                 "now": now().isoformat(timespec="minutes"), "dataAsOf": DEMO_NOW.isoformat(timespec="minutes"),
                 "note": "Sample workspace with synthetic data."},
        "modules": {"accountHealth": has_accounts, "salesAssist": has_accounts, "knowledge": True, "ask": True},
        "suggestions": getattr(t.world, "ASK_SUGGESTIONS", None) or [
            "Why does the settlement job run at 2 AM?", "Why do we keep idempotency keys for 72 hours?",
            "How do I fix a settlement “lock held” failure?", "Who else understands reconciliation-service?"],
        "integrations": actions.integrations(), "llm": llm.status(),
    }


# --------------------------------------------------------------------- home

@app.get("/api/home/knowledge-risk")
def home(request: Request) -> dict:
    workspaces.mark(_uid(request), "risk")
    risk = analysis.company_risk()
    return {**risk, "activeHandovers": [h for h in handover.list_handovers() if h["status"] != "closed"],
            "closedHandovers": [h for h in handover.list_handovers() if h["status"] == "closed"]}


@app.get("/api/people")
def list_people() -> list[dict]:
    return people.list_people()


@app.get("/api/people/{pid}")
def person(pid: str) -> dict:
    p = people.profile(pid)
    if not p:
        raise HTTPException(404, "No such person")
    return p


# ---------------------------------------------------------------- handovers

class NewHandover(BaseModel):
    leaverId: str
    lastDay: str
    joinerId: str | None = None


@app.post("/api/handovers")
def create_handover(body: NewHandover, x_relay_persona: str | None = Header(None)) -> dict:
    actor = _persona(x_relay_persona)
    return handover.create(body.leaverId, body.lastDay, body.joinerId, actor)


@app.get("/api/handovers")
def list_handovers() -> list[dict]:
    return handover.list_handovers()


@app.get("/api/handovers/{hid}")
def get_handover(hid: str) -> dict:
    return handover.get(hid)


@app.post("/api/handovers/{hid}/analyze")
def analyze(hid: str) -> dict:
    aid = handover.start_analysis(hid)
    ctx = contextvars.copy_context()  # keep this workspace's graph in the worker thread
    threading.Thread(target=ctx.run, args=(_run_analysis, hid, aid), daemon=True).start()
    return {"analysisId": aid, "handoverId": hid}


def _run_analysis(hid: str, aid: str) -> None:
    try:
        handover.analyze(hid, aid, delay=ANALYSIS_DELAY)
    except Exception:
        log.exception("analysis failed")


def _sse(stream: str, request: Request, follow: bool = True) -> EventSourceResponse:
    last = request.headers.get("last-event-id")

    async def gen():
        async for ev in bus.subscribe(stream, last, follow=follow):
            if await request.is_disconnected():
                break
            yield {"id": ev["eventId"], "data": json.dumps(ev)}
    return EventSourceResponse(gen(), ping=15)


@app.get("/api/analyses/{aid}/events")
def analysis_events(aid: str, request: Request):
    return _sse(aid, request)


@app.get("/api/handovers/{hid}/events")
def handover_events(hid: str, request: Request):
    return _sse(handover.stream(hid), request)


@app.get("/api/handovers/{hid}/customer-impact")
def customer_impact(hid: str) -> list[dict]:
    """Accounts whose risk rose because they depend on the leaver (the Handover -> Detective hand-off)."""
    return handover.customer_impact_view(hid)


@app.get("/api/handovers/{hid}/graph")
def handover_graph(hid: str) -> dict:
    return graphviews.handover_graph(hid)


class Assign(BaseModel):
    successorId: str
    managerApproval: bool = True


@app.post("/api/handovers/{hid}/risks/{rid}/assign")
def assign(hid: str, rid: str, body: Assign, x_relay_persona: str | None = Header(None)) -> dict:
    if not body.managerApproval:
        raise HTTPException(400, "Assignment needs the manager's approval")
    return handover.assign(hid, rid, body.successorId, _persona(x_relay_persona))


class Dismiss(BaseModel):
    reason: str = ""


@app.post("/api/handovers/{hid}/risks/{rid}/dismiss")
def dismiss(hid: str, rid: str, body: Dismiss, x_relay_persona: str | None = Header(None)) -> dict:
    return handover.dismiss(hid, rid, body.reason, _persona(x_relay_persona))


@app.post("/api/handovers/{hid}/risks/{rid}/restore")
def restore(hid: str, rid: str, x_relay_persona: str | None = Header(None)) -> dict:
    return handover.restore(hid, rid, _persona(x_relay_persona))


@app.post("/api/handovers/{hid}/risks/{rid}/verify")
def verify(hid: str, rid: str, x_relay_persona: str | None = Header(None)) -> dict:
    return handover.verify(hid, rid, _persona(x_relay_persona))


@app.post("/api/handovers/{hid}/risks/{rid}/skip")
def skip(hid: str, rid: str, x_relay_persona: str | None = Header(None)) -> dict:
    return handover.skip(hid, rid, _persona(x_relay_persona))


@app.post("/api/handovers/{hid}/accept-suggestions")
def accept_all(hid: str, x_relay_persona: str | None = Header(None)) -> dict:
    """Accept the top suggested successor for every unassigned item."""
    actor = _persona(x_relay_persona)
    n = 0
    for r in handover.risks(hid):
        if not r["successor"] and r["suggestions"] and r["state"] not in ("dismissed",):
            handover.assign(hid, r["id"], r["suggestions"][0]["id"], actor)
            n += 1
    return {"assigned": n}


@app.post("/api/handovers/{hid}/verify-captured")
def verify_all(hid: str, x_relay_persona: str | None = Header(None)) -> dict:
    """Verify every captured answer that has a next owner."""
    actor = _persona(x_relay_persona)
    n = 0
    for r in handover.risks(hid):
        if r["state"] == "captured" and r["successor"]:
            handover.verify(hid, r["id"], actor)
            n += 1
    return {"verified": n}


@app.get("/api/handovers/{hid}/interview")
def get_interview(hid: str) -> dict:
    return interview.interview(hid)


class Answer(BaseModel):
    riskItemId: str
    answerText: str


@app.post("/api/handovers/{hid}/answers")
def save_answer(hid: str, body: Answer, x_relay_persona: str | None = Header(None)) -> dict:
    return handover.capture(hid, body.riskItemId, body.answerText, _persona(x_relay_persona))


@app.post("/api/handovers/{hid}/close")
def close(hid: str, x_relay_persona: str | None = Header(None)) -> dict:
    return handover.close(hid, _persona(x_relay_persona))


@app.get("/api/handovers/{hid}/actions")
def handover_actions(hid: str) -> list[dict]:
    return actions.handover_actions(hid)


@app.get("/api/handovers/{hid}/doc-proposals")
def doc_proposals(hid: str) -> list[dict]:
    return proposals.list_for(hid)


@app.post("/api/doc-proposals/{pid}/approve")
def approve_doc(pid: str, x_relay_persona: str | None = Header(None)) -> dict:
    return proposals.approve(pid, _persona(x_relay_persona))


# ------------------------------------------------------------------ sources

@app.get("/api/sources/{label}/{sid:path}")
def source(label: str, sid: str) -> dict:
    s = analysis.get_source(label, sid)
    if not s:
        raise HTTPException(404, "Source not found")
    return s


# ------------------------------------------------------------------ day one

@app.get("/api/day-one/{pid}")
def day_one(pid: str, request: Request, x_relay_persona: str | None = Header(None)) -> dict:
    if x_relay_persona == pid:
        workspaces.mark(_uid(request), "dayone")
    return onboarding.day_one(pid)


@app.post("/api/checklist/{cid}/toggle")
def toggle(cid: str, x_relay_persona: str | None = Header(None)) -> dict:
    return onboarding.toggle_check(cid, _persona(x_relay_persona))


# ---------------------------------------------------------------------- ask

class Question(BaseModel):
    question: str


@app.post("/api/ask")
def ask_question(body: Question, request: Request, x_relay_persona: str | None = Header(None)) -> dict:
    workspaces.mark(_uid(request), "ask")
    return ask.ask(body.question, _persona(x_relay_persona))


# ------------------------------------------------------------------ actions

class Intro(BaseModel):
    personId: str


@app.post("/api/actions/intro")
def propose_intro(body: Intro, x_relay_persona: str | None = Header(None)) -> dict:
    return actions.propose_intro(_persona(x_relay_persona), body.personId)


class Approve(BaseModel):
    approvedPayload: dict[str, Any] | None = None


@app.post("/api/actions/{aid}/approve")
def approve_action(aid: str, body: Approve, x_relay_persona: str | None = Header(None)) -> dict:
    return actions.approve(aid, _persona(x_relay_persona), body.approvedPayload)


@app.get("/api/actions/{aid}")
def get_action(aid: str) -> dict:
    return actions.get(aid)


# --------------------------------------------------------------------- demo

class Reset(BaseModel):
    confirm: bool = False


@app.post("/api/demo/reset")
def demo_reset(body: Reset, request: Request) -> dict:
    if not body.confirm:
        raise HTTPException(400, "Send {\"confirm\": true} to reset the demo")
    workspaces.require_admin(_uid(request), _wid(request))
    from .health import investigator
    from .ingest.pipeline import reset
    from .sales import live
    reset(db.current_graph_name())
    investigator.reset(db.current_graph_name())
    live.reset(db.current_graph_name())
    bus.reset()
    return {"ok": True, "message": "Relay reset the graph, handovers, answers, actions and checklists to the demo start."}


class FastForward(BaseModel):
    handoverId: str


@app.post("/api/demo/fast-forward")
def fast_forward(body: FastForward) -> dict:
    n = interview.fast_forward(body.handoverId)
    return {"answered": n}


app.include_router(relay_router)
app.include_router(repos_router)
app.include_router(connectors_router)
app.include_router(graph_router)
