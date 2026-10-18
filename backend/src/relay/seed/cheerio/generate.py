"""Generate the Cheerio synthetic exports (deterministic, fixed seed).

    uv run relay seed --tenant cheerio

Writes tool-shaped exports under data/cheerio/: HR, service catalog, CRM, Slack,
Confluence, Jira, meeting transcripts, GitHub, plus the customer-facing exports
from `commercial.py` (support desk, product usage, billing, conversations,
roadmap, calendar and call recordings). The ingestion pipeline reads only these
files. Every person, customer and message is invented.
"""

from __future__ import annotations

import hashlib
import json
import random
import shutil
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from ...config import DEMO_NOW, IST, REPO_ROOT
from ...scoring import OWNER_BONUS, SIGNAL_WEIGHTS, decay
from . import commercial, planted, textgen, world

DATA_DIR = REPO_ROOT / "data" / "cheerio"
KEY_PREFIX = "CHEER"
KEY_START = 2100
UNIQUE_ACCOUNT = "cust-kairo"
# Jira workflow statuses on the "Cheerio Dev" board, by status category.
JIRA_STATUS = {"Done": ["On Prod", "On Prod", "On Prod", "QA PASSED (PROD)"],
               "In Progress": ["In Progress", "In Progress", "PR REQUESTED", "ON STAGE"],
               "To Do": ["Sprint Items"], "Backlog": ["Backlog"]}

SEED = 20261013
WINDOW_START = datetime(2026, 2, 16, tzinfo=IST)
WINDOW_END = datetime(2026, 10, 16, 18, 0, tzinfo=IST)

# Raw-score targets per expertise level (see scoring.py for the squash).
TARGETS = {"O": (24.0, 30.0), "S": (13.0, 17.0), "C": (6.9, 8.0), "W": (1.4, 2.8)}
MIX_REPO = {"commit": 0.62, "review": 0.2, "answer": 0.12, "ticket": 0.06}
MIX_NOREPO = {"answer": 0.62, "ticket": 0.38}
MIX_KAIRO = {"contact": 0.7, "ticket": 0.3}
MIX_CUSTOMER = {"answer": 0.6, "ticket": 0.4}
# Rahul is the only person committing to billing-reconciler in eight months.
EXCLUSIVE_COMMITTER = {"sys-reconciler": "p-rahul"}

TEAM_CHANNEL = {"team-messaging": "messaging", "team-platform": "platform", "team-automations": "automations",
                "team-trust": "eng", "team-data": "eng", "team-cs": "cs", "team-sales": "cs"}
CHANNELS = [
    ("C0GENERAL", "general", "Company-wide announcements and chatter", False),
    ("C0ENG", "eng", "Engineering questions, builds and help", False),
    ("C0MESSAGING", "messaging", "Messaging pod: send pipeline, wallet, settlement, recon", False),
    ("C0PLATFORM", "platform", "Platform: gateway, CI, infra, staging, voice", False),
    ("C0AUTOMATIONS", "automations", "Automations pod: workflows, Shopify, AI assistant", False),
    ("C0CS", "cs", "Customer escalations, renewals and asks from CS", False),
    ("C0INCIDENTS", "incidents", "Alerts and incident coordination", False),
    ("C0EXTKAIRO", "ext-kairo-living", "Slack Connect with Kairo Living", True),
]
CHANNEL_ID = {name: cid for cid, name, _, _ in CHANNELS}
DM_KAIRO = "D0KAIRORAHUL"

PEOPLE = {p["id"]: p for p in world.PEOPLE + world.FORMER_PEOPLE}
SYSTEMS = {s["id"]: s for s in world.SYSTEMS}
CUSTOMERS = {c["id"]: c for c in world.CUSTOMERS}
CONTACTS = {c["id"]: c for c in world.CONTACTS}
BOTS = {b["id"]: b for b in world.BOTS}


def _slack_id(actor: str) -> str:
    return "U0" + actor.split("-", 1)[1].replace("-", "").upper()


def _email(actor: str) -> str:
    if actor in PEOPLE:
        return PEOPLE[actor]["email"]
    if actor in CONTACTS:
        c = CONTACTS[actor]
        domain = CUSTOMERS[c["customer"]]["name"].lower().replace(" ", "") + ".example"
        return c["name"].lower().replace(" ", ".") + "@" + domain
    return actor.split("-", 1)[1] + "@bots." + world.DOMAIN


