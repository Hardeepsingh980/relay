"""Cheerio's customer portfolio: CRM, support desk, product bugs, usage, billing and conversations.

Deterministic (fixed seed) and relative to the demo date, so "renewal in 23 days"
always reads the same. Everything here is fictional.

Hand-planted stories:
  * Northwind Foods (the hero): HubSpot health 82, but the champion left, three
    differently worded tickets map to bug CHEER-2547, campaign-report usage is
    down 70%, the new admin mentioned evaluating other tools, and a promise made
    at the Q3 review ("SSO by December") now depends on a roadmap item that moved
    to Q1. Rahul Verma (leaving Friday) is their technical contact.
  * Saffron Threads, Banyan Home, Medora Wellness: other "silent risk" accounts
    (CRM healthy, graph risky) renewing this quarter.
  * Harbor & Pine Candles, Mitti Organics, Copperleaf Tea Co., Kesar Kitchen: the
    other accounts hit by CHEER-2547 (the bug's blast radius).
  * Pearl Dental Clinics, Bluebird Bakehouse: decoys that look risky in the CRM
    but have counter-evidence (bug fixed, usage recovered, engaged successor).
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from ...config import DEMO_NOW, IST
from ...health.model import BASELINE_WEEKS, CURRENT_WEEKS, N_WEEKS
from . import catalog, stories, world

SEED = 412
N_ACCOUNTS = 120
AS_OF = DEMO_NOW.date()
RESERVED_TICKETS = {"SUP-20417", "SUP-20502", "SUP-20588"}
PEOPLE = {p["id"]: p for p in world.PEOPLE + world.FORMER_PEOPLE}
CSMS = ["p-sneha", "p-rhea", "p-vivek"]
AES = ["p-kabir", "p-simran", "p-neel"]
SUPPORT = "p-riya"
CAST_FIRST = {p["name"].split()[0] for p in world.PEOPLE + world.FORMER_PEOPLE}


def email(pid: str) -> str:
    return PEOPLE[pid]["email"]


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def plan_for(arr: int) -> str:
    return "Enterprise" if arr >= 1_000_000 else "Pro" if arr >= 400_000 else "Growth" if arr >= 90_000 else "Startup"


def stage_for(renewal_in: int, rng: random.Random) -> str:
    if renewal_in > 45:
        return "Not started"
    if renewal_in > 30:
        return rng.choice(["Follow-up sent", "No response", "Not started"])
    return rng.choice(["In conversation", "Meeting booked", "Negotiating", "Invoice raised"])


@dataclass
class Portfolio:
    accounts: list[dict] = field(default_factory=list)
    tickets: list[dict] = field(default_factory=list)
    bugs: list[dict] = field(default_factory=list)
    usage: list[dict] = field(default_factory=list)
    invoices: list[dict] = field(default_factory=list)
    wallets: list[dict] = field(default_factory=list)
    conversations: list[dict] = field(default_factory=list)
    features: list[dict] = field(default_factory=list)


class Builder:
    def __init__(self) -> None:
        self.rng = random.Random(SEED)
        self.p = Portfolio()
        self.ticket_seq = 18000
        self.conv_seq = 5000
        self.used_names: set[str] = {c["name"] for c in world.CONTACTS}
        self.bugs: dict[str, dict] = {}
        self.bugs_by_feature: dict[str, list[dict]] = {}
        self.open_bug_arr: dict[str, set[str]] = {}
        self.arr: dict[str, int] = {}
        self.acc: dict[str, dict] = {}

    # ---------- helpers ----------
    def day(self, offset: int, hour: int = 11, minute: int = 0) -> datetime:
        d = AS_OF + timedelta(days=offset)
        return datetime(d.year, d.month, d.day, hour, minute, tzinfo=IST)

    def iso_day(self, offset: int) -> str:
        return (AS_OF + timedelta(days=offset)).isoformat()

    def week_start(self, idx: int) -> date:
        last = AS_OF - timedelta(days=7)
        last = last - timedelta(days=last.weekday())
        return last - timedelta(weeks=(N_WEEKS - 1 - idx))

    def person_name(self, country: str) -> str:
        first, last = (catalog.IN_FIRST, catalog.IN_LAST) if country == "IN" else (catalog.US_FIRST, catalog.US_LAST)
        while True:
            name = f"{self.rng.choice(first)} {self.rng.choice(last)}"
            if name not in self.used_names and name.split()[0] not in CAST_FIRST:
                self.used_names.add(name)
                return name

    def next_ticket_id(self) -> str:
        self.ticket_seq += self.rng.randint(1, 3)
        while f"SUP-{self.ticket_seq}" in RESERVED_TICKETS:
            self.ticket_seq += 1
        return f"SUP-{self.ticket_seq}"

    def next_conv_id(self) -> str:
        self.conv_seq += 1
        return f"CNV-{self.conv_seq}"

    # ---------- catalog ----------
    def features(self) -> None:
        for fid, name, owner, systems, _ in catalog.FEATURES:
            self.p.features.append({"id": fid, "name": name, "owner_email": email(owner), "systems": systems})

    def add_bug(self, key: str | None, feature: str, title: str, keyword: str, created: int, status: str,
                priority: str, fixed: int | None = None, description: str = "", symptoms: list[str] | None = None,
                planted: bool = False, workaround: str | None = None, jira_status: str | None = None) -> dict:
        resolved = self.day(fixed, 17, 30) if fixed is not None else None
        bug = {
            "key": key, "summary": title, "status": status, "jira_status": jira_status,
            "assignee_email": email(catalog.FEATURE_OWNER[feature]), "reporter_email": email(SUPPORT),
            "components": [], "customer": None, "labels": ["customer-reported"],
            "created": self.day(created, 12), "updated": resolved or self.day(min(-1, created + 3), 12),
            "resolved": resolved, "description": description or title, "comments": [],
            "issuetype": "Bug", "priority": priority, "feature": catalog.FEATURE_NAME[feature],
            "keyword": keyword, "workaround": workaround,
            "_feature": feature, "_symptoms": symptoms or [], "_planted": planted,
        }
        if status == "Done":
            bug["comments"].append({"author_email": bug["assignee_email"], "created": resolved,
                                    "body": "Fix is On Prod. CS pls confirm with the customers who reported it."})
        self.p.bugs.append(bug)
        if key:
            self.bugs[key] = bug
        if not planted:
            self.bugs_by_feature.setdefault(feature, []).append(bug)
        return bug

    def bugs_catalog(self) -> None:
        # Planted bugs first (fixed keys referenced by the stories).
        self.add_bug("CHEER-2547", "F-REPORTS", "Campaign report CSV export times out for broadcasts over 50k recipients",
                     "export", -36, "To Do", "P3", jira_status="BUGS",
                     description="Large CSV exports from Campaign reports time out after 60s and return an empty file "
                                 "(header row only) or no download. Reproducible above ~50,000 recipients.",
                     workaround="Exporting one day of sends at a time completes normally.", planted=True)
        self.add_bug("CHEER-2498", "F-ACCESS", "Login OTP not delivered for users on email OTP", "login OTP", -48,
                     "In Progress", "P2", jira_status="In Progress", planted=True,
                     description="Email OTP for agent login is queued behind marketing email and arrives after it expires.")
        self.add_bug("CHEER-2505", "F-SHOPIFY", "COD confirmation not sent for orders with discount codes",
                     "COD confirmation", -64, "To Do", "P3", jira_status="Sprint Items", planted=True,
                     description="Shopify orders with a discount code skip the COD-confirmation trigger.")
        self.add_bug("CHEER-2561", "F-INBOX", "Same customer number appears as two conversations in inbox",
                     "duplicate conversations", -40, "In Progress", "P2", jira_status="ON STAGE", planted=True,
                     description="Numbers saved with and without +91 open separate conversations; agents reply twice.")
        self.add_bug("CHEER-2469", "F-CAMPAIGNS", "Broadcast sent three times after a send retry", "triple send", -70,
                     "Done", "P2", fixed=-21, jira_status="On Prod", planted=True)

        # Background bugs: each template once (old, fixed), plus later regressions for most.
        for feature, templates in catalog.BUG_TEMPLATES.items():
            for title, keyword, symptoms in templates:
                created = -self.rng.randint(120, 178)
                self.add_bug(None, feature, title, keyword, created, "Done", self.rng.choice(["P2", "P3", "P3", "P4"]),
                             fixed=created + self.rng.randint(6, 40), symptoms=symptoms)
        for feature, templates in catalog.BUG_TEMPLATES.items():
            for title, keyword, symptoms in templates:
                if self.rng.random() < 0.1:
                    continue
                created = -self.rng.randint(15, 110)
                is_open = self.rng.random() < 0.38
                fixed = None if is_open else min(-1, created + self.rng.randint(5, 35))
                self.add_bug(None, feature, f"Regression: {title}", keyword, created,
                             self.rng.choice(["To Do", "In Progress"]) if is_open else "Done",
                             self.rng.choice(["P2", "P3", "P4"]), fixed=fixed, symptoms=symptoms)

    # ---------- accounts ----------
    def account(self, key: str, name: str, industry: str, arr: int, renewal_in: int, crm: int, features: list[str],
                csm: str, ae: str, planted: str = "", country: str = "IN", seats: int | None = None,
                world_rec: dict | None = None, wallet: int | None = None, stage: str | None = None) -> dict:
        seats = seats or max(2, int(arr / self.rng.uniform(25000, 45000)))
        domain = f"{slug(name)}.example"
        rec = {
            "name": name, "aliases": world_rec["aliases"] if world_rec else [], "industry": industry,
            "country": country, "domain": domain, "plan": world_rec["tier"] if world_rec else plan_for(arr),
            "arr": arr, "mrr": round(arr / 12), "seats": seats, "billing_term": self.rng.choice(["Annual", "Annual", "Half-yearly", "Quarterly"]),
            "renewal_date": self.iso_day(renewal_in), "crm_health_score": crm,
            "crm_health_source": "HubSpot health (logins, NPS, seat utilisation)",
            "renewal_stage": stage or stage_for(renewal_in, self.rng), "lifecycle": "active",
            "cs_owner_email": email(csm), "sales_poc_email": email(ae),
            "integration_owner_email": email(world_rec["integrationOwner"]) if world_rec else None,
            "technical_contact_email": email(world_rec["technicalContact"]) if world_rec and world_rec.get("technicalContact") else None,
            "summary": world_rec["summary"] if world_rec else f"{industry} brand on Cheerio since {self.iso_day(-self.rng.randint(200, 900))[:7]}.",
            "features": [catalog.FEATURE_NAME[f] for f in features], "planted": planted, "contacts": [],
            "_key": key, "_features": features,
        }
        self.p.accounts.append(rec)
        self.acc[key] = rec
        self.arr[key] = arr
        bal = wallet if wallet is not None else int(round(max(6000, arr / 12 * self.rng.uniform(0.15, 0.6)), -2))
        self.p.wallets.append({"account": name, "balance": bal, "currency": "INR",
                               "last_topup_at": self.day(-self.rng.randint(3, 25)), "last_topup_amount": int(round(arr / 12 * 0.5, -3))})
        return rec

    def contact(self, acc: dict, name: str, role: str, title: str, champion: bool = False, joined: int = -700,
                left: int | None = None, bounced: bool = False, successor_of: str | None = None) -> dict:
        first, last = name.split(" ", 1)
        c = {"name": name, "email": f"{slug(first)}.{slug(last)}@{acc['domain']}", "role": role, "title": title,
             "is_champion": champion, "joined": self.iso_day(joined), "left": self.iso_day(left) if left is not None else None,
             "email_status": "bouncing" if bounced else "ok",
             "email_bounced_at": self.iso_day(left + 3) if (bounced and left is not None) else None,
             "successor_of": successor_of}
        acc["contacts"].append(c)
        return c

    def ticket(self, acc: dict, contact: dict, created: int, title: str, body: str, status: str, feature: str,
               bug: dict | None = None, confidence: float = 0.0, method: str = "support-triage",
               priority: str = "normal", tid: str | None = None) -> dict:
        t = {"id": tid or self.next_ticket_id(), "account": acc["name"], "requester_email": contact["email"],
             "subject": title, "body": body, "created": self.day(created, self.rng.randint(9, 19), self.rng.randrange(60)),
             "status": status, "priority": priority, "feature": catalog.FEATURE_NAME[feature],
             "channel": self.rng.choice(["email", "WhatsApp", "in-app chat"]),
             "assignee_email": email(SUPPORT) if self.rng.random() < 0.7 else acc["cs_owner_email"], "linked_bug": None}
        if bug is not None:
            t["linked_bug"] = {"key": bug["key"], "_bug": bug, "confidence": round(confidence, 2), "method": method,
                               "linked_at": self.iso_day(created + self.rng.randint(0, 2)),
                               "linked_by": "Support agent" if method == "support-triage" else "Auto-triage classifier v3"}
        self.p.tickets.append(t)
        return t

    def conversation(self, acc: dict, contact: dict, when: int, channel: str, text: str, internal: str | None = None,
                     summary: str = "") -> dict:
        c = {"id": self.next_conv_id(), "account": acc["name"], "channel": channel,
             "occurred_at": self.day(when, self.rng.randint(10, 18)), "contact_email": contact["email"],
             "internal_email": email(internal) if internal else acc["cs_owner_email"],
             "text": text, "summary": summary or text[:90]}
        self.p.conversations.append(c)
        return c

    def invoices(self, acc: dict, lateness: list[int]) -> None:
        """Quarterly invoices, oldest first. `lateness` = days paid after due date per invoice."""
        latest_issue = -self.rng.randint(40, 60)
        n = len(lateness)
        for i, late in enumerate(lateness):
            issued = latest_issue - 91 * (n - 1 - i)
            due = issued + 15
            paid = due + late
            self.p.invoices.append({
                "id": f"INV-{slug(acc['name'])[:6].upper()}-{i + 1:02d}", "account": acc["name"],
                "issued": self.iso_day(issued), "due": self.iso_day(due),
                "paid": self.iso_day(paid) if paid <= 0 else None,
                "days_late": max(0, late) if paid <= 0 else None,
                "amount": round(acc["arr"] / 4 * 1.18), "amount_ex_gst": round(acc["arr"] / 4),
                "status": "paid" if paid <= 0 else "open", "source": "Billing (GST invoices)"})

    def usage(self, acc: dict, features: list[str], wau_base: float, wau_curve,
              feature_curves: dict | None = None, drop_weeks: set[int] | None = None,
              exact: dict[str, tuple[float, float]] | None = None) -> None:
        """Weekly usage series. `exact` pins window means: metric -> (baseline_mean, current_mean)."""
        feature_curves = feature_curves or {}
        exact = exact or {}
        series: dict[str, list[float]] = {"active_users": [wau_base * wau_curve(i) * self.rng.uniform(0.96, 1.04)
                                                           for i in range(N_WEEKS)]}
        for f in features:
            share = self.rng.uniform(0.7, 1.15)
            curve = feature_curves.get(f, wau_curve)
            series[f] = [wau_base * curve(i) * catalog.FEATURE_RATE[f] * share * self.rng.uniform(0.94, 1.06)
                         for i in range(N_WEEKS)]
        for metric, (b_mean, c_mean) in exact.items():
            s = series[metric]
            for (lo, hi), target in ((BASELINE_WEEKS, b_mean), (CURRENT_WEEKS, c_mean)):
                idx = range(lo, hi + 1)
                vals = [round(s[i]) for i in idx]
                vals[-1] += round(target * len(vals)) - sum(vals)  # make the window mean exact
                for i, v in zip(idx, vals):
                    s[i] = v
        for metric, values in series.items():
            for i, v in enumerate(values):
                if drop_weeks and i in drop_weeks:
                    continue  # missing week in the source data: leave a gap, never interpolate
                self.p.usage.append({"account": acc["name"], "week": self.week_start(i).isoformat(), "week_index": i,
                                     "metric": "active_users" if metric == "active_users" else "feature_events",
                                     "feature": None if metric == "active_users" else catalog.FEATURE_NAME[metric],
                                     "value": int(round(v))})

    # ---------- background ----------
    def background_account(self, idx: int, name: str, industry: str, country: str) -> None:
        rng = self.rng
        profile = rng.choices(["healthy", "drifting", "at_risk"], weights=[72, 18, 10])[0]
        arr = int(round(min(600000, max(40000, rng.lognormvariate(11.98, 0.62))), -3))
        crm = {"healthy": rng.randint(68, 92), "drifting": rng.randint(58, 80), "at_risk": rng.randint(30, 58)}[profile]
        others = [f for f, *_ in catalog.FEATURES if f not in catalog.CORE_FEATURES]
        features = list(catalog.CORE_FEATURES) + rng.sample(others, rng.randint(2, 5))
        wallet = rng.randint(1200, 4800) if (profile == "at_risk" and rng.random() < 0.35) else None
        acc = self.account(f"bg{idx:03d}", name, industry, arr, rng.randint(5, 365), crm, features,
                           rng.choice(CSMS), rng.choice(AES), country=country, wallet=wallet)

        champion_left = profile == "at_risk" and rng.random() < 0.5
        champ = self.contact(acc, self.person_name(country), "Admin", rng.choice(["Founder", "Head of Growth", "CRM Manager"]),
                             champion=True, joined=-rng.randint(300, 1200),
                             left=-rng.randint(20, 85) if champion_left else None, bounced=champion_left)
        people = [champ]
        for _ in range(rng.randint(2, 4)):
            role = rng.choice(catalog.CONTACT_ROLES)
            left = -rng.randint(10, 170) if rng.random() < 0.06 else None
            people.append(self.contact(acc, self.person_name(country), role, role, joined=-rng.randint(100, 1000), left=left))
        if champion_left:
            people[1]["successor_of"] = champ["email"]

        decline = {"healthy": rng.uniform(-0.08, 0.08), "drifting": rng.uniform(0.08, 0.25),
                   "at_risk": rng.uniform(0.3, 0.55)}[profile]
        start = rng.randint(17, 21)

        def curve(i: int, d=decline, s=start) -> float:
            return 1.0 if i < s else 1.0 - d * min(1.0, (i - s + 1) / 3)

        drop = {rng.randint(3, 10)} if rng.random() < 0.04 else None
        self.usage(acc, features, acc["seats"] * rng.uniform(0.5, 0.8), curve, drop_weeks=drop)

        late_last = rng.randint(8, 25) if (profile == "at_risk" and rng.random() < 0.4) else rng.randint(-6, 4)
        self.invoices(acc, [rng.randint(-6, 3), rng.randint(-6, 5), late_last])

        active = [p for p in people if p["left"] is None] or people
        for _ in range(rng.randint(5, 14)):
            created = -rng.randint(2, 178)
            raiser = rng.choice(active)
            feature = rng.choice(features)
            bug = self._pick_background_bug(feature, created, acc)
            if bug is not None and rng.random() < 0.6:
                subject = rng.choice(bug["_symptoms"])
                if bug["status"] == "Done" and bug["resolved"] and bug["resolved"].date() < AS_OF:
                    status = "solved"
                else:
                    status = rng.choice(["open", "pending"])
                method = "support-triage" if rng.random() < 0.7 else "auto-triage"
                conf = rng.uniform(0.86, 0.99) if method == "support-triage" else rng.uniform(0.62, 0.95)
                self.ticket(acc, raiser, created, subject, self._ticket_body(subject, feature), status, feature, bug, conf, method)
                if bug["status"] != "Done":
                    self.open_bug_arr.setdefault(id(bug), set()).add(acc["_key"])
            else:
                subject = rng.choice(catalog.HOWTO_TICKETS[feature])
                self.ticket(acc, raiser, created, subject, self._ticket_body(subject, feature),
                            "solved" if created < -5 else "open", feature, priority="low")

        tones = {"healthy": ["positive", "neutral", "neutral"],
                 "drifting": ["neutral", "neutral", "frustrated", "positive"],
                 "at_risk": ["frustrated", "competitor", "budget", "neutral"]}[profile]
        for _ in range(rng.randint(2, 5)):
            tone = rng.choice(tones)
            text = rng.choice(catalog.CONVERSATION_SNIPPETS[tone])
            speaker = rng.choice(active)
            self.conversation(acc, speaker, -rng.randint(1, 178), rng.choice(["Call notes", "WhatsApp group", "Email"]),
                              f"{speaker['name'].split()[0]}: {text}")

    def _pick_background_bug(self, feature: str, created: int, acc: dict) -> dict | None:
        when = self.day(created)
        candidates = []
        for bug in self.bugs_by_feature.get(feature, []):
            b_fixed = bug["resolved"]
            if bug["created"] <= when and (b_fixed is None or when <= b_fixed + timedelta(days=3)):
                if bug["status"] != "Done":
                    accounts = self.open_bug_arr.get(id(bug), set()) | {acc["_key"]}
                    # Keep any single background bug's footprint well below CHEER-2547's.
                    if sum(self.arr[a] for a in accounts) > 1_200_000:
                        continue
                candidates.append(bug)
        return self.rng.choice(candidates) if candidates else None

    def _ticket_body(self, subject: str, feature: str) -> str:
        return (f"{self.rng.choice(catalog.TICKET_BODY_OPENERS)} {subject.rstrip('?.')} in "
                f"{catalog.FEATURE_NAME[feature]}. {self.rng.choice(catalog.TICKET_BODY_CLOSERS)}")

    def _older_history(self, acc: dict, contact: dict, features: list[str], n: int, before: int) -> None:
        """Older, resolved tickets so planted accounts look like real customers."""
        for _ in range(n):
            created = -self.rng.randint(-before, 175)
            feature = self.rng.choice(features)
            subject = self.rng.choice(catalog.HOWTO_TICKETS[feature])
            self.ticket(acc, contact, created, subject, self._ticket_body(subject, feature), "solved", feature, priority="low")

    # ---------- planted stories ----------
    def planted(self) -> None:
        self._northwind()
        self._world_accounts()
        self._bug_blast_radius()
        self._saffron()
        self._banyan()
        self._medora()
        self._pearl()
        self._bluebird()

    def _northwind(self) -> None:
        feats = ["F-CAMPAIGNS", "F-TEMPLATES", "F-INBOX", "F-REPORTS", "F-SHOPIFY", "F-WORKFLOWS"]
        wrec = next(c for c in world.CUSTOMERS if c["id"] == "cust-northwind")
        acc = self.account("northwind", "Northwind Foods", "Food & beverage", 960000, 23, 82, feats, "p-sneha", "p-kabir",
                           planted="hero", seats=56, world_rec=wrec, wallet=38400, stage="Meeting booked")
        ritika = self.contact(acc, "Ritika Sharma", "Admin", "Head of Retention", champion=True, joined=-910, left=-42, bounced=True)
        aman = self.contact(acc, "Aman Khurana", "Admin", "Growth Manager", joined=-300, successor_of=ritika["email"])
        self.contact(acc, "Farzana Sheikh", "Finance Manager", "Finance Manager", joined=-640)
        self.contact(acc, "Mohit Bhalla", "Founder", "Co-founder & CEO", joined=-1100)
        self.used_names.update({"Ritika Sharma", "Aman Khurana", "Farzana Sheikh", "Mohit Bhalla"})
        self._older_history(acc, ritika, feats, 6, before=-60)

        bug = self.bugs["CHEER-2547"]
        self.ticket(acc, aman, -30, "Campaign report export broken",
                    "Hi team, the CSV export of our Diwali broadcast report is broken. It starts, then nothing "
                    "downloads. Ritika used to handle reports so not sure if some setting changed. Pls check. - Aman",
                    "open", "F-REPORTS", bug, 0.94, "support-triage", "high", tid="SUP-20417")
        self.ticket(acc, aman, -24, "Download not working",
                    "Hello, still can't download the campaign report as CSV. One day of sends works but the full "
                    "broadcast doesn't. This is blocking our month-end review.",
                    "pending", "F-REPORTS", bug, 0.91, "support-triage", "high", tid="SUP-20502")
        self.ticket(acc, aman, -17, "Report comes out empty",
                    "Hi, the export finally finished but the file is empty, just the header row. We need this for "
                    "the investor update on Friday. Any update would help.",
                    "open", "F-REPORTS", bug, 0.83, "auto-triage", "high", tid="SUP-20588")

        def wau(i: int) -> float:
            return 1.0 if i < 20 else (0.85 if i == 20 else (0.75 if i == 21 else 0.68))

        def reports(i: int) -> float:
            return 1.0 if i < 20 else (0.7 if i == 20 else (0.45 if i == 21 else 0.3))

        self.usage(acc, feats, 50, wau, {"F-REPORTS": reports, "F-INBOX": lambda i: 1.0 if i < 21 else 0.9},
                   exact={"active_users": (50, 34), "F-REPORTS": (420, 126)})
        self.invoices(acc, [-2, 0, 4])
        self.conversation(acc, ritika, -120, "Call notes",
                          "Ritika: The weekly campaign report export is part of our Monday review now, the whole growth "
                          "team works from it.", summary="Quarterly check-in with Ritika")
        self.conversation(acc, aman, -38, "Email",
                          "Aman: Hi Sneha, I've taken over as Cheerio admin now that Ritika has moved on. "
                          "Could you send me the admin onboarding guide?", summary="Aman introduces himself as the new admin")
        self.conversation(acc, aman, -9, "Call notes",
                          "Check-in call with Aman. Aman: Honestly the exports have been a headache since Ritika left, "
                          "and we're evaluating a couple of other tools before the renewal. Asked for a timeline on the "
                          "CSV export fix.", summary="Renewal check-in with Aman")

    def _world_accounts(self) -> None:
        """Commercial profiles for the other three integration-heavy accounts (healthy on paper and in the graph)."""
        specs = [
            ("kairo", "cust-kairo", "Home & decor", 2400000, 160, 72, ["F-CAMPAIGNS", "F-TEMPLATES", "F-INBOX", "F-API", "F-REPORTS"],
             "p-arnav", "p-kabir", [("Shalini Gokhale", "Admin", "Head of Customer Experience", True)], 180000),
            ("glowra", "cust-glowra", "Beauty & personal care", 720000, 120, 81,
             ["F-CAMPAIGNS", "F-TEMPLATES", "F-INBOX", "F-SHOPIFY", "F-REPORTS", "F-AI"],
             "p-sneha", "p-kabir", [("Ishani Kulkarni", "Admin", "CRM Lead", True)], 52000),
            ("crestline", "cust-crestline", "Lending & BFSI", 1200000, 200, 76, ["F-CAMPAIGNS", "F-TEMPLATES", "F-INBOX", "F-API", "F-VOICE"],
             "p-sneha", "p-simran", [("Rohit Menezes", "Admin", "Head of Collections", True)], 96000),
        ]
        for key, wid, industry, arr, renewal, crm, feats, csm, ae, extra, wallet in specs:
            wrec = next(c for c in world.CUSTOMERS if c["id"] == wid)
            acc = self.account(key, wrec["name"], industry, arr, renewal, crm, feats, csm, ae, planted="integration",
                               world_rec=wrec, wallet=wallet)
            for c in world.CONTACTS:
                if c["customer"] == wid:
                    self.contact(acc, c["name"], c["role"], c["role"], joined=-600)
            admin = None
            for name, role, title, champ in extra:
                self.used_names.add(name)
                admin = self.contact(acc, name, role, title, champion=champ, joined=-700)
            self._older_history(acc, admin, feats, 5, before=-30)
            self.usage(acc, feats, acc["seats"] * 0.7, lambda i: 1.0)
            self.invoices(acc, [0, -2, 1])
            if key == "glowra":
                self.conversation(acc, admin, -15, "WhatsApp group",
                                  "Ishani: The Diwali broadcast did really well, really happy with it.", internal="p-kabir")
            else:
                self.conversation(acc, admin, -self.rng.randint(15, 40), "Email",
                                  f"{admin['name'].split()[0]}: Could you share the release notes for the latest update?")

    def _bug_blast_radius(self) -> None:
        bug = self.bugs["CHEER-2547"]
        specs = [
            ("harborpine", "Harbor & Pine Candles", "Home & decor", "US", 480000, 140, 76,
             [(-37, "CSV export times out on big campaigns"), (-12, "Export only works one day at a time")]),
            ("mitti", "Mitti Organics", "Food & beverage", "IN", 420000, 201, 71, [(-20, "Can't export the full festive campaign")]),
            ("copperleaf", "Copperleaf Tea Co.", "Food & beverage", "IN", 360000, 95, 84,
             [(-15, "Export file is blank"), (-6, "CSV download fails")]),
            ("kesar", "Kesar Kitchen", "Food & beverage", "IN", 300000, 260, 68, [(-26, "Campaign report export error")]),
        ]
        for key, name, industry, country, arr, renewal, crm, tickets in specs:
            feats = ["F-CAMPAIGNS", "F-TEMPLATES", "F-INBOX", "F-REPORTS", "F-SHOPIFY"]
            acc = self.account(key, name, industry, arr, renewal, crm, feats, self.rng.choice(CSMS), self.rng.choice(AES),
                               planted="blast-radius", country=country)
            admin = self.contact(acc, self.person_name(country), "Admin", "Head of Growth", champion=True, joined=-800)
            analyst = self.contact(acc, self.person_name(country), "Marketing Executive", "CRM Executive", joined=-400)
            self.contact(acc, self.person_name(country), "Finance Manager", "Finance Manager", joined=-500)
            self._older_history(acc, admin, feats, 5, before=-40)
            for created, subject in tickets:
                self.ticket(acc, analyst, created, subject,
                            f"Hi team, {subject[0].lower()}{subject[1:]}. It has happened on every large export this week.",
                            "open", "F-REPORTS", bug, self.rng.uniform(0.84, 0.95), "support-triage", "normal")
            self.usage(acc, feats, acc["seats"] * 0.7, lambda i: 1.0, {"F-REPORTS": lambda i: 1.0 if i < 21 else 0.82})
            self.invoices(acc, [0, -3, 1])
            self.conversation(acc, admin, -self.rng.randint(30, 70), "WhatsApp group",
                              f"{admin['name'].split()[0]}: Could you share the release notes for the latest update?")

    def _silent(self, key: str, name: str, industry: str, arr: int, renewal: int, crm: int, feats: list[str],
                bug_key: str | None, ticket_subjects: list[tuple[int, str]], champion_left: int | None,
                successor: bool, wau_mean: tuple[float, float], feature_drop: tuple[str, float, float] | None,
                convs: list[tuple[int, str]], lateness: list[int], csm: str, ae: str, wallet: int | None = None) -> dict:
        acc = self.account(key, name, industry, arr, renewal, crm, feats, csm, ae, planted="silent", wallet=wallet)
        champ = self.contact(acc, self.person_name("IN"), "Admin", "Head of Growth", champion=True,
                             joined=-950, left=champion_left, bounced=champion_left is not None)
        people = [self.contact(acc, self.person_name("IN"), r, r, joined=-self.rng.randint(200, 700))
                  for r in ("Ops Manager", "CRM Manager", "Finance Manager")]
        if successor and champion_left is not None:
            people[0]["successor_of"] = champ["email"]
        self._older_history(acc, champ, feats, 6, before=-95)
        if bug_key:
            bug = self.bugs[bug_key]
            for created, subject in ticket_subjects:
                self.ticket(acc, people[0], created, subject,
                            f"Hi team, {subject[0].lower()}{subject[1:]}. Several people on our side are affected.",
                            "open", bug["_feature"], bug, self.rng.uniform(0.82, 0.95), "support-triage", "high")
        b, c = wau_mean
        curves, exact = {}, {"active_users": (b, c)}
        if feature_drop:
            f, fb, fc = feature_drop
            curves[f] = lambda i: 1.0 if i < 20 else 0.5
            exact[f] = (fb, fc)
        self.usage(acc, feats, b, lambda i: 1.0 if i < 20 else c / b, curves, exact=exact)
        self.invoices(acc, lateness)
        for when, text in convs:
            self.conversation(acc, people[0], when, "Call notes", text)
        return acc

    def _saffron(self) -> None:
        acc = self._silent("saffron", "Saffron Threads", "Fashion & apparel", 840000, 41, 79,
                           ["F-CAMPAIGNS", "F-TEMPLATES", "F-INBOX", "F-ACCESS", "F-SHOPIFY", "F-AI"], "CHEER-2498",
                           [(-44, "Agents not getting login OTP"), (-31, "Login OTP comes after it expires"),
                            (-19, "Team locked out, OTP not coming again")],
                           champion_left=-55, successor=False, wau_mean=(140, 101), feature_drop=("F-INBOX", 1500, 825),
                           convs=[(-14, "Ops Manager: We've had a demo from another platform and the login problems came up a lot.")],
                           lateness=[0, -2, 3], csm="p-rhea", ae="p-simran")
        # A missing usage week in the source data (exercise the "show a gap" rule).
        self.p.usage = [u for u in self.p.usage
                        if not (u["account"] == acc["name"] and u["metric"] == "active_users" and u["week_index"] == 8)]

    def _banyan(self) -> None:
        self._silent("banyan", "Banyan Home", "Home & decor", 660000, 58, 74,
                     ["F-CAMPAIGNS", "F-TEMPLATES", "F-INBOX", "F-SHOPIFY", "F-WORKFLOWS", "F-API"], "CHEER-2505",
                     [(-50, "COD confirmation not going for some orders"), (-22, "Discount orders skip the COD message")],
                     champion_left=-70, successor=True, wau_mean=(96, 48), feature_drop=("F-SHOPIFY", 300, 120),
                     convs=[(-28, "Ops Manager: After the reorg we're under pressure to cut software costs this year, "
                                  "so the renewal will get scrutinised."),
                            (-11, "Ops Manager: It's frustrating that COD confirmations still need manual follow-up.")],
                     lateness=[0, 2, 11], csm="p-vivek", ae="p-neel")

    def _medora(self) -> None:
        self._silent("medora", "Medora Wellness", "Health & wellness", 540000, 76, 77,
                     ["F-CAMPAIGNS", "F-TEMPLATES", "F-INBOX", "F-AI", "F-WORKFLOWS"], "CHEER-2561",
                     [(-38, "Same customer showing twice in inbox"), (-25, "Duplicate chats for one number"),
                      (-9, "Agents replying twice to the same customer")],
                     champion_left=None, successor=False, wau_mean=(80, 52), feature_drop=("F-INBOX", 560, 252),
                     convs=[(-21, "Ops Manager: Leadership asked us to look at alternatives before we renew."),
                            (-16, "Ops Manager: The team is losing patience with the duplicate conversations."),
                            (-6, "Ops Manager: Merging duplicates by hand again is frustrating for our support team.")],
                     lateness=[0, 1, 9], csm="p-vivek", ae="p-simran", wallet=3200)

    def _pearl(self) -> None:
        feats = ["F-CAMPAIGNS", "F-TEMPLATES", "F-INBOX", "F-VOICE"]
        acc = self.account("pearl", "Pearl Dental Clinics", "Healthcare", 120000, 30, 46, feats, "p-rhea", "p-neel",
                           planted="decoy")
        admin = self.contact(acc, self.person_name("IN"), "Admin", "Practice Manager", champion=True, joined=-700)
        lead = self.contact(acc, self.person_name("IN"), "Ops Manager", "Clinic Lead", joined=-300)
        self._older_history(acc, admin, feats, 3, before=-90)
        bug = self.bugs["CHEER-2469"]
        for created, subject in [(-52, "Patients got the reminder three times"), (-45, "Appointment broadcast sent 3x"),
                                 (-38, "Triple messages to patients"), (-30, "Broadcast still duplicating")]:
            self.ticket(acc, lead, created, subject, f"Hi, {subject.lower()}. Patients are complaining.",
                        "solved", "F-CAMPAIGNS", bug, self.rng.uniform(0.9, 0.97), "support-triage", "normal")
        self.usage(acc, feats, 18, lambda i: 1.0 if i < 16 else (0.72 if i < 21 else 1.03),
                   {"F-CAMPAIGNS": lambda i: 1.0 if i < 16 else (0.4 if i < 21 else 1.05)})
        self.invoices(acc, [0, 0, -1])
        self.conversation(acc, admin, -12, "Email",
                          f"{admin['name'].split()[0]}: Thanks for the quick fix, everything is running smoothly again.")

    def _bluebird(self) -> None:
        feats = ["F-CAMPAIGNS", "F-TEMPLATES", "F-INBOX", "F-SHOPIFY"]
        acc = self.account("bluebird", "Bluebird Bakehouse", "Food & beverage", 84000, 34, 52, feats, "p-rhea", "p-simran",
                           planted="decoy", country="US")
        owner = self.contact(acc, self.person_name("US"), "Admin", "Owner", champion=True, joined=-1000, left=-63, bounced=True)
        felix = self.contact(acc, "Felix Ward", "Admin", "General Manager", joined=-400, successor_of=owner["email"])
        self.used_names.add("Felix Ward")
        self._older_history(acc, owner, feats, 4, before=-70)
        self.usage(acc, feats, 12, lambda i: 1.0 if i < 17 else (0.75 if i < 20 else 1.06))
        self.invoices(acc, [0, 1, -2])
        self.conversation(acc, felix, -26, "Call notes",
                          "Felix: Onboarding went well, the abandoned-cart flow is a big hit with our regulars.")
        self.conversation(acc, felix, -8, "Email",
                          "Felix: We're planning to roll Cheerio out to two more stores next quarter.")

    # ---------- build ----------
    def build(self) -> Portfolio:
        self.features()
        self.bugs_catalog()
        self.planted()
        names: list[tuple[str, str, str]] = []
        seen = {a["name"] for a in self.p.accounts}
        while len(names) < N_ACCOUNTS - len(self.p.accounts):
            if self.rng.random() < 0.25:
                suffix, industry = self.rng.choice(catalog.US_SUFFIXES)
                name, country = f"{self.rng.choice(catalog.US_PREFIXES)} {suffix}", "US"
            else:
                suffix, industry = self.rng.choice(catalog.IN_SUFFIXES)
                name, country = f"{self.rng.choice(catalog.IN_PREFIXES)} {suffix}", "IN"
            if name not in seen:
                seen.add(name)
                names.append((name, industry, country))
        for i, (name, industry, country) in enumerate(names, start=1):
            self.background_account(i, name, industry, country)
        return self.p


def build() -> tuple[Portfolio, dict]:
    """The portfolio plus the hand-written customer stories (meetings, promises, roadmap, calendar, calls, docs)."""
    p = Builder().build()
    return p, stories.build({a["name"]: a for a in p.accounts})
