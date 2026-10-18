"""Build a company graph from its exports: load -> extract -> score -> freshness -> risk scan.

Each tenant (sample company) builds into its own pristine `<graph>_base`, and the
working graph (and every workspace) is a copy of it.
"""

from __future__ import annotations

import time
from typing import Callable

from .. import db, tenants
from ..config import DEMO_NOW, settings
from . import extract, score
from .accounts import load_accounts
from .load import Exports, create_fulltext, load

BASE_SUFFIX = "_base"
WS_INFIX = "_ws_"


def freshness(g, company: str) -> int:
    """Mark docs whose content predates knowledge found later, or whose author left."""
    db.run("MATCH (d:Doc) SET d.freshness = 'current', d.staleReason = null", g=g)
    db.run("""MATCH (d:Doc) WHERE d.t < $cutoff SET d.freshness = 'aging',
              d.staleReason = 'Not updated in over six months'""",
           {"cutoff": DEMO_NOW.timestamp() - 183 * 86400}, g=g)
    db.run("""MATCH (a:Person {status: 'left'})-[:AUTHORED]->(d:Doc)
              SET d.freshness = 'stale', d.staleReason = 'Author ' + a.name + ' has left ' + $company""",
           {"company": company}, g=g)
    res = db.rows("""MATCH (d:Doc)-[:DOCUMENTS]->(s:System)<-[:ABOUT]-(k)
                     WHERE (k:Workaround OR k:Decision) AND k.firstSeen > d.t AND NOT (k)-[:SOURCED_FROM]->(d)
                       AND d.kind IN ['runbook', 'design', 'onboarding']
                     WITH d, collect(DISTINCT k.summary) AS later
                     SET d.freshness = 'stale',
                         d.staleReason = 'Written before ' + toString(size(later)) + ' later change(s): ' + later[0]
                     RETURN count(d) AS n""", g=g)
    return res[0]["n"] if res else 0


def demo_graph(tenant: tenants.Tenant) -> str:
    """The tenant's shared demo graph. Tests point RELAY_GRAPH at e.g. `lumen_test`."""
    configured = settings().graph_name
    return configured if tenants.for_graph(configured).id == tenant.id else tenant.graph


def build(progress: Callable[[str], None] = print, extractor: str | None = None,
          tenant: str | None = None, target: str | None = None) -> dict:
    """Build a tenant's pristine graph and its working copy (`target`, default: the tenant's demo graph)."""
    s = settings()
    t = tenants.get(tenant) if tenant else tenants.for_graph(target or s.graph_name)
    extractor = extractor or s.extractor
    target = target or demo_graph(t)
    t0 = time.time()
    base = db.graph(target + BASE_SUFFIX)
    try:
        base.delete()
    except Exception:
        pass
    ex = Exports.read(t.data_dir)
    progress(f"[{t.name}] Read exports: {len(ex.messages)} messages, {len(ex.pages)} docs, {len(ex.issues)} Jira issues, "
             f"{len(ex.meetings)} meetings, {len(ex.commits)} commits, {len(ex.accounts)} accounts, "
             f"{len(ex.support)} support tickets")
    rv = load(base, ex)
    progress("Loaded people, systems, accounts and evidence")
    acc = load_accounts(base, ex, rv)
    if acc.get("accounts"):
        progress(f"Loaded customer data: {acc['supportTickets']} support tickets, {acc['bugs']} bugs, "
                 f"{acc['usageWeeks']} usage weeks, {acc['signals']} signals, {acc['promises']} promises")
    if extractor == "gemini":
        from .llm_extract import gemini_extract
        res = gemini_extract(ex, rv, base, progress)
    else:
        res = extract.seed_extract(ex, rv)
    stats = extract.write(base, res)
    progress(f"Extracted {stats['items']} decisions/workarounds from {stats['links']} source links ({stats['version']})")
    edges = score.compute(base)
    sc = score.write(base, edges)
    progress(f"Scored expertise: {sc['knows']} KNOWS->System, {sc['accounts']} KNOWS->Account edges")
    stale = freshness(base, t.name)
    progress(f"Freshness: {stale} docs predate later knowledge")
    create_fulltext(base)
    db.run("CREATE (:Company {id: $id, name: $name, tagline: $tag, builtAt: $at, extraction: $ext})",
           {"id": t.id, "name": t.name, "tag": t.tagline, "at": time.time(), "ext": stats["version"]}, g=base)
    if acc.get("accounts"):
        from ..health import risk
        token = db.use_graph(base.name)
        try:
            scanned = risk.scan()
        finally:
            db.reset_graph(token)
        progress(f"Detective scan: {len(scanned)} accounts scored, "
                 f"{sum(1 for v in scanned.values() if v['silent'])} silent risks")
    reset(target)
    counts = db.rows("MATCH (n) RETURN labels(n)[0] AS label, count(n) AS n ORDER BY n DESC", g=base)
    return {"tenant": t.id, "graph": target, "seconds": round(time.time() - t0, 1), "extraction": stats["version"],
            "nodes": {r["label"]: r["n"] for r in counts}}


def base_graph_name(graph: str | None = None) -> str:
    """The pristine build a working or workspace graph is copied from."""
    graph = graph or db.current_graph_name()
    if WS_INFIX in graph:
        graph = graph.split(WS_INFIX, 1)[0]
    if graph.endswith(BASE_SUFFIX):
        return graph
    return graph + BASE_SUFFIX


def reset(target: str | None = None) -> None:
    """Restore a working graph (default: the current one) from its pristine build."""
    target = target or db.current_graph_name()
    source = base_graph_name(target)
    if db.exists(target):
        db.graph(target).delete()
    db.graph(source).copy(target)
