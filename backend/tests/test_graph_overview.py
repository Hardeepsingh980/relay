"""Knowledge graph explorer: /api/graph/overview and /api/graph/node on the Cheerio test graph."""

from urllib.parse import quote

import test_cheerio
from test_cheerio import GRAPH, NORTHWIND

# Reuse the Cheerio test graph fixtures: the session build and a clean copy per test.
cheerio_built = test_cheerio.cheerio_built
cheerio = test_cheerio.cheerio

KNOWLEDGE_TYPES = {"Person", "Team", "System", "Account", "Contact", "Feature", "Bug", "RoadmapItem", "Promise",
                   "Playbook", "Decision", "Workaround", "Doc", "Meeting", "Channel", "Risk"}
ACTIVITY_TYPES = {"Message", "Commit", "PullRequest", "Conversation", "Signal"}


def _check(data: dict) -> None:
    nodes, edges, stats, types = data["nodes"], data["edges"], data["stats"], data["types"]
    ids = [n["id"] for n in nodes]
    assert len(ids) == len(set(ids)), "node ids are unique"
    assert all(":" in i for i in ids), "ids are namespaced by label"
    assert stats["shownNodes"] == len(nodes) and stats["shownEdges"] == len(edges)
    assert stats["totalNodes"] >= len(nodes) and stats["totalRelationships"] >= len(edges)
    assert stats["ms"] >= 0
    known = set(ids)
    assert all(e["s"] in known and e["t"] in known for e in edges), "every edge endpoint is a returned node"
    assert all(e["type"] for e in edges)
    by_type: dict[str, int] = {}
    for n in nodes:
        by_type[n["type"]] = by_type.get(n["type"], 0) + 1
        assert n["name"] and n["degree"] >= 0
    assert {t["type"]: t["count"] for t in types} == by_type, "the legend counts match the nodes"
    assert all(t["color"].startswith("#") and t["label"] for t in types)
    assert not any(n["type"] in ("UsageWeek", "Invoice") for n in nodes)


def test_knowledge_layer(cheerio):
    from relay.api_graph import overview_data
    data = overview_data("knowledge")
    _check(data)
    types = {t["type"] for t in data["types"]}
    assert KNOWLEDGE_TYPES <= types
    assert not types & ACTIVITY_TYPES
    # Only support tickets that are symptoms of a known bug.
    tickets = {n["id"] for n in data["nodes"] if n["type"] == "Ticket"}
    assert tickets
    symptom = {e["s"] for e in data["edges"] if e["type"] == "SYMPTOM_OF"}
    assert tickets <= symptom
    acc = next(n for n in data["nodes"] if n["id"] == f"Account:{NORTHWIND}")
    assert acc["extra"]["usageWeeks"] > 0 and acc["extra"]["invoices"] > 0


def test_full_layer_adds_activity(cheerio):
    from relay.api_graph import MESSAGE_CAP, overview_data
    k, f = overview_data("knowledge"), overview_data("full")
    _check(f)
    assert f["stats"]["shownNodes"] > k["stats"]["shownNodes"] and f["stats"]["shownEdges"] > k["stats"]["shownEdges"]
    assert ACTIVITY_TYPES <= {t["type"] for t in f["types"]}
    assert sum(1 for n in f["nodes"] if n["type"] == "Message") <= MESSAGE_CAP
    assert {n["id"] for n in k["nodes"]} <= {n["id"] for n in f["nodes"]}


def test_node_detail(cheerio):
    from relay.api_graph import node_data
    d = node_data(f"Account:{NORTHWIND}")
    assert d["type"] == "Account" and d["name"] == "Northwind Foods"
    assert d["aggregates"]["usageWeeks"] > 0
    assert d["neighbours"] and all(len(g["items"]) <= 60 and g["total"] >= len(g["items"]) for g in d["neighbours"])
    assert all(":" in it["id"] for g in d["neighbours"] for it in g["items"])
    assert all(len(v) <= 401 for v in d["props"].values() if isinstance(v, str))
    assert node_data("Account:no-such-account") is None and node_data("Nope:x") is None


def test_routes(cheerio, monkeypatch):
    """The routes answer through the API (gzip on request) inside the session's workspace graph."""
    from fastapi.testclient import TestClient

    from relay import api
    user = {"id": "u-graph-test", "name": "Graph Test", "email": "graph@example.com"}
    monkeypatch.setattr(api, "_context", lambda token: (user, {"id": "w-graph-test", "graph": GRAPH}))
    c = TestClient(api.app)
    r = c.get("/api/graph/overview", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200, r.text
    assert r.headers.get("content-encoding") == "gzip"
    body = r.json()
    assert body["graph"] == GRAPH and body["stats"]["shownNodes"] == len(body["nodes"]) > 0
    assert c.get("/api/graph/overview?layer=nope").status_code == 422
    pr = next(n["id"] for n in c.get("/api/graph/overview?layer=full").json()["nodes"] if n["type"] == "PullRequest")
    r = c.get("/api/graph/node/" + quote(pr, safe=""))
    assert r.status_code == 200 and r.json()["id"] == pr, r.text
    assert c.get(f"/api/graph/node/Account:{NORTHWIND}").json()["type"] == "Account"
    assert c.get("/api/graph/node/Person:nobody-here").status_code == 404
