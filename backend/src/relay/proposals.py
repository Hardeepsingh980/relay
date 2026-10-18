"""Stale-doc updates proposed from captured handover answers (BR-12).

A proposal is a reviewable diff. Nothing touches the canonical doc until a
human approves it, and the approval itself is recorded.
"""

from __future__ import annotations

import difflib
import threading
from datetime import datetime

from pydantic import BaseModel

from . import analysis, db, llm
from .config import now


class DocRewrite(BaseModel):
    updated_body: str
    change_summary: str


SYSTEM = ("You maintain internal engineering runbooks. Update the document so it reflects the captured "
          "handover knowledge. Keep the existing structure and tone, change only what the new knowledge "
          "contradicts or adds, and do not invent facts that are not in the inputs.")


def _now() -> str:
    return now().isoformat(timespec="seconds")


def _stale_docs_for(item_id: str) -> list[dict]:
    systems = [s["id"] for s in analysis.item_systems(item_id)]
    if not systems:
        return []
    return [r["d"] for r in db.rows("""MATCH (d:Doc)-[:DOCUMENTS]->(s:System) WHERE s.id IN $ids
                                       AND d.kind = 'runbook' AND d.freshness IN ['stale', 'aging']
                                       RETURN DISTINCT d""", {"ids": systems}, readonly=True)]


def _knowledge_for_doc(doc_id: str, hid: str) -> list[dict]:
    """All captured answers in this handover that explain systems this doc documents."""
    return [r["k"] for r in db.rows("""MATCH (d:Doc {id: $d})-[:DOCUMENTS]->(s:System)<-[:EXPLAINS]-(k:Knowledge {handoverId: $h})
                                       RETURN DISTINCT k ORDER BY k.capturedAt""", {"d": doc_id, "h": hid}, readonly=True)]


def _rewrite(doc: dict, knowledge: list[dict]) -> tuple[str, str, str]:
    """Return (after, summary, mode)."""
    body = doc.get("body") or ""
    notes = "\n\n".join(f"Q: {k.get('question')}\nA: {k['answer']}" for k in knowledge)
    if llm.available():
        try:
            prompt = (f"Document title: {doc['title']}\n\nCurrent document:\n```\n{body}\n```\n\n"
                      f"Handover knowledge captured from the previous owner:\n{notes}\n\n"
                      "Return the full updated document as markdown, and a one-sentence summary of the change.")
            out = llm.generate(prompt, DocRewrite, system=SYSTEM)
            return out.updated_body.strip(), out.change_summary.strip(), "llm"
        except llm.LLMUnavailable:
            pass
    sections = []
    for k in knowledge:
        day = datetime.fromisoformat(k["capturedAt"]).strftime("%-d %b %Y")
        sections.append(f"## From the handover: {k.get('question') or 'captured knowledge'}\n"
                        f"_Captured from {k.get('authorName')} on {day}. Review before relying on it._\n\n{k['answer']}")
    after = body.rstrip() + "\n\n" + "\n\n".join(sections)
    return after, f"Adds {len(knowledge)} handover answer(s) the runbook doesn't cover.", "template"


_lock = threading.Lock()


def propose_doc_update(hid: str, rid: str) -> dict | None:
    with _lock:  # answers about the same runbook arrive together; build one proposal at a time
        return _propose(hid, rid)


def _propose(hid: str, rid: str) -> dict | None:
    r = db.rows("MATCH (r:RiskItem {id: $id}) RETURN r.itemId AS item, r.type AS type", {"id": rid}, readonly=True)
    if not r or r[0]["type"] not in ("Workaround", "Decision", "System"):
        return None
    docs = _stale_docs_for(r[0]["item"])
    if not docs:
        return None
    doc = docs[0]
    knowledge = _knowledge_for_doc(doc["id"], hid)
    if not knowledge:
        return None
    after, summary, mode = _rewrite(doc, knowledge)
    before = doc.get("body") or ""
    diff = "\n".join(difflib.unified_diff(before.splitlines(), after.splitlines(), "current", "proposed", lineterm=""))
    pid = f"dp-{hid}-{doc['id']}"
    params = {"id": pid, "doc": doc["id"], "title": doc["title"], "before": before, "after": after, "diff": diff,
              "summary": summary, "mode": mode, "now": _now(), "hid": hid,
              "kids": [k["id"] for k in knowledge], "reason": doc.get("staleReason")}
    exists = db.rows("MATCH (p:DocProposal {id: $id}) RETURN p.status AS s", {"id": pid}, readonly=True)
    if exists and exists[0]["s"] == "applied":
        return proposal(pid)
    if exists:
        db.run("""MATCH (p:DocProposal {id: $id}) SET p.after = $after, p.diff = $diff, p.summary = $summary,
                  p.mode = $mode, p.updatedAt = $now, p.knowledgeIds = $kids, p.status = 'proposed'""", params)
    else:
        db.run("""MATCH (d:Doc {id: $doc}) CREATE (p:DocProposal {id: $id, docId: $doc, title: $title, before: $before,
                  after: $after, diff: $diff, summary: $summary, mode: $mode, status: 'proposed', handoverId: $hid,
                  createdAt: $now, updatedAt: $now, knowledgeIds: $kids, staleReason: $reason})-[:UPDATES]->(d)""", params)
    db.run("MATCH (p:DocProposal {id: $id})-[b:BASED_ON]->() DELETE b", {"id": pid})
    db.run("UNWIND $kids AS kid MATCH (p:DocProposal {id: $id}), (k:Knowledge {id: kid}) CREATE (p)-[:BASED_ON]->(k)",
           {"id": pid, "kids": params["kids"]})
    return proposal(pid)


def proposal(pid: str) -> dict | None:
    r = db.rows("MATCH (p:DocProposal {id: $id}) RETURN p", {"id": pid}, readonly=True)
    if not r:
        return None
    p = r[0]["p"]
    return {k: p.get(k) for k in ("id", "docId", "title", "summary", "diff", "status", "mode", "createdAt",
                                  "updatedAt", "approvedBy", "approvedAt", "staleReason", "knowledgeIds", "after")}


def list_for(hid: str) -> list[dict]:
    return [proposal(r["id"]) for r in db.rows("MATCH (p:DocProposal {handoverId: $h}) RETURN p.id AS id ORDER BY p.createdAt",
                                               {"h": hid}, readonly=True)]


def approve(pid: str, actor: str) -> dict:
    p = proposal(pid)
    if not p:
        raise ValueError("No such proposal")
    name = db.rows("MATCH (a:Person {id: $id}) RETURN a.name AS n", {"id": actor}, readonly=True)[0]["n"]
    db.run("""MATCH (p:DocProposal {id: $id})-[:UPDATES]->(d:Doc)
              SET d.body = p.after, d.updatedAt = $now, d.t = $t, d.freshness = 'current', d.staleReason = null,
                  p.status = 'applied', p.approvedBy = $name, p.approvedAt = $now""",
           {"id": pid, "now": _now(), "t": now().timestamp(), "name": name})
    return {**proposal(pid), "destination": "Relay copy of the doc (Confluence write is simulated in demo mode)"}

