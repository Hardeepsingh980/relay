"""Demo readiness checks against the planted story of the current tenant (PRD section 3.3 / 19.1)."""

from __future__ import annotations

import json

from . import analysis, db, tenants


def _world():
    return tenants.current().world


def _names() -> dict[str, str]:
    w = _world()
    return {s["id"]: s["name"] for s in w.SYSTEMS} | {c["id"]: c["name"] for c in w.CUSTOMERS}


def _planted_sources() -> dict[str, set[str]]:
    """World decision/workaround id -> ids of the sources it was planted in."""
    out: dict[str, set[str]] = {}
    path = tenants.current().data_dir / "annotations" / "extractions.jsonl"
    for line in path.read_text().splitlines():
        r = json.loads(line)
        for a in r["annotations"]:
            if a["kind"] != "obsoletes":
                out.setdefault(a["item"], set()).add(r["source_id"])
    return out


def _graph_id(world_id: str) -> str:
    """Map a world id to the pipeline's id: systems/customers by name; decisions and
    workarounds by id (seed mode) or, for LLM extraction, by the sources they share."""
    names = _names()
    if world_id in names:
        r = db.rows("MATCH (n) WHERE (n:System OR n:Account) AND n.name = $n RETURN n.id AS id",
                    {"n": names[world_id]}, readonly=True)
        return r[0]["id"] if r else world_id
    if db.rows("MATCH (n {id: $id}) RETURN n.id LIMIT 1", {"id": world_id}, readonly=True):
        return world_id
    srcs = sorted(_planted_sources().get(world_id, ()))
    r = db.rows("""MATCH (i)-[:SOURCED_FROM]->(s) WHERE (i:Decision OR i:Workaround) AND s.id IN $srcs
                   RETURN i.id AS id, count(s) AS n ORDER BY n DESC LIMIT 1""", {"srcs": srcs}, readonly=True)
    return r[0]["id"] if r else world_id


def checks() -> list[tuple[str, bool, str]]:
    world = _world()
    out = []
    items = analysis.unique_knowledge(world.LEAVER)
    ids = {i["id"] for i in items}
    planted = {_graph_id(x) for x in world.PLANTED_UNIQUE}
    decoys = {_graph_id(x) for x in world.DECOYS}
    missing = planted - ids
    out.append(("Planted unique items found (precision test, 5/5)", not missing,
                f"missing: {sorted(missing)}" if missing else f"{len(planted)}/{len(planted)}"))
    leaked = decoys & ids
    out.append(("Decoys excluded (API gateway and other shared systems)", not leaked,
                f"leaked: {sorted(leaked)}" if leaked else f"{len(decoys)} decoys excluded"))
    counts = {t: sum(1 for i in items if i["type"] == t) for t in world.EXPECTED_RAHUL_COUNTS}
    out.append(("Risk inventory: Systems 3, Customers 1, Decisions 4, Workarounds 4",
                counts == world.EXPECTED_RAHUL_COUNTS, str(counts)))
    co = analysis.company_risk()
    out.append((f"Company single points of failure = {world.EXPECTED_COMPANY_SPOF}",
                co["singlePointsOfFailure"] == world.EXPECTED_COMPANY_SPOF, str(co["singlePointsOfFailure"])))
    by_person = {p["id"]: p["unique"] for p in co["people"]}
    out.append(("Unique items per person match the plan", by_person == world.EXPECTED_SPOF_BY_PERSON, str(by_person)))
    no_source = []
    for i in items:
        ev = analysis.evidence(i["id"], world.LEAVER)
        if not ev.get("sources"):
            no_source.append(i["title"])
    out.append(("Every risk item has at least one source", not no_source,
                f"no sources: {no_source}" if no_source else f"{len(items)}/{len(items)}"))
    rb = db.rows("MATCH (d:Doc {id: 'DOC-1042'}) RETURN d.freshness AS f", readonly=True)
    out.append(("Settlement runbook is flagged stale", bool(rb) and rb[0]["f"] == "stale", rb[0]["f"] if rb else "missing"))
    out += _health_checks(world)
    return out


def _health_checks(world) -> list[tuple[str, bool, str]]:
    """Account Health and Sales Assist expectations (tenants with a customer dataset)."""
    exp = getattr(world, "EXPECTED_HEALTH", None)
    if not exp:
        return []
    out = []
    rows = {r["name"]: r for r in db.rows("""MATCH (a:Account) WHERE a.detectiveRisk IS NOT NULL
                                             RETURN a.name AS name, a.detectiveRisk AS risk, a.crmHealthScore AS crm,
                                                    a.silentRisk AS silent, a.arr AS arr""", readonly=True)}
    hero = rows.get(exp["hero"], {})
    out.append((f"{exp['hero']}: Relay risk {exp['hero_risk']}% vs CRM {exp['hero_crm']}",
                hero.get("risk") == exp["hero_risk"] and hero.get("crm") == exp["hero_crm"],
                f"risk {hero.get('risk')}, CRM {hero.get('crm')}"))
    silent = sorted(n for n, r in rows.items() if r["silent"])
    out.append(("Silent-risk accounts match the plan", silent == sorted(exp["silent"]), ", ".join(silent)))
    bug = db.rows("""MATCH (b:Bug {id: $b})<-[:SYMPTOM_OF]-(:Ticket)-[:CONCERNS]->(a:Account)
                     RETURN count(DISTINCT a) AS n, sum(DISTINCT a.arr) AS arr""", {"b": exp["bug"]}, readonly=True)[0]
    out.append((f"{exp['bug']} blast radius: {exp['bug_accounts']} accounts", bug["n"] == exp["bug_accounts"], f"{bug['n']} accounts"))
    prm = db.rows("""MATCH (p:Promise {id: $p})-[:DEPENDS_ON]->(r:RoadmapItem) RETURN r.status AS s, p.due < r.eta AS late""",
                  {"p": exp["promise_at_risk"]}, readonly=True)
    out.append(("Promise at risk: due before its roadmap ETA", bool(prm) and prm[0]["late"], str(prm[0] if prm else None)))
    return out


def run_eval() -> bool:
    ok = True
    for name, passed, detail in checks():
        ok &= passed
        print(f"{'PASS' if passed else 'FAIL'}  {name}  [{detail}]")
    print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
    return ok
