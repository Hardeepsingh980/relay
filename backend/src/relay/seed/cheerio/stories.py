"""Hand-written customer stories for the Cheerio world (all fictional).

Roadmap, past customer meetings (and the promises made in them), this week's
calendar, the pre-recorded Northwind renewal call that Sales Assist replays,
product docs the live panel answers from, playbooks, and past investigation
episodes (Relay's memory).
"""

from __future__ import annotations

from datetime import datetime

from ...config import IST
from . import world

PEOPLE = {p["id"]: p for p in world.PEOPLE + world.FORMER_PEOPLE}


def at(day: str, hm: str = "10:00") -> datetime:
    return datetime.fromisoformat(f"{day}T{hm}:00").replace(tzinfo=IST)


def em(pid: str) -> str:
    return PEOPLE[pid]["email"]


def name(pid: str) -> str:
    return PEOPLE[pid]["name"]


# ---------------------------------------------------------------------------
# Roadmap (product board)
# ---------------------------------------------------------------------------

ROADMAP = [
    {"id": "RM-101", "title": "SSO (SAML) and SCIM provisioning", "feature": "Team, login & roles", "status": "delayed",
     "eta": "2027-03-31", "eta_label": "Q1 2027", "original_eta": "2026-12-15", "original_label": "December 2026",
     "owner": "p-isha", "updated": at("2026-10-09", "17:20"),
     "public_note": "Planned for Q1 2027.",
     "internal_note": "Moved from December to Q1 after IdP testing with Okta and Azure AD found session-refresh issues. Don't commit to December."},
    {"id": "RM-102", "title": "Instagram DM automation in workflows", "feature": "Workflows & chatbots", "status": "in_progress",
     "eta": "2026-11-30", "eta_label": "End of November", "original_eta": "2026-11-30", "original_label": "End of November",
     "owner": "p-varun", "updated": at("2026-10-12"), "public_note": "In beta with five brands.", "internal_note": "On track."},
    {"id": "RM-103", "title": "Voice AI nodes inside workflows", "feature": "Voice AI", "status": "planned",
     "eta": "2027-01-31", "eta_label": "January 2027", "original_eta": "2027-01-31", "original_label": "January 2027",
     "owner": "p-varun", "updated": at("2026-10-01"), "public_note": "Planned.", "internal_note": "Depends on the carrier upgrade."},
    {"id": "RM-104", "title": "Multiple transfer numbers for voice agents", "feature": "Voice AI", "status": "planned",
     "eta": "2026-12-20", "eta_label": "December 2026", "original_eta": "2026-12-20", "original_label": "December 2026",
     "owner": "p-varun", "updated": at("2026-10-05"), "public_note": "Planned for December.", "internal_note": "Ritu owns the SIP side."},
    {"id": "RM-105", "title": "Wallet low-balance alerts on WhatsApp", "feature": "Broadcast campaigns", "status": "shipped",
     "eta": "2026-09-30", "eta_label": "Shipped 30 Sep", "original_eta": "2026-09-30", "original_label": "September 2026",
     "owner": "p-isha", "updated": at("2026-09-30"), "public_note": "Live for all workspaces.", "internal_note": ""},
    {"id": "RM-106", "title": "Carousel templates via messaging-api", "feature": "Messaging API & webhooks", "status": "shipped",
     "eta": "2026-09-08", "eta_label": "Shipped 8 Sep (v3.14)", "original_eta": "2026-09-08", "original_label": "September 2026",
     "owner": "p-isha", "updated": at("2026-09-08"), "public_note": "Live in messaging-api v3.14.", "internal_note": ""},
    {"id": "RM-107", "title": "Campaign report exports v2 (async, emailed link)", "feature": "Campaign reports", "status": "planned",
     "eta": "2027-02-28", "eta_label": "February 2027", "original_eta": "2027-02-28", "original_label": "February 2027",
     "owner": "p-isha", "updated": at("2026-09-22"), "public_note": "Planned.",
     "internal_note": "Long-term fix for large exports. CHEER-2547 is the short-term fix."},
    {"id": "RM-108", "title": "RCS channel", "feature": "Broadcast campaigns", "status": "planned",
     "eta": "2027-03-31", "eta_label": "Q1 2027", "original_eta": "2027-03-31", "original_label": "Q1 2027",
     "owner": "p-naina", "updated": at("2026-09-15"), "public_note": "Planned.", "internal_note": "Carrier contracts pending."},
    {"id": "RM-109", "title": "Hindi and Hinglish replies for the AI assistant", "feature": "AI assistant", "status": "in_progress",
     "eta": "2026-11-15", "eta_label": "Mid-November", "original_eta": "2026-11-15", "original_label": "Mid-November",
     "owner": "p-varun", "updated": at("2026-10-10"), "public_note": "In progress.", "internal_note": "Rohan owns the model routing."},
    {"id": "RM-110", "title": "Agent-level delivery analytics", "feature": "Campaign reports", "status": "cut",
     "eta": None, "eta_label": "Cut from Q4", "original_eta": "2026-12-15", "original_label": "December 2026",
     "owner": "p-isha", "updated": at("2026-10-02"), "public_note": "Not planned this year.", "internal_note": "Cut for SSO."},
]


