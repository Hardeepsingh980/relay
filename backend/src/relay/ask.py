"""Ask: sourced answers with an inspectable graph path.

1. Link the question to systems/customers through catalog aliases.
2. Retrieve candidates with FalkorDB full-text indexes, and by walking the
   graph out from the linked entities (decisions, workarounds, captured
   handover knowledge, and their sources).
3. Answer only from the retrieved evidence: Gemini when available,
   otherwise an extractive answer built from the best evidence.
4. Return the path that connects question -> system -> decision -> source -> person.

Private DMs are never used as evidence for someone who wasn't in them.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from . import analysis, ask_graph, db, llm, tenants, textmatch
from .analysis import fmt_day, source_ref

STOP = set("""a an the is are was were be been do does did why what when where who whom how which of to in on at for
from by with and or not it its this that these those we our us you your i me my can could should would will
there their they them about into than then so as if any some all has have had just like still ever""".split())

TYPE_BONUS = {"Knowledge": 0.9, "Decision": 0.8, "Workaround": 0.6, "Doc": 0.35, "Meeting": 0.35, "Message": 0.25,
              "Ticket": 0.2, "Commit": 0.1}
FULLTEXT_LABELS = ["Knowledge", "Decision", "Workaround", "Message", "Doc", "Meeting", "Ticket", "Commit"]
FOLLOWUPS = ["Who decided this?", "Has it changed since?", "Who else understands {s}?"]


class LLMAnswer(BaseModel):
    answer: str = Field(description="2-4 sentences. Cite evidence inline as [E1], [E2]. No preamble.")
    citations: list[str] = Field(description="Evidence ids actually used, e.g. ['E1','E3']")
    confidence: Literal["high", "medium", "low"]
    supported: bool = Field(description="False if the evidence does not answer the question")


SYSTEM = ("You answer questions from employees of {company} ({tagline}), using ONLY the numbered evidence. "
          "Write 2-4 plain sentences that explain the reason, not just the fact. Cite evidence inline as [E1]. "
          "Prefer captured handover answers and decision records, but keep original sources. If sources disagree "
          "or one is stale, say which is newer. If the evidence doesn't answer the question, say so and set "
          "supported=false. Never invent names, numbers or dates. Use plain English, short sentences and no jargon.")


def _terms(q: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", q.lower())
    out = []
    for w in words:
        if w in STOP or len(w) < 2:
            continue
        out.append(w)
        if w.isdigit() and len(w) <= 2:  # "2 AM" -> also match "02:00"
            out.append(f"{int(w):02d}")
    return out


def _fulltext(label: str, terms: list[str], k: int = 8) -> list[dict]:
    if not terms:
        return []
    query = "|".join(sorted(set(terms)))
    try:
        rows = db.rows(f"""CALL db.idx.fulltext.queryNodes('{label}', $q) YIELD node, score
                           RETURN node, score ORDER BY score DESC LIMIT {k}""", {"q": query}, readonly=True)
    except Exception:
        return []
    return rows


def _visible(node: dict, persona: str | None) -> bool:
    if node.get("_labels", [None])[0] != "Message":
        return True
    r = db.rows("""MATCH (m:Message {id: $id})-[:IN_CHANNEL]->(c:Channel)
                   OPTIONAL MATCH (p:Person {id: $p})-[:SENT]->(:Message)-[:IN_CHANNEL]->(c)
                   RETURN c.isIm AS im, count(p) AS mine""", {"id": node["id"], "p": persona or ""}, readonly=True)
    return not r or not r[0]["im"] or r[0]["mine"] > 0


def _people_answer(q: str, ents: list[dict]) -> dict | None:
    """'Who else understands X?' is a pure graph question."""
    if not ents or not re.search(r"\bwho\b.*\b(know|knows|understand|understands|own|owns|expert|ask)\b", q.lower()):
        return None
    e = ents[0]
    rows = db.rows(f"""MATCH (p:Person)-[k:{analysis.KNOWLEDGE_EDGES}]->(x {{id: $x}}) WHERE p.status IN $active
                       RETURN p.id AS id, p.name AS name, p.role AS role, k.score AS score, k.basis AS basis,
                              k.commits AS commits, k.answers AS answers, p.lastDay AS lastDay
                       ORDER BY k.score DESC LIMIT 5""", {"x": e["id"], "active": analysis.ACTIVE}, readonly=True)
    if not rows:
        return None
    name = db.rows("MATCH (x {id: $x}) RETURN coalesce(x.name, x.summary) AS n", {"x": e["id"]}, readonly=True)[0]["n"]
    strong = [r for r in rows if r["score"] > analysis.ALTERNATE]
    parts = []
    for r in rows[:3]:
        why = "verified in a handover" if r.get("basis") == "handover-verified" else \
              ", ".join(b for b in [f"{r['commits']} commits" if r.get("commits") else "",
                                     f"{r['answers']} answers in Slack" if r.get("answers") else ""] if b) or "activity"
        leaving = f", leaving {fmt_day(r['lastDay'] + 'T00:00:00+05:30')}" if r.get("lastDay") else ""
        parts.append(f"{r['name']} ({r['role']}; {why}{leaving})")
    lead = (f"{len(strong)} people have a strong link to {name}" if len(strong) > 1 else
            f"Only {strong[0]['name']} has a strong link to {name}" if strong else f"Nobody has a strong link to {name}")
    answer = f"{lead}: " + "; ".join(parts) + "."
    path = [{"kind": "question", "label": q}, {"kind": "system" if e["label"] == "System" else "customer", "label": name, "id": e["id"]}] + \
           [{"kind": "person", "label": r["name"], "id": r["id"]} for r in rows[:2]]
    return {"answer": answer, "segments": [{"text": answer}], "sources": [], "path": path, "mode": "graph",
            "confidence": "high", "supported": True, "conflicts": [], "freshness": None,
            "followups": [f"Why does {name} work the way it does?", f"What breaks in {name} most often?"]}


TEXT_FIELDS = {"Decision": ("summary", "rationale"), "Workaround": ("summary",), "Knowledge": ("question", "answer"),
               "Message": ("text",), "Doc": ("title", "body"), "Meeting": ("title", "text"),
               "Ticket": ("title", "description"), "Commit": ("message",)}
WHY_RE = re.compile(r"\b(why|reason|rationale|how come|decide|decided)\b")
HOW_RE = re.compile(r"\b(how|fix|fixes|error|errors|fail|fails|failed|failing|stuck|broken|workaround|recover|deal)\b")


def _coverage(terms: list[str], node: dict, label: str) -> tuple[float, int, int]:
    """(share, hits, n) of the question's content terms found in the candidate (prefix match as cheap stemming)."""
    if not terms:
        return 0.0, 0, 0
    text = " ".join(str(node.get(f) or "") for f in TEXT_FIELDS.get(label, ()))
    words = set(re.findall(r"[a-z0-9]+", text.lower()))
    hits = 0
    uniq = sorted(set(t for t in terms if not (t.isdigit() and len(t) == 1)))
    for t in uniq:
        stem = t[:4] if len(t) > 4 else t
        if any(w.startswith(stem) for w in words):
            hits += 1
    return hits / max(len(uniq), 1), hits, len(uniq)


