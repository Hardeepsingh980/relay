"""Gemini extraction of decisions and workarounds from unstructured sources.

1. Read each knowledge-bearing source (meeting transcripts, docs, Slack threads
   with replies) and extract candidate decisions/workarounds, the systems they
   are about, and the role every participant played.
2. Resolve duplicates: the same decision shows up in a meeting, a thread and a
   commit. One call per kind clusters candidates into canonical items.
3. Find tickets that make a workaround obsolete.

Every response is cached (see llm.py), so a rebuild is deterministic and free.
"""

from __future__ import annotations

import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Literal

from falkordb import Graph
from pydantic import BaseModel, Field

from .. import llm
from .extract import Extraction, ExtractionResult, ItemDef
from .load import Exports, Resolver, slug

VERSION = "gemini-extract@2"

Role = Literal["proposer", "co-proposer", "supporter", "approver", "ack", "author", "applier"]


class Participant(BaseModel):
    name: str = Field(description="Full name exactly as it appears in the source")
    role: Role


class Candidate(BaseModel):
    kind: Literal["decision", "workaround"]
    summary: str = Field(description="Imperative, under 14 words, e.g. 'Retain payment idempotency keys for 72 hours'")
    rationale: str | None = Field(description="Why, in one sentence, only if the source states it")
    about: list[str] = Field(description="Names from the provided systems/customers list only")
    participants: list[Participant]
    quote: str = Field(description="Shortest verbatim sentence from the source that supports this")


class SourceExtraction(BaseModel):
    items: list[Candidate]


class Cluster(BaseModel):
    summary: str
    rationale: str | None
    about: list[str]
    members: list[int] = Field(description="Indexes of the candidates that describe the same item")


class Clusters(BaseModel):
    clusters: list[Cluster]


class Obsoletes(BaseModel):
    workaround_index: int | None = Field(description="Index of the workaround this ticket makes unnecessary, or null")


SYSTEM = """You extract durable organisational knowledge for a company knowledge graph. Be conservative.

DECISION: a deliberate, lasting technical or business choice that the source shows being MADE or RECORDED
together with its reasoning (a TTL, a schedule, a matching rule, a security exception, a policy threshold).
Not: a document that merely describes how something currently works, plans for this week, status updates,
task assignments.

WORKAROUND: a repeatable operational fix for a recurring problem where the source gives CONCRETE steps
(an exact command, query, flag or procedure). Ordinary troubleshooting advice ("re-run the import",
"check the logs", "wait for the retry") is NOT a workaround.

Roles for decisions:
  proposer    argued for it with reasons, or set the terms of how it will work (even if someone else asked)
  co-proposer jointly proposed it with reasons
  supporter   argued for it with substance of their own
  approver    signed off without giving the reasoning
  ack         was present, asked about it, or acknowledged it
Roles for workarounds:
  author      explained the fix
  applier     independently applied or re-explained it WITHOUT being instructed in this same source
  ack         asked, followed instructions given in this source, thanked, or confirmed it worked

Include every named participant who interacted with the item, using only names that appear in the source.
Return an empty list for chatter, standups, status updates and alerts without discussion."""

DECISION_ROLES = {"proposer", "co-proposer", "supporter", "approver", "ack"}
WORKAROUND_ROLES = {"author", "applier", "ack"}
CODE_RE = re.compile(r"`[^`]{3,}`")


def _sources(ex: Exports, rv: Resolver) -> list[tuple[str, str, str]]:
    """(label, id, text) for every source worth reading."""
    names = {e["email"]: e["name"] for e in ex.employees}
    for a in ex.accounts:
        for c in a["contacts"]:
            names[c["email"]] = f"{c['name']} ({a['name']})"
    user_names = {u["id"]: (names.get(u.get("email")) or u["real_name"]) for u in ex.users}
    out = []
    for m in ex.meetings:
        if m.get("kind") == "customer":
            continue  # customer calls carry promises, extracted by the Sales Assist pipeline
        lines = "\n".join(f"{names.get(x['speaker_email'], 'Unknown')}: {x['text']}" for x in m["transcript"])
        out.append(("Meeting", m["id"], f"Meeting: {m['title']} ({m['start'][:10]})\n{lines}\nNotes: {m['notes']}"))
    for p in ex.pages:
        out.append(("Doc", p["id"], f"Document: {p['title']} (by {names.get(p['author_email'], 'unknown')}, "
                                     f"updated {p['updated'][:10]})\n{p['body']}"))
    threads: dict[str, list[dict]] = defaultdict(list)
    for m in ex.messages:
        threads[f"{m['channel']}:{m.get('thread_ts') or m['ts']}"].append(m)
    for tid, msgs in threads.items():
        if len(msgs) < 2:
            continue
        msgs.sort(key=lambda m: float(m["ts"]))
        text = "\n".join(f"{user_names.get(m['user'], 'Unknown')}: {m['text']}" for m in msgs)
        if not rv.mentions(text) and not re.search(r"`[^`]+`", text):
            continue
        out.append(("Message", tid, f"Slack thread in {msgs[0]['channel']}\n{text}"))
    for c in ex.commits:
        if "(" in c["message"] and len(c["message"]) > 40:
            out.append(("Commit", c["sha"], f"Commit by {names.get(c['author_email'], 'unknown')} in {c['repo']}: {c['message']}"))
    return out


