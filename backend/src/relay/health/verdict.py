"""Evidence-grounded verdict assembly.

The causal chain is built from tool output (graph first); prose is either templated
here or written by the LLM and then validated against the evidence ids the tools
actually returned.
"""

from __future__ import annotations

from .tools import SIGNAL_LABELS, inr, short_name

# Who linked a ticket to its bug, in words.
METHOD_WORDS = {"support-triage": "a support agent", "auto-triage": "the auto-triage tool"}
# Factor labels that start with a name (a feature or a person) keep their capital letter mid-sentence.
NAMED_FACTORS = ("feature_decline", "internal_owner_leaving")

NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}


def words(n: int) -> str:
    return NUMBER_WORDS.get(n, str(n))


def weeks(days: int) -> str:
    w = round(days / 7)
    return f"{words(w)} week{'s' if w != 1 else ''}" if days >= 10 else f"{days} days"


def sentence(text: str) -> str:
    return text[:1].upper() + text[1:]


def first(name: str) -> str:
    return name.split()[0]


def method_words(method: str | None) -> str:
    return METHOD_WORDS.get(method or "", method or "an unknown method")


def build(d: dict, company: str = "Cheerio") -> dict:
    """d: tool name -> ToolResult.data for the tools that ran."""
    ov = d["account_overview"]
    acc = ov["account"]
    name, short = acc["name"], short_name(acc["name"])
    champ = d.get("champion_changes", {})
    tickets = d.get("ticket_root_causes", {})
    usage = d.get("usage_trend", {})
    sigs = d.get("signals", {})
    billing = d.get("billing_events", {})
    risk = d.get("risk_breakdown", {})
    chain_data = d.get("causal_chain", {})
    proms = d.get("promises", {})
    owners = d.get("internal_owners", {})
    mem = d.get("memory", {})
    best = (chain_data.get("candidates") or [None])[0]

    departed = next((x for x in champ.get("departures", []) if x["champion"]), None)
    cluster = None
    if best:
        cluster = next((c for c in tickets.get("clusters", []) if c["bugId"] == best["bugId"]), None)
    if cluster is None:
        cluster = next((c for c in tickets.get("clusters", []) if c["open"] and c["confidentLinks"]), None)
    feature = None
    if cluster:
        feature = next((m for m in usage.get("featureDeclines", []) if m["key"] == cluster["featureId"]), None)
    top_feature = (usage.get("featureDeclines") or [None])[0]
    wau = usage.get("weeklyActiveUsers")
    risk_signals = [s for s in sigs.get("signals", []) if s["type"] in ("competitor_evaluation", "budget_pressure", "frustration")]
    competitor = next((s for s in risk_signals if s["type"] == "competitor_evaluation"), None)
    positive = [s for s in sigs.get("signals", []) if s["type"] in ("renewal_positive", "praise")]
    renewal = ov["renewalInDays"]
    score = risk.get("risk", acc.get("detectiveRisk"))
    at_risk_promises = [p for p in proms.get("promises", []) if p["atRisk"]]
    leaving = owners.get("leaving", [])

    steps: list[dict] = []

    def step(title: str, detail: str, evidence: list[str], kind: str, source: str, confidence: float | None = None,
             in_chain: bool = True) -> None:
        steps.append({"title": title, "detail": detail, "evidenceIds": [e for e in evidence if e], "kind": kind,
                      "source": source, "confidence": confidence, "inChain": in_chain})

    chain_successor = bool(best and best.get("formerChampions"))
    if departed:
        succ = departed.get("successor")
        detail = f"{departed['name']} ({departed['role']}) left {weeks(departed['daysAgo'])} ago."
        if departed.get("emailStatus") == "bouncing":
            detail += " Their email now bounces."
        detail += f" {succ['name']} took over." if succ else " The CRM shows nobody taking over."
        step("Main contact left", detail, [departed["id"], succ["id"] if succ else None], "observed", "CRM",
             in_chain=chain_successor)
    if cluster:
        n = len(cluster["tickets"])
        titles = ", ".join(f"“{t['title']}”" for t in cluster["tickets"][:3])
        who = " and ".join(first(r) for r in cluster["reporters"][:2])
        step(f"{words(n).capitalize()} tickets in {cluster['spanDays']} days",
             f"{who} raised {words(n)} tickets{' with different wording' if cluster['distinctWordings'] > 1 else ''}: {titles}.",
             [t["id"] for t in cluster["tickets"]], "observed", "Support desk")
        methods: dict[str, int] = {}
        for t in cluster["tickets"]:
            methods[t["method"]] = methods.get(t["method"], 0) + 1
        avg = sum(t["confidence"] for t in cluster["tickets"]) / n
        how = " and ".join(f"{method_words(k)} ({v})" for k, v in methods.items())
        status = cluster.get("jiraStatus") or cluster["bugStatus"]
        step(f"{'One bug behind them' if n > 1 else 'The bug behind it'}: {cluster['bugId']}",
             f"{'Both' if n == 2 else ('All ' + words(n) if n > 2 else 'It')} point{'s' if n == 1 else ''} to {cluster['bugId']} "
             f"({cluster['bugTitle']}). The bug is {weeks(cluster['bugAgeDays'])} old, in {status} at {cluster['bugPriority']}"
             f"{', owned by ' + cluster['owner'] if cluster['owner'] else ''}. Linked by {how}, with an average "
             f"confidence of {avg:.2f}.",
             [cluster["bugId"]] + [t["id"] for t in cluster["tickets"]], "inferred", "Support + Jira",
             confidence=round(avg, 2))
    usage_metric = feature if (feature and feature["declinePct"] >= 20) else (
        top_feature if top_feature and top_feature["declinePct"] >= 20 else None)
    if usage_metric or (wau and wau["declinePct"] >= 10):
        bits, ev = [], []
        if usage_metric:
            bits.append(f"{usage_metric['metric']} usage is down {usage_metric['declinePct']}% "
                        f"({usage_metric['baseline']:.0f} → {usage_metric['current']:.0f} events a week)")
            ev.append(f"usage:{acc['id']}:{usage_metric['key']}")
        if wau and wau["declinePct"] >= 10:
            bits.append(f"active users are down {wau['declinePct']}%")
            ev.append(f"usage:{acc['id']}:wau")
        title = (f"{usage_metric['metric']} usage down {usage_metric['declinePct']}%" if usage_metric
                 else f"Active users down {wau['declinePct']}%")
        step(title, " ".join(sentence(b) + "." for b in bits)
             + " This compares the last 4 weeks with an earlier 8-week average.", ev, "observed", "Product analytics")
    if competitor:
        step("Competitor mention", f"{competitor['speaker']}: “{competitor['quote']}” ({competitor['date']}).",
             [competitor["conversationId"], competitor["signalId"]], "observed", "Conversation",
             confidence=competitor["confidence"])
    for s in risk_signals:
        if s is competitor or s["type"] == "competitor_evaluation":
            continue
        step(SIGNAL_LABELS[s["type"]], f"{s['speaker']}: “{s['quote']}” ({s['date']}).",
             [s["conversationId"], s["signalId"]], "observed", "Conversation", confidence=s["confidence"], in_chain=False)
    for p in at_risk_promises:
        dep = p.get("dependsOn") or {}
        step(f"Promise at risk: {p['text']}",
             f"{p['madeBy'] or 'Someone'} promised this in “{p['meeting']}” (due {p['due']}). "
             f"{dep.get('title', 'The work it depends on')} is now {dep.get('status')}"
             f"{', expected ' + dep['eta'] if dep.get('eta') else ''}.",
             [p["id"], dep.get("id"), p.get("meetingId")], "inferred", "Meetings + Roadmap", in_chain=False)
    for p in leaving:
        rel = ", ".join(p["relations"]) or "knows the account"
        step(f"{p['name']} is leaving", f"{p['name']} ({rel}) leaves on {p['lastDay']}. The account depends on {first(p['name'])}.",
             [p["id"]], "observed", "HR + Handover", in_chain=False)
    if billing.get("latestLate"):
        inv = billing["invoices"][0]
        step("Late payment", f"The customer paid the latest invoice ({inv['id']}) {inv['daysLate']} days late.", [inv["id"]],
             "observed", "Billing", in_chain=False)

    # Counter-evidence (why an account may be lower priority than it looks).
    counter = []
    fixed = [c for c in tickets.get("clusters", []) if not c["open"]]
    if fixed:
        c = fixed[0]
        k = len(c["tickets"])
        counter.append({"title": f"{c['bugId']} is fixed", "detail": f"{k} recent ticket{'s point' if k != 1 else ' points'} "
                        f"to {c['bugId']}, and that bug is fixed. Ticket status: "
                        f"{', '.join(sorted({t['status'] for t in c['tickets']}))}.",
                        "evidenceIds": [c["bugId"]] + [t["id"] for t in c["tickets"]]})
    if wau and wau["declinePct"] <= -3:
        counter.append({"title": "Usage recovered", "detail": f"Active users are {abs(wau['declinePct'])}% above the usual level.",
                        "evidenceIds": [f"usage:{acc['id']}:wau"]})
    for s in positive[:2]:
        counter.append({"title": SIGNAL_LABELS[s["type"]], "detail": f"{s['speaker']}: “{s['quote']}” ({s['date']}).",
                        "evidenceIds": [s["conversationId"], s["signalId"]]})
    if departed and departed.get("successor") and positive and not chain_successor:
        counter.append({"title": "Handover looks healthy",
                        "detail": f"{departed['successor']['name']} replaced {departed['name']} and is active and positive.",
                        "evidenceIds": [departed["successor"]["id"]]})

    # Headline + three-sentence story.
    if cluster and best:
        if chain_successor and departed:
            headline = (f"{short} is at risk because a broken {cluster['bugKeyword']} feature is hurting "
                        f"the new admin's trust.")
        else:
            headline = (f"{short} is at risk because {cluster['bugId']} ({cluster['bugKeyword']}) keeps breaking "
                        f"{cluster['feature']} for their team.")
    elif score is not None and score >= 50:
        top = [f for f in sorted(risk.get("factors", []), key=lambda f: -f["points"]) if f["points"] > 0][:2]
        top_labels = [f["label"] if f["key"] in NAMED_FACTORS else f["label"][:1].lower() + f["label"][1:] for f in top]
        headline = f"{short} is at risk: {' and '.join(top_labels)}."
    elif score is not None and score < 25 and counter:
        headline = f"{short} is at lower risk than its CRM score suggests."
    elif score is not None and score < 25:
        headline = f"{short} is at low risk. No single warning sign stands out."
    else:
        headline = f"{short} has some risk, but no single cause explains it."

    story = []
    if departed:
        succ = departed.get("successor")
        story.append(f"{departed['name']}, {company}'s main contact at {short}, left {weeks(departed['daysAgo'])} ago"
                     + (f" and {succ['name']} took over as admin." if succ else ", and nobody is recorded as taking over."))
    if cluster:
        n = len(cluster["tickets"])
        lead = cluster["reporters"][0] if cluster["reporters"] else "The team"
        if departed is None or first(lead) != first(departed["name"]):
            lead = first(lead)
        if cluster["open"]:
            span = weeks(cluster["spanDays"]) if cluster["spanDays"] >= 10 else f"{cluster['spanDays']} days"
            story.append(f"Within {span}, {lead} raised {words(n)} {cluster['bugKeyword']} ticket{'s' if n > 1 else ''} "
                         f"that {'both ' if n == 2 else ('all ' if n > 2 else '')}point{'s' if n == 1 else ''} to "
                         f"{cluster['bugId']}, still at {cluster['bugPriority']} after {weeks(cluster['bugAgeDays'])}.")
    tail = []
    if usage_metric:
        tail.append(f"{usage_metric['metric']} usage is down {usage_metric['declinePct']}%")
    elif wau and wau["declinePct"] >= 10:
        tail.append(f"active users are down {wau['declinePct']}%")
    if competitor:
        tail.append(f"{first(competitor['speaker'])} says they are looking at other tools")
    if tail:
        story.append(sentence(", ".join(tail)) + f", and renewal is in {renewal} days.")
    if score is not None and score < 25 and counter:
        story = story[:1] + [c["detail"] for c in counter[:2]]
    if not story and counter:
        story = [c["detail"] for c in counter[:3]]
    if not story:
        story = [f"No chain of evidence explains a change at {short}. Renewal is in {renewal} days."]

    caveats = ["The risk percentage is a score built from the factors shown. It is not a measured probability."]
    weak = [t for c in tickets.get("clusters", []) for t in c["tickets"] if t["confidence"] < 0.85 and c["open"]]
    for t in weak[:2]:
        caveats.append(f"{sentence(method_words(t['method']))} linked {t['id']} with confidence {t['confidence']:.2f}. "
                       f"Treat that link as likely, not certain.")
    if not best:
        caveats.append("For this account, no chain connects tickets, an open bug and a feature with falling usage.")

    numbered = [s for s in steps if s["inChain"]]
    supporting = [s for s in steps if not s["inChain"]]
    for i, s in enumerate(numbered, 1):
        s["n"] = i
    past = (mem.get("episodes") or [None])[0]
    return {
        "accountId": acc["id"], "accountName": name, "headline": headline, "story": story,
        "risk": score, "riskLabel": "risk of leaving", "crmHealthScore": acc["crmHealthScore"],
        "renewalInDays": renewal, "arr": acc["arr"], "arrLabel": inr(acc["arr"]),
        "chain": numbered, "supporting": supporting, "counterEvidence": counter, "caveats": caveats,
        "factors": risk.get("factors", []), "riskBase": risk.get("base"),
        "bugId": cluster["bugId"] if cluster and cluster["open"] else None,
        "promisesAtRisk": [{"id": p["id"], "text": p["text"], "why": p["why"], "madeBy": p["madeBy"]} for p in at_risk_promises],
        "ownersLeaving": [{"id": p["id"], "name": p["name"], "lastDay": p["lastDay"], "relations": p["relations"]} for p in leaving],
        "memory": past and {"id": past["id"], "at": past["at"], "verdict": past["verdict"], "outcome": past["outcome"]},
        "narrativeSource": "template",
    }


def validate(verdict: dict, evidence_ids: set[str]) -> list[str]:
    """Every material claim must cite evidence that exists. Returns problems (empty = ok)."""
    problems = []
    for s in verdict["chain"] + verdict["supporting"]:
        missing = [e for e in s["evidenceIds"] if e not in evidence_ids]
        if not s["evidenceIds"]:
            problems.append(f"Step '{s['title']}' has no evidence")
        elif missing:
            problems.append(f"Step '{s['title']}' cites unknown evidence {missing}")
    return problems