def _contact(acc: dict, role: str | None = None, champion: bool | None = None, name_: str | None = None) -> dict:
    for c in acc["contacts"]:
        if name_ and c["name"] == name_:
            return c
        if role and c["role"] == role and c["left"] is None:
            return c
        if champion is not None and c["is_champion"] == champion and not name_ and not role:
            return c
    raise KeyError((acc["name"], role, name_))


def _line(speaker: dict | str, text: str) -> dict:
    if isinstance(speaker, str):
        return {"speaker_email": em(speaker), "text": text}
    return {"speaker_email": speaker["email"], "text": text}


def _notes(overview: list[tuple[str, str]], actions: dict[str, list[str]]) -> str:
    out = ["Overview"] + [f"- **{k}:** {v}" for k, v in overview]
    if actions:
        out += ["", "Action Items"]
        for owner, items in actions.items():
            out.append(f"**{owner}**")
            out += [f"- {i}" for i in items]
    return "\n".join(out)


def build(accounts: dict[str, dict]) -> dict:
    nw = accounts["Northwind Foods"]
    ritika, aman = _contact(nw, name_="Ritika Sharma"), _contact(nw, name_="Aman Khurana")
    mohit = _contact(nw, name_="Mohit Bhalla")
    saffron = accounts["Saffron Threads"]
    saffron_ops = _contact(saffron, role="Ops Manager")
    glowra = accounts["Glowra Beauty"]
    sofia, ishani = _contact(glowra, name_="Sofia Mathew"), _contact(glowra, name_="Ishani Kulkarni")
    banyan, medora = accounts["Banyan Home"], accounts["Medora Wellness"]
    banyan_ops, medora_ops = _contact(banyan, role="Ops Manager"), _contact(medora, role="Ops Manager")
    crest = accounts["Crestline Finance"]
    tarun, rohit = _contact(crest, name_="Tarun Bajaj"), _contact(crest, name_="Rohit Menezes")
    kairo = accounts["Kairo Living"]
    sid, pooja = _contact(kairo, name_="Siddharth Kale"), _contact(kairo, name_="Pooja Natarajan")

    meetings: list[dict] = []
    promises: list[dict] = []

    def meeting(mid, title, start, account, attendees, transcript, notes_, mins=30):
        meetings.append({"id": mid, "title": title, "start": start, "kind": "customer", "account": account["name"],
                         "attendees": [a if "@" in a else em(a) for a in attendees], "duration_min": mins,
                         "transcript": transcript, "notes": notes_})

    def promise(pid, text, made_by, account, mid, made_at, due, depends=None, status="open", quote=""):
        promises.append({"id": pid, "kind": "promise", "text": text, "made_by_email": em(made_by),
                         "account": account["name"], "source_id": mid, "made_at": made_at, "due": due,
                         "depends_on": depends, "status": status, "quote": quote})

    # Northwind Q3 review: the "SSO by December" promise that is now at risk.
    mid = "mtg-cust-2026-08-21-northwind-qbr"
    meeting(mid, "Northwind Foods <> Cheerio: Q3 business review", at("2026-08-21", "16:00"), nw,
            ["p-sneha", "p-kabir", ritika["email"], mohit["email"]], [
                _line("p-sneha", "Thanks for joining. Quick recap: the abandoned-cart and COD flows recovered about ₹5.4 lakh last quarter, and delivery rates are at 96%."),
                _line(ritika, "The campaign reports are what my team lives in. Every Monday we export the weekend broadcasts and plan the week from there."),
                _line(mohit, "Good. The big ask from our side is SSO. Our agency team keeps sharing logins and our security person isn't happy."),
                _line("p-kabir", "SSO is on the roadmap for December. We'll have it for you by December, I'll make sure you're in the first batch."),
                _line(mohit, "December works. Let's revisit at renewal."),
                _line("p-sneha", "I'll also set up a refresher on the new template library for your agents."),
            ], _notes([("Results", "Cart and COD flows recovered ~₹5.4L last quarter; delivery rate 96%."),
                       ("Reports", "Growth team exports weekend broadcast reports every Monday."),
                       ("SSO", "Mohit asked for SSO for the agency team; Kabir committed to December.")],
                      {"Kabir Anand": ["Get Northwind into the first SSO batch, December (02:40)"],
                       "Sneha Bose": ["Template library refresher for Northwind's agents (03:30)"]}))
    promise("prm-northwind-sso", "SSO for Northwind's agency team by December", "p-kabir", nw, mid, at("2026-08-21", "16:12"),
            "2026-12-15", {"kind": "RoadmapItem", "id": "RM-101"},
            quote="SSO is on the roadmap for December. We'll have it for you by December")
    promise("prm-northwind-refresher", "Template library refresher for Northwind's agents", "p-sneha", nw, mid,
            at("2026-08-21", "16:20"), "2026-09-05", None, status="kept",
            quote="I'll also set up a refresher on the new template library for your agents.")

    # Saffron: a broken promise (fix "next sprint" for a bug that is still open).
    mid = "mtg-cust-2026-09-03-saffron"
    meeting(mid, "Saffron Threads <> Cheerio: monthly check-in", at("2026-09-03", "15:00"), saffron,
            ["p-rhea", saffron_ops["email"]], [
                _line(saffron_ops, "Our agents keep getting locked out. The login OTP comes after it has already expired."),
                _line("p-rhea", "Engineering has it. It'll be fixed next sprint, I'll keep you posted."),
                _line(saffron_ops, "Okay, pls do. It's slowing the team down every morning."),
            ], _notes([("Login OTP", "Agents locked out; OTP arrives after expiry.")],
                      {"Rhea Malik": ["Confirm the OTP fix ships next sprint (00:40)"]}), mins=20)
    promise("prm-saffron-otp", "Fix the login OTP issue next sprint", "p-rhea", saffron, mid, at("2026-09-03", "15:04"),
            "2026-09-24", {"kind": "Bug", "id": "CHEER-2498"}, quote="It'll be fixed next sprint, I'll keep you posted.")

    # Glowra: a promise that was kept.
    mid = "mtg-cust-2026-09-18-glowra"
    meeting(mid, "Glowra Beauty <> Cheerio: festive season planning", at("2026-09-18", "12:00"), glowra,
            ["p-kabir", "p-sneha", sofia["email"], ishani["email"]], [
                _line(sofia, "Diwali is our biggest week. Last year the weekly cap paused half our audience on day two."),
                _line("p-kabir", "We'll raise Glowra's weekly marketing cap for the Diwali sale window. Trust has a festive exception process for exactly this."),
                _line(ishani, "Great, we'll send the audience plan by Friday."),
            ], _notes([("Diwali", "Weekly cap paused half the audience last year.")],
                      {"Kabir Anand": ["Festive cap exception for the Diwali window (00:35)"]}), mins=25)
    promise("prm-glowra-cap", "Raise Glowra's weekly marketing cap for the Diwali sale", "p-kabir", glowra, mid,
            at("2026-09-18", "12:06"), "2026-10-10", None, status="kept",
            quote="We'll raise Glowra's weekly marketing cap for the Diwali sale window.")

    mid = "mtg-cust-2026-10-06-banyan"
    meeting(mid, "Banyan Home <> Cheerio: Instagram automation", at("2026-10-06", "14:00"), banyan,
            ["p-vivek", "p-neel", banyan_ops["email"]], [
                _line(banyan_ops, "Half our leads come from Instagram DMs now. Can the workflows reply there too?"),
                _line("p-neel", "Instagram DM automation is in beta. We'll have it live for you by the end of November."),
            ], _notes([("Instagram", "Banyan wants DM automation in workflows.")],
                      {"Neel Banerjee": ["Add Banyan to the Instagram DM beta (00:30)"]}), mins=20)
    promise("prm-banyan-ig", "Instagram DM automation live for Banyan by end of November", "p-neel", banyan, mid,
            at("2026-10-06", "14:05"), "2026-11-30", {"kind": "RoadmapItem", "id": "RM-102"},
            quote="We'll have it live for you by the end of November.")

    mid = "mtg-cust-2026-10-08-medora"
    meeting(mid, "Medora Wellness <> Cheerio: AI assistant review", at("2026-10-08", "11:30"), medora,
            ["p-vivek", medora_ops["email"]], [
                _line(medora_ops, "Most of our customers write in Hindi. The assistant keeps answering in English."),
                _line("p-vivek", "Hindi and Hinglish replies are being built now. You'll have them by mid-November."),
            ], _notes([("AI assistant", "Replies in English to Hindi messages.")],
                      {"Vivek Chandra": ["Share the Hindi replies beta date (00:45)"]}), mins=20)
    promise("prm-medora-hindi", "Hindi replies for the AI assistant by mid-November", "p-vivek", medora, mid,
            at("2026-10-08", "11:36"), "2026-11-15", {"kind": "RoadmapItem", "id": "RM-109"},
            quote="You'll have them by mid-November.")

    mid = "mtg-cust-2026-09-25-crestline"
    meeting(mid, "Crestline Finance <> Cheerio: EMI reminders review", at("2026-09-25", "12:00"), crest,
            ["p-jay", "p-sneha", tarun["email"], rohit["email"]], [
                _line(tarun, "Our nightly batch sometimes fails and we don't know what retries look like on your side."),
                _line("p-jay", "I'll share the webhook retry schedule doc with your team by Tuesday."),
                _line(rohit, "And overdue reminders are working well, collections are up."),
            ], _notes([("Retries", "Crestline wants the webhook retry schedule.")],
                      {"Jay Patel": ["Share the webhook retry schedule doc (00:50)"]}), mins=25)
    promise("prm-crestline-retry-doc", "Share the webhook retry schedule doc", "p-jay", crest, mid,
            at("2026-09-25", "12:08"), "2026-09-30", None, status="kept",
            quote="I'll share the webhook retry schedule doc with your team by Tuesday.")

    mid = "mtg-cust-2026-10-01-kairo"
    meeting(mid, "Kairo Living <> Cheerio: integration sync", at("2026-10-01", "10:30"), kairo,
            ["p-rahul", "p-jay", sid["email"], pooja["email"]], [
                _line(sid, "Our SHA-256 signer is now planned for early January. Can you still do the side-by-side week?"),
                _line("p-rahul", "Yes. Once your test vectors land I'll run both verifiers side by side for a week in January, then we switch off v1."),
                _line(pooja, "Perfect, I'll send the vectors as soon as security signs off."),
            ], _notes([("Signatures", "Kairo's v2 signer planned for January.")],
                      {"Rahul Verma": ["Side-by-side HMAC verification week in January (00:40)"]}), mins=30)
    promise("prm-kairo-hmac", "Side-by-side HMAC v2 verification in January", "p-rahul", kairo, mid,
            at("2026-10-01", "10:36"), "2027-01-31", {"kind": "Ticket", "id": "CHEER-2471"},
            quote="I'll run both verifiers side by side for a week in January")

    # ------------------------------------------------------------- calendar
    calendar = [
        {"id": "evt-2026-10-19-northwind", "title": "Northwind Foods <> Cheerio: renewal", "start": at("2026-10-19", "15:00"),
         "end": at("2026-10-19", "15:30"), "account": nw["name"], "kind": "renewal",
         "attendees": [em("p-sneha"), em("p-kabir"), aman["email"], mohit["email"]], "owner": em("p-sneha"),
         "recording": "call-northwind-renewal", "meet_url": "https://meet.example/nwf-rnwl-ctx"},
        {"id": "evt-2026-10-20-glowra", "title": "Glowra Beauty <> Cheerio: Diwali results", "start": at("2026-10-20", "11:00"),
         "end": at("2026-10-20", "11:30"), "account": glowra["name"], "kind": "qbr",
         "attendees": [em("p-kabir"), em("p-sneha"), sofia["email"], ishani["email"]], "owner": em("p-kabir"),
         "recording": None, "meet_url": "https://meet.example/glw-dwl-rsl"},
        {"id": "evt-2026-10-20-copperleaf", "title": "Copperleaf Tea Co. <> Cheerio: monthly check-in",
         "start": at("2026-10-20", "15:00"), "end": at("2026-10-20", "15:20"), "account": "Copperleaf Tea Co.", "kind": "check-in",
         "attendees": [accounts["Copperleaf Tea Co."]["cs_owner_email"], accounts["Copperleaf Tea Co."]["contacts"][0]["email"]],
         "owner": accounts["Copperleaf Tea Co."]["cs_owner_email"], "recording": None, "meet_url": "https://meet.example/cpl-mth-chk"},
        {"id": "evt-2026-10-21-saffron", "title": "Saffron Threads <> Cheerio: renewal check-in", "start": at("2026-10-21", "16:00"),
         "end": at("2026-10-21", "16:30"), "account": saffron["name"], "kind": "renewal",
         "attendees": [em("p-rhea"), em("p-simran"), saffron_ops["email"]], "owner": em("p-rhea"),
         "recording": None, "meet_url": "https://meet.example/sfn-rnwl-chk"},
        {"id": "evt-2026-10-22-crestline", "title": "Crestline Finance <> Cheerio: quarterly review", "start": at("2026-10-22", "12:00"),
         "end": at("2026-10-22", "12:45"), "account": crest["name"], "kind": "qbr",
         "attendees": [em("p-jay"), em("p-sneha"), tarun["email"]], "owner": em("p-sneha"),
         "recording": None, "meet_url": "https://meet.example/cst-qtr-rvw"},
        {"id": "evt-2026-10-23-kairo", "title": "Kairo Living <> Cheerio: integration sync", "start": at("2026-10-23", "10:30"),
         "end": at("2026-10-23", "11:00"), "account": kairo["name"], "kind": "sync",
         "attendees": [em("p-rahul"), em("p-jay"), sid["email"], pooja["email"]], "owner": em("p-rahul"),
         "recording": None, "meet_url": "https://meet.example/kro-int-syn"},
    ]

    # ------------------------------------------------- the pre-recorded call
    # Timestamps in seconds, spaced to the spoken length of each line (demo/tts.py). Sales Assist replays these through the same
    # pipeline a meeting bot would feed (transcript segment -> trigger -> card).
    seg = [
        (0, "p-sneha", "Hi Aman, hi Mohit, thanks for making time. Quick heads-up: this call is recorded and Cheerio's assistant takes notes for me, is that okay?"),
        (8, mohit, "Sure, go ahead."),
        (9.6, "p-sneha", "So the renewal is on 11 November. Before we talk pricing, I wanted to hear how the last quarter went for you."),
        (16.4, aman, "Campaigns are fine, the Diwali broadcast did well. But the campaign report exports keep failing. For a month now we can't download the full report for the big broadcasts."),
        (27.6, "p-sneha", "I'm sorry about that, I know you've raised it more than once."),
        (31.2, aman, "Three times. Ritika used to pull those reports every Monday, and now my team rebuilds them by hand."),
        (38.2, mohit, "The other thing for us is login. Our agency team has twelve people on the inbox. Is SSO coming in December? Kabir mentioned December last time."),
        (47.5, "p-kabir", "Let me be straight with you: SSO has moved to Q1. I don't want to promise December and miss it."),
        (53.5, mohit, "Okay. Q1 is fine if it's real. Can you put that in writing?"),
        (58.4, "p-kabir", "Yes, I'll confirm the Q1 timeline in writing this week."),
        (62.3, aman, "Also, can we send carousel templates from the API? Our developer wants to push product carousels straight from Shopify."),
        (69.8, "p-sneha", "Yes, that shipped in September. I'll send you the docs after the call."),
        (73.5, mohit, "Honestly, one of the platforms we looked at is quite a bit cheaper on the Pro plan."),
        (78.9, "p-kabir", "Understood. Can I show you the revenue attribution from your Diwali campaigns before we talk numbers? Your abandoned-cart flow alone recovered about ₹6.2 lakh last quarter."),
        (89.1, mohit, "That would help."),
        (90.3, aman, "Coming back to the exports, when will that actually be fixed?"),
        (94.2, "p-sneha", "Our engineer Dev owns that fix. I'll get you a fix date by Friday."),
        (98.3, aman, "Okay, Friday works."),
        (99.9, "p-kabir", "And on the renewal, I'll send a proposal with the Pro plan and the AI credits bundle by Wednesday."),
        (106.9, mohit, "Sounds good. Thanks, both."),
        (109.1, "p-sneha", "Thanks Aman, thanks Mohit. Talk soon."),
    ]
    calls = {"call-northwind-renewal": {
        "id": "call-northwind-renewal", "event_id": "evt-2026-10-19-northwind", "title": calendar[0]["title"],
        "account": nw["name"], "started_at": calendar[0]["start"], "duration_s": 113, "consent": True,
        "source": "Pre-recorded call replayed through the meeting-bot pipeline",
        "segments": [{"t": t, "speaker_email": sp if isinstance(sp, str) and "@" in sp else (em(sp) if isinstance(sp, str) else sp["email"]),
                      "speaker_name": name(sp) if isinstance(sp, str) else sp["name"], "text": tx} for t, sp, tx in seg],
    }}

    # ------------------------------------------------------- product docs
    docs = [
        {"id": "DOC-2001", "title": "Release notes: September 2026", "space": "PROD", "kind": "release-notes",
         "author": "p-isha", "created": at("2026-09-30", "18:00"), "updated": at("2026-09-30", "18:00"),
         "labels": [], "customers": [],
         "body": """# Release notes: September 2026

- **Carousel templates via messaging-api** (v3.14, 8 Sep): send product carousels of up to 10 cards from the API. Shopify product variables work in every card. Docs: /docs/api/carousel-templates.
- **Workflows: wait-for-reply node** (15 Sep): pause a workflow until the customer answers, with a timeout branch.
- **Inbox: snooze conversations** (22 Sep): hide a chat until a time you pick; it comes back assigned to the same agent.
- **Wallet low-balance alerts on WhatsApp** (30 Sep): admins get a WhatsApp alert when the wallet drops below a threshold they set."""},
        {"id": "DOC-2002", "title": "Product FAQ for CS (Q4 2026)", "space": "CS", "kind": "faq",
         "author": "p-arnav", "created": at("2026-09-02"), "updated": at("2026-10-12", "12:30"),
         "labels": [], "customers": [],
         "body": """# Product FAQ for CS (Q4 2026)

**Is SSO available?** Not yet. SSO (SAML) and SCIM provisioning are planned for Q1 2027; they moved from December after IdP testing. Don't commit to December. Say Q1 and offer to confirm the timeline in writing. Owner: Isha Chawla.

**Can customers send carousel templates from the API?** Yes, since messaging-api v3.14 (8 Sep). Docs: /docs/api/carousel-templates.

**Large campaign report exports fail.** Known issue CHEER-2547 for broadcasts over 50k recipients. Workaround: export one day of sends at a time. Owner: Dev Malhotra.

**How many transfer numbers can a voice agent have?** One today. Multiple transfer numbers are planned for December (RM-104).

**Can the AI assistant reply in Hindi?** Hindi and Hinglish replies are in progress for mid-November (RM-109).

**Is there Instagram DM automation?** In beta, generally available at the end of November (RM-102)."""},
        {"id": "DOC-2003", "title": "Battlecard: price objections vs cheaper WhatsApp tools", "space": "SALES", "kind": "playbook",
         "author": "p-kabir", "created": at("2026-06-10"), "updated": at("2026-09-28", "16:00"),
         "labels": [], "customers": [],
         "body": """# Battlecard: price objections vs cheaper WhatsApp tools

From the deals we won this year:
1. Show attributed revenue before talking price. Cart and COD flows usually recover 8–12% of abandoned carts; put the rupee number on screen.
2. Don't discount the plan. Bundle AI assistant credits for two months instead.
3. Point at delivery support: a named CSM and weekend on-call, with RCAs for every incident.
4. If they compare per-message prices, compare per-conversation cost including failed sends and refunds."""},
        {"id": "DOC-2004", "title": "Save playbook: champion left and a product issue", "space": "CS", "kind": "playbook",
         "author": "p-arnav", "created": at("2026-05-14"), "updated": at("2026-08-30", "11:00"),
         "labels": [], "customers": [],
         "body": """# Save playbook: champion left and a product issue

What worked on the accounts we saved this year:
1. Exec sponsor call within 7 days, run by the CSM with the Head of CS.
2. A fix date from the bug owner, in writing, before the call.
3. Admin re-onboarding for the successor (60 minutes, their own data).
4. Service credit for the weeks the issue blocked them, approved by Finance.

When a promised feature slips: tell the customer before they ask, give the new quarter rather than a date you can't hold, and confirm it in writing."""},
        {"id": "DOC-2005", "title": "Pricing and plans (2026)", "space": "SALES", "kind": "policy",
         "author": "p-naina", "created": at("2026-01-05"), "updated": at("2026-07-01", "10:00"),
         "labels": [], "customers": [],
         "body": """# Pricing and plans (2026)

Plans: Startup, Growth, Pro and Enterprise, billed monthly, quarterly, half-yearly or annually. Prices are ex-GST (18%).
Agent seats: ₹1,500 per user per month on Pro. Message credits are prepaid into the wallet and billed at Meta's rate plus our margin.
Pro includes AI assistant credits; Enterprise adds SSO (when available), a named CSM and custom integrations."""},
        {"id": "DOC-2006", "title": "Renewal process", "space": "CS", "kind": "policy",
         "author": "p-arnav", "created": at("2025-11-10"), "updated": at("2026-06-15", "10:00"),
         "labels": [], "customers": [],
         "body": """# Renewal process

CS owns renewals. The window opens 45 days before plan end for annual plans (30 days for quarterly).
Stages: Not started, Follow-up sent, No response, In conversation, Meeting booked, Negotiating, Invoice raised, Payment pending, Renewed.
An account is Lapsed 30 days after plan end. Every promise made on a renewal call goes into the account notes the same day."""},
    ]

    # ----------------------------------------------- procedural memory
    healthy = [a["name"] for a in accounts.values() if not a["planted"] and a["crm_health_score"] >= 84][:6]
    playbooks = [
        {"id": "pb-champion-bug", "kind": "playbook", "name": "Champion left + product issue",
         "trigger": "champion_departed+unresolved_bug_tickets", "source_id": "DOC-2004",
         "steps": ["Exec sponsor call within 7 days", "Fix date from the bug owner, in writing", "Admin re-onboarding for the successor",
                   "Service credit for the blocked weeks"],
         "worked_for": healthy[:3], "outcome": "3 of 4 saves renewed in 2026"},
        {"id": "pb-price-objection", "kind": "playbook", "name": "Price objection vs cheaper tools",
         "trigger": "competitor_signal", "source_id": "DOC-2003",
         "steps": ["Show attributed revenue before price", "Bundle AI credits instead of discounting",
                   "Compare per-conversation cost including failed sends"],
         "worked_for": healthy[3:5], "outcome": "Won 2 of 3 competitive renewals"},
        {"id": "pb-roadmap-slip", "kind": "playbook", "name": "Promised feature slipped",
         "trigger": "promise_at_risk", "source_id": "DOC-2004",
         "steps": ["Tell the customer before they ask", "Give the new quarter, not a date you can't hold",
                   "Confirm in writing", "PM joins the next call"],
         "worked_for": healthy[5:6], "outcome": "Kept the renewal on schedule"},
    ]

    # --------------------------------------------- episodic memory (past)
    episodes = [
        {"id": "ep-2026-09-19-pearl", "kind": "investigation", "account": "Pearl Dental Clinics", "at": at("2026-09-19", "11:40"),
         "actor": em("p-arnav"), "risk": 58,
         "verdict": "Risk came from the triple-send bug CHEER-2469: four tickets in three weeks and campaign usage down 60%. The fix was in progress.",
         "outcome": "Service credit approved; usage back above baseline after the fix shipped on 28 Sep."},
        {"id": "ep-2026-09-09-bluebird", "kind": "investigation", "account": "Bluebird Bakehouse", "at": at("2026-09-09", "15:10"),
         "actor": em("p-rhea"), "risk": 31,
         "verdict": "The owner left, but the new GM Felix Ward is engaged and usage is recovering.",
         "outcome": "No action needed; checked in after 30 days."},
    ]

    return {"roadmap": [{**{k: v for k, v in r.items() if k != "owner"}, "owner_email": em(r["owner"])} for r in ROADMAP],
            "meetings": meetings, "promises": promises, "calendar": calendar, "calls": calls,
            "docs": [{**d, "author_email": em(d.pop("author"))} for d in docs],
            "playbooks": playbooks, "episodes": episodes}
