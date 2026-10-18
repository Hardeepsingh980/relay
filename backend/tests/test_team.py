"""One-click team sign-in: each browser gets its own copy of the Cheerio workspace."""

from fastapi.testclient import TestClient


def test_team_sign_in_reuses_one_private_workspace():
    from relay import api, auth, db, team

    c = TestClient(api.app)
    members = c.get("/api/auth/team").json()["members"]
    assert [m["id"] for m in members] == ["p-arnav", "p-sneha", "p-priya", "p-rahul", "p-aisha"]
    assert all(m["name"] and m["home"].startswith("/") and m["task"] for m in members)

    first = c.post("/api/auth/team", json={"personId": "p-arnav"})
    assert first.status_code == 200 and first.json()["user"]["sandbox"] is True
    sandbox = c.cookies.get(team.SANDBOX_COOKIE)
    ws1 = c.get("/api/session", headers={"X-Relay-Persona": "p-arnav"}).json()["workspace"]["id"]

    c.post("/api/auth/sign-out")
    c.post("/api/auth/team", json={"personId": "p-priya"})
    assert c.cookies.get(team.SANDBOX_COOKIE) == sandbox
    ws2 = c.get("/api/session", headers={"X-Relay-Persona": "p-priya"}).json()["workspace"]["id"]
    assert ws1 == ws2

    other = TestClient(api.app)
    other.post("/api/auth/team", json={"personId": "p-arnav"})
    ws3 = other.get("/api/session").json()["workspace"]["id"]
    assert ws3 != ws1
    assert c.post("/api/auth/team", json={"personId": "p-nobody"}).status_code == 404

    for wid in (ws1, ws3):
        w = db.rows("MATCH (u:User)-[:MEMBER_OF]->(w:Workspace {id: $w}) RETURN u.id AS u, w", {"w": wid}, g=auth._g())[0]
        team._delete(w["u"], w["w"])
    assert not db.rows("MATCH (w:Workspace {id: $w}) RETURN w", {"w": ws1}, g=auth._g())


def test_public_landing_graph_is_real_and_needs_no_sign_in():
    from relay import api

    d = TestClient(api.app).get("/api/public/graph").json()
    ids = {n["id"] for n in d["nodes"]}
    assert len(ids) > 150 and len(d["edges"]) > 400
    assert all(e["s"] in ids and e["t"] in ids for e in d["edges"])
    assert [s["agent"] for s in d["stories"]] == ["Account Health", "Handovers", "Sales Assist"]
    assert all(set(s["path"]) <= ids and len(s["path"]) >= 4 for s in d["stories"])
    names = {n["id"]: n["name"] for n in d["nodes"]}
    assert names[d["stories"][0]["path"][0]] == "Northwind Foods" and "78%" in d["stories"][0]["text"]
    assert "12 things" in d["stories"][1]["text"] and "Q1 2027" in d["stories"][2]["text"]
