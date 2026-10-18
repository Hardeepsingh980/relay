"""Graph logic against the planted Lumen story."""

from relay import analysis, evaluate
from relay.seed.lumen import world


def test_readiness_checks(fresh):
    failed = [(name, detail) for name, ok, detail in evaluate.checks() if not ok]
    assert not failed, failed


def test_rahul_inventory_counts(fresh):
    items = analysis.unique_knowledge(world.LEAVER)
    counts = {t: sum(i["type"] == t for i in items) for t in world.EXPECTED_RAHUL_COUNTS}
    assert counts == world.EXPECTED_RAHUL_COUNTS


def test_team_membership_alone_is_not_expertise(fresh):
    # Aisha is on Payments but has no activity: no knowledge edges at all.
    from relay import db
    n = db.rows("MATCH (:Person {id: 'p-aisha'})-[k:KNOWS|DECIDED]->() RETURN count(k) AS n")[0]["n"]
    assert n == 0


def test_former_employee_is_not_an_alternate(fresh):
    ev = analysis.evidence("sys-reconciliation-service", world.LEAVER)
    karan = next(a for a in ev["alternates"] if a["name"] == "Vinod Shah")
    assert karan["status"] == "left" and not karan["credible"]


def test_ledger_outbox_is_thin_after_departure(fresh):
    thin = {t["id"]: t["remaining"] for t in analysis.thin_coverage(world.LEAVER)}
    assert thin.get("dec-ledger-outbox") == "Vishal Rao"