def retrieve(question: str, persona: str | None) -> tuple[list[dict], list[dict], set[str]]:
    q = question.lower()
    ents = textmatch.mentions(question)
    ent_ids = {e["id"] for e in ents}
    terms = _terms(question)
    why, how = bool(WHY_RE.search(q)), bool(HOW_RE.search(q))
    cand: dict[str, dict] = {}

    def add(node: dict, text_score: float, via: str) -> None:
        c = cand.setdefault(node["id"], {"node": node, "label": node["_labels"][0], "text": 0.0, "via": set()})
        c["text"] = max(c["text"], text_score)
        c["via"].add(via)

    for label in FULLTEXT_LABELS:
        rows = _fulltext(label, terms)
        top = max((r["score"] for r in rows), default=1) or 1
        for r in rows:
            add(r["node"], r["score"] / top, "text")
    for e in ents:
        for r in db.rows("MATCH (i)-[:ABOUT]->(x {id: $x}) WHERE i:Decision OR i:Workaround RETURN i", {"x": e["id"]}, readonly=True):
            add(r["i"], 0.0, "graph")
        for r in db.rows("MATCH (k:Knowledge)-[:EXPLAINS]->(x {id: $x}) RETURN k", {"x": e["id"]}, readonly=True):
            add(r["k"], 0.0, "graph")

    scored = []
    for nid, c in cand.items():
        label = c["label"]
        cov, hits, n = _coverage(terms, c["node"], label)
        linked = bool(ent_ids) and bool(db.rows(
            """MATCH (n {id: $n})-[:ABOUT|EXPLAINS|MENTIONS|DOCUMENTS|CONCERNS|IN_REPO]->(x) WHERE x.id IN $ents
               RETURN x.id LIMIT 1""", {"n": nid, "ents": list(ent_ids)}, readonly=True))
        relevant = cov >= 0.34 and hits >= min(2, n)
        if not relevant and not (linked and (cov > 0 or label in ("Decision", "Workaround", "Knowledge"))):
            continue
        mult = 1.0
        if why and label in ("Decision", "Knowledge"):
            mult = 1.5
        if how and label in ("Workaround", "Knowledge"):
            mult = 1.5
        score = 2.0 * cov + 0.6 * c["text"] + 0.6 * TYPE_BONUS.get(label, 0.1) * mult + (0.7 if linked else 0.0)
        scored.append((score, c))
    ranked = [c for _, c in sorted(scored, key=lambda x: -x[0])]
    evidence: list[dict] = []
    seen: set[str] = set()

    def push(node: dict, role: str) -> None:
        if node["id"] in seen or len(evidence) >= 8 or not _visible(node, persona):
            return
        seen.add(node["id"])
        evidence.append({"node": node, "role": role})

    for c in ranked[:5]:
        node = c["node"]
        if c["label"] in ("Decision", "Workaround"):
            push(node, "item")
            for r in db.rows("MATCH (:%s {id: $id})-[:SOURCED_FROM]->(s) RETURN s ORDER BY s.t DESC LIMIT 2" % c["label"],
                             {"id": node["id"]}, readonly=True):
                push(r["s"], "source")
        elif c["label"] == "Knowledge":
            push(node, "knowledge")
        else:
            push(node, "source")
    return evidence, ents, ent_ids


