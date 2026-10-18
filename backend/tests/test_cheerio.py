"""Relay on the Cheerio tenant: Account Health, the Handover hand-off, Sales Assist, Ask and MCP.

Builds an isolated `cheerio_test` graph with the deterministic seed extractor. No LLM, and no
live integration credentials, so every approved action comes back simulated or as a local draft.
"""

import asyncio

import pytest

GRAPH = "cheerio_test"
NORTHWIND = "cust-northwind-foods"
KAIRO = "cust-kairo-living"


@pytest.fixture(scope="session")
def cheerio_built():
    from relay import db
    from relay.ingest.pipeline import build
    out = build(progress=lambda *_: None, extractor="seed", tenant="cheerio", target=GRAPH)
    yield out
    for name in db._client().list_graphs():
        if name.startswith(GRAPH):
            db.graph(name).delete()


@pytest.fixture()
def cheerio(cheerio_built, monkeypatch):
    """A clean copy of the Cheerio graph as the current graph, with no artificial delays."""
    from relay import db
    from relay.health import investigator
    from relay.ingest.pipeline import reset
    from relay.sales import live
    monkeypatch.setenv("RELAY_STEP_DELAY", "0")
    for var in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY", "SLACK_WEBHOOK_URL",
                "GOOGLE_OAUTH_REFRESH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    reset(GRAPH)
    token = db.use_graph(GRAPH)
    investigator.reset(GRAPH)
    live.reset(GRAPH)
    yield
    db.reset_graph(token)


def test_cheerio_readiness_checks(cheerio):
    from relay import evaluate
    failed = [(name, detail) for name, ok, detail in evaluate.checks() if not ok]
    assert not failed, failed


def test_northwind_is_a_silent_risk(cheerio):
    from relay.health import risk
    r = risk.account_risk(NORTHWIND)
    assert (r["risk"], r["crm"], r["silent"]) == (78, 82, True)
    keys = {f["key"] for f in r["factors"]}
    assert {"champion_departed", "unresolved_bug_tickets", "competitor_signal", "promise_at_risk"} <= keys
    assert "late_payment" not in keys and "internal_owner_leaving" not in keys


def test_investigation_verdict_and_save_plan(cheerio):
    from relay import db
    from relay.health import investigator

    async def run():
        inv = investigator.start(NORTHWIND, "guided", actor="test")
        await inv.task
        fu = await inv.follow_up("Who else is hit by this bug?")
        done = await inv.approve(list(inv.actions), "Test Approver")
        return inv, fu, done

    inv, fu, done = asyncio.run(run())
    v = inv.verdict
    assert inv.status == "completed" and v["bugId"] == "CHEER-2547" and v["risk"] == 78
    assert len(v["story"]) == 3 and all(s["evidenceIds"] for s in v["chain"])
    assert not v["evidenceProblems"]
    assert v["blastRadius"]["accounts"] == 4 and v["blastRadius"]["arr"] == 1_560_000
    assert v["promisesAtRisk"] and v["playbook"]["id"] == "pb-champion-bug"
    assert inv.causal["nodeIds"] and "CHEER-2547" in inv.causal["nodeIds"]
    assert fu["tool"] == "blast_radius" and "4 other accounts" in fu["answer"]
    # No live credentials: nothing may claim to have changed an external system.
    assert 2 <= len(done) <= 4 and {a["status"] for a in done} <= {"simulated", "drafted"}
    logged = db.rows("MATCH (x:Action {origin: 'account-health'}) RETURN x.approvedBy AS by, x.status AS s")
    assert len(logged) == len(done) and all(r["by"] == "Test Approver" for r in logged)
    assert db.rows("MATCH (e:Episode {kind: 'investigation'})-[:FOR_ACCOUNT]->(:Account {id: $a}) RETURN count(e) AS n",
                   {"a": NORTHWIND})[0]["n"] == 1


def test_handover_hands_accounts_to_the_detective(cheerio):
    from relay import handover
    from relay.health import risk
    h = handover.create("p-rahul", "2026-10-23", "p-aisha", "p-priya")
    aid = handover.start_analysis(h["handover"]["id"])
    handover.analyze(h["handover"]["id"], aid, delay=0)
    assert risk.account_risk(NORTHWIND)["risk"] == 84
    impact = {r["id"]: r for r in handover.customer_impact_view(h["handover"]["id"])}
    assert set(impact) == {NORTHWIND, KAIRO}
    assert impact[NORTHWIND]["before"] == 78 and impact[NORTHWIND]["after"] == 84


