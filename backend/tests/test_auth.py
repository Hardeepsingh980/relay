"""Accounts, sessions and API protection."""

import uuid

from fastapi.testclient import TestClient

from relay.api import app


def _email() -> str:
    return f"a-{uuid.uuid4().hex[:8]}@example.com"


def test_api_requires_sign_in(fresh):
    c = TestClient(app)
    assert c.get("/api/health").status_code == 200
    assert c.get("/api/auth/providers").json()["password"] is True
    assert c.get("/api/home/knowledge-risk").status_code == 401
    assert c.get("/api/auth/me").status_code == 401


def test_sign_up_sign_out_sign_in(fresh):
    c = TestClient(app)
    email = _email()
    r = c.post("/api/auth/sign-up", json={"name": "Ada Lovelace", "email": email.upper(), "password": "analytical-engine"})
    assert r.status_code == 201
    assert r.json()["user"]["email"] == email          # normalised
    assert "httponly" in r.headers["set-cookie"].lower()
    assert c.get("/api/auth/me").json()["user"]["name"] == "Ada Lovelace"
    r = c.get("/api/home/knowledge-risk")
    assert r.status_code == 403 and r.json()["code"] == "no_workspace"   # signed in, no workspace yet
    assert c.post("/api/workspaces", json={"name": "Analytical Engines"}).status_code == 200
    assert c.get("/api/home/knowledge-risk").status_code == 200

    assert c.post("/api/auth/sign-out").json()["ok"]
    assert c.get("/api/home/knowledge-risk").status_code == 401

    assert c.post("/api/auth/sign-in", json={"email": email, "password": "wrong-password"}).status_code == 401
    r = c.post("/api/auth/sign-in", json={"email": email, "password": "analytical-engine"})
    assert r.status_code == 200
    assert c.get("/api/home/knowledge-risk").status_code == 200


def test_validation_and_duplicates(fresh):
    c = TestClient(app)
    assert c.post("/api/auth/sign-up", json={"name": "A", "email": _email(), "password": "longenough"}).status_code == 400
    assert c.post("/api/auth/sign-up", json={"name": "Ann", "email": "not-an-email", "password": "longenough"}).status_code == 400
    assert c.post("/api/auth/sign-up", json={"name": "Ann", "email": _email(), "password": "short"}).status_code == 400
    email = _email()
    assert c.post("/api/auth/sign-up", json={"name": "Ann", "email": email, "password": "longenough"}).status_code == 201
    assert c.post("/api/auth/sign-up", json={"name": "Ann", "email": email, "password": "longenough"}).status_code == 409


def test_rate_limit(fresh):
    c = TestClient(app)
    email = _email()
    c.post("/api/auth/sign-up", json={"name": "Rate Limited", "email": email, "password": "longenough"})
    codes = [c.post("/api/auth/sign-in", json={"email": email, "password": "nope-nope"}).status_code for _ in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429


def test_demo_reset_keeps_accounts(fresh):
    c = TestClient(app)
    c.post("/api/auth/sign-up", json={"name": "Keeps Session", "email": _email(), "password": "longenough"})
    c.post("/api/workspaces", json={"name": "Reset Co"})
    assert c.post("/api/demo/reset", json={"confirm": True}).json()["ok"]
    assert c.get("/api/auth/me").status_code == 200