def _evidence_text(e: dict) -> str:
    n, label = e["node"], e["node"]["_labels"][0]
    if label == "Decision":
        return f"Decision record ({n.get('decidedAt')}): {n['summary']}. Rationale: {n.get('rationale') or 'not recorded'}"
    if label == "Workaround":
        return f"Workaround (seen {n.get('sourceCount')} times): {n['summary']}"
    if label == "Knowledge":
        return f"Handover answer from {n.get('authorName')} ({fmt_day(n.get('capturedAt'))}). Q: {n.get('question')} A: {n.get('answer')}"
    ref = source_ref(n)
    stale = f" [doc freshness: {n.get('freshness')}: {n.get('staleReason')}]" if n.get("freshness") in ("stale", "aging") else ""
    if label == "Message":
        who = db.rows("MATCH (a)-[:SENT]->(:Message {id: $id}) RETURN a.name AS n", {"id": n["id"]}, readonly=True)
        thread = db.rows("""MATCH (m:Message {threadId: $t}) OPTIONAL MATCH (a)-[:SENT]->(m)
                            RETURN a.name AS who, m.text AS text ORDER BY m.t LIMIT 6""", {"t": n["threadId"]}, readonly=True)
        convo = " / ".join(f"{t['who']}: {t['text']}" for t in thread)
        return f"Slack {ref['label']} ({who[0]['n'] if who else 'unknown'}): {convo}"
    return f"{ref['kind']} {ref['label']}: {(ref.get('excerpt') or '')[:600]}{stale}"


def _path(evidence: list[dict], ents: list[dict], question: str) -> list[dict]:
    path = [{"kind": "question", "label": question}]
    items = [e["node"] for e in evidence if e["node"]["_labels"][0] in ("Decision", "Workaround")]
    prefer = "Decision" if WHY_RE.search(question.lower()) else "Workaround" if HOW_RE.search(question.lower()) else None
    item = next((n for n in items if n["_labels"][0] == prefer), items[0] if items else None)
    know = next((e["node"] for e in evidence if e["node"]["_labels"][0] == "Knowledge"), None)
    anchor = None
    target = item or know
    if target:
        rows = db.rows("""MATCH (i {id: $i})-[:ABOUT|EXPLAINS]->(x) WHERE x:System OR x:Account
                          RETURN x.id AS id, x.name AS name, labels(x)[0] AS label""", {"i": target["id"]}, readonly=True)
        ent_ids = [e["id"] for e in ents]
        rows.sort(key=lambda r: (r["id"] not in ent_ids, r["label"] != "System"))
        anchor = rows[0] if rows else None
    elif ents:
        anchor = db.rows("MATCH (x {id: $x}) RETURN x.id AS id, x.name AS name, labels(x)[0] AS label",
                         {"x": ents[0]["id"]}, readonly=True)[0]
    if anchor:
        path.append({"kind": anchor["label"].lower(), "label": anchor["name"], "id": anchor["id"], "edge": "about"})
    if item:
        path.append({"kind": item["_labels"][0].lower(), "label": item["summary"], "id": item["id"], "edge": "explained by"})
        src = db.rows(f"""MATCH (:{item['_labels'][0]} {{id: $i}})-[:SOURCED_FROM]->(s)
                           RETURN s, CASE labels(s)[0] WHEN 'Meeting' THEN 0 WHEN 'Message' THEN 1 WHEN 'Doc' THEN 2 ELSE 3 END AS pref
                           ORDER BY pref, s.t LIMIT 1""", {"i": item["id"]}, readonly=True)
        if src:
            ref = source_ref(src[0]["s"])
            path.append({"kind": ref["kind"], "label": ref["label"], "id": ref["id"], "nodeLabel": ref["nodeLabel"], "edge": "recorded in"})
        who = db.rows("""MATCH (p:Person)-[k:DECIDED|KNOWS]->(i {id: $i}) RETURN p.id AS id, p.name AS name
                          ORDER BY k.score DESC LIMIT 1""", {"i": item["id"]}, readonly=True)
        if who:
            path.append({"kind": "person", "label": who[0]["name"], "id": who[0]["id"], "edge": "by"})
    if know:
        path.append({"kind": "handover", "label": f"Handover answer · {fmt_day(know.get('capturedAt'))}", "id": know["id"],
                     "nodeLabel": "Knowledge", "edge": "captured as"})
    return path