def test_live_call_cards_and_follow_through(cheerio):
    from relay import db
    from relay.health import risk
    from relay.sales import brief, live
    b = brief.build("evt-2026-10-19-northwind")
    assert any("Q1 2027" in g for g in b["goals"]) and b["openIssues"][0]["bugId"] == "CHEER-2547"

    async def run():
        s = live.start("evt-2026-10-19-northwind", speed=20)
        await s.task
        return s

    s = asyncio.run(run())
    kinds = [c["kind"] for c in s.cards]
    titles = [c["title"] for c in s.cards]
    assert "SSO moved to Q1 2027" in titles and "Promise at risk" in titles
    assert {"consent", "bug", "answer", "objection", "expert", "risk"} <= set(kinds)
    assert kinds.count("promise") >= 3
    assert all(c["latencyMs"] < 3000 for c in s.cards)
    expert = next(c for c in s.cards if c["kind"] == "expert")
    hops = expert["path"]["hops"]
    assert hops[0]["id"] == s.ctx.rep_id and hops[-1]["id"] == expert["action"]["toId"]
    assert any("shortestPath" in q["cypher"] for q in expert["queries"])
    r = s.result
    assert [x["id"] for x in r["superseded"]] == ["prm-northwind-sso"]
    assert r["health"]["before"] == 78 and r["health"]["after"] == 73
    assert risk.account_risk(NORTHWIND)["risk"] == 73
    assert any(a["type"] == "email.draft" and a["customerFacing"] for a in r["actions"])
    held = db.rows("MATCH (m:Meeting {id: 'evt-2026-10-19-northwind'})-[:PRODUCED]->(p:Promise) RETURN count(p) AS n")
    assert held[0]["n"] >= 3


def test_ask_answers_from_the_graph_and_sees_new_messages(cheerio):
    from relay import ask
    from relay.ingest import live as ingest
    a = ask.ask("Why is Northwind Foods at risk?", "p-arnav")
    assert a["mode"] == "graph" and "78%" in a["answer"] and a["sources"]
    sso = ask.ask("Is SSO coming in December?", "p-sneha")
    assert "Q1 2027" in sso["answer"]
    before = ask.ask("When will the campaign report export bug be fixed?", "p-sneha")
    assert "CHEER-2547" in before["answer"] and "no fix date" in before["answer"].lower()
    ingest.slack_message("cs", "p-dev", "Update on CHEER-2547: the fix is ON STAGE and goes to prod on Thursday 22 Oct.")
    after = ask.ask("When will the campaign report export bug be fixed?", "p-sneha")
    assert "ON STAGE" in after["answer"] and any(p["kind"] == "message" for p in after["path"])


def test_tenants_are_isolated(cheerio, built):
    from relay import db
    cheerio_people = {r["n"] for r in db.rows("MATCH (p:Person) RETURN p.name AS n")}
    lumen_people = {r["n"] for r in db.rows("MATCH (p:Person) RETURN p.name AS n", g=db.graph("lumen_test"))}
    assert "Rahul Verma" in cheerio_people and "Rahul Verma" not in lumen_people
    assert not cheerio_people & lumen_people
    assert db.rows("MATCH (a:Account) RETURN count(a) AS n", g=db.graph("lumen_test"))[0]["n"] == 4


def test_mcp_exposes_agent_tools(cheerio):
    from mcp import Client

    from relay.health.mcp_server import server

    async def run():
        async with Client(server) as c:
            names = {t.name for t in (await c.list_tools()).tools}
            res = await c.call_tool("risk_radar", {"limit": 3})
            exp = await c.call_tool("experts", {"bug_id": "CHEER-2547", "from_person_id": "p-sneha"})
            return names, res, exp

    names, res, exp = asyncio.run(run())
    assert not exp.is_error and "steps away through shared work" in exp.content[0].text
    assert {"risk_radar", "causal_chain", "blast_radius", "promises", "unique_knowledge", "meeting_brief", "ask",
            "approve_action"} <= names
    assert not res.is_error and "Northwind Foods" in res.content[0].text


def test_live_call_with_typed_lines(cheerio):
    """No recording: lines typed (or spoken) in Relay go through the same triggers and graph lookups."""
    from relay.sales import live

    async def run():
        s = live.start("evt-2026-10-19-northwind", live=True)
        import asyncio as aio
        await aio.sleep(0.05)
        a = await s.say("Is SSO coming in December? We were told December.", "customer")
        b = await s.say("I'll send you the fix date for the export bug by Friday.", "rep")
        result = await s.end()
        return s, a, b, result

    s, a, b, result = asyncio.run(run())
    assert s.speakers["customer"] and s.speakers["rep"]
    assert any(c["kind"] == "roadmap" for c in a["cards"])
    assert any(c["kind"] == "promise" for c in b["cards"])
    assert s.status == "summarised" and result["health"]["after"] <= result["health"]["before"]
