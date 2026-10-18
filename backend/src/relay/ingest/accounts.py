"""Load the customer-facing exports: CRM commercials, product features and bugs, the
support desk, product usage, billing, customer conversations, the roadmap, the
calendar, promises, playbooks and past episodes.

Everything joins the same graph as the knowledge layer, so a support ticket can be
traced to a bug, its owner, the systems behind the feature and the people who know them.
"""

from __future__ import annotations

import json
from datetime import datetime

from falkordb import Graph

from .. import db
from ..health import signals
from .load import Exports, Resolver, _t, slug


def _day(iso: str | None) -> str | None:
    return iso[:10] if iso else None


def load_accounts(g: Graph, ex: Exports, rv: Resolver) -> dict:
    if not ex.features:
        return {"accounts": 0}
    acc_id = rv.customer_by_name
    wallets = {w["account"]: w for w in ex.wallets}

    # --- CRM commercials ---------------------------------------------------
    rows = []
    for a in ex.accounts:
        w = wallets.get(a["name"], {})
        rows.append({"id": acc_id[a["name"]], "industry": a.get("industry"), "country": a.get("country"),
                     "domain": a.get("domain"), "plan": a.get("plan"), "arr": a.get("arr"), "mrr": a.get("mrr"),
                     "seats": a.get("seats"), "term": a.get("billing_term"), "renewal": a.get("renewal_date"),
                     "crm": a.get("crm_health_score"), "crmSrc": a.get("crm_health_source"),
                     "stage": a.get("renewal_stage"), "life": a.get("lifecycle"), "planted": a.get("planted") or "",
                     "wallet": w.get("balance"), "topupAt": w.get("last_topup_at")})
    db.batched("""UNWIND $rows AS r MATCH (a:Account {id: r.id})
                  SET a.industry = r.industry, a.country = r.country, a.domain = r.domain, a.plan = r.plan, a.arr = r.arr,
                      a.mrr = r.mrr, a.seats = r.seats, a.billingTerm = r.term, a.renewalDate = r.renewal,
                      a.crmHealthScore = r.crm, a.crmHealthSource = r.crmSrc, a.renewalStage = r.stage,
                      a.lifecycle = r.life, a.planted = r.planted, a.walletBalance = r.wallet, a.lastTopupAt = r.topupAt""",
               rows, g=g)
    for role, key in (("cs_owner", "cs_owner_email"), ("sales_poc", "sales_poc_email")):
        db.batched(f"""UNWIND $rows AS r MATCH (p:Person {{email: r.e}}), (a:Account {{id: r.id}})
                       CREATE (p)-[:MANAGES {{role: '{role}', source: 'CRM'}}]->(a)""",
                   [{"e": a[key], "id": acc_id[a["name"]]} for a in ex.accounts if a.get(key)], g=g)
    db.batched("""UNWIND $rows AS r MATCH (p:Person {email: r.e}), (a:Account {id: r.id})
                  CREATE (p)-[:TECH_CONTACT_FOR {source: 'CRM'}]->(a)""",
               [{"e": a["technical_contact_email"], "id": acc_id[a["name"]]} for a in ex.accounts
                if a.get("technical_contact_email")], g=g)

    # --- product catalog ---------------------------------------------------
    db.batched("UNWIND $rows AS r CREATE (:Feature {id: r.id, name: r.name})",
               [{"id": f["id"], "name": f["name"]} for f in ex.features], g=g)
    db.batched("""UNWIND $rows AS r MATCH (f:Feature {id: r.id}), (p:Person {email: r.e}) CREATE (f)-[:OWNED_BY]->(p)""",
               [{"id": f["id"], "e": f["owner_email"]} for f in ex.features], g=g)
    db.batched("""UNWIND $rows AS r MATCH (f:Feature {id: r.id}), (s:System {id: r.s}) CREATE (f)-[:SERVED_BY]->(s)""",
               [{"id": f["id"], "s": rv.system_by_name[s]} for f in ex.features for s in f["systems"]
                if s in rv.system_by_name], g=g)
    db.batched("""UNWIND $rows AS r MATCH (a:Account {id: r.a}), (f:Feature {id: r.f}) CREATE (a)-[:USES {since: r.since}]->(f)""",
               [{"a": acc_id[a["name"]], "f": rv.feature_by_name[n], "since": None}
                for a in ex.accounts for n in a.get("features", []) if n in rv.feature_by_name], g=g)

    # --- Jira bugs (issues already loaded as :Ticket) ----------------------
    bugs = [i for i in ex.issues if i.get("issuetype") == "Bug"]
    db.batched("""UNWIND $rows AS r MATCH (t:Ticket {id: r.id}) SET t:Bug, t.priority = r.priority, t.keyword = r.kw,
                  t.workaround = r.wk, t.feature = r.feature""",
               [{"id": b["key"], "priority": b.get("priority"), "kw": b.get("keyword"), "wk": b.get("workaround"),
                 "feature": b.get("feature")} for b in bugs], g=g)
    db.batched("""UNWIND $rows AS r MATCH (b:Bug {id: r.id}), (f:Feature {id: r.f}) CREATE (b)-[:AFFECTS]->(f)""",
               [{"id": b["key"], "f": rv.feature_by_name[b["feature"]]} for b in bugs if b.get("feature") in rv.feature_by_name], g=g)

    # --- support desk ------------------------------------------------------
    tk, raised, concerns, about, symptom, assigned = [], [], [], [], [], []
    for t in ex.support:
        tk.append({"id": t["id"], "title": t["subject"], "description": t["body"], "status": t["status"],
                   "priority": t["priority"], "channel": t["channel"], "createdAt": t["created"], "t": _t(t["created"]),
                   "url": f"https://support.{ex.tenant}.example/tickets/{t['id'].split('-')[1]}"})
        _, c = rv.actor(t["requester_email"])
        if c:
            raised.append({"c": c, "id": t["id"]})
        concerns.append({"id": t["id"], "a": acc_id[t["account"]]})
        if t.get("feature") in rv.feature_by_name:
            about.append({"id": t["id"], "f": rv.feature_by_name[t["feature"]]})
        if t.get("linked_bug"):
            lb = t["linked_bug"]
            symptom.append({"id": t["id"], "b": lb["key"], "conf": lb["confidence"], "method": lb["method"],
                            "at": lb["linked_at"], "by": lb["linked_by"]})
        _, p = rv.actor(t.get("assignee_email"))
        if p:
            assigned.append({"id": t["id"], "p": p})
    db.batched("""UNWIND $rows AS r CREATE (:Ticket {id: r.id, title: r.title, description: r.description, status: r.status,
                  priority: r.priority, channel: r.channel, createdAt: r.createdAt, t: r.t, url: r.url, source: 'support',
                  issueType: 'Support'})""", tk, g=g)
    db.batched("UNWIND $rows AS r MATCH (c:Contact {id: r.c}), (t:Ticket {id: r.id}) CREATE (c)-[:RAISED]->(t)", raised, g=g)
    db.batched("UNWIND $rows AS r MATCH (t:Ticket {id: r.id}), (a:Account {id: r.a}) CREATE (t)-[:CONCERNS]->(a)", concerns, g=g)
    db.batched("UNWIND $rows AS r MATCH (t:Ticket {id: r.id}), (f:Feature {id: r.f}) CREATE (t)-[:ABOUT_FEATURE]->(f)", about, g=g)
    db.batched("""UNWIND $rows AS r MATCH (t:Ticket {id: r.id}), (b:Bug {id: r.b})
                  CREATE (t)-[:SYMPTOM_OF {confidence: r.conf, method: r.method, linkedAt: r.at, linkedBy: r.by}]->(b)""",
               symptom, g=g)
    db.batched("UNWIND $rows AS r MATCH (t:Ticket {id: r.id}), (p:Person {id: r.p}) CREATE (t)-[:ASSIGNED_TO]->(p)", assigned, g=g)

    # --- product usage -----------------------------------------------------
    use = [{"id": f"use-{slug(u['account'])}-{slug(u['feature'] or 'active')}-{u['week_index']:02d}",
            "a": acc_id[u["account"]], "week": u["week"], "i": u["week_index"], "metric": u["metric"], "v": u["value"],
            "f": rv.feature_by_name.get(u["feature"]) if u["feature"] else None} for u in ex.usage]
    db.batched("""UNWIND $rows AS r MATCH (a:Account {id: r.a})
                  CREATE (u:UsageWeek {id: r.id, week: r.week, weekIndex: r.i, metric: r.metric, value: r.v,
                          sourceSystem: 'Product analytics'})-[:OF_ACCOUNT]->(a)""", use, size=2000, g=g)
    db.batched("""UNWIND $rows AS r MATCH (u:UsageWeek {id: r.id}), (f:Feature {id: r.f}) CREATE (u)-[:OF_FEATURE]->(f)""",
               [u for u in use if u["f"]], size=2000, g=g)

    # --- billing -----------------------------------------------------------
    db.batched("""UNWIND $rows AS r MATCH (a:Account {id: r.a})
                  CREATE (:Invoice {id: r.id, issuedAt: r.issued, dueDate: r.due, paidDate: r.paid, daysLate: r.late,
                          amount: r.amount, amountExGst: r.ex, status: r.status, sourceSystem: r.src})-[:BILLED_TO]->(a)""",
               [{"id": i["id"], "a": acc_id[i["account"]], "issued": i["issued"], "due": i["due"], "paid": i["paid"],
                 "late": i["days_late"], "amount": i["amount"], "ex": i.get("amount_ex_gst"), "status": i["status"],
                 "src": i.get("source", "Billing")} for i in ex.invoices], g=g)

    # --- customer conversations + extracted signals -------------------------
    convs, parts, sigs = [], [], []
    for c in ex.conversations:
        convs.append({"id": c["id"], "a": acc_id[c["account"]], "channel": c["channel"], "at": c["occurred_at"],
                      "t": _t(c["occurred_at"]), "text": c["text"], "summary": c["summary"]})
        for email in (c["contact_email"], c.get("internal_email")):
            label, x = rv.actor(email)
            if x:
                parts.append({"label": label, "x": x, "id": c["id"]})
        for i, s in enumerate(signals.extract(c["text"])):
            sigs.append({"id": f"SIG-{c['id'].split('-')[1]}-{i}", "conv": c["id"], **s, "at": _day(c["occurred_at"])})
    db.batched("""UNWIND $rows AS r MATCH (a:Account {id: r.a})
                  CREATE (:Conversation {id: r.id, channel: r.channel, occurredAt: r.at, t: r.t, text: r.text,
                          summary: r.summary, sourceSystem: 'Conversation log'})-[:WITH_ACCOUNT]->(a)""", convs, g=g)
    for label in ("Contact", "Person"):
        db.batched(f"""UNWIND $rows AS r MATCH (x:{label} {{id: r.x}}), (c:Conversation {{id: r.id}})
                       CREATE (x)-[:PARTICIPATED_IN]->(c)""", [p for p in parts if p["label"] == label], g=g)
    write_signals(g, sigs, "Conversation")

    # --- roadmap -----------------------------------------------------------
    for r in ex.roadmap:
        db.run("""CREATE (:RoadmapItem {id: $id, title: $title, status: $status, eta: $eta, etaLabel: $etaLabel,
                  originalEta: $oeta, originalLabel: $olabel, publicNote: $pub, internalNote: $internal,
                  updatedAt: $updated, t: $t, url: $url})""",
               {"id": r["id"], "title": r["title"], "status": r["status"], "eta": r["eta"], "etaLabel": r["eta_label"],
                "oeta": r["original_eta"], "olabel": r["original_label"], "pub": r["public_note"],
                "internal": r["internal_note"], "updated": r["updated"], "t": _t(r["updated"]),
                "url": f"https://roadmap.{ex.tenant}.example/items/{r['id']}"}, g=g)
    db.batched("""UNWIND $rows AS r MATCH (i:RoadmapItem {id: r.id}), (f:Feature {id: r.f}) CREATE (i)-[:FOR_FEATURE]->(f)""",
               [{"id": r["id"], "f": rv.feature_by_name[r["feature"]]} for r in ex.roadmap if r["feature"] in rv.feature_by_name], g=g)
    db.batched("""UNWIND $rows AS r MATCH (i:RoadmapItem {id: r.id}), (p:Person {email: r.e}) CREATE (i)-[:OWNED_BY]->(p)""",
               [{"id": r["id"], "e": r["owner_email"]} for r in ex.roadmap], g=g)

    # --- calendar: upcoming customer meetings --------------------------------
    for e in ex.calendar:
        db.run("""CREATE (:Meeting {id: $id, title: $title, date: $start, end: $end, t: $t, kind: 'customer',
                  status: 'scheduled', meetingType: $kind, recording: $rec, url: $url, text: $title})""",
               {"id": e["id"], "title": e["title"], "start": e["start"], "end": e["end"], "t": _t(e["start"]),
                "kind": e["kind"], "rec": e.get("recording"), "url": e.get("meet_url")}, g=g)
        if e["account"] in acc_id:
            db.run("MATCH (m:Meeting {id: $m}), (a:Account {id: $a}) CREATE (m)-[:WITH]->(a)",
                   {"m": e["id"], "a": acc_id[e["account"]]}, g=g)
        for email in e["attendees"]:
            label, x = rv.actor(email)
            if x:
                db.run(f"MATCH (x:{label} {{id: $x}}), (m:Meeting {{id: $m}}) CREATE (x)-[:INVITED_TO]->(m)",
                       {"x": x, "m": e["id"]}, g=g)
        label, owner = rv.actor(e.get("owner"))
        if owner:
            db.run("MATCH (p:Person {id: $p}), (m:Meeting {id: $m}) CREATE (p)-[:HOSTS]->(m)", {"p": owner, "m": e["id"]}, g=g)

    # --- seed-mode annotations: promises and playbooks -----------------------
    items = [json.loads(x) for x in (ex.root / "annotations" / "items.jsonl").read_text().splitlines() if x.strip()]
    promises = [i for i in items if i["kind"] == "promise"]
    for p in promises:
        write_promise(g, rv, p)
    for pb in (i for i in items if i["kind"] == "playbook"):
        db.run("""CREATE (b:Playbook {id: $id, name: $name, trigger: $trigger, steps: $steps, outcome: $outcome,
                  memory: 'procedural'})""",
               {"id": pb["id"], "name": pb["name"], "trigger": pb["trigger"], "steps": json.dumps(pb["steps"]),
                "outcome": pb["outcome"]}, g=g)
        db.run("MATCH (b:Playbook {id: $id}), (d:Doc {id: $doc}) CREATE (b)-[:SOURCED_FROM]->(d)",
               {"id": pb["id"], "doc": pb["source_id"]}, g=g)
        for name in pb["worked_for"]:
            if name in acc_id:
                db.run("MATCH (b:Playbook {id: $id}), (a:Account {id: $a}) CREATE (b)-[:WORKED_FOR]->(a)",
                       {"id": pb["id"], "a": acc_id[name]}, g=g)

    # --- episodic memory -----------------------------------------------------
    for e in ex.episodes:
        db.run("""CREATE (ep:Episode {id: $id, kind: $kind, at: $at, t: $t, risk: $risk, verdict: $verdict,
                  outcome: $outcome, memory: 'episodic'})""",
               {"id": e["id"], "kind": e["kind"], "at": e["at"], "t": _t(e["at"]), "risk": e.get("risk"),
                "verdict": e["verdict"], "outcome": e.get("outcome")}, g=g)
        if e["account"] in acc_id:
            db.run("MATCH (ep:Episode {id: $id}), (a:Account {id: $a}) CREATE (ep)-[:FOR_ACCOUNT]->(a)",
                   {"id": e["id"], "a": acc_id[e["account"]]}, g=g)
        _, p = rv.actor(e.get("actor"))
        if p:
            db.run("MATCH (p:Person {id: $p}), (ep:Episode {id: $id}) CREATE (p)-[:RAN]->(ep)", {"p": p, "id": e["id"]}, g=g)

    return {"accounts": len(ex.accounts), "supportTickets": len(tk), "bugs": len(bugs), "usageWeeks": len(use),
            "conversations": len(convs), "signals": len(sigs), "promises": len(promises),
            "roadmapItems": len(ex.roadmap), "calendar": len(ex.calendar)}


