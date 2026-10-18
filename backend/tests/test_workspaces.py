"""Workspaces, teammates, isolation, connections and the full-circle journey."""

import re

from conftest import new_client

PRIYA = {"X-Relay-Persona": "p-priya"}


def test_invite_and_join(fresh):
    owner = new_client("Owner One", "Northwind")
    out = owner.post("/api/workspace/invites", json={"emails": ["new.hire@example.com"], "role": "member"}).json()["invites"]
    token = re.search(r"/join/(.+)$", out[0]["link"]).group(1)

    from fastapi.testclient import TestClient
    from relay.api import app
    guest = TestClient(app)
    info = guest.get(f"/api/invites/{token}").json()
    assert info["workspace"] == "Northwind" and info["valid"]
    # The invite is bound to its email address.
    assert guest.post("/api/auth/sign-up", json={"name": "Wrong", "email": "other@example.com", "password": "longenough",
                                                 "invite": token}).status_code == 403
    r = guest.post("/api/auth/sign-up", json={"name": "New Hire", "email": "new.hire@example.com", "password": "longenough",
                                              "invite": token})
    assert r.status_code == 201 and r.json()["joined"]["name"] == "Northwind"
    assert guest.get("/api/me").json()["workspace"]["role"] == "member"
    team = owner.get("/api/workspace/members").json()
    assert {m["name"] for m in team["members"]} == {"Owner One", "New Hire"} and team["invites"] == []
    # Members can't invite or reset; the invite can't be reused.
    assert guest.post("/api/workspace/invites", json={"emails": ["x@example.com"]}).status_code == 403
    assert guest.post("/api/demo/reset", json={"confirm": True}).status_code == 403
    assert guest.get(f"/api/invites/{token}").json()["valid"] is False


def test_workspaces_are_isolated(fresh):
    a, b = new_client("Ann A", "Team A"), new_client("Ben B", "Team B")
    r = a.post("/api/handovers", json={"leaverId": "p-rahul", "lastDay": "2026-10-23", "joinerId": "p-aisha"}, headers=PRIYA)
    assert r.status_code == 200
    assert len(a.get("/api/handovers").json()) == 1
    assert b.get("/api/handovers").json() == []
    assert b.get("/api/home/knowledge-risk").json()["singlePointsOfFailure"] == 23


def test_connections_and_journey(fresh):
    c = new_client("Journey", "Circle Co")
    j = c.get("/api/journey").json()
    assert j["steps"][0]["done"] and j["next"] == "connections"
    conns = {x["id"]: x for x in c.get("/api/workspace/connections").json()}
    assert conns["slack"]["status"] == "connected" and conns["slack"]["mode"] == "demo"
    assert conns["jira_live"]["status"] == "disconnected"
    bad = c.post("/api/workspace/connections/jira", json={"baseUrl": "not a url", "email": "a@b.co", "token": "x", "project": "LUM"})
    assert bad.status_code == 400
    assert c.post("/api/workspace/connections/slack", json={}).status_code in (404, 405)
    j = c.get("/api/journey").json()
    assert next(s for s in j["steps"] if s["id"] == "connections")["done"]
    c.post("/api/workspace/invites", json={"emails": ["mate@example.com"]})
    c.get("/api/home/knowledge-risk")
    hid = c.post("/api/handovers", json={"leaverId": "p-rahul", "lastDay": "2026-10-23", "joinerId": "p-aisha"},
                 headers=PRIYA).json()["handover"]["id"]
    done = {s["id"] for s in c.get("/api/journey").json()["steps"] if s["done"]}
    assert {"workspace", "connections", "teammates", "risk", "handover"} <= done
    assert hid