def gemini_extract(ex: Exports, rv: Resolver, g: Graph, progress: Callable[[str], None] = print) -> ExtractionResult:
    if not llm.available():
        raise llm.LLMUnavailable("Gemini extraction needs GEMINI_API_KEY; use --extractor seed")
    person_by_name = {e["name"]: e["employee_id"] for e in ex.employees}
    sources = _sources(ex, rv)
    # Only customers the sources mention: the commercial portfolio has 120 accounts, and listing all of
    # them adds noise to every prompt (and changes every cache key when one is renamed).
    blob = "\n".join(text for _, _, text in sources).lower()
    mentioned = [a["name"] for a in ex.accounts
                 if any(alias in blob for alias in {a["name"].lower(), *(x.lower() for x in a.get("aliases", []))})]
    catalog = [s["name"] for s in ex.systems] + mentioned
    progress(f"Gemini: reading {len(sources)} sources for decisions and workarounds")

    def read(src: tuple[str, str, str]) -> tuple[str, str, list[Candidate]]:
        label, sid, text = src
        prompt = f"Known systems and customers: {', '.join(catalog)}\n\nSource:\n{text[:12000]}"
        try:
            return label, sid, llm.generate(prompt, SourceExtraction, system=SYSTEM, cache=True).items
        except llm.LLMUnavailable:
            return label, sid, []

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(read, sources))
    text_of = {(label, sid): text for label, sid, text in sources}
    cands: list[tuple[str, str, Candidate]] = []
    for label, sid, items in results:
        for c in items:
            allowed = DECISION_ROLES if c.kind == "decision" else WORKAROUND_ROLES
            c.participants = [p for p in c.participants if p.role in allowed]
            if c.kind == "decision" and not (c.rationale or "").strip():
                continue  # a decision without stated reasoning is a description, not a decision record
            if c.kind == "workaround" and not CODE_RE.search(text_of[(label, sid)]):
                continue  # workarounds need concrete steps (an exact command or query)
            cands.append((label, sid, c))
    progress(f"Gemini: {len(cands)} candidates; resolving duplicates")

    items: list[ItemDef] = []
    links: list[Extraction] = []
    workaround_ids: list[str] = []
    for kind in ("decision", "workaround"):
        group = [(i, x) for i, x in enumerate(cands) if x[2].kind == kind]
        if not group:
            continue
        listing = "\n".join(f"[{n}] {c.summary} | about: {', '.join(c.about)} | why: {c.rationale or '-'}"
                            for n, (_, (_, _, c)) in enumerate(group))
        clusters = llm.generate(
            f"Group these {kind} candidates so each group is one real-world {kind}. Every index must appear in "
            f"exactly one group. Write a canonical summary, rationale and about list for each group.\n\n{listing}",
            Clusters, system="You deduplicate entries for a knowledge graph. Be conservative: only merge true duplicates.",
            cache=True).clusters
        used: set[int] = set()
        for cl in clusters:
            members = [m for m in cl.members if 0 <= m < len(group) and m not in used]
            if not members:
                continue
            used.update(members)
            prefix = "dec" if kind == "decision" else "wk"
            iid = f"{prefix}-{slug(cl.summary)[:48]}"
            while any(i.id == iid for i in items):
                iid += "-x"
            about = [e for e in (rv.entity(n) for n in cl.about if n in catalog) if e]
            items.append(ItemDef(iid, kind, cl.summary, cl.rationale, None, about))
            if kind == "workaround":
                workaround_ids.append(iid)
            for m in members:
                label, sid, c = group[m][1]
                roles = {person_by_name[p.name]: p.role for p in c.participants if p.name in person_by_name}
                links.append(Extraction(label, sid, kind, iid, roles, c.quote))
    # Decision dates: earliest source that recorded it.
    progress(f"Gemini: {len(items)} canonical decisions/workarounds")

    done = [t for t in ex.issues if t["status"] == "Done" and t["comments"]]
    wk = [i for i in items if i.kind == "workaround"]
    if wk:
        listing = "\n".join(f"[{n}] {w.summary}" for n, w in enumerate(wk))
        for t in done:
            text = f"{t['summary']}\n{t['description']}\n" + "\n".join(c["body"] for c in t["comments"])
            if not re.search(r"no longer|not needed|removes|obsolete|unnecessary", text, re.I):
                continue
            r = llm.generate(f"Workarounds:\n{listing}\n\nTicket {t['key']} (Done):\n{text}\n\n"
                             "Does this ticket make one of the workarounds unnecessary? Return its index or null.",
                             Obsoletes, system="You link resolved tickets to the workarounds they retire.", cache=True)
            if r.workaround_index is not None and 0 <= r.workaround_index < len(wk):
                links.append(Extraction("Ticket", t["key"], "obsoletes", wk[r.workaround_index].id, {}))
    return ExtractionResult(items, links, VERSION)