class Gen:
    def __init__(self) -> None:
        self.rng = random.Random(SEED)
        self.messages: list[dict] = []
        self.docs: list[dict] = []
        self.tickets: list[dict] = []
        self.meetings: list[dict] = []
        self.commits: list[dict] = []
        self.pulls: list[dict] = []
        self.extractions: list[dict] = []   # seed-mode annotations, keyed by source
        self._ts_used: set[str] = set()
        self._reviews: list[tuple[str, str, datetime]] = []  # (reviewer, repo, when)

    # ----------------------------------------------------------------- utils
    def bounds(self, pid: str) -> tuple[datetime, datetime]:
        """When this person could have produced activity at all."""
        p = PEOPLE[pid]
        start = datetime.fromisoformat(p["startDate"]).replace(tzinfo=IST) + timedelta(days=10)
        end = datetime.fromisoformat(p["endDate"]).replace(tzinfo=IST) if p.get("endDate") else WINDOW_END
        return start, min(end, WINDOW_END)

    def active_between(self, pid: str) -> tuple[datetime, datetime]:
        start, end = self.bounds(pid)
        return max(WINDOW_START, start), end

    def when(self, pid: str, lo: datetime | None = None, hi: datetime | None = None) -> datetime:
        a, b = self.bounds(pid)
        lo, hi = max(a, lo or WINDOW_START), min(b, hi or WINDOW_END)
        if hi <= lo:
            hi = lo + timedelta(days=1)
        for _ in range(20):
            t = lo + timedelta(seconds=self.rng.uniform(0, (hi - lo).total_seconds()))
            if t.weekday() < 5:
                break
        hour = self.rng.choice([10, 10, 11, 11, 12, 14, 15, 15, 16, 17, 18, 19, 21])
        return t.replace(hour=hour, minute=self.rng.randrange(60), second=self.rng.randrange(60), microsecond=0)

    def ts(self, t: datetime) -> str:
        base = int(t.timestamp())
        micro = 100
        while f"{base}.{micro:06d}" in self._ts_used:
            micro += 1
        s = f"{base}.{micro:06d}"
        self._ts_used.add(s)
        return s

    def sha(self) -> str:
        return f"{self.rng.getrandbits(48):012x}"

    def pick(self, seq):
        return seq[self.rng.randrange(len(seq))]

    def fill(self, template: str, item: str, extra: dict | None = None) -> str:
        v = textgen.VOCAB.get(item, {})
        s = self.pick(textgen.SPOKEN[item])
        vals = {
            "s": s, "S": s[0].upper() + s[1:],
            "symptom": self.pick(v["symptom"]) if v.get("symptom") else "acting up",
            "cause": self.pick(v["cause"]) if v.get("cause") else "a config issue",
            "fix": self.pick(v["fix"]) if v.get("fix") else "check the logs",
        }
        vals["Fix"] = vals["fix"][0].upper() + vals["fix"][1:]
        vals.update(extra or {})
        return template.format(**vals)

    # ------------------------------------------------------------ messages
    def post(self, channel: str, actor: str, t: datetime, text: str, thread_ts: str | None = None) -> str:
        cid = CHANNEL_ID.get(channel, channel)
        ts = self.ts(t)
        msg = {"ts": ts, "channel": cid, "user": _slack_id(actor), "text": text}
        if thread_ts:
            msg["thread_ts"] = thread_ts
        self.messages.append(msg)
        return ts

    def thread(self, channel: str, start: datetime, msgs: list[tuple[str, int, str]],
               annotations: list[dict] | None = None) -> str:
        root_ts = None
        for actor, minutes, text in msgs:
            t = start + timedelta(minutes=minutes)
            ts = self.post(channel, actor, t, text, thread_ts=root_ts)
            root_ts = root_ts or ts
        if annotations:
            self.extractions.append({"source_type": "slack_thread", "source_id": f"{CHANNEL_ID.get(channel, channel)}:{root_ts}",
                                     "annotations": annotations})
        return root_ts

    # ------------------------------------------------------------- planted
    def planted(self) -> None:
        for th in planted.SLACK_THREADS:
            self.thread(th["channel"], th["start"], th["messages"], th.get("annotations"))
        for m in planted.MEETINGS:
            self.meetings.append(self._meeting_record(m["id"], m["title"], m["start"], m["attendees"],
                                                      m["transcript"], m["notes"]))
            if m.get("annotations"):
                self.extractions.append({"source_type": "meeting", "source_id": m["id"], "annotations": m["annotations"]})
        for d in planted.DOCS:
            self.docs.append(self._doc_record(d))
            if d["id"] in planted.DOC_ANNOTATIONS:
                self.extractions.append({"source_type": "doc", "source_id": d["id"],
                                         "annotations": planted.DOC_ANNOTATIONS[d["id"]]})
        for tk in planted.TICKETS:
            self.tickets.append(self._ticket_record(tk))
        self.extractions.append({"source_type": "ticket", "source_id": "CHEER-2412",
                                 "annotations": [{"kind": "obsoletes", "item": "wk-ledger-replay", "roles": {"p-arjun": "author"}}]})
        for c in planted.COMMITS:
            self.commits.append({"sha": c["sha"], "repo": c["repo"], "author": c["author"], "date": c["date"],
                                 "message": c["message"]})
            if c.get("annotations"):
                self.extractions.append({"source_type": "commit", "source_id": c["sha"], "annotations": c["annotations"]})
        # Kairo's engineers DM Rahul directly.
        for i, (contact, text) in enumerate([
            ("c-siddharth", "Hey Rahul, quick one before I raise it formally: tomorrow's order file may be split in two parts. OK on your side?"),
            ("c-pooja", "Rahul, is the webhook IP allowlist still 3 addresses? Our infra team is asking."),
            ("c-siddharth", "Can we do a 15-min call on the v2 signature timeline next week?"),
            ("c-pooja", "Sent you the draft of the new store-code file spec, would love your eyes on it before it goes wide."),
            ("c-siddharth", "Our ops team says you're the person to ask about file cutoffs. Is 01:30 still the latest we can drop?"),
        ]):
            t = self.when("p-rahul", lo=WINDOW_START + timedelta(days=30 * i + 20), hi=WINDOW_START + timedelta(days=30 * i + 50))
            root = self.post(DM_KAIRO, contact, t, text)
            self.post(DM_KAIRO, "p-rahul", t + timedelta(minutes=self.rng.randint(4, 40)), self.pick([
                "Yes, that works. The importer waits for the done-marker, so a split file is fine as long as both parts land before 01:50.",
                "Still 3, same as the integration doc. I'll send you the list again to be safe.",
                "Sure, Tuesday 11:00 IST works. I'll bring the side-by-side verification plan.",
                "Had a look. The store section reads fine, left two small comments on the date format.",
                "01:30 is the latest that still gives us slack before the 01:50 pull. 01:45 at a push.",
            ]), thread_ts=root)

    # ---------------------------------------------------------------- docs
    def _doc_record(self, d: dict) -> dict:
        return {"id": d["id"], "title": d["title"], "space": d["space"], "kind": d["kind"],
                "author": d["author"], "created": d["created"], "updated": d["updated"],
                "labels": [SYSTEMS[s]["name"] for s in d["systems"]],
                "customers": [CUSTOMERS[c]["name"] for c in d["customers"]], "body": d["body"]}

    def bulk_docs(self) -> None:
        n = 1200
        kinds = [("runbook", "Runbook: {name}"), ("design", "{name}: design notes"), ("design", "{name}: FAQ")]
        for sid, levels in world.EXPERTISE.items():
            if not sid.startswith("sys-"):
                continue
            sysrec = SYSTEMS[sid]
            existing = {d["kind"] for d in self.docs if sysrec["name"] in d["labels"]}
            writers = [p for p, lv in levels.items() if lv in ("O", "S")]
            for kind, title in kinds:
                if kind in existing and kind == "runbook":
                    continue
                if not writers or self.rng.random() < 0.35:
                    continue
                author = writers[0] if self.rng.random() < 0.6 else self.pick(writers)
                updated = self.when(author, lo=datetime(2025, 4, 1, tzinfo=IST))
                v = textgen.VOCAB[sid]
                body = (f"# {title.format(name=sysrec['name'])}\n\n{sysrec['summary']}\n\n"
                        f"## Common issues\n" + "\n".join(
                            f"- When it is {s}: usually {c}. Fix: {f}." for s, c, f in zip(v['symptom'], v['cause'], v['fix'])))
                n += 1
                self.docs.append({"id": f"DOC-{n:04d}", "title": title.format(name=sysrec["name"]),
                                  "space": {"team-messaging": "MSG", "team-platform": "PLAT", "team-automations": "AUTO",
                                            "team-trust": "TRUST", "team-data": "DATA"}[sysrec["team"]],
                                  "kind": kind, "author": author, "created": updated - timedelta(days=self.rng.randint(5, 90)),
                                  "updated": updated, "labels": [sysrec["name"]], "customers": [], "body": body})
        general = [
            ("Engineering handbook", "p-sameer", "policy"), ("Security policy", "p-ishaan", "policy"),
            ("Expense policy", "p-sunil", "policy"), ("Leave policy", "p-leela", "policy"),
            ("Incident response and RCA process", "p-sana", "policy"), ("Code review guidelines", "p-vikram", "policy"),
            ("Q3 planning: Messaging", "p-isha", "prd"), ("Q3 planning: Automations", "p-varun", "prd"),
            ("PRD: Wallet low-balance alerts", "p-isha", "prd"), ("PRD: Instagram DM automation", "p-varun", "prd"),
            ("Retro: Sprint 64", "p-maya", "retro"), ("Retro: Q2 on-call", "p-ishaan", "retro"),
            ("CS onboarding checklist for new accounts", "p-arnav", "onboarding"), ("Data team onboarding", "p-meera", "onboarding"),
            ("Brand and writing guide", "p-naina", "policy"), ("Interviewing at Cheerio", "p-leela", "policy"),
            ("Crestline Finance integration overview", "p-jay", "design"), ("Northwind Foods account plan", "p-sneha", "design"),
        ]
        for title, author, kind in general:
            n += 1
            updated = self.when(author, lo=datetime(2025, 6, 1, tzinfo=IST))
            cust = [c["name"] for c in world.CUSTOMERS if c["name"].split()[0] in title]
            self.docs.append({"id": f"DOC-{n:04d}", "title": title, "space": "ENG" if kind in ("policy", "retro") else "PROD",
                              "kind": kind, "author": author, "created": updated - timedelta(days=30), "updated": updated,
                              "labels": [], "customers": cust,
                              "body": f"# {title}\n\nOwner: {PEOPLE[author]['name']}.\n\nThis page is maintained by the owner; ask in #general for changes."})

    # ------------------------------------------------------------ activity
    def raw_so_far(self, pid: str, item: str) -> float:
        raw = 0.0
        rec = SYSTEMS.get(item) or CUSTOMERS.get(item)
        if rec and (rec.get("serviceOwner") == pid or rec.get("integrationOwner") == pid):
            raw += OWNER_BONUS
        name = rec["name"]
        for d in self.docs:
            if d["author"] == pid and (name in d["labels"] or name in d["customers"]):
                raw += SIGNAL_WEIGHTS["doc"] * decay(d["updated"], DEMO_NOW)
        if item.startswith("sys-") and rec.get("repo"):
            for c in self.commits:
                if c["author"] == pid and c["repo"] == rec["repo"]:
                    raw += SIGNAL_WEIGHTS["commit"] * decay(c["date"], DEMO_NOW)
        return raw

    def activity(self) -> None:
        # Fixed history first: Rahul's 214 billing-reconciler commits in eight
        # months, and Karan's older commits from before he left.
        recon = SYSTEMS["sys-reconciler"]["repo"]
        planted_recon = sum(1 for c in self.commits if c["repo"] == recon and c["author"] == "p-rahul")
        for _ in range(214 - planted_recon):
            t = self.when("p-rahul", lo=WINDOW_START + timedelta(days=5))
            self.commits.append(self._commit("p-rahul", recon, t))
        for _ in range(140):
            t = self.when("p-karan", lo=datetime(2025, 3, 1, tzinfo=IST), hi=datetime(2025, 12, 12, tzinfo=IST))
            self.commits.append(self._commit("p-karan", recon, t))
        for _ in range(30):
            t = self.when("p-karan", lo=datetime(2025, 5, 1, tzinfo=IST), hi=datetime(2025, 11, 30, tzinfo=IST))
            self.commits.append(self._commit("p-karan", SYSTEMS["sys-settlement"]["repo"], t))

        for item in sorted(world.EXPERTISE):
            for pid, level in sorted(world.EXPERTISE[item].items()):
                target = self.rng.uniform(*TARGETS[level])
                raw = self.raw_so_far(pid, item)
                if item.startswith("sys-"):
                    mix = MIX_REPO if SYSTEMS[item].get("repo") else MIX_NOREPO
                else:
                    mix = MIX_KAIRO if item == UNIQUE_ACCOUNT else MIX_CUSTOMER
                if EXCLUSIVE_COMMITTER.get(item, pid) != pid:
                    mix = {k: v for k, v in mix.items() if k != "commit"}
                kinds, weights = zip(*mix.items())
                guard = 0
                while raw < target and guard < 400:
                    guard += 1
                    kind = self.rng.choices(kinds, weights)[0]
                    t = self.when(pid)
                    raw += self._emit(kind, pid, item, t)

    def _commit(self, pid: str, repo: str, t: datetime) -> dict:
        thing = self.pick(textgen.COMMIT_THINGS[repo])
        return {"sha": self.sha(), "repo": repo, "author": pid, "date": t,
                "message": self.pick(textgen.COMMIT_TEMPLATES).format(thing=thing)}

    def _emit(self, kind: str, pid: str, item: str, t: datetime) -> float:
        rec = SYSTEMS.get(item) or CUSTOMERS[item]
        if kind == "commit":
            self.commits.append(self._commit(pid, rec["repo"], t))
        elif kind == "review":
            self._reviews.append((pid, rec["repo"], t))
        elif kind == "answer":
            self._answer_thread(pid, item, t)
        elif kind == "contact":
            self._kairo_contact(pid, t)
        elif kind == "ticket":
            open_ = (DEMO_NOW - t).days < 25 and self.rng.random() < 0.4
            self._activity_ticket(pid, item, t, open_)
            return SIGNAL_WEIGHTS["ticket_open" if open_ else "ticket"] * decay(t, DEMO_NOW)
        return SIGNAL_WEIGHTS[kind] * decay(t, DEMO_NOW)

    def _asker_for(self, pid: str, item: str, t: datetime) -> str:
        rec = SYSTEMS.get(item) or CUSTOMERS[item]
        team = rec.get("team") or "team-cs"
        known = set(world.EXPERTISE.get(item, {}))
        pool = [p for p, r in PEOPLE.items()
                if p != pid and p not in known and r["status"] == "active"
                and self.active_between(p)[0] <= t and (r["team"] == team or self.rng.random() < 0.25)]
        pool = pool or [p for p in PEOPLE if p != pid and PEOPLE[p]["status"] == "active"]
        return self.pick(sorted(pool))

    def _answer_thread(self, pid: str, item: str, t: datetime) -> None:
        if item.startswith("cust-"):
            channel = "cs"
            q = self.fill(self.pick(textgen.CUSTOMER_Q_TEMPLATES), item)
        else:
            team = SYSTEMS[item]["team"]
            channel = TEAM_CHANNEL.get(team, "eng") if self.rng.random() < 0.75 else "eng"
            q = self.fill(self.pick(textgen.QUESTION_TEMPLATES), item)
        asker = self._asker_for(pid, item, t)
        a = self.fill(self.pick(textgen.ANSWER_TEMPLATES), item)
        msgs = [(asker, 0, q), (pid, self.rng.randint(3, 50), a)]
        if self.rng.random() < 0.6:
            msgs.append((asker, msgs[-1][1] + self.rng.randint(2, 30), self.pick(textgen.ACKS)))
        self.thread(channel, t - timedelta(minutes=55), msgs)

    def _kairo_contact(self, pid: str, t: datetime) -> None:
        idx = self.rng.randrange(len(textgen.KAIRO_ROOTS))
        contact, root = textgen.KAIRO_ROOTS[idx]
        d = t.strftime("%Y%m%d")
        root = root.format(d=d, d2=(t + timedelta(days=5)).strftime("%d %b"))
        if pid == "p-rahul":
            reply = textgen.KAIRO_REPLIES[idx]
            channel = DM_KAIRO if self.rng.random() < 0.25 else "ext-kairo-living"
        else:
            reply = self.pick(["Thanks Siddharth, noted on our side. I'll make sure the team sees this before tonight's pull.",
                               "Thanks Pooja, logging this on our side and looping in the right people for tonight."])
            channel = "ext-kairo-living"
        msgs = [(contact, 0, root), (pid, self.rng.randint(5, 45), reply)]
        self.thread(channel, t - timedelta(minutes=50), msgs)

    def _activity_ticket(self, pid: str, item: str, t: datetime, open_: bool) -> None:
        rec = SYSTEMS.get(item) or CUSTOMERS[item]
        v = textgen.VOCAB[item]
        if item.startswith("sys-"):
            summary = f"{rec['name']}: " + self.pick([
                f"investigate when {self.pick(textgen.SPOKEN[item])} is {self.pick(v['symptom'])}",
                self.pick(v["fix"]),
                f"follow-up: {self.pick(v['cause'])}",
            ])
        else:
            summary = f"{rec['name']}: " + self.pick(v["symptom"])
        reporter = self._asker_for(pid, item, t)
        created = t - timedelta(days=self.rng.randint(1, 18), hours=self.rng.randint(0, 8))
        status = self.pick(["In Progress", "To Do"]) if open_ else "Done"
        self.tickets.append({
            "key": None, "summary": summary, "status": status, "assignee": pid, "reporter": reporter,
            "components": [rec["name"]] if item.startswith("sys-") else [],
            "customer": rec["name"] if item.startswith("cust-") else None,
            "created": created, "updated": t, "resolved": None if open_ else t, "labels": [],
            "description": f"Reported by {PEOPLE[reporter]['name']}. Seen when {self.pick(v['symptom']) if v['symptom'] else 'running normally'}.",
            "comments": [] if open_ else [{"author": pid, "created": t, "body": f"Fixed: {self.pick(v['fix'])}." if v["fix"] else "Done."}],
        })

    def _ticket_record(self, tk: dict) -> dict:
        return {
            "key": tk["key"], "summary": tk["summary"], "status": tk["status"], "assignee": tk["assignee"],
            "reporter": tk["reporter"], "components": [SYSTEMS[s]["name"] for s in tk["components"]],
            "customer": CUSTOMERS[tk["customer"]]["name"] if tk.get("customer") else None,
            "created": tk["created"], "updated": tk["resolved"] or tk["created"], "resolved": tk["resolved"],
            "labels": tk.get("labels", []), "description": tk["description"],
            "comments": [{"author": a, "created": when, "body": body} for a, when, body in tk["comments"]],
        }

    # -------------------------------------------------------------- github
    def pull_requests(self) -> None:
        by_repo_author: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for c in sorted(self.commits, key=lambda c: c["date"]):
            by_repo_author[(c["repo"], c["author"])].append(c)
        numbers: dict[str, int] = defaultdict(lambda: 100)
        prs_by_repo: dict[str, list[dict]] = defaultdict(list)
        for (repo, author), commits in sorted(by_repo_author.items()):
            i = 0
            while i < len(commits):
                size = self.rng.choice([1, 1, 2, 2, 3, 4])
                chunk = [commits[i]]
                while len(chunk) < size and i + len(chunk) < len(commits) and \
                        (commits[i + len(chunk)]["date"] - chunk[0]["date"]).days <= 3:
                    chunk.append(commits[i + len(chunk)])
                i += len(chunk)
                last = chunk[-1]
                prs_by_repo[repo].append({"repo": repo, "author": author, "title": chunk[0]["message"],
                                          "created_at": chunk[0]["date"] - timedelta(hours=1),
                                          "merged_at": last["date"] + timedelta(hours=self.rng.randint(1, 30)),
                                          "commits": [c["sha"] for c in chunk], "reviews": []})
        for repo, prs in prs_by_repo.items():
            prs.sort(key=lambda p: p["created_at"])
            for p in prs:
                numbers[repo] += 1
                p["number"] = numbers[repo]
        for reviewer, repo, t in self._reviews:
            candidates = [p for p in prs_by_repo[repo] if p["author"] != reviewer
                          and not any(r["reviewer"] == reviewer for r in p["reviews"])]
            if not candidates:
                continue
            pr = min(candidates, key=lambda p: abs((p["merged_at"] - t).total_seconds()))
            pr["reviews"].append({"reviewer": reviewer, "submitted_at": t,
                                  "state": self.pick(["APPROVED", "APPROVED", "COMMENTED", "CHANGES_REQUESTED"])})
        self.pulls = [p for prs in prs_by_repo.values() for p in prs]

    # ------------------------------------------------------------ meetings
    def _meeting_record(self, mid, title, start, attendees, transcript, notes) -> dict:
        return {"id": mid, "title": title, "start": start, "attendees": attendees,
                "transcript": [{"speaker": s, "text": tx} for s, tx in transcript], "notes": notes}

    def bulk_meetings(self) -> None:
        series = [
            ("Messaging pod sync", "team-messaging", ["p-isha"], 10),
            ("Platform sync", "team-platform", [], 8),
            ("Automations pod sync", "team-automations", ["p-varun"], 8),
            ("Trust & data sync", "team-trust", ["p-meera", "p-lina"], 5),
            ("All-hands", None, [], 6),
            ("Renewals pipeline review", "team-cs", ["p-naina"], 5),
        ]
        for title, team, extra, n in series:
            for i in range(n):
                day = WINDOW_START + timedelta(days=int((i + 0.5) * (WINDOW_END - WINDOW_START).days / n))
                while day.weekday() != 1:
                    day += timedelta(days=1)
                start = day.replace(hour=11 if team else 16, minute=0)
                if team:
                    attendees = [p for p, r in PEOPLE.items() if r["team"] == team and r["status"] == "active"
                                 and self.active_between(p)[0] <= start] + extra
                else:
                    attendees = [p for p, r in PEOPLE.items() if r["status"] == "active" and self.active_between(p)[0] <= start]
                lines = []
                speakers = attendees if team else ["p-ananya", "p-sameer", "p-naina", "p-leela"]
                for sp in speakers[:7]:
                    mine = [it for it, lv in world.EXPERTISE.items() if lv.get(sp) in ("O", "S")]
                    if mine and team:
                        it = self.pick(sorted(mine))
                        lines.append((sp, self.fill(self.pick([
                            "{S}: the follow-up from last week is merged, nothing blocking.",
                            "I'm still on {s}; the fix for {cause} ships Thursday.",
                            "Quick update on {s}: quiet week, two small tickets closed.",
                        ]), it)))
                    else:
                        lines.append((sp, self.pick([
                            "Nothing major from me this week.", "Hiring update: two offers out, one accepted.",
                            "Reminder that the offsite agenda doc is open for comments.",
                            "Collections are at 85% of billing this month, best so far.",
                            "Please update your OKR progress before Friday.",
                        ])))
                mid = f"mtg-{start:%Y-%m-%d}-{title.lower().replace(' ', '-').replace('&', 'and')}"
                self.meetings.append(self._meeting_record(mid, title, start, attendees, lines,
                                                          "Overview\n- **Status:** Updates only. No decisions recorded."))

    # -------------------------------------------------------------- filler
    def filler(self, target_messages: int = 3000, target_tickets: int = 400) -> None:
        active = sorted(p for p, r in PEOPLE.items() if r["status"] == "active")
        eng_items = {p: sorted(it for it, lv in world.EXPERTISE.items() if lv.get(p) in ("O", "S", "C") and it.startswith("sys-"))
                     for p in active}
        repos = sorted({s["repo"] for s in world.SYSTEMS if s.get("repo")})
        while len(self.tickets) < target_tickets:
            sid = self.pick(sorted(SYSTEMS))
            reporter = self.pick(active)
            t = self.when(reporter)
            self.tickets.append({"key": None, "summary": f"{SYSTEMS[sid]['name']}: " + self.pick([
                "tidy up alert thresholds", "document config flags", "upgrade dependencies", "add dashboard panel",
                "remove dead feature toggle", "improve error messages"]),
                "status": self.pick(["Backlog", "Backlog", "To Do"]), "assignee": None, "reporter": reporter,
                "components": [SYSTEMS[sid]["name"]], "customer": None, "created": t, "updated": t,
                "resolved": None, "labels": [], "description": "Nice to have. Pick up when there's slack in the sprint.",
                "comments": []})
        kinds = ["standup", "deploy", "alert", "social"]
        while len(self.messages) < target_messages:
            kind = self.rng.choices(kinds, [0.3, 0.25, 0.15, 0.3])[0]
            if kind == "standup":
                pid = self.pick([p for p in active if eng_items[p]])
                items = eng_items[pid]
                t = self.when(pid)
                channel = TEAM_CHANNEL.get(PEOPLE[pid]["team"], "eng")
                text = self.fill(self.pick(textgen.STANDUPS), self.pick(items),
                                 {"s2": self.pick(textgen.SPOKEN[self.pick(items)])})
                self.post(channel, pid, t, text)
            elif kind == "deploy":
                repo = self.pick(repos)
                who = self.pick([c["author"] for c in self.commits if c["repo"] == repo and PEOPLE[c["author"]]["status"] == "active"])
                t = self.when(who)
                text = self.pick(textgen.DEPLOYS).format(repo=repo.split("/")[1], ver=f"v{self.rng.randint(1, 4)}.{self.rng.randint(0, 30)}.{self.rng.randint(0, 9)}",
                                                         who=PEOPLE[who]["name"])
                self.post("eng", "b-deploybot", t, text)
            elif kind == "alert":
                sid = self.pick(sorted(SYSTEMS))
                t = self.when("p-sana")
                self.post("incidents", "b-pagerduty", t, self.pick(textgen.ALERTS).format(name=SYSTEMS[sid]["name"]))
            else:
                pid = self.pick(active)
                t = self.when(pid)
                self.post("general", pid, t, self.pick(textgen.SOCIAL).format(name=PEOPLE[self.pick(active)]["name"].split()[0]))

    # --------------------------------------------------------------- write
    def assign_ticket_keys(self, bugs: list[dict]) -> None:
        """One key sequence for the whole Jira project, in creation order; planted keys stay fixed."""
        allt = self.tickets + bugs
        taken = {int(t["key"].split("-")[1]) for t in allt if t["key"]}
        n = KEY_START
        for t in sorted((t for t in allt if not t["key"]), key=lambda t: t["created"]):
            n += 1
            while n in taken:
                n += 1
            t["key"] = f"{KEY_PREFIX}-{n}"

    def write(self, out: Path) -> dict:
        portfolio, stories = commercial.build()
        if out.exists():
            shutil.rmtree(out)
        for sub in ("hr", "catalog", "crm", "slack", "confluence", "jira", "meetings", "github", "annotations",
                    "support", "product", "billing", "conversations", "roadmap", "calendar", "calls", "memory"):
            (out / sub).mkdir(parents=True, exist_ok=True)
        status_rng = random.Random(SEED + 1)

        def iso(t):
            return t.isoformat() if isinstance(t, datetime) else t

        def dump(path: Path, rows: list[dict]):
            with path.open("w") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False, default=iso) + "\n")

        def public(r: dict) -> dict:
            return {k: v for k, v in r.items() if not k.startswith("_")}

        people = world.PEOPLE + world.FORMER_PEOPLE
        dump(out / "hr" / "employees.jsonl", [{
            "employee_id": p["id"], "name": p["name"], "email": p["email"], "title": p["role"],
            "team": next(t["name"] for t in world.TEAMS if t["id"] == p["team"]),
            "manager_email": PEOPLE[p["managerId"]]["email"] if p["managerId"] else None,
            "start_date": p["startDate"], "end_date": p["endDate"], "status": p["status"]} for p in people])
        dump(out / "catalog" / "systems.jsonl", [{
            "name": s["name"], "aliases": s["aliases"], "team": next(t["name"] for t in world.TEAMS if t["id"] == s["team"]),
            "owner_email": PEOPLE[s["serviceOwner"]]["email"], "criticality": s["criticality"], "repo": s["repo"],
            "summary": s["summary"]} for s in world.SYSTEMS])
        dump(out / "catalog" / "features.jsonl", portfolio.features)
        # HubSpot-style CRM export: every customer, including the integration-heavy four.
        dump(out / "crm" / "accounts.jsonl", [{**public(a), "tier": a["plan"]} for a in portfolio.accounts])

        actors = list(PEOPLE) + list(CONTACTS) + list(BOTS)
        users = []
        for a in actors:
            if a in PEOPLE:
                users.append({"id": _slack_id(a), "real_name": PEOPLE[a]["name"], "email": _email(a), "is_bot": False,
                              "deleted": PEOPLE[a]["status"] == "left"})
            elif a in CONTACTS:
                users.append({"id": _slack_id(a), "real_name": CONTACTS[a]["name"], "email": _email(a), "is_bot": False,
                              "external_org": CUSTOMERS[CONTACTS[a]["customer"]]["name"]})
            else:
                users.append({"id": _slack_id(a), "real_name": BOTS[a]["name"], "email": None, "is_bot": True})
        dump(out / "slack" / "users.jsonl", users)
        chans = [{"id": cid, "name": name, "purpose": purpose, "is_shared": shared, "is_im": False}
                 for cid, name, purpose, shared in CHANNELS]
        chans.append({"id": DM_KAIRO, "name": None, "purpose": None, "is_shared": True, "is_im": True,
                      "members": [_slack_id("p-rahul"), _slack_id("c-siddharth"), _slack_id("c-pooja")]})
        dump(out / "slack" / "channels.jsonl", chans)
        dump(out / "slack" / "messages.jsonl", sorted(self.messages, key=lambda m: float(m["ts"])))

        pages = [{
            "id": d["id"], "title": d["title"], "space": d["space"], "kind": d["kind"],
            "author_email": _email(d["author"]), "created": d["created"], "updated": d["updated"],
            "labels": d["labels"], "customers": d["customers"], "body": d["body"]} for d in self.docs]
        pages += [{k: v for k, v in d.items()} for d in stories["docs"]]
        for pg in pages:
            pg["url"] = f"https://cheerio.atlassian.example/wiki/spaces/{pg['space']}/pages/{pg['id'].split('-')[1]}"
        dump(out / "confluence" / "pages.jsonl", sorted(pages, key=lambda d: d["id"]))

        self.assign_ticket_keys(portfolio.bugs)
        issues = [{
            "key": t["key"], "summary": t["summary"], "issuetype": "Task",
            "status": status_rng.choice(JIRA_STATUS[t["status"]]), "status_category": t["status"],
            "assignee_email": _email(t["assignee"]) if t["assignee"] else None,
            "reporter_email": _email(t["reporter"]), "components": t["components"], "customer": t["customer"],
            "labels": t.get("labels", []), "created": t["created"], "updated": t["updated"], "resolved": t["resolved"],
            "description": t["description"],
            "comments": [{"author_email": _email(c["author"]), "created": c["created"], "body": c["body"]} for c in t["comments"]]}
            for t in self.tickets]
        for b in portfolio.bugs:
            issues.append({**public(b), "status": b["jira_status"] or status_rng.choice(JIRA_STATUS[b["status"]]),
                           "status_category": b["status"]})
        for i in issues:
            i.pop("jira_status", None)
        dump(out / "jira" / "issues.jsonl", sorted(issues, key=lambda t: int(t["key"].split("-")[1])))

        meetings = [{
            "id": m["id"], "title": m["title"], "start": m["start"], "kind": "internal", "account": None,
            "attendees": [_email(a) for a in m["attendees"]],
            "transcript": [{"speaker_email": _email(x["speaker"]), "text": x["text"]} for x in m["transcript"]],
            "notes": m["notes"]} for m in self.meetings]
        meetings += stories["meetings"]
        dump(out / "meetings" / "transcripts.jsonl", sorted(meetings, key=lambda m: m["start"]))
        dump(out / "github" / "commits.jsonl", [{
            "sha": c["sha"], "repo": c["repo"], "author_email": _email(c["author"]), "date": c["date"], "message": c["message"]}
            for c in sorted(self.commits, key=lambda c: c["date"])])
        dump(out / "github" / "pulls.jsonl", [{
            "repo": p["repo"], "number": p["number"], "title": p["title"], "author_email": _email(p["author"]),
            "created_at": p["created_at"], "merged_at": p["merged_at"], "commit_shas": p["commits"],
            "reviews": [{"reviewer_email": _email(r["reviewer"]), "submitted_at": r["submitted_at"], "state": r["state"]}
                        for r in p["reviews"]]} for p in sorted(self.pulls, key=lambda p: (p["repo"], p["number"]))])

        # Customer-facing systems.
        tickets = []
        for t in portfolio.tickets:
            row = dict(t)
            if row["linked_bug"]:
                row["linked_bug"] = {**{k: v for k, v in t["linked_bug"].items() if k != "_bug"},
                                     "key": t["linked_bug"]["_bug"]["key"]}
            tickets.append(row)
        dump(out / "support" / "tickets.jsonl", sorted(tickets, key=lambda t: t["id"]))
        dump(out / "product" / "usage.jsonl", portfolio.usage)
        dump(out / "billing" / "invoices.jsonl", portfolio.invoices)
        dump(out / "billing" / "wallets.jsonl", portfolio.wallets)
        dump(out / "conversations" / "customer.jsonl", sorted(portfolio.conversations, key=lambda c: c["occurred_at"]))
        dump(out / "roadmap" / "items.jsonl", stories["roadmap"])
        dump(out / "calendar" / "events.jsonl", stories["calendar"])
        for cid, call in stories["calls"].items():
            (out / "calls" / f"{cid}.json").write_text(json.dumps(call, ensure_ascii=False, default=iso, indent=1) + "\n")
        dump(out / "memory" / "episodes.jsonl", stories["episodes"])

        # Seed-mode extraction labels. Kept apart from the raw exports on purpose.
        items = [{"id": d["id"], "kind": "decision", "summary": d["summary"], "rationale": d["rationale"],
                  "decidedAt": d["decidedAt"], "about": [(SYSTEMS.get(a) or CUSTOMERS[a])["name"] for a in d["about"]]}
                 for d in world.DECISIONS]
        items += [{"id": w["id"], "kind": "workaround", "summary": w["summary"], "rationale": None, "decidedAt": None,
                   "about": [(SYSTEMS.get(a) or CUSTOMERS[a])["name"] for a in w["about"]]} for w in world.WORKAROUNDS]
        items += stories["promises"] + stories["playbooks"]
        dump(out / "annotations" / "items.jsonl", items)
        dump(out / "annotations" / "extractions.jsonl", [{
            "source_type": e["source_type"], "source_id": e["source_id"],
            "annotations": [{"kind": a["kind"], "item": a["item"],
                             "roles": {_email(p): r for p, r in a["roles"].items()}} for a in e["annotations"]]}
            for e in self.extractions])

        manifest = {"seed": SEED, "company": world.COMPANY, "generated_for": DEMO_NOW.isoformat(),
                    "counts": {"people": len(people), "slack_messages": len(self.messages),
                               "slack_channels": len(CHANNELS), "docs": len(pages), "jira_issues": len(issues),
                               "meetings": len(meetings), "commits": len(self.commits), "pulls": len(self.pulls),
                               "accounts": len(portfolio.accounts), "support_tickets": len(portfolio.tickets),
                               "bugs": len(portfolio.bugs), "usage_rows": len(portfolio.usage),
                               "invoices": len(portfolio.invoices), "conversations": len(portfolio.conversations),
                               "promises": len(stories["promises"]), "roadmap_items": len(stories["roadmap"]),
                               "calendar_events": len(stories["calendar"])},
                    "note": "Synthetic data. Cheerio's product is real; every person, customer, message and number is invented."}
        digest = hashlib.sha256()
        for f in sorted(out.rglob("*.json*")):
            if f.name != "manifest.json":
                digest.update(f.read_bytes())
        manifest["sha256"] = digest.hexdigest()
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        return manifest


def generate(out: Path = DATA_DIR) -> dict:
    g = Gen()
    g.planted()
    g.bulk_docs()
    g.activity()
    g.pull_requests()
    g.bulk_meetings()
    g.filler()
    return g.write(out)


if __name__ == "__main__":
    print(json.dumps(generate(), indent=2))