def write_signals(g: Graph, sigs: list[dict], source_label: str) -> None:
    db.batched(f"""UNWIND $rows AS r MATCH (c:{source_label} {{id: r.conv}})
                   CREATE (s:Signal {{id: r.id, type: r.type, phrase: r.phrase, quote: r.quote, confidence: r.confidence,
                           method: r.method, extractedAt: r.at}})
                   CREATE (c)-[:EXPRESSES {{quote: r.quote, confidence: r.confidence, method: r.method}}]->(s)""",
               sigs, g=g)


def write_promise(g: Graph | None, rv: Resolver | None, p: dict, account_id: str | None = None,
                  maker_id: str | None = None) -> None:
    """A promise made to a customer: who made it, in which meeting, what it depends on."""
    g = g or db.graph()
    account_id = account_id or rv.customer_by_name[p["account"]]
    if maker_id is None and rv is not None:
        _, maker_id = rv.actor(p["made_by_email"])
    made_at = p["made_at"].isoformat() if isinstance(p["made_at"], datetime) else p["made_at"]
    db.run("""CREATE (:Promise {id: $id, text: $text, due: $due, status: $status, madeAt: $at, t: $t, quote: $quote,
              extraction: $how})""",
           {"id": p["id"], "text": p["text"], "due": p["due"], "status": p["status"], "at": made_at,
            "t": datetime.fromisoformat(made_at).timestamp(), "quote": p.get("quote", ""),
            "how": p.get("extraction", "seed-annotations@1")}, g=g)
    db.run("MATCH (m:Meeting {id: $m}), (p:Promise {id: $id}) CREATE (m)-[:PRODUCED]->(p)", {"m": p["source_id"], "id": p["id"]}, g=g)
    db.run("MATCH (p:Promise {id: $id}), (a:Account {id: $a}) CREATE (p)-[:TO]->(a)", {"id": p["id"], "a": account_id}, g=g)
    if maker_id:
        db.run("MATCH (x:Person {id: $x}), (p:Promise {id: $id}) CREATE (x)-[:MADE]->(p)", {"x": maker_id, "id": p["id"]}, g=g)
    dep = p.get("depends_on")
    if dep:
        label = {"RoadmapItem": "RoadmapItem", "Bug": "Bug", "Ticket": "Ticket"}[dep["kind"]]
        db.run(f"MATCH (p:Promise {{id: $id}}), (d:{label} {{id: $d}}) CREATE (p)-[:DEPENDS_ON]->(d)",
               {"id": p["id"], "d": dep["id"]}, g=g)