def _extractive(evidence: list[dict]) -> tuple[str, list[str]]:
    """Answer from the best-ranked evidence when no LLM is available."""
    parts, cites = [], []
    first_item = next(((i, e) for i, e in enumerate(evidence) if e["role"] == "item"), None)
    know = next(((i, e) for i, e in enumerate(evidence) if e["role"] == "knowledge"), None)

    def src_tag(after: int) -> str:
        j = next((j for j in range(after + 1, len(evidence)) if evidence[j]["role"] == "source"), None)
        return f"E{(j if j is not None else after) + 1}"

    if first_item:
        i, e = first_item
        n = e["node"]
        tag = src_tag(i)
        if n["_labels"][0] == "Decision":
            why = (n.get("rationale") or "").rstrip(".")
            who = db.rows("MATCH (p:Person)-[d:DECIDED]->(:Decision {id: $i}) RETURN p.name AS n ORDER BY d.score DESC LIMIT 1",
                          {"i": n["id"]}, readonly=True)
            actor = who[0]["n"].split()[0] if who else "the team"
            when = f" on {fmt_day(n['decidedAt'] + 'T00:00:00+05:30')}" if n.get("decidedAt") else ""
            summary = n["summary"][0].lower() + n["summary"][1:]
            parts.append(f"{why} [{tag}]. That's why {actor} decided{when} to {summary}." if why
                         else f"{actor} decided{when} to {summary} [{tag}].")
        else:
            src = evidence[int(tag[1:]) - 1]["node"]
            who = db.rows("MATCH (p:Person)-[k:KNOWS]->(:Workaround {id: $i}) RETURN p.name AS n ORDER BY k.score DESC LIMIT 1",
                          {"i": n["id"]}, readonly=True)
            fix = src.get("text") if src.get("_labels", [None])[0] == "Message" else None
            thread = db.rows("""MATCH (m:Message {threadId: $t})<-[:SENT]-(p:Person) WHERE m.substantive
                                RETURN m.text AS text ORDER BY m.t LIMIT 2""", {"t": src.get("threadId")}, readonly=True) \
                if fix else []
            detail = " ".join(t["text"] for t in thread) if thread else ""
            parts.append(f"Known workaround: {n['summary'][0].lower() + n['summary'][1:]} [{tag}]."
                         + (f" {who[0]['n'].split()[0]} explained it: “{detail[:320]}”" if detail and who else ""))
        cites.append(tag)
    if know:
        i, e = know
        sentences = re.split(r"(?<=[.!?])\s+", e["node"]["answer"])
        parts.append(f"{(e['node'].get('authorName') or 'The previous owner').split()[0]} added in the handover: "
                     f"{sentences[0]} [E{i + 1}]")
        cites.append(f"E{i + 1}")
    if not parts and evidence:
        ref = source_ref(evidence[0]["node"])
        parts.append(f"The closest match is {ref['label']}: “{(ref.get('excerpt') or '')[:220]}” [E1]")
        cites.append("E1")
    return " ".join(parts), cites


