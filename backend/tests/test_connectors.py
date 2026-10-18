"""Connections: catalog shape, live verification (httpx mocked), encrypted storage, masking, Slack bot, MCP."""

import json
import socket
import threading
import time

import httpx
import pytest

from relay import connectors

REQUIRED = {"hubspot", "zendesk", "intercom", "freshdesk", "slack", "jira", "linear", "confluence", "notion", "github",
            "fireflies", "gong", "google"}


def _resp(status: int, body=None, headers: dict | None = None, url: str = "https://example.test/") -> httpx.Response:
    kw = {"json": body} if body is not None else {"text": ""}
    return httpx.Response(status, request=httpx.Request("GET", url), headers=headers, **kw)


class FakeHttp:
    """Stands in for httpx.request: returns queued responses (or raises) and records the calls."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls: list[tuple[str, str, dict]] = []

    def __call__(self, method, url, **kw):
        self.calls.append((method, url, kw))
        r = self.results.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture()
def fake(monkeypatch):
    def install(*results):
        f = FakeHttp(*results)
        monkeypatch.setattr(connectors.httpx, "request", f)
        return f
    return install


# ------------------------------------------------------------------ catalog

def test_catalog_shape():
    ids = {p.id for p in connectors.CATALOG}
    assert REQUIRED <= ids
    for p in connectors.CATALOG:
        assert p.category in connectors.CATEGORIES
        assert p.auth in ("api_key", "oauth")
        assert p.color.startswith("#") and len(p.color) == 7
        assert p.docs.startswith("https://") and p.uses and p.fields
        assert any(f.secret for f in p.fields), f"{p.id} has no secret field"
    assert connectors.BY_ID["google"].auth == "oauth"


def test_mask():
    assert connectors.mask("ghp_abcdefgh1234") == "••••1234"
    assert connectors.mask("short") == "••••"
    assert connectors.mask(None) == "••••"


def test_catalog_api(client):
    data = client.get("/api/connectors").json()
    assert data["canManage"] is True and data["mcp"] == [] and data["mcpUses"]
    assert [c["name"] for c in data["categories"]] == connectors.CATEGORIES
    providers = {p["id"]: p for c in data["categories"] for p in c["providers"]}
    assert REQUIRED <= set(providers)
    assert not any(p["connected"] for p in providers.values())
    # Sample data comes from the workspace's demo-mode Connection rows.
    assert {s["id"] for s in data["sample"]} >= {"slack", "jira", "confluence", "github"}
    assert providers["slack"]["sample"] and providers["linear"]["sample"] is None
    assert providers["google"]["redirectUri"].endswith("/api/auth/google/callback")


# ------------------------------------------------------------------ verify failure paths

def test_verify_rejected_token_shows_provider_message(fake):
    f = fake(_resp(401, {"status": "error", "message": "Authentication credentials not found."}))
    r = connectors.verify_hubspot({"token": "pat-na1-bad"})
    assert not r["ok"] and "HTTP 401" in r["detail"] and "Authentication credentials not found" in r["detail"]
    method, url, kw = f.calls[0]
    assert url == "https://api.hubapi.com/crm/v3/objects/companies?limit=1"
    assert kw["headers"]["Authorization"] == "Bearer pat-na1-bad" and kw["timeout"] == 10.0


def test_verify_unreachable_and_timeout(fake):
    fake(httpx.ConnectError("boom"))
    assert "Couldn't reach GitHub" in connectors.verify_github({"token": "x"})["detail"]
    fake(httpx.ReadTimeout("slow"))
    assert "did not answer within 10 seconds" in connectors.verify_notion({"token": "x"})["detail"]


def test_verify_slack(fake):
    f = fake()
    r = connectors.verify_slack({"token": "xoxp-user-token", "channel": "#cs"})
    assert not r["ok"] and "xoxb-" in r["detail"] and not f.calls   # rejected before any call
    fake(_resp(200, {"ok": False, "error": "invalid_auth"}))
    assert "invalid_auth" in connectors.verify_slack({"token": "xoxb-1", "channel": "#cs"})["detail"]
    f = fake(_resp(200, {"ok": True, "user": "relay", "team": "Acme"}))
    r = connectors.verify_slack({"token": "xoxb-1", "channel": "cs"})
    assert r["ok"] and r["account"] == "relay in Acme" and f.calls[0][:2] == ("POST", "https://slack.com/api/auth.test")


def test_verify_anonymous_answers_are_failures(fake):
    fake(_resp(200, {"user": {"id": None, "name": "Anonymous user"}}))
    assert not connectors.verify_zendesk({"subdomain": "acme", "email": "a@b.co", "token": "t"})["ok"]
    fake(_resp(200, {"type": "anonymous"}))
    assert not connectors.verify_confluence({"site": "https://acme.atlassian.net", "email": "a@b.co", "token": "t"})["ok"]


def test_verify_graphql_errors(fake):
    fake(_resp(400, {"errors": [{"message": "Authentication required, not authenticated"}]}))
    r = connectors.verify_linear({"api_key": "lin_api_bad"})
    assert not r["ok"] and "Authentication required" in r["detail"]
    fake(_resp(200, {"data": {"user": None}, "errors": [{"message": "Invalid API key"}]}))
    assert "Invalid API key" in connectors.verify_fireflies({"api_key": "bad"})["detail"]


def test_verify_google_client(fake):
    bad = {"client_id": "123.apps.googleusercontent.com", "client_secret": "GOCSPX-x"}
    fake(_resp(401, {"error": "invalid_client", "error_description": "Unauthorized"}))
    assert "does not recognise" in connectors.verify_google_client(bad)["detail"]
    fake(_resp(400, {"error": "invalid_grant", "error_description": "Malformed auth code."}))
    assert connectors.verify_google_client(bad)["ok"]
    assert not connectors.verify_google_client({"client_id": "nope", "client_secret": "x"})["ok"]


def test_bad_addresses_are_refused_before_any_call(fake):
    f = fake()
    from relay.auth import AuthError
    with pytest.raises(AuthError):
        connectors.verify_zendesk({"subdomain": "acme.evil.com/x", "email": "a@b.co", "token": "t"})
    with pytest.raises(AuthError):
        connectors.verify_confluence({"site": "http://acme.atlassian.net", "email": "a@b.co", "token": "t"})
    with pytest.raises(AuthError):
        connectors.verify_gong({"access_key": "a", "secret": "b", "base_url": "https://attacker.example"})
    assert not f.calls


# ------------------------------------------------------------------ storage

def test_connect_stores_encrypted_and_never_returns_secret(client, fake):
    from relay import db, workspaces
    from relay.auth import _g

    token = "github_pat_SECRETVALUE7890"
    fake(_resp(401, {"message": "Bad credentials"}))
    r = client.post("/api/connectors/github", json={"fields": {"token": token}})
    assert r.status_code == 400 and "Bad credentials" in r.json()["error"]

    fake(_resp(200, {"login": "octocat"}, headers={"x-oauth-scopes": "repo"}))
    r = client.post("/api/connectors/github", json={"fields": {"token": token}})
    assert r.status_code == 200, r.text
    view = r.json()
    assert view["connected"] and view["account"] == "octocat" and view["verifiedAt"]
    assert view["values"] == {"token": "••••7890"}

    listing = client.get("/api/connectors")
    assert token not in listing.text and "SECRETVALUE" not in r.text
    wid = client.get("/api/me").json()["workspace"]["id"]
    row = db.rows("MATCH (c:Connection {provider: 'github_live'})-[:IN]->(:Workspace {id: $w}) RETURN c",
                  {"w": wid}, g=_g())[0]["c"]
    assert token not in json.dumps(row)                                # encrypted at rest
    assert workspaces.secret(wid, "github_live") == {"token": token}   # and readable by the server
    # The sample-data row for GitHub is untouched.
    assert db.rows("MATCH (c:Connection {provider: 'github', mode: 'demo'})-[:IN]->(:Workspace {id: $w}) RETURN c",
                   {"w": wid}, g=_g())

    assert client.delete("/api/connectors/github").status_code == 200
    gh = next(p for c in client.get("/api/connectors").json()["categories"] for p in c["providers"] if p["id"] == "github")
    assert not gh["connected"] and workspaces.secret(wid, "github_live") == {}


def test_only_admins_connect(client):
    from relay.auth import AuthError
    wid = client.get("/api/me").json()["workspace"]["id"]
    with pytest.raises(AuthError) as e:
        connectors.connect("u-not-a-member", wid, "github", {"token": "x"})
    assert e.value.status == 403


def test_slack_bot_posts_with_fallback(client, fake, monkeypatch):
    from relay import db
    from relay.health import plan

    fake(_resp(200, {"ok": True, "user": "relay", "team": "Acme"}))
    r = client.post("/api/connectors/slack", json={"fields": {"token": "xoxb-123-abc-SECRET", "channel": "relay-test"}})
    assert r.status_code == 200 and r.json()["values"] == {"token": "••••CRET", "channel": "#relay-test"}
    me = client.get("/api/me").json()["workspace"]
    from relay import workspaces
    graph = workspaces._workspace(me["id"])["graph"]
    tokens = db.use_workspace(me["id"], graph)
    try:
        assert plan.integration_status()["slack"] == {"mode": "live", "label": "Slack #relay-test"}
        posts = []

        def fake_post(url, headers=None, json=None, timeout=None):
            posts.append((url, json["channel"]))
            body = {"ok": False, "error": "not_in_channel"} if json["channel"] == "#cs" else {"ok": True, "channel": "C1", "ts": "1.2"}
            return _resp(200, body)

        monkeypatch.setattr(plan.httpx, "post", fake_post)
        out = plan.execute({"type": "slack.post", "destination": {"mode": "live"}, "payload": {"channel": "#cs", "message": "hi"}})
        assert out.status == "succeeded" and "#relay-test" in out.message and "not_in_channel" in out.message
        assert posts == [("https://slack.com/api/chat.postMessage", "#cs"),
                         ("https://slack.com/api/chat.postMessage", "#relay-test")]
    finally:
        db._current_workspace.reset(tokens[0])
        db._current_graph.reset(tokens[1])


# ------------------------------------------------------------------ MCP

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def mcp_url():
    import uvicorn
    from mcp.server.mcpserver import MCPServer

    srv = MCPServer(name="test-tools")

    @srv.tool(description="Add two numbers.")
    def add(a: int, b: int) -> int:
        return a + b

    @srv.tool(description="Say hello.")
    def hello(name: str) -> str:
        return f"hello {name}"

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(srv.streamable_http_app(), host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/mcp"
    server.should_exit = True
    t.join(timeout=5)


def test_mcp_server_add_list_remove(client, mcp_url):
    r = client.post("/api/connectors/mcp", json={"name": "Test tools", "url": mcp_url, "token": "secret-bearer-123456"})
    assert r.status_code == 200, r.text
    m = r.json()
    assert {t["name"] for t in m["tools"]} == {"add", "hello"} and m["transport"] == "streamable-http"
    assert m["token"] == "••••3456"
    listing = client.get("/api/connectors")
    assert "secret-bearer-123456" not in listing.text and len(listing.json()["mcp"]) == 1
    assert client.delete(f"/api/connectors/mcp/{m['id']}").status_code == 200
    assert client.get("/api/connectors").json()["mcp"] == []


def test_mcp_unreachable_is_an_error(client):
    r = client.post("/api/connectors/mcp", json={"name": "Nothing", "url": f"http://127.0.0.1:{_free_port()}/mcp"})
    assert r.status_code == 400 and "Couldn't connect" in r.json()["error"]
    assert client.post("/api/connectors/mcp", json={"name": "Bad", "url": "ftp://x"}).status_code == 400
