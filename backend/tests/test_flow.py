"""End-to-end: Priya starts the handover, Rahul answers, Aisha inherits it."""

import time

from fastapi.testclient import TestClient

PRIYA, RAHUL, AISHA = ({"X-Relay-Persona": p} for p in ("p-priya", "p-rahul", "p-aisha"))


def _start(c: TestClient) -> str:
    r = c.post("/api/handovers", json={"leaverId": "p-rahul", "lastDay": "2026-10-23", "joinerId": "p-aisha"}, headers=PRIYA)
    assert r.status_code == 200, r.text
    hid = r.json()["handover"]["id"]
    aid = c.post(f"/api/handovers/{hid}/analyze").json()["analysisId"]
    for _ in range(100):
        if c.get(f"/api/handovers/{hid}").json()["handover"]["status"] == "active":
            break
        time.sleep(0.1)
    events = c.get(f"/api/analyses/{aid}/events").text
    assert "analysis.completed" in events
    return hid


def test_full_handover(client):
    c = client
    assert c.get("/api/home/knowledge-risk").json()["singlePointsOfFailure"] == 23
    hid = _start(c)
    h = c.get(f"/api/handovers/{hid}").json()
    assert h["coverage"]["total"] == 12 and h["coverage"]["atRisk"] == 12
    risks = {r["itemId"]: r for r in h["riskItems"]}
    assert all(r["evidence"]["sources"] for r in risks.values())

    # Assignment alone does not reduce the risk count.
    lock = risks["wk-settle-lock"]
    succ = lock["suggestions"][0]["id"]
    r = c.post(f"/api/handovers/{hid}/risks/{lock['id']}/assign", json={"successorId": succ}, headers=PRIYA)
    assert r.json()["state"] == "assigned"
    assert c.get(f"/api/handovers/{hid}").json()["coverage"]["atRisk"] == 12

    # Only the leaver can answer; the answer becomes a Knowledge node.
    assert c.post(f"/api/handovers/{hid}/answers", json={"riskItemId": lock["id"], "answerText": "x" * 10},
                  headers=PRIYA).status_code == 400
    iv = c.get(f"/api/handovers/{hid}/interview").json()
    q = next(q for q in iv["questions"] if q["itemId"] == "wk-settle-lock")
    assert q["source"] and q["context"]
    r = c.post(f"/api/handovers/{hid}/answers", json={"riskItemId": lock["id"], "answerText": q["sampleAnswer"]}, headers=RAHUL)
    assert r.json()["state"] == "captured"
    # Captured is not resolved until verified.
    assert c.get(f"/api/handovers/{hid}").json()["coverage"]["atRisk"] == 12
    props = c.get(f"/api/handovers/{hid}/doc-proposals").json()
    assert props and props[0]["docId"] == "DOC-1042" and "+" in props[0]["diff"]

    r = c.post(f"/api/handovers/{hid}/risks/{lock['id']}/verify", headers=PRIYA)
    assert r.json()["state"] == "verified"
    assert c.get(f"/api/handovers/{hid}").json()["coverage"]["atRisk"] == 11
    # Verification gave the successor a credible link, so the company count drops too.
    assert c.get("/api/home/knowledge-risk").json()["singlePointsOfFailure"] == 22

    # Dismiss the obsolete workaround with a reason; it leaves the active count.
    replay = risks["wk-ledger-replay"]
    r = c.post(f"/api/handovers/{hid}/risks/{replay['id']}/dismiss",
               json={"reason": "Obsolete since LUM-412 shipped"}, headers=PRIYA)
    assert r.json()["state"] == "dismissed"
    assert c.get(f"/api/handovers/{hid}").json()["coverage"]["atRisk"] == 10
    assert c.get("/api/home/knowledge-risk").json()["singlePointsOfFailure"] == 21

    # Aisha's Day One shows the inherited answer, five people and a checklist.
    d = c.get("/api/day-one/p-aisha").json()
    assert len(d["services"]) == 3
    assert len(d["meet"]) == 5 and d["meet"][0]["id"] == "p-rahul"
    assert any(card["itemId"] == "wk-settle-lock" for card in d["fromLeaver"])
    kinds = [x["kind"] for x in d["checklist"]]
    assert kinds.count("doc") == 4 and "ticket" in kinds and "people" in kinds
    ck = d["checklist"][0]["id"]
    assert c.post(f"/api/checklist/{ck}/toggle", headers=AISHA).json()["done"] is True

    # Intro booking is reviewable and honest about simulation.
    a = c.post("/api/actions/intro", json={"personId": "p-rahul"}, headers=AISHA).json()
    assert a["status"] == "proposed"
    done = c.post(f"/api/actions/{a['id']}/approve", json={}, headers=AISHA).json()
    assert done["status"] == "simulated" and "Saved in Relay" in done["result"]["message"]

    # Ticket moves are proposed from assignments, approved by the manager only.
    acts = c.get(f"/api/handovers/{hid}/actions").json()
    reassign = [x for x in acts if x["type"] == "ticket.reassign"]
    assert reassign, acts
    assert c.post(f"/api/actions/{reassign[0]['id']}/approve", json={}, headers=AISHA).status_code == 400
    assert c.post(f"/api/actions/{reassign[0]['id']}/approve", json={}, headers=PRIYA).json()["status"] == "simulated"


def test_ask_settlement(client):
    c = client
    r = c.post("/api/ask", json={"question": "Why does the settlement job run at 2 AM?"}, headers=AISHA).json()
    assert r["sources"], r
    assert "01:30" in r["answer"] or "Acme" in r["answer"]
    kinds = [p["kind"] for p in r["path"]]
    assert kinds[0] == "question" and "system" in kinds and "decision" in kinds and "person" in kinds
    who = c.post("/api/ask", json={"question": "Who else understands reconciliation-service?"}, headers=AISHA).json()
    assert who["mode"] == "graph" and "Aditya" in who["answer"]


def test_dm_privacy(fresh):
    from relay import ask
    ev, _, _ = ask.retrieve("Is 01:30 still the latest Acme can drop the file?", "p-aisha")
    assert all(e["node"].get("channel") != "D0ACMERAHUL" for e in ev)


def test_reset_restores_state(client):
    c = client
    _start(c)
    assert c.get("/api/handovers").json()
    assert c.post("/api/demo/reset", json={"confirm": True}).json()["ok"]
    assert c.get("/api/handovers").json() == []
