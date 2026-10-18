"""Contextual handover interview: one question per risk item, grounded in real activity.

Question sources, in order: curated prompts for the planted story (cached, per
the demo plan), Gemini grounded on the item's evidence, then a template built
from the same evidence. Every question carries a "why we're asking" line and
the source it came from.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel, Field

from . import db, handover, llm, tenants

_LUMEN_CURATED: dict[str, dict[str, str]] = {
    "dec-idem-72h": {
        "context": "You pushed for 72-hour idempotency keys in the 12 March architecture review. The reasoning isn't written down anywhere else.",
        "prompt": "Why 72 hours? What would break if someone shortened the TTL to 24 hours?"},
    "dec-settle-2am": {
        "context": "In April you moved nightly settlement to 02:00 and explained why in #payments. The runbook still says midnight.",
        "prompt": "Why does settlement run at 02:00, and what should someone check before changing the schedule?"},
    "wk-settle-lock": {
        "context": "You've rescued a 'lock held' settlement failure twice in #payments. The runbook still says to just re-run.",
        "prompt": "Walk us through recovering a settlement run that fails with 'lock held'. What goes wrong with a plain re-run?"},
    "cust-acme-bank": {
        "context": "Acme Bank's engineers come straight to you: 37 conversations, including direct messages.",
        "prompt": "Who should the next contact know at Acme Bank, and what do they usually need from us?"},
    "sys-reconciliation-service": {
        "context": "You made all 214 commits to reconciliation-service in the last eight months.",
        "prompt": "What does the next owner need to know first: what breaks, how you fix it, and what only looks scary?"},
    "wk-flaky-test": {
        "context": "You've unblocked deploys from the flaky test_concurrent_capture_refund 12 times since May.",
        "prompt": "Why does it flake, and what is the real fix?"},
    "sys-settlement-batch": {
        "context": "You made most of the commits to settlement-batch this year, and you're its owner in the service catalog.",
        "prompt": "What's normal for the nightly run, and which failures actually need a human?"},
    "wk-acme-bom": {
        "context": "Every month-end since July you've fixed Acme's statement import in #incidents.",
        "prompt": "What's different about Acme's month-end file, and what should whoever is on call that night do?"},
    "sys-acme-sftp-bridge": {
        "context": "You've answered 33 threads about the acme-sftp-bridge and wrote its integration notes.",
        "prompt": "What does the bridge do that isn't obvious from its config, and what needs doing on a schedule?"},
    "wk-ledger-replay": {
        "context": "Twice this year you cleared phantom recon mismatches after a ledger deploy with a 24-hour replay.",
        "prompt": "Is the ledger replay still needed now that the outbox (LUM-412) has shipped?"},
    "dec-acme-hmac": {
        "context": "In June you agreed with Acme in #ext-acme-bank to keep accepting their HMAC-SHA1 signatures.",
        "prompt": "What's the exception, when does it end, and what has to happen before we switch Acme to v2?"},
    "dec-recon-matching": {
        "context": "You wrote RFC-014 and shipped match_v2: bank reference first, then a ±1 minor-unit tolerance for FX.",
        "prompt": "Why only for FX lines, and what would go wrong if someone widened the tolerance?"},
}

_LUMEN_SAMPLES: dict[str, str] = {
    "dec-idem-72h": "Acme retries failed payout callbacks with backoff for up to 72 hours after an outage. It's in section 4.2 of their integration annex, not in their public API docs. Over a weekend, a Friday-night failure can be retried on Monday morning. With a 24h TTL those late retries looked like new requests, which is what caused the 18 Feb duplicate credits. If anyone wants to shorten it, get Acme to shorten their retry window first. The Redis cost is about 1.2 GB at today's volume.",
    "dec-settle-2am": "Acme drops the daily statement file on the SFTP bridge at about 01:30 IST, and Finance needs the ledger closed by 06:00. At midnight we were reconciling the previous day's partial file. 02:00 gives Acme 30 minutes of slack and the run still finishes by about 02:40. Before moving it, check Acme's drop time in #ext-acme-bank (they post when they're late) and talk to Sunil in Finance about the 06:00 close.",
    "wk-settle-lock": "If settlement fails with 'lock held', the previous run crashed without releasing its row in settlement_locks. Delete only that stale row (batch_id = the failed batch, released_at IS NULL), then run `settlement-batch run --resume-from <batch_id>`. Never start a fresh run: it creates a new batch and double-pays merchants whose payouts already went out. LUM-458 is the ticket to alert on old locks before the job fails.",
    "cust-acme-bank": "Daniel Okafor is the integration lead and decides anything about timelines or contracts. Mei Lin is the engineer who actually changes things on their side (files, signatures, test vectors). They post in #ext-acme-bank, and DM when the statement will be late. They need three things: confirmation that we got the file, quick checks when callbacks get rejected, and a heads-up before anything changes on our side. The open item is the HMAC v2 migration in January (LUM-471).",
    "sys-reconciliation-service": "Three things break. Late Acme files: the importer retries every 15 minutes until 07:00. Month-end files with a BOM: run recon-cli normalize. And mismatches after ledger deploys, which the outbox fixed in September. The exceptions dashboard looks scary, but timing exceptions auto-close the next night. Matching rules are in RFC-014 behind the match_v2 flag, so read that before touching the FX tolerance.",
    "wk-flaky-test": "test_concurrent_capture_refund shares Redis db 0 with the idempotency suite. When pytest-randomly runs them back to back the keys collide and the capture assertion fails. Re-run only that job with `pytest -p no:randomly -k concurrent_capture_refund`. The real fix is LUM-449: give the test its own Redis db through REDIS_TEST_DB in conftest. It's about an hour of work.",
    "sys-settlement-batch": "It parallelises per merchant after the first ten minutes, so long runs are normal on big payout days. Holds live in payout_holds and need ops approval to release. The two real failure modes are the stale lock (see the lock answer) and a late day-close snapshot from the ledger. The schedule is 02:00 IST, not midnight as the runbook says.",
    "sys-acme-sftp-bridge": "It pulls ACME_STMT_<date>.csv from sftp.acmebank.example and waits for the .done marker before handing the file to recon. Acme rotates their host key every June, so update known_hosts from the bridge config repo before their rotation date. It also verifies Acme's webhooks: v1 HMAC-SHA1 for Acme only, behind acme_hmac_v1, and v2 for everyone else.",
    "dec-recon-matching": "Acme rounds FX conversions half-up and our ledger uses banker's rounding, so the two can differ by one minor unit. Matching on bank reference first, then amount with a ±1 tolerance for FX lines only, removed about 2% false mismatches a night. Don't widen the tolerance for non-FX lines, it would hide real errors.",
    "dec-acme-hmac": "Acme's SHA-256 signer slipped to Q1 2027, so we accept v1 HMAC-SHA1 for Acme only, behind the acme_hmac_v1 flag on the bridge. Manish logged the compliance exception (LUM-433, valid until 31 Mar 2027). When Mei sends the v2 test vectors, run both verifiers side by side for a week, then remove the flag (LUM-471).",
    "wk-acme-bom": "Acme's month-end export runs on a different system that adds a UTF-8 BOM and CRLF line endings, and the importer rejects the header. Run `recon-cli normalize --strip-bom --crlf <file>`, then re-import. It happens on the 1st of every month around 02:30, so whoever is on call that night should know about it.",
    "wk-ledger-replay": "After a ledger-service deploy, run `recon-cli replay --source ledger --window 24h` to clear the phantom mismatches. Since Arjun's outbox (LUM-412) shipped on 15 Sep it shouldn't be needed any more. I haven't had to run it since.",
}


# Cheerio's planted story. Facts come from seed/cheerio/world.py; systems and the customer use graph ids.
_CHEERIO_CURATED: dict[str, dict[str, str]] = {
    "dec-settle-6am": {
        "context": "In April you moved nightly wallet settlement to 06:00 IST and explained why in #messaging. The runbook still says midnight.",
        "prompt": "Why does wallet settlement run at 06:00, and what must someone check before they change the time?"},
    "wk-settle-lock": {
        "context": "You fixed a settlement run that failed with 'lock held' more than once. The runbook still says to run it again.",
        "prompt": "How do you recover a settlement run that fails with 'lock held'? What goes wrong if you only run it again?"},
    "dec-idem-72h": {
        "context": "You asked for 72-hour idempotency keys in the 12 March architecture review. The reason is not written down anywhere else.",
        "prompt": "Why 72 hours? What breaks if someone shortens the key lifetime to 24 hours?"},
    "cust-kairo-living": {
        "context": "Kairo Living's engineers come straight to you, in #ext-kairo-living and by direct message.",
        "prompt": "Who must the next contact know at Kairo Living, and what do they usually need from us?"},
    "sys-billing-reconciler": {
        "context": "You own billing-reconciler in the service catalog, and you made most of its recent commits.",
        "prompt": "What must the next owner know first: what breaks, how you fix it, and what only looks bad?"},
    "dec-recon-matching": {
        "context": "You decided that billing-reconciler matches on message ID first, then on amount with a ±0.01 USD tolerance for FX debits.",
        "prompt": "Why does the tolerance apply only to FX-converted debits, and what goes wrong if someone makes it wider?"},
    "dec-kairo-hmac": {
        "context": "In June you agreed with Kairo Living to keep accepting their HMAC-SHA1 webhook signatures.",
        "prompt": "What is the exception, when does it end, and what must happen before Kairo moves to v2?"},
    "wk-kairo-bom": {
        "context": "At month-end you fix the import of Kairo Living's order file.",
        "prompt": "What is different about Kairo's month-end file, and what does the person on call do that night?"},
    "sys-wallet-settlement": {
        "context": "You own wallet-settlement in the service catalog.",
        "prompt": "What is normal for the nightly run, and which failures need a person?"},
    "sys-kairo-erp-bridge": {
        "context": "You own kairo-erp-bridge in the service catalog, and you answer most questions about it.",
        "prompt": "What does the bridge do that its configuration does not show, and what must happen on a schedule?"},
    "wk-flaky-test": {
        "context": "You unblocked deploys from the flaky test_concurrent_send_refund job many times.",
        "prompt": "Why does it fail at random, and what is the real fix?"},
    "wk-ledger-replay": {
        "context": "After wallet-ledger deploys, you cleared false mismatches in the reconciler with a 24-hour replay.",
        "prompt": "Is the ledger replay still needed now that the outbox (CHEER-2412) shipped?"},
}

_CHEERIO_SAMPLES: dict[str, str] = {
    "dec-settle-6am": ("Meta closes its pricing data on UTC days, which ends at 05:30 IST. Midnight runs billed partial "
                       "days, and Finance had to re-issue invoices twice in March. Before you move the job, make sure "
                       "that Meta's day has closed, and talk to Finance."),
    "wk-settle-lock": ("'Lock held' means an earlier run stopped and left its lock. Clear the stale lock, then resume "
                       "the run. Do not run it again from the start, because that settles the same wallets twice."),
    "dec-idem-72h": ("Kairo's ERP retries failed order events for up to 72 hours after an outage. With a 24-hour key, "
                     "those retries looked new, and on 18 Feb we sent duplicate order confirmations. Keep the key "
                     "lifetime longer than Kairo's retry window."),
    "dec-recon-matching": ("Meta bills in USD and rounds conversions half-up. Wallets debit in INR with banker's "
                           "rounding. So the two can differ by a cent, and exact matching flagged about 2% of debits "
                           "every night. Keep the tolerance for FX-converted debits only."),
    "dec-kairo-hmac": ("Kairo's SHA-256 signer slipped to Q1 2027. We accept v1 HMAC-SHA1 signatures for Kairo only, "
                       "behind the kairo_hmac_v1 flag. Turn the flag off when Kairo confirms their v2 cutover."),
    "wk-kairo-bom": ("Kairo's month-end order file has a byte-order mark and Windows line endings, so the importer "
                     "rejects the header. Strip the BOM and the CRLFs, then import the file again."),
    "wk-flaky-test": ("The test fails when the runner shuffles test order. Re-run the job without random ordering. "
                      "The real fix is to give the test its own data, so that order does not matter."),
    "wk-ledger-replay": ("After a wallet-ledger deploy, replay 24 hours of ledger events into the reconciler. Since "
                         "the outbox shipped in CHEER-2412, you do not need the replay any more."),
}

_CURATED = {"lumen": _LUMEN_CURATED, "cheerio": _CHEERIO_CURATED}
_SAMPLES = {"lumen": _LUMEN_SAMPLES, "cheerio": _CHEERIO_SAMPLES}


def curated() -> dict[str, dict[str, str]]:
    return _CURATED.get(tenants.current().id, {})


def samples() -> dict[str, str]:
    return _SAMPLES.get(tenants.current().id, {})


def story_key(item_id: str) -> str:
    """Map a graph item to its planted-story key, so curated prompts survive LLM extraction
    (where decisions and workarounds get generated ids). Matches on shared sources."""
    if item_id in curated() or item_id in samples():
        return item_id
    from .evaluate import _planted_sources
    srcs = {r["id"] for r in db.rows("MATCH (i {id: $i})-[:SOURCED_FROM]->(s) RETURN s.id AS id",
                                     {"i": item_id}, readonly=True)}
    if not srcs:
        return item_id
    best, overlap = item_id, 0
    for key, planted in _planted_sources().items():
        n = len(srcs & planted)
        if n > overlap and (key in curated() or key in samples()):
            best, overlap = key, n
    return best


class GeneratedQuestion(BaseModel):
    context: str = Field(description="One sentence: the specific activity of theirs that prompted this question, with a date or count.")
    prompt: str = Field(description="One short, specific question about tacit knowledge the next owner needs.")


SYSTEM = ("You write handover interview questions for a departing engineer. Ground every question in the "
          "evidence given (their commits, threads, meetings). Be specific, warm and brief. Never ask about "
          "personal matters, performance, or why they are leaving. No preamble.")


def _second_person(fact: str, first: str) -> str:
    """'Rahul explained it 4 times' -> 'You explained it 4 times'; '70 commits to x' -> 'You made 70 commits to x'."""
    if fact.startswith(first + " "):
        return "You " + fact[len(first) + 1:]
    if fact[:1].isdigit():
        return "You made " + fact
    word = fact.split()[0]
    if word == "Listed":
        return "You are listed" + fact[len(word):]
    if word in ("Answered", "Wrote", "Had"):
        return "You " + fact[0].lower() + fact[1:]
    return fact


def _template(r: dict, first: str = "") -> dict:
    facts = r["evidence"].get("facts") or []
    lead = _second_person(facts[0], first) if facts else f"You know {r['title']} better than anyone else."
    title = r["title"]
    low = title[0].lower() + title[1:]
    prompt = {
        "System": f"What does the next owner of {title} need to know first? What breaks, how do you fix it, and what only looks scary?",
        "Account": f"Who at {title} does the next contact need to know, and what do they usually need from us?",
        "Decision": f"Why did we decide to {low}? What breaks if someone changes it?",
        "Workaround": f"Walk us through it. When do you need to {low}, and what is the real fix?",
    }[r["type"]]
    context = lead if lead.endswith(".") else lead + "."
    return {"context": context, "prompt": prompt}


def _generate(r: dict, first: str) -> tuple[dict, str]:
    key = story_key(r["itemId"])
    known = curated().get(key)
    if llm.available():
        # A live model call, grounded on the item's evidence (and the planted story's facts when we have them).
        ev = r["evidence"]
        excerpts = "\n".join(f"- [{s['kind']}] {s['label']}: {(s.get('excerpt') or '')[:300]}" for s in ev.get("sources", []))
        hint = f"\nKnown context: {known['context']}" if known else ""
        prompt = (f"Item ({r['type']}): {r['title']}\nWhy it depends on them:\n"
                  + "\n".join(f"- {f}" for f in ev.get("facts", []))
                  + f"{hint}\nSources:\n{excerpts}\n\nWrite the context line (second person, 'You ...') and the question. "
                  "Use plain English and short sentences.")
        try:
            q = llm.generate(prompt, GeneratedQuestion, system=SYSTEM)
            return {"context": q.context, "prompt": q.prompt}, "llm"
        except llm.LLMUnavailable:
            pass
    if known:
        return known, "curated"
    return _template(r, first), "template"


def ensure_questions(hid: str) -> None:
    todo = [r for r in handover.risks(hid) if not r["question"]]
    if not todo:
        return
    first = handover.get(hid)["leaver"]["name"].split()[0]

    def build(r: dict) -> tuple[str, dict]:
        q, mode = _generate(r, first)
        src = (r["evidence"].get("sources") or [None])[0]
        return r["id"], {**q, "mode": mode, "source": src}

    with ThreadPoolExecutor(max_workers=6) as pool:
        for rid, q in pool.map(build, todo):
            db.run("MATCH (r:RiskItem {id: $id}) SET r.question = $q", {"id": rid, "q": json.dumps(q)})


def interview(hid: str) -> dict:
    ensure_questions(hid)
    h = handover.get(hid)
    items = [r for r in h["riskItems"] if r["state"] != "dismissed"]
    keys = {r["itemId"]: story_key(r["itemId"]) for r in items}
    order = list(curated())
    items.sort(key=lambda r: (keys[r["itemId"]] not in order,
                              order.index(keys[r["itemId"]]) if keys[r["itemId"]] in order else 0,
                              -(r["priority"] or 0)))
    questions = [{
        "riskId": r["id"], "itemId": r["itemId"], "type": r["type"], "title": r["title"], "state": r["state"],
        "skipped": r["skipped"], "context": r["question"]["context"], "prompt": r["question"]["prompt"],
        "mode": r["question"]["mode"], "source": r["question"]["source"],
        "answer": r["knowledge"]["answer"] if r["knowledge"] else None,
        "sampleAnswer": samples().get(keys[r["itemId"]]),
    } for r in items]
    answered = sum(1 for q in questions if q["answer"])
    skipped = sum(1 for q in questions if q["skipped"] and not q["answer"])
    nxt = next((i for i, q in enumerate(questions) if not q["answer"] and not q["skipped"]), None)
    return {"handover": h["handover"], "leaver": h["leaver"], "joiner": h["joiner"], "questions": questions,
            "progress": {"answered": answered, "skipped": skipped, "total": len(questions), "next": nxt}}


def fast_forward(hid: str) -> int:
    """Presenter helper: answer every remaining question with its sample answer."""
    data = interview(hid)
    n = 0
    for q in data["questions"]:
        if not q["answer"] and q["sampleAnswer"]:
            handover.capture(hid, q["riskId"], q["sampleAnswer"], data["leaver"]["id"],
                             {"prompt": q["prompt"], "source": q["source"]})
            n += 1
    return n