def _conflicts(evidence: list[dict], ents: list[dict], refs: dict[str, dict]) -> list[dict]:
    """Stale docs that predate the decision/workaround behind this answer (e.g. a runbook saying midnight)."""
    items = [e["node"]["id"] for e in evidence if e["node"]["_labels"][0] in ("Decision", "Workaround")]
    if not items:
        return []
    rows = db.rows("""MATCH (k)-[:ABOUT]->(s:System)<-[:DOCUMENTS]-(d:Doc) WHERE k.id IN $items AND k.firstSeen > d.t
                      AND d.freshness = 'stale' AND NOT (k)-[:SOURCED_FROM]->(d)
                      RETURN DISTINCT d, CASE d.kind WHEN 'runbook' THEN 0 ELSE 1 END AS pref
                      ORDER BY pref, d.t DESC LIMIT 1""", {"items": items}, readonly=True)
    out = []
    for r in rows:
        ref = source_ref(r["d"])
        out.append({"source": ref, "note": f"“{ref['title']}” (last updated {fmt_day(r['d'].get('t'))}) predates "
                                           f"this and may say otherwise. It's marked stale."})
    return out


def _segments(answer: str, sources: dict[str, dict]) -> list[dict]:
    """Split '...text [E1] more' into text and source-pill segments."""
    out = []
    for piece in re.split(r"(\[E\d+(?:,\s*E\d+)*\])", answer):
        if not piece:
            continue
        m = re.fullmatch(r"\[(E\d+(?:,\s*E\d+)*)\]", piece)
        if m:
            for tag in re.split(r",\s*", m.group(1)):
                if tag in sources:
                    out.append({"source": tag})
        else:
            out.append({"text": piece})
    return out


def ask(question: str, persona: str | None = None) -> dict:
    question = question.strip()
    if not question:
        return {"answer": "", "segments": [], "sources": [], "path": [], "mode": "empty"}
    ents = textmatch.mentions(question)
    people = _people_answer(question, ents)
    if people:
        return people
    graph_first = ask_graph.try_answer(question)
    if graph_first:
        return graph_first
    evidence, ents, _ = retrieve(question, persona)
    refs = {}
    for i, e in enumerate(evidence):
        n = e["node"]
        label = n["_labels"][0]
        if label in ("Decision", "Workaround"):
            src = db.rows(f"MATCH (:{label} {{id: $i}})-[:SOURCED_FROM]->(s) RETURN s ORDER BY s.t LIMIT 1",
                          {"i": n["id"]}, readonly=True)
            ref = source_ref(src[0]["s"]) if src else {"kind": label.lower(), "id": n["id"], "label": n["summary"]}
            ref = {**ref, "via": n["summary"]}
        else:
            ref = source_ref(n)
        refs[f"E{i + 1}"] = ref
    conflicts = _conflicts(evidence, ents, refs)
    if not evidence:
        top = []
        if ents:
            top = db.rows(f"""MATCH (p:Person)-[k:{analysis.KNOWLEDGE_EDGES}]->(x {{id: $x}}) WHERE p.status IN $active
                              RETURN p.name AS name ORDER BY k.score DESC LIMIT 2""",
                          {"x": ents[0]["id"], "active": analysis.ACTIVE}, readonly=True)
        ask_next = " or ".join(t["name"] for t in top) if top else "the owning team"
        msg = f"I couldn't find a supported answer in the graph. Try asking {ask_next}."
        return {"answer": msg, "segments": [{"text": msg}], "sources": [], "path": [{"kind": "question", "label": question}],
                "mode": "no-evidence", "confidence": "low", "supported": False, "conflicts": [], "freshness": None,
                "followups": []}

    mode, confidence, supported = "extractive", "medium", True
    answer, cites = None, []
    if llm.available():
        block = "\n".join(f"[E{i + 1}] {_evidence_text(e)}" for i, e in enumerate(evidence))
        prompt = f"Question: {question}\n\nEvidence:\n{block}"
        try:
            t = tenants.current()
            out = llm.generate(prompt, LLMAnswer, system=SYSTEM.format(company=t.name, tagline=t.tagline.lower()))
            answer, cites, confidence, supported, mode = out.answer, out.citations, out.confidence, out.supported, "llm"
        except llm.LLMUnavailable:
            pass
    if answer is None:
        answer, cites = _extractive(evidence)
    used = [t for t in refs if t in cites or f"[{t}]" in answer]
    newest = max((r.get("at") or "" for t, r in refs.items() if t in used), default=None)
    ent_name = next((p["label"] for p in _path(evidence, ents, question) if p["kind"] in ("system", "customer")), "this system")
    return {
        "answer": answer, "segments": _segments(answer, refs),
        "sources": [{"tag": t, **refs[t]} for t in refs if t in used] or [{"tag": t, **r} for t, r in list(refs.items())[:3]],
        "path": _path(evidence, ents, question), "mode": mode, "confidence": confidence, "supported": supported,
        "conflicts": conflicts, "freshness": {"newest": newest, "label": fmt_day(newest) if newest else None},
        "followups": [f.format(s=ent_name) for f in FOLLOWUPS],
    }
