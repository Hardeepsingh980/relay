"""External actions: reviewable proposals, explicit approval, honest results.

Every action shows destination and payload before it runs. Execution goes
through an adapter: a live one when its credentials are configured, otherwise
the simulated adapter, whose results are labelled "simulated" and never
"succeeded", so a demo can't pass a fake change off as a real one.

Live adapters (all optional, server-side credentials only):
  Google Calendar  GOOGLE_OAUTH_CLIENT_ID / _SECRET / _REFRESH_TOKEN, GOOGLE_CALENDAR_ID
  Gmail drafts     same Google OAuth credentials (gmail.compose scope)
  Jira             JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import datetime, timedelta
from email.message import EmailMessage

import httpx

from . import db, handover, tenants
from .config import IST, now

TYPES = {
    "calendar.intro": {"destination": "Google Calendar", "integration": "google_calendar"},
    "ticket.reassign": {"destination": "Jira", "integration": "jira"},
    "email.draft": {"destination": "Gmail (draft only)", "integration": "gmail"},
}


class ActionError(ValueError):
    pass


# ------------------------------------------------------------- integrations

def _creds(provider: str) -> dict:
    """Live credentials for the current workspace (connected in Settings), else server env vars."""
    from . import workspaces
    c = workspaces.secret(db.current_workspace_id(), provider)
    if c:
        return c
    if provider == "google" and os.getenv("GOOGLE_OAUTH_REFRESH_TOKEN"):
        return {"refresh_token": os.environ["GOOGLE_OAUTH_REFRESH_TOKEN"]}
    if provider == "jira_live" and all(os.getenv(k) for k in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY")):
        return {"base_url": os.environ["JIRA_BASE_URL"], "email": os.environ["JIRA_EMAIL"],
                "token": os.environ["JIRA_API_TOKEN"], "project": os.environ["JIRA_PROJECT_KEY"]}
    return {}


def _google_configured() -> bool:
    from . import google_oauth
    return google_oauth.configured() and bool(_creds("google").get("refresh_token"))


def _jira_configured() -> bool:
    return bool(_creds("jira_live"))


def integrations() -> list[dict]:
    google = _google_configured()
    jira = _jira_configured()
    return [
        {"id": "synthetic", "name": f"{tenants.current().name} sample data", "state": "Connected", "mode": "synthetic",
         "detail": "Slack, Confluence, Jira, meetings and GitHub exports (synthetic sample data)"},
        {"id": "google_calendar", "name": "Google Calendar", "state": "Connected" if google else "Simulated",
         "mode": "live" if google else "simulated"},
        {"id": "gmail", "name": "Gmail drafts", "state": "Connected" if google else "Simulated",
         "mode": "live" if google else "simulated"},
        {"id": "jira", "name": "Jira", "state": "Connected" if jira else "Simulated", "mode": "live" if jira else "simulated"},
    ]


def _mode(type_: str) -> str:
    integ = TYPES[type_]["integration"]
    return next(i["mode"] for i in integrations() if i["id"] == integ)


def _google_token() -> str:
    from . import google_oauth
    return google_oauth.refresh(_creds("google")["refresh_token"])


def _live_calendar(p: dict) -> dict:
    cal = os.getenv("GOOGLE_CALENDAR_ID", "primary")
    start = datetime.fromisoformat(p["start"])
    body = {"summary": p["title"], "description": p["description"],
            "start": {"dateTime": start.isoformat()},
            "end": {"dateTime": (start + timedelta(minutes=p["durationMinutes"])).isoformat()}}
    # Demo attendees are fictional; they're listed in the description, not invited.
    r = httpx.post(f"https://www.googleapis.com/calendar/v3/calendars/{cal}/events", params={"sendUpdates": "none"},
                   headers={"Authorization": f"Bearer {_google_token()}"}, json=body, timeout=20)
    r.raise_for_status()
    ev = r.json()
    return {"externalId": ev["id"], "url": ev.get("htmlLink"), "message": "Event created in Google Calendar"}


def _live_gmail(p: dict) -> dict:
    msg = EmailMessage()
    msg["To"] = ", ".join(p["to"])
    msg["Subject"] = p["subject"]
    msg.set_content(p["body"])
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    r = httpx.post("https://gmail.googleapis.com/gmail/v1/users/me/drafts",
                   headers={"Authorization": f"Bearer {_google_token()}"}, json={"message": {"raw": raw}}, timeout=20)
    r.raise_for_status()
    return {"externalId": r.json()["id"], "url": "https://mail.google.com/mail/#drafts",
            "message": "Draft saved in Gmail. Nothing was sent."}


def _live_jira(p: dict) -> dict:
    c = _creds("jira_live")
    base = c["base_url"].rstrip("/")
    auth = (c["email"], c["token"])
    body = {"fields": {"project": {"key": c["project"]}, "issuetype": {"name": "Task"},
                       "summary": f"[Handover] {p['ticketKey']}: {p['title']}",
                       "description": {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [
                           {"type": "text", "text": f"Reassigned from {p['fromName']} to {p['toName']} by Relay handover. {p['comment']}"}]}]}}}
    r = httpx.post(f"{base}/rest/api/3/issue", auth=auth, json=body, timeout=20)
    r.raise_for_status()
    key = r.json()["key"]
    return {"externalId": key, "url": f"{base}/browse/{key}",
            "message": f"Created {key} in Jira for the reassignment (the {tenants.current().name} ticket is sample data)."}


LIVE = {"calendar.intro": _live_calendar, "email.draft": _live_gmail, "ticket.reassign": _live_jira}


# ------------------------------------------------------------------ records

def _view(a: dict) -> dict:
    return {**{k: a.get(k) for k in ("id", "type", "title", "status", "mode", "destination", "handoverId", "createdAt",
                                       "approvedBy", "approvedAt", "finishedAt", "riskId", "key")},
            "payload": json.loads(a.get("payload") or "{}"), "result": json.loads(a["result"]) if a.get("result") else None}


def get(aid: str) -> dict:
    r = db.rows("MATCH (a:Action {id: $id}) RETURN a", {"id": aid}, readonly=True)
    if not r:
        raise ActionError("No such action")
    return _view(r[0]["a"])


def _upsert(key: str, type_: str, title: str, payload: dict, hid: str | None, risk_id: str | None = None) -> dict:
    """Idempotent on `key`: re-proposing the same action updates it while it is still pending."""
    aid = "act-" + hashlib.sha1(key.encode()).hexdigest()[:10]
    r = db.rows("MATCH (a:Action {id: $id}) RETURN a.status AS s", {"id": aid}, readonly=True)
    params = {"id": aid, "key": key, "type": type_, "title": title, "payload": json.dumps(payload), "hid": hid,
              "rid": risk_id, "dest": TYPES[type_]["destination"], "mode": _mode(type_),
              "now": now().isoformat(timespec="seconds")}
    if not r:
        db.run("""CREATE (:Action {id: $id, key: $key, type: $type, title: $title, payload: $payload, status: 'proposed',
                  mode: $mode, destination: $dest, handoverId: $hid, riskId: $rid, createdAt: $now})""", params)
    elif r[0]["s"] == "proposed":
        db.run("MATCH (a:Action {id: $id}) SET a.title = $title, a.payload = $payload, a.mode = $mode", params)
    return get(aid)


def propose_intro(joiner: str, other: str) -> dict:
    j, o = handover.person(joiner), handover.person(other)
    if not j or not o:
        raise ActionError("Unknown person")
    start = (now() + timedelta(days=1)).replace(hour=11, minute=0, second=0, microsecond=0)
    while start.weekday() >= 5:
        start += timedelta(days=1)
    payload = {"attendees": [j["email"], o["email"]], "attendeeNames": [j["name"], o["name"]],
               "title": f"Intro: {j['name'].split()[0]} <> {o['name'].split()[0]}", "start": start.isoformat(),
               "durationMinutes": 30,
               "description": f"30-minute intro booked from Relay Day One. {o['name']} ({o['role']}) is one of "
                              f"{j['name'].split()[0]}'s five recommended people. Attendees: {j['name']}, {o['name']}."}
    return _upsert(f"intro:{joiner}:{other}", "calendar.intro", payload["title"], payload, None)


def handover_actions(hid: str) -> list[dict]:
    """Propose ticket moves and the customer intro from the current assignments."""
    h = handover.get(hid)
    leaver = h["leaver"]
    succ_for: dict[str, dict] = {}
    for r in h["riskItems"]:
        if not r["successor"] or r["state"] == "dismissed":
            continue
        targets = [r["itemId"]] if r["type"] in ("System", "Account") else []
        targets += [s["id"] for s in db.rows("MATCH (:%s {id: $i})-[:ABOUT]->(s) RETURN s.id AS id" % r["type"],
                                             {"i": r["itemId"]}, readonly=True)]
        for t in targets:
            succ_for.setdefault(t, {**r["successor"], "riskId": r["id"], "direct": r["type"] in ("System", "Account")})
            if r["type"] in ("System", "Account"):
                succ_for[t] = {**r["successor"], "riskId": r["id"], "direct": True}
    tickets = db.rows("""MATCH (t:Ticket)-[:OWNED_BY]->(:Person {id: $l}) WHERE t.status IN ['To Do', 'In Progress', 'Backlog']
                         MATCH (t)-[:CONCERNS]->(x) RETURN t.id AS key, t.title AS title, t.status AS status,
                         collect(x.id) AS targets ORDER BY t.id""", {"l": leaver["id"]}, readonly=True)
    for t in tickets:
        to = next((succ_for[x] for x in t["targets"] if x in succ_for and succ_for[x]["direct"]), None) or \
             next((succ_for[x] for x in t["targets"] if x in succ_for), None)
        if not to:
            continue
        payload = {"ticketKey": t["key"], "title": t["title"], "status": t["status"], "fromId": leaver["id"],
                   "fromName": leaver["name"], "toId": to["id"], "toName": to["name"],
                   "comment": f"Reassigned as part of {leaver['name'].split()[0]}'s handover (last day {h['handover']['lastDay']})."}
        _upsert(f"reassign:{hid}:{t['key']}", "ticket.reassign", f"Reassign {t['key']} to {to['name']}", payload, hid, to["riskId"])
    for r in h["riskItems"]:
        if r["type"] != "Account" or not r["successor"] or r["state"] == "dismissed":
            continue
        contacts = db.rows("MATCH (c:Contact)-[:WORKS_AT]->(:Account {id: $c}) RETURN c.name AS name, c.email AS email",
                           {"c": r["itemId"]}, readonly=True)
        s = handover.person(r["successor"]["id"])
        last = datetime.fromisoformat(h["handover"]["lastDay"])
        names = " and ".join(c["name"].split()[0] for c in contacts)
        open_items = db.rows("""MATCH (t:Ticket)-[:CONCERNS]->(:Account {id: $c}) WHERE t.status IN ['To Do', 'In Progress', 'Backlog']
                                RETURN t.id AS key, t.title AS title ORDER BY t.id""", {"c": r["itemId"]}, readonly=True)
        open_text = ("\n\nOpen items on our side:\n" + "\n".join(f"- {t['key']}: {t['title']}" for t in open_items)) if open_items else ""
        s_first = s["name"].split()[0]
        shared = db.rows("""MATCH (ch:Channel) WHERE ch.name STARTS WITH 'ext-' AND toLower(ch.purpose) CONTAINS toLower($n)
                            RETURN ch.name AS name LIMIT 1""", {"n": r["title"]}, readonly=True)
        where = f"#{shared[0]['name']} threads" if shared else "our shared threads"
        body = (f"Hi {names},\n\nAfter {last:%-d %B}, {s['name']} ({s['role']}) takes over the {tenants.current().name} side "
                f"of our integration from me. From now on, please include {s_first} in {where} and in any "
                f"integration or webhook issues.{open_text}\n\nThanks for everything,\n{leaver['name'].split()[0]}")
        payload = {"to": [c["email"] for c in contacts], "cc": [s["email"]], "subject": f"Your new {tenants.current().name} contact: {s['name']}",
                   "body": body, "customer": r["title"]}
        _upsert(f"intro-email:{hid}:{r['itemId']}", "email.draft", f"Draft intro to {r['title']}: {s['name']}", payload, hid, r["id"])
    rows = db.rows("MATCH (a:Action {handoverId: $h}) RETURN a ORDER BY a.createdAt, a.id", {"h": hid}, readonly=True)
    return [_view(x["a"]) for x in rows]


def approve(aid: str, actor: str, payload: dict | None = None) -> dict:
    a = get(aid)
    if a["status"] not in ("proposed", "failed"):
        raise ActionError(f"Action is already {a['status']}")
    p = handover.person(actor)
    if a["type"] == "calendar.intro":
        attendees = [r["id"] for r in db.rows("MATCH (x:Person) WHERE x.email IN $e RETURN x.id AS id",
                                               {"e": a["payload"]["attendees"]}, readonly=True)]
        if actor not in attendees:
            raise ActionError("Only an attendee can book this intro")
    elif a["handoverId"]:
        h = handover.get(a["handoverId"])
        if actor != h["manager"]["id"]:
            raise ActionError("Only the handover's manager can approve this action")
    final = {**a["payload"], **(payload or {})}
    stamp = now().isoformat(timespec="seconds")
    db.run("""MATCH (a:Action {id: $id}) SET a.status = 'running', a.approvedBy = $by, a.approvedAt = $at,
              a.payload = $payload""", {"id": aid, "by": p["name"], "at": stamp, "payload": json.dumps(final)})
    mode = _mode(a["type"])
    try:
        if mode == "live":
            result, status = LIVE[a["type"]](final), "succeeded"
        else:
            result, status = _simulate(a["type"], final), "simulated"
    except Exception as e:  # report the real failure
        result, status = {"message": f"{TYPES[a['type']]['destination']} returned an error: {e}"}, "failed"
    db.run("""MATCH (a:Action {id: $id}) SET a.status = $s, a.result = $r, a.mode = $m, a.finishedAt = $at""",
           {"id": aid, "s": status, "r": json.dumps(result), "m": mode, "at": now().isoformat(timespec="seconds")})
    if status in ("succeeded", "simulated") and a["type"] == "ticket.reassign":
        # Mirror the move in Relay's graph so ownership stays truthful.
        db.run("""MATCH (t:Ticket {id: $k})-[o:OWNED_BY]->() DELETE o""", {"k": final["ticketKey"]})
        db.run("""MATCH (t:Ticket {id: $k}), (p:Person {id: $to}) CREATE (t)-[:OWNED_BY {via: 'handover'}]->(p)""",
               {"k": final["ticketKey"], "to": final["toId"]})
    return get(aid)


def _simulate(type_: str, p: dict) -> dict:
    when = datetime.fromisoformat(p["start"]).astimezone(IST) if "start" in p else None
    msg = {
        "calendar.intro": (f"Saved in Relay: a 30-minute intro on {when:%a %-d %b, %H:%M} IST. Connect Google Calendar "
                           "to send the invite" if when else "Saved in Relay. Connect Google Calendar to send the invite"),
        "ticket.reassign": (f"Saved in Relay: move {p.get('ticketKey')} from {p.get('fromName')} to {p.get('toName')}. "
                            "Connect Jira to move it there too"),
        "email.draft": "Draft saved in Relay. Connect Gmail to save it as a Gmail draft",
    }[type_]
    return {"message": msg + "."}
