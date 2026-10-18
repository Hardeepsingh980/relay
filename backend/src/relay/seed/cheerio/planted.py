"""Hand-written sources that carry the Cheerio storylines (all fictional).

Each planted source may carry `annotations`: the decisions/workarounds a careful
reader would extract from it, with the role each participant played. The seed
extractor uses these; the Gemini extractor has to find them from the text.
"""

from __future__ import annotations

from datetime import datetime

from ...config import IST


def at(day: str, hm: str = "10:00") -> datetime:
    return datetime.fromisoformat(f"{day}T{hm}:00").replace(tzinfo=IST)


def ann(kind: str, item: str, roles: dict[str, str]) -> dict:
    return {"kind": kind, "item": item, "roles": roles}


def notes(overview: list[tuple[str, str]], actions: dict[str, list[str]]) -> str:
    """Meeting notes in the Fireflies layout the team uses: overview bullets, then action items by owner."""
    out = ["Overview"] + [f"- **{k}:** {v}" for k, v in overview]
    if actions:
        out += ["", "Action Items"]
        for owner, items in actions.items():
            out.append(f"**{owner}**")
            out += [f"- {i}" for i in items]
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Slack threads: (channel, [(person, minutes_after_root, text)], annotations)
# The first tuple is the root message.
# ---------------------------------------------------------------------------

SLACK_THREADS: list[dict] = [
    # Why settlement runs at 6 AM (decision, Rahul only)
    {"channel": "messaging", "start": at("2026-04-08", "10:12"), "messages": [
        ("p-kavya", 0, "Why does the settlement job kick off at 6 AM? Finance wants invoices out at midnight so customers see them first thing."),
        ("p-rahul", 6, "Pls don't 🙂 Meta's pricing analytics are on UTC days, so yesterday only closes at 05:30 IST. When we ran at midnight we billed partial days, and Finance had to re-issue invoices twice in March."),
        ("p-rahul", 7, "06:00 gives Meta's export half an hour of slack and we still finish before the 08:00 morning sends. I moved the cron in wallet-settlement last night (commit 4e1c9a2)."),
        ("p-kavya", 12, "Makes sense, thanks. Is that written down anywhere?"),
        ("p-rahul", 15, "Not really, it's in my head and in this thread. I'll add it to the runbook."),
    ], "annotations": [ann("decision", "dec-settle-6am", {"p-rahul": "proposer", "p-kavya": "ack"})]},

    # Stale settlement lock (workaround; the runbook is out of date)
    {"channel": "messaging", "start": at("2026-08-27", "06:47"), "messages": [
        ("b-betterstack", 0, "[Better Stack] wallet-settlement FAILED: run 8812 aborted, lock held by previous run (settlement_locks)."),
        ("p-neha", 9, "Settlement failed this morning with 'lock held'. Followed the runbook and re-ran but it fails the same way."),
        ("p-rahul", 16, "The runbook is out of date, sorry. The previous run crashed without releasing its row in settlement_locks. Delete the stale row first: `DELETE FROM settlement_locks WHERE run_id = 8812 AND released_at IS NULL;`"),
        ("p-rahul", 17, "Then resume with `wallet-settlement run --resume-from 8812`. A plain re-run starts a fresh run and debits every wallet twice for the same day."),
        ("p-neha", 31, "That worked, thank you! 🙏"),
    ], "annotations": [ann("workaround", "wk-settle-lock", {"p-rahul": "author", "p-neha": "ack"})]},
    {"channel": "messaging", "start": at("2026-09-24", "06:35"), "messages": [
        ("p-omar", 0, "wallet-settlement is stuck on 'lock held' again (run 9140). The runbook says to just re-run it?"),
        ("p-rahul", 11, "Same fix as last month: clear the stale row in settlement_locks for 9140, then `wallet-settlement run --resume-from 9140`. Don't start a fresh run, it double-debits wallets."),
        ("p-omar", 25, "Done, it's green now. Thanks"),
    ], "annotations": [ann("workaround", "wk-settle-lock", {"p-rahul": "author", "p-omar": "ack"})]},

    # Ledger replay after deploys (workaround, obsolete since CHEER-2412 shipped)
    {"channel": "messaging", "start": at("2026-05-14", "11:20"), "messages": [
        ("p-arjun", 0, "Recon is showing ~300 mismatches after this morning's wallet-ledger deploy. Real or noise?"),
        ("p-rahul", 8, "Noise. The ledger drops debit events while it deploys (there's no outbox), so recon never sees them. Run `recon-cli replay --source ledger --window 24h` and they clear."),
        ("p-arjun", 20, "Cleared. We should fix the root cause though, I'll write up an outbox RFC."),
    ], "annotations": [ann("workaround", "wk-ledger-replay", {"p-rahul": "author", "p-arjun": "ack"})]},
    {"channel": "messaging", "start": at("2026-07-02", "10:05"), "messages": [
        ("p-kavya", 0, "Recon dashboard went red right after the ledger deploy. Is it the replay thing again?"),
        ("p-rahul", 5, "Yep. `recon-cli replay --source ledger --window 24h`. It goes away for good once Arjun's outbox lands."),
        ("p-kavya", 14, "Ran it, all matched now 👍"),
    ], "annotations": [ann("workaround", "wk-ledger-replay", {"p-rahul": "author", "p-kavya": "ack"})]},

    # Kairo webhook signatures (decision with Kairo, Rahul only)
    {"channel": "ext-kairo-living", "start": at("2026-06-17", "16:40"), "messages": [
        ("c-siddharth", 0, "Hi Rahul, our webhook signer is still on HMAC-SHA1. The SHA-256 (v2) cutover has slipped to Q1 next year. Can you keep accepting v1 until then?"),
        ("p-rahul", 14, "Yes. We'll keep the v1 verifier enabled on the kairo-erp-bridge for Kairo only, behind the `kairo_hmac_v1` flag. Everyone else stays on v2. I'll get a compliance exception logged on our side."),
        ("p-rahul", 15, "Pooja, could you send the v2 test vectors when they're ready? We'll run both verifiers side by side for a week before switching."),
        ("c-pooja", 40, "Will do, probably early January."),
    ], "annotations": [ann("decision", "dec-kairo-hmac", {"p-rahul": "proposer"})]},

    # Staging VPN reset: widely known (decoy workaround)
    {"channel": "eng", "start": at("2026-04-20", "15:02"), "messages": [
        ("p-ritu", 0, "Staging VPN keeps dropping every few minutes, anyone else?"),
        ("p-rahul", 4, "Happens when the Tailscale node key gets stale. `tailscale down && tailscale up --reset` fixes it for me."),
        ("p-ritu", 9, "That did it, thanks"),
    ], "annotations": [ann("workaround", "wk-vpn-reset", {"p-rahul": "author", "p-ritu": "ack"})]},
    {"channel": "eng", "start": at("2026-06-02", "11:40"), "messages": [
        ("p-gautam", 0, "Can't reach staging, VPN connected but nothing resolves?"),
        ("p-sana", 3, "Reset Tailscale: `tailscale down && tailscale up --reset`. If that fails, re-auth from the admin console, the node key probably expired."),
        ("p-gautam", 8, "Fixed, ty"),
    ], "annotations": [ann("workaround", "wk-vpn-reset", {"p-sana": "author", "p-gautam": "ack"})]},
    {"channel": "eng", "start": at("2026-07-15", "09:55"), "messages": [
        ("p-omar", 0, "First week question: my staging VPN disconnects constantly. Is that normal?"),
        ("p-tom", 6, "Known issue, run `tailscale up --reset` after `tailscale down`. It's in the dev setup doc under VPN too."),
        ("p-omar", 10, "Works now 🙏"),
    ], "annotations": [ann("workaround", "wk-vpn-reset", {"p-tom": "applier", "p-omar": "ack"})]},
    {"channel": "eng", "start": at("2026-09-09", "14:20"), "messages": [
        ("p-kavya", 0, "VPN to staging is dead again for me"),
        ("p-ritu", 2, "Do the Tailscale reset (`tailscale down && tailscale up --reset`). Sana says the node keys rotate every 30 days now."),
        ("p-kavya", 7, "Yep, back. Thanks"),
    ], "annotations": [ann("workaround", "wk-vpn-reset", {"p-ritu": "applier", "p-kavya": "ack"})]},

    # Vikram: Kong plugin changes need a rolling restart
    {"channel": "platform", "start": at("2026-05-19", "12:10"), "messages": [
        ("p-ritu", 0, "Changed the rate-limit plugin config on the gateway and ran `kong reload`, but the old limits are still applied. Am I missing a step?"),
        ("p-vikram", 7, "Reload doesn't rebuild the plugin iterator for plugins with shared dicts. Do a rolling restart of the Kong pods (`kubectl rollout restart deploy/kong -n edge`). Reload only picks up route/service changes."),
        ("p-ritu", 18, "Restarted, new limits are live. Thanks!"),
    ], "annotations": [ann("workaround", "wk-kong-reload", {"p-vikram": "author", "p-ritu": "ack"})]},
    {"channel": "platform", "start": at("2026-08-11", "16:30"), "messages": [
        ("p-tom", 0, "Kong plugin change isn't taking effect after reload?"),
        ("p-vikram", 5, "Same gotcha as Ritu hit in May. Plugins with shared dicts need a rolling restart, `kong reload` isn't enough."),
        ("p-tom", 12, "👍 done"),
    ], "annotations": [ann("workaround", "wk-kong-reload", {"p-vikram": "author", "p-tom": "ack"})]},

    # Vikram: CI runner disk
    {"channel": "platform", "start": at("2026-06-23", "10:45"), "messages": [
        ("b-betterstack", 0, "[Better Stack] github actions: 6 jobs queued > 15m, runner ci-runner-03 out of disk."),
        ("p-tom", 6, "ci-runner-03 is full again, should I just recycle the VM?"),
        ("p-vikram", 10, "Don't recycle it, the warm cache is what keeps builds under 8 minutes. Run `docker builder prune --filter until=72h -f` on the runner, then `docker image prune -a --filter until=168h`. It frees ~120 GB."),
        ("p-tom", 21, "Freed 118 GB, queue is draining."),
    ], "annotations": [ann("workaround", "wk-ci-disk", {"p-vikram": "author", "p-tom": "ack"})]},
    {"channel": "platform", "start": at("2026-09-15", "09:20"), "messages": [
        ("b-betterstack", 0, "[Better Stack] github actions: runner ci-runner-01 out of disk."),
        ("p-vikram", 12, "Pruned the builder cache on ci-runner-01 (72h filter). We should automate this, but the prune flags matter: pruning everything kills the warm cache."),
    ], "annotations": [ann("workaround", "wk-ci-disk", {"p-vikram": "author"})]},

    # Meera: finance snapshot full refresh when Meta's pricing export is late
    {"channel": "eng", "start": at("2026-06-01", "09:35"), "messages": [
        ("p-lina", 0, "May revenue in the month-end report is short by about ₹4L vs Finance's number. Is the finance reporting model broken?"),
        ("p-meera", 9, "Meta's pricing export for the 31st landed late, so the incremental snapshot skipped the last day. Re-run `dbt run --select finance_snapshot --full-refresh`. Always do a full refresh on the 1st if Meta's export was late."),
        ("p-lina", 30, "Numbers tie out now, thanks Meera"),
    ], "annotations": [ann("workaround", "wk-finrep-refresh", {"p-meera": "author", "p-lina": "ack"})]},
    {"channel": "eng", "start": at("2026-09-01", "10:15"), "messages": [
        ("p-lina", 0, "August month-end report looks short again, Meta's export was late last night"),
        ("p-meera", 6, "Same as June: full refresh of finance_snapshot. I'll run it now."),
    ], "annotations": [ann("workaround", "wk-finrep-refresh", {"p-meera": "author", "p-lina": "ack"})]},

    # Dev: pg_cron before restoring staging
    {"channel": "platform", "start": at("2026-07-21", "18:05"), "messages": [
        ("p-sana", 0, "Restored the staging db from last night's snapshot and now every scheduled job ran twice. What did I break?"),
        ("p-dev", 8, "pg_cron comes back enabled from the snapshot and replays missed runs. Before a restore, run `SELECT cron.unschedule(jobid) FROM cron.job;`, restore, then re-apply the schedule from infra/pg_cron.sql."),
        ("p-sana", 20, "Ah, that explains it. Thanks Dev"),
    ], "annotations": [ann("workaround", "wk-pgcron-restore", {"p-dev": "author", "p-sana": "ack"})]},
]

# Flaky test: a recurring thread every other week, always answered by Rahul.
_FLAKY_ASKERS = ["p-omar", "p-kavya", "p-neha", "p-arjun", "p-zoya", "p-omar", "p-kavya",
                 "p-gautam", "p-neha", "p-omar", "p-rohan", "p-kavya"]
_FLAKY_ROOTS = [
    "Deploy blocked again: `test_concurrent_send_refund` failed on the messaging-api build. Looks unrelated to my change?",
    "messaging-api build red on `test_concurrent_send_refund`, passed locally. Flaky?",
    "Anyone seen `test_concurrent_send_refund` fail with a Redis key collision? It's blocking my deploy.",
]
_FLAKY_FIXES = [
    "It's the flaky one. The test shares a Redis db with the idempotency tests, so it races when pytest-randomly puts them next to each other. Re-run just that job with `pytest -p no:randomly -k concurrent_send` and it passes.",
    "Same flake. Re-run the job with `-p no:randomly`. The real fix is giving that test its own Redis db (CHEER-2449), I haven't had time.",
    "Known flake: random test ordering plus a shared Redis db. Re-run with `pytest -p no:randomly -k concurrent_send_refund`, don't retry the whole pipeline.",
]
for i, day in enumerate(["2026-05-06", "2026-05-20", "2026-06-03", "2026-06-17", "2026-07-01", "2026-07-15",
                         "2026-07-29", "2026-08-12", "2026-08-26", "2026-09-09", "2026-09-23", "2026-10-07"]):
    asker = _FLAKY_ASKERS[i]
    SLACK_THREADS.append({
        "channel": "eng", "start": at(day, f"{11 + i % 5}:{(i * 7) % 60:02d}"), "messages": [
            (asker, 0, _FLAKY_ROOTS[i % 3]),
            ("p-rahul", 4 + i % 6, _FLAKY_FIXES[i % 3]),
            (asker, 15 + i % 9, "Re-ran it, green 👍" if i % 2 else "Thanks, that worked"),
        ],
        "annotations": [ann("workaround", "wk-flaky-test", {"p-rahul": "author", asker: "ack"})],
    })

# Kairo's month-end order file BOM: every month-end, Rahul fixes it.
for day, oncall, fname in [("2026-07-01", "p-sana", "KAIRO_ORDERS_20260630.csv"),
                           ("2026-08-01", "p-dev", "KAIRO_ORDERS_20260731.csv"),
                           ("2026-09-01", "p-sana", "KAIRO_ORDERS_20260831.csv"),
                           ("2026-10-01", "p-tom", "KAIRO_ORDERS_20260930.csv")]:
    SLACK_THREADS.append({
        "channel": "incidents", "start": at(day, "02:31"), "messages": [
            ("b-betterstack", 0, f"[Better Stack] kairo-erp-bridge: order file import failed: {fname}: invalid header '\\ufefforder_id'"),
            (oncall, 7, "kairo bridge import is failing on Kairo's month-end file, the header looks garbled. Anyone know this one?"),
            ("p-rahul", 15, f"Month-end files from Kairo come with a UTF-8 BOM and CRLF line endings (their month-end export runs on a different system). Run `bridge-cli normalize --strip-bom --crlf {fname}` and re-import. It happens every month-end."),
            (oncall, 24, "👍 import went through"),
        ],
        "annotations": [ann("workaround", "wk-kairo-bom", {"p-rahul": "author", oncall: "ack"})],
    })

# ---------------------------------------------------------------------------
# Internal meetings (Fireflies-style notes)
# ---------------------------------------------------------------------------

MEETINGS: list[dict] = [
    {"id": "mtg-2026-03-12-messaging-arch", "title": "Messaging architecture review", "start": at("2026-03-12", "15:00"),
     "attendees": ["p-priya", "p-rahul", "p-arjun", "p-neha", "p-kavya", "p-isha"],
     "transcript": [
         ("p-priya", "Next item is idempotency key retention for sends. Keys expire after 24 hours right now. Neha, you raised this after the 18 Feb duplicates?"),
         ("p-neha", "Yes. The duplicate order confirmations on the 18th came from Kairo's ERP retrying order events after our keys had already expired. Their customers got the same WhatsApp message two or three times."),
         ("p-rahul", "I want to argue for 72 hours, not 48. Kairo's ERP keeps retrying failed events with backoff for up to 72 hours after an outage. It's in their integration annex, not in any public doc. And their weekend batch means a Friday-night failure can get retried on Monday morning."),
         ("p-arjun", "72 hours triples the Redis footprint for keys though."),
         ("p-rahul", "It's about 1.2 GB at current volume and we have headroom. A duplicate message costs us a refund and the customer's quality rating, far more than memory. Anything shorter than their retry window just moves the bug."),
         ("p-isha", "Do customers see any difference?"),
         ("p-rahul", "No, it's invisible to them. It only changes how long we remember a request."),
         ("p-priya", "OK, let's go with 72 hours. Rahul, can you make the change?"),
         ("p-rahul", "Yes, I'll ship it this week."),
         ("p-priya", "Last thing: Kavya, the campaign cost export, where are we?"),
         ("p-kavya", "Merged yesterday, it goes out with Thursday's release."),
     ],
     "notes": notes([("Idempotency keys", "Retention for send requests goes from 24h to 72h to cover Kairo's ERP retry window."),
                     ("Campaign cost export", "Merged, ships with Thursday's release.")],
                    {"Rahul Verma": ["Update the key TTL in messaging-api this week (03:10)"],
                     "Kavya Reddy": ["Ship the campaign cost export on Thursday (04:05)"]}),
     "annotations": [ann("decision", "dec-idem-72h", {"p-rahul": "proposer", "p-priya": "approver", "p-neha": "ack", "p-arjun": "ack"})]},

    {"id": "mtg-2026-02-20-rca", "title": "RCA review: duplicate Kairo order confirmations (18 Feb)", "start": at("2026-02-20", "11:00"),
     "attendees": ["p-priya", "p-rahul", "p-neha", "p-arjun", "p-sana", "p-isha"],
     "transcript": [
         ("p-priya", "Timeline first. At 21:40 on the 18th Kairo had an ERP outage and queued their order events."),
         ("p-neha", "They came back about 26 hours later and we sent 41,000 order confirmations twice, because the keys had expired."),
         ("p-sana", "Alerting caught it from the duplicate-send monitor about 40 minutes later."),
         ("p-rahul", "We refunded the wallet the same morning and Kairo sent an apology broadcast. I'd like to revisit the key TTL properly at the architecture review rather than patch it today."),
         ("p-priya", "Agreed. Action item: revisit idempotency TTL, owner Rahul."),
     ],
     "notes": notes([("Root cause", "Kairo ERP retries arrived after the 24h idempotency key expiry."),
                     ("Impact", "41,000 duplicate order confirmations; wallet debits refunded the same morning.")],
                    {"Rahul Verma": ["Revisit the idempotency TTL at the architecture review (04:20)"]}),
     "annotations": []},

    {"id": "mtg-2026-06-09-gateway-idem", "title": "Gateway idempotency design", "start": at("2026-06-09", "14:00"),
     "attendees": ["p-vikram", "p-sana", "p-rahul", "p-ritu", "p-priya"],
     "transcript": [
         ("p-vikram", "Proposal: the gateway enforces the Idempotency-Key header on every POST to /messages and rejects duplicates at the edge."),
         ("p-rahul", "I'm in. We can reuse the messaging-api keystore so the 72-hour window stays the same everywhere. Otherwise the gateway and the service disagree about what counts as a duplicate."),
         ("p-sana", "From an ops side I like it, since duplicates never reach the services. We need a dashboard for rejected keys."),
         ("p-vikram", "Agreed. Shared keystore, 72h TTL, a 409 with the original response for duplicates."),
         ("p-ritu", "I can take the Kong plugin."),
         ("p-priya", "Sounds good from Messaging."),
     ],
     "notes": notes([("Decision", "Enforce Idempotency-Key at the gateway using the shared messaging keystore (72h).")],
                    {"Ritu Bansal": ["Build the Kong idempotency plugin (04:40)"], "Sana Mirza": ["Dashboard for rejected keys (03:15)"]}),
     "annotations": [ann("decision", "dec-gateway-idem", {"p-vikram": "proposer", "p-rahul": "co-proposer", "p-sana": "supporter", "p-priya": "ack"})]},

    {"id": "mtg-2026-04-22-cart-timing", "title": "Automations: abandoned-cart timing", "start": at("2026-04-22", "16:00"),
     "attendees": ["p-nikhil", "p-maya", "p-farah", "p-rahul", "p-varun", "p-tara"],
     "transcript": [
         ("p-nikhil", "Our 15-minute first reminder is reaching shoppers who are still in the UPI app. Block rate on cart messages is three times our other templates. I want 30 minutes for the first reminder and a cap of two reminders per checkout."),
         ("p-maya", "We tested it with two brands and recovery stayed flat while blocks dropped by half."),
         ("p-farah", "Fine from Trust as long as send-guard still counts cart reminders toward the weekly marketing cap."),
         ("p-rahul", "On the messaging side nothing changes. We just pass the workflow's frequency key through to send-guard."),
         ("p-varun", "Let's make it the default for new workflows next sprint."),
     ],
     "notes": notes([("Decision", "First abandoned-cart reminder at 30 minutes, at most two reminders per checkout.")],
                    {"Varun Desai": ["Make it the default for new workflows next sprint (05:10)"]}),
     "annotations": [ann("decision", "dec-cart-30min", {"p-nikhil": "proposer", "p-maya": "co-proposer", "p-farah": "supporter", "p-rahul": "supporter"})]},

    {"id": "mtg-2026-07-28-outbox", "title": "RFC-019 review: wallet-ledger transactional outbox", "start": at("2026-07-28", "15:30"),
     "attendees": ["p-arjun", "p-rahul", "p-kavya", "p-priya", "p-neha"],
     "transcript": [
         ("p-arjun", "The ledger drops debit events while it deploys, which is what makes recon report phantom mismatches. The RFC proposes a transactional outbox table and a relay."),
         ("p-rahul", "Strong yes from recon. Today we paper over it with a 24-hour replay after every deploy. With an outbox recon can trust the event stream again."),
         ("p-kavya", "Sounds good to me."),
         ("p-priya", "Approved. Arjun, track it as CHEER-2412."),
     ],
     "notes": notes([("Decision", "Adopt a transactional outbox for wallet-ledger events (CHEER-2412, owner Arjun).")],
                    {"Arjun Nair": ["Implement RFC-019 under CHEER-2412 (02:30)"]}),
     "annotations": [ann("decision", "dec-ledger-outbox", {"p-arjun": "proposer", "p-rahul": "supporter", "p-kavya": "ack", "p-priya": "ack"})]},

    {"id": "mtg-2026-05-05-ci-runners", "title": "CI runner strategy", "start": at("2026-05-05", "11:30"),
     "attendees": ["p-vikram", "p-ishaan", "p-sana", "p-tom"],
     "transcript": [
         ("p-ishaan", "Finance asked whether we can move CI to GitHub-hosted machines to cut the VM bill."),
         ("p-vikram", "I'd keep self-hosted. The deploy pipeline holds the Meta system-user tokens for every customer's WhatsApp number, so hosted machines would put those tokens outside our SOC 2 boundary. The audit cost dwarfs the VM bill."),
         ("p-sana", "Okay, noted."),
         ("p-ishaan", "OK, we stay self-hosted. Vikram, can you write up the cost comparison for Finance?"),
     ],
     "notes": notes([("Decision", "CI stays on self-hosted runners inside the production VPC.")],
                    {"Vikram Sethi": ["Cost comparison for Finance (03:40)"]}),
     "annotations": [ann("decision", "dec-ci-selfhosted", {"p-vikram": "proposer", "p-ishaan": "approver", "p-sana": "ack"})]},

    {"id": "mtg-2026-07-14-freq-cap", "title": "Marketing frequency cap review", "start": at("2026-07-14", "12:00"),
     "attendees": ["p-farah", "p-manish", "p-divya", "p-yusuf"],
     "transcript": [
         ("p-divya", "The June spike in blocks is mostly gone, but some workspaces still blast the same audience every other day."),
         ("p-farah", "I want the default cap at 5 marketing messages per recipient per 7 days. The workspaces that got flagged were sending 6 to 12 a week, and even big festive campaigns rarely need more than 4. Anything lower starts hurting real campaigns."),
         ("p-manish", "Approved from compliance, as long as it's logged as a documented policy change."),
         ("p-divya", "I'll update the quality alerts."),
     ],
     "notes": notes([("Decision", "Default marketing cap: 5 messages per recipient per 7 days.")],
                    {"Divya Krishnan": ["Update the quality alerts (03:05)"]}),
     "annotations": [ann("decision", "dec-freq-cap", {"p-farah": "proposer", "p-manish": "approver", "p-divya": "ack"})]},

    {"id": "mtg-2026-04-30-revenue", "title": "Month-end revenue recognition", "start": at("2026-04-30", "17:00"),
     "attendees": ["p-meera", "p-sunil", "p-lina"],
     "transcript": [
         ("p-sunil", "The auditors flagged that our revenue report books message revenue at wallet top-up."),
         ("p-meera", "I'll switch the finance reporting models to recognise revenue when Meta bills the conversation. Unspent top-ups stay as a wallet liability. It also lines up with the settlement report Finance already reconciles."),
         ("p-sunil", "Approved. Start from April close."),
     ],
     "notes": notes([("Decision", "Message revenue recognised when Meta bills the conversation (Meera).")], {}),
     "annotations": [ann("decision", "dec-revenue-consumption", {"p-meera": "proposer", "p-sunil": "approver", "p-lina": "ack"})]},
]

# ---------------------------------------------------------------------------
# Docs (Confluence-like). `systems` are page labels; `customers` likewise.
# ---------------------------------------------------------------------------

DOCS: list[dict] = [
    {"id": "DOC-1042", "title": "Runbook: Nightly wallet settlement (wallet-settlement)", "space": "MSG", "kind": "runbook",
     "author": "p-rahul", "created": at("2025-09-10"), "updated": at("2026-02-03", "18:20"),
     "systems": ["sys-settlement"], "customers": [],
     "body": """# Runbook: Nightly wallet settlement

Owner: Rahul Verma. Last reviewed 3 Feb 2026.

## Schedule
wallet-settlement runs nightly at 00:00 IST from the `settlement-nightly` cron and normally finishes in 25 to 40 minutes.

## Inputs
- Meta pricing analytics export for the previous day.
- wallet-ledger day-close snapshot.

## If the job fails
1. Check the Better Stack alert for the failing run id.
2. Re-run: `wallet-settlement run --date <YYYY-MM-DD>`.
3. Confirm invoices on the billing dashboard.
4. If it fails twice, page the Messaging on-call.

## Contacts
Escalation: Rahul Verma."""},
    {"id": "DOC-1107", "title": "RFC-014: Billing reconciliation matching strategy", "space": "MSG", "kind": "rfc",
     "author": "p-rahul", "created": at("2026-05-18"), "updated": at("2026-05-20", "12:00"),
     "systems": ["sys-reconciler"], "customers": [],
     "body": """# RFC-014: Billing reconciliation matching strategy

Status: Accepted (20 May 2026). Author: Rahul Verma. Reviewer: Arjun Nair.

## Problem
Exact amount matching between Meta's pricing export and wallet debits flags about 2% of FX-converted debits as mismatches every night.

## Decision
Match on Meta's message ID (wamid) first. Then match on amount with a tolerance of ±0.01 USD, for FX-converted debits only.

## Why
Meta bills in USD and rounds conversions half-up. Wallets debit in INR and the ledger uses banker's rounding (half-even). The two disagree by at most one cent. Widening the tolerance for everything would hide real errors, so it applies to FX debits only.

## Rollout
Shipped in billing-reconciler behind `match_v2`, enabled 28 May."""},
    {"id": "DOC-0981", "title": "Kairo Living integration notes", "space": "MSG", "kind": "design",
     "author": "p-rahul", "created": at("2025-11-03"), "updated": at("2026-01-15", "10:30"),
     "systems": ["sys-kairo-bridge", "sys-msg-api"], "customers": ["cust-kairo"],
     "body": """# Kairo Living integration notes

- Order files: `KAIRO_ORDERS_<YYYYMMDD>.csv`, pulled by kairo-erp-bridge from `sftp.kairoliving.example` at 01:50.
- Webhooks: order and delivery events from their ERP, signed by Kairo, sent through messaging-api as order-update templates.
- Escalation: Siddharth Kale (Integration Lead), Pooja Natarajan (Platform Engineer). Shared channel #ext-kairo-living.
- Technical contact on our side: Rahul Verma."""},
    {"id": "DOC-0612", "title": "billing-reconciler: architecture overview", "space": "MSG", "kind": "design",
     "author": "p-karan", "created": at("2025-03-04"), "updated": at("2025-08-12", "16:00"),
     "systems": ["sys-reconciler"], "customers": [],
     "body": """# billing-reconciler: architecture overview

The service imports Meta's daily pricing export, normalises it into billable lines and matches them against wallet debits. Mismatches are written to `recon_mismatches` and surfaced on the recon dashboard.

Components: importer, matcher, mismatch writer, `recon-cli` for operators."""},
    {"id": "DOC-1063", "title": "messaging-api: idempotency keys", "space": "MSG", "kind": "design",
     "author": "p-neha", "created": at("2026-03-18"), "updated": at("2026-03-20", "14:10"),
     "systems": ["sys-msg-api"], "customers": [],
     "body": """# messaging-api: idempotency keys

Clients send an `Idempotency-Key` header on POST /messages. Keys and the original response live in Redis with a 72-hour TTL. A repeated key returns the stored response with status 200 and header `Idempotent-Replayed: true`."""},
    {"id": "DOC-1031", "title": "RCA: duplicate Kairo order confirmations (18 Feb 2026)", "space": "MSG", "kind": "postmortem",
     "author": "p-priya", "created": at("2026-02-19"), "updated": at("2026-02-20", "13:00"),
     "systems": ["sys-msg-api", "sys-ledger"], "customers": ["cust-kairo"],
     "body": """# RCA: duplicate Kairo order confirmations (18 Feb 2026)

Impact: 41,000 order confirmations sent twice; wallet debits refunded within 12 hours.
Root cause: Kairo ERP retries arrived after the 24h idempotency key expiry.
Action items: revisit idempotency TTL (owner: Rahul Verma)."""},
    {"id": "DOC-1188", "title": "RFC-019: wallet-ledger transactional outbox", "space": "MSG", "kind": "rfc",
     "author": "p-arjun", "created": at("2026-07-20"), "updated": at("2026-07-29", "11:00"),
     "systems": ["sys-ledger", "sys-reconciler"], "customers": [],
     "body": """# RFC-019: wallet-ledger transactional outbox

Status: Accepted. Tracking: CHEER-2412.

wallet-ledger writes events to an `outbox` table in the same transaction as the ledger entry. A relay publishes them with at-least-once delivery, keyed by event id. This removes the event loss during deploys that causes phantom reconciliation mismatches."""},
    {"id": "DOC-0870", "title": "Messaging team onboarding", "space": "MSG", "kind": "onboarding",
     "author": "p-priya", "created": at("2025-05-12"), "updated": at("2025-06-30", "10:00"),
     "systems": ["sys-msg-api", "sys-ledger", "sys-reconciler", "sys-settlement"], "customers": [],
     "body": """# Messaging team onboarding

1. Get access to GitHub, Better Stack and the messaging Grafana folder.
2. Read the wallet-ledger and messaging-api READMEs.
3. Shadow one on-call week before joining the rotation.
4. Ask Rahul about the reconciler and settlement."""},
    {"id": "DOC-1120", "title": "api-gateway: Idempotency-Key enforcement", "space": "PLAT", "kind": "design",
     "author": "p-vikram", "created": at("2026-06-11"), "updated": at("2026-06-15", "15:00"),
     "systems": ["sys-gateway", "sys-msg-api"], "customers": [],
     "body": """# api-gateway: Idempotency-Key enforcement

The gateway enforces `Idempotency-Key` on POST /messages using the shared messaging keystore (72h TTL). Duplicates get a 409 with the original response. Plugin owner: Ritu Bansal."""},
    {"id": "DOC-0745", "title": "CI pipeline guide", "space": "PLAT", "kind": "runbook",
     "author": "p-vikram", "created": at("2025-08-01"), "updated": at("2025-11-20", "12:00"),
     "systems": ["sys-ci"], "customers": [],
     "body": """# CI pipeline guide

Runners are self-hosted VMs (ci-runner-01..04) inside the production VPC. Workflows live in `.github/workflows/`. Production deploys need the QA PASSED label and an approval step."""},
    {"id": "DOC-1015", "title": "send-guard: policy and frequency rules", "space": "TRUST", "kind": "design",
     "author": "p-farah", "created": at("2026-02-25"), "updated": at("2026-07-16", "10:00"),
     "systems": ["sys-sendguard"], "customers": [],
     "body": """# send-guard: policy and frequency rules

Rules run on every campaign before it sends, in priority order. Default marketing cap: 5 messages per recipient per 7 days (since July 2026). Trust can raise the cap per workspace for approved festive campaigns."""},
    {"id": "DOC-1092", "title": "Finance reporting models", "space": "DATA", "kind": "design",
     "author": "p-meera", "created": at("2026-05-02"), "updated": at("2026-05-06", "09:00"),
     "systems": ["sys-finrep", "sys-dwh"], "customers": [],
     "body": """# Finance reporting models

Message revenue is recognised when Meta bills the conversation, not at wallet top-up (since April 2026 close). Unspent top-ups are reported as wallet liability. Models: `finance_snapshot`, `revenue_monthly`, `wallet_liability_daily`."""},
    {"id": "DOC-0702", "title": "Developer environment setup", "space": "ENG", "kind": "onboarding",
     "author": "p-tom", "created": at("2025-07-14"), "updated": at("2026-07-16", "11:00"),
     "systems": ["sys-staging"], "customers": [],
     "body": """# Developer environment setup

1. Install the Cheerio CLI and Tailscale.
2. VPN: if staging drops, run `tailscale down && tailscale up --reset`.
3. Request staging DB read access in #platform."""},
    {"id": "DOC-0655", "title": "On-call policy", "space": "ENG", "kind": "policy",
     "author": "p-ishaan", "created": at("2025-04-01"), "updated": at("2026-03-02", "10:00"),
     "systems": [], "customers": [],
     "body": "# On-call policy\n\nTwo leads cover weekends and acknowledge pages within 15 minutes. Every incident gets an RCA doc and any untracked fix gets a ticket. On-call handover is on Mondays at 11:00."},
    {"id": "DOC-1150", "title": "Glowra Beauty account plan", "space": "CS", "kind": "design",
     "author": "p-kabir", "created": at("2026-03-10"), "updated": at("2026-06-24", "10:00"),
     "systems": [], "customers": ["cust-glowra"],
     "body": "# Glowra Beauty account plan\n\nFestive calendar, broadcast volumes, the weekly cap exception process, and the escalation path to Sofia Mathew."},
]

# ---------------------------------------------------------------------------
# Tickets (Jira project "Cheerio Dev")
# ---------------------------------------------------------------------------

TICKETS: list[dict] = [
    {"key": "CHEER-2412", "summary": "wallet-ledger: transactional outbox for event emission",
     "status": "Done", "assignee": "p-arjun", "reporter": "p-arjun", "components": ["sys-ledger"],
     "created": at("2026-07-29"), "resolved": at("2026-09-15", "17:30"), "customer": None,
     "description": "Implement RFC-019. Removes event loss during deploys (and the 24h recon replay we do after every ledger deploy).",
     "comments": [("p-arjun", at("2026-09-15", "17:30"), "Shipped to prod. Recon replay after deploys is no longer needed.")]},
    {"key": "CHEER-2433", "summary": "Compliance exception: Kairo HMAC-SHA1 webhook signatures",
     "status": "Done", "assignee": "p-manish", "reporter": "p-rahul", "components": ["sys-kairo-bridge"],
     "created": at("2026-06-18"), "resolved": at("2026-06-25"), "customer": "cust-kairo",
     "description": "Kairo cannot sign with SHA-256 until Q1 2027. Keep v1 verification for Kairo only, behind kairo_hmac_v1.",
     "comments": [("p-manish", at("2026-06-25"), "Exception approved until 31 Mar 2027.")]},
    {"key": "CHEER-2449", "summary": "messaging-api: give test_concurrent_send_refund its own Redis db",
     "status": "To Do", "assignee": "p-rahul", "reporter": "p-rahul", "components": ["sys-msg-api"],
     "created": at("2026-06-17"), "resolved": None, "customer": None,
     "description": "The test shares a Redis db with the idempotency suite and fails under random ordering about once a week, blocking deploys.",
     "comments": []},
    {"key": "CHEER-2458", "summary": "wallet-settlement: alert when a lock is older than 30 minutes",
     "status": "To Do", "assignee": "p-rahul", "reporter": "p-neha", "components": ["sys-settlement"],
     "created": at("2026-08-28"), "resolved": None, "customer": None,
     "description": "Stale rows in settlement_locks block the nightly run. Alert before the job fails.",
     "comments": []},
    {"key": "CHEER-2466", "summary": "kairo-erp-bridge: handle partial Kairo order files",
     "status": "In Progress", "assignee": "p-rahul", "reporter": "p-rahul", "components": ["sys-kairo-bridge"],
     "created": at("2026-09-08"), "resolved": None, "customer": "cust-kairo",
     "description": "Detect truncated order files and wait for the complete file instead of sending delivery updates early.",
     "comments": [("p-rahul", at("2026-10-12"), "Detection is done; retry/wait logic still to do.")]},
    {"key": "CHEER-2471", "summary": "kairo-erp-bridge: migrate Kairo webhooks to HMAC-SHA256 (v2)",
     "status": "Backlog", "assignee": "p-rahul", "reporter": "p-rahul", "components": ["sys-kairo-bridge"],
     "created": at("2026-06-18"), "resolved": None, "customer": "cust-kairo",
     "description": "Run v1 and v2 verifiers side by side for a week once Kairo sends test vectors (expected Jan 2027), then remove kairo_hmac_v1.",
     "comments": []},
    {"key": "CHEER-2480", "summary": "wallet-settlement: add --dry-run to --resume-from",
     "status": "To Do", "assignee": None, "reporter": "p-priya", "components": ["sys-settlement"],
     "created": at("2026-10-14"), "resolved": None, "customer": None, "labels": ["good-first-issue"],
     "description": "Print which wallets a resume would debit without writing anything. A good starter ticket for a new teammate.",
     "comments": []},
]

# ---------------------------------------------------------------------------
# Specific commits (counted inside each author's totals)
# ---------------------------------------------------------------------------

COMMITS: list[dict] = [
    {"repo": "cheerio/wallet-settlement", "author": "p-rahul", "date": at("2026-04-07", "23:40"),
     "sha": "4e1c9a2f7b0d", "message": "Move nightly settlement cron to 06:00 IST (Meta's pricing day closes 05:30 IST)",
     "annotations": [ann("decision", "dec-settle-6am", {"p-rahul": "proposer"})]},
    {"repo": "cheerio/messaging-api", "author": "p-rahul", "date": at("2026-03-16", "19:05"),
     "sha": "9b77e01c3a54", "message": "Extend send idempotency key TTL to 72h (messaging arch review, 12 Mar)",
     "annotations": []},
    {"repo": "cheerio/billing-reconciler", "author": "p-rahul", "date": at("2026-05-28", "18:10"),
     "sha": "c0ffee14ab12", "message": "match_v2: message ID first, ±0.01 USD tolerance for FX debits (RFC-014)",
     "annotations": [ann("decision", "dec-recon-matching", {"p-rahul": "proposer"})]},
]

# RFC-014 records the decision; Arjun reviewed it.
DOC_ANNOTATIONS = {
    "DOC-1107": [ann("decision", "dec-recon-matching", {"p-rahul": "proposer", "p-arjun": "ack"})],
    "DOC-1188": [ann("decision", "dec-ledger-outbox", {"p-arjun": "proposer"})],
    "DOC-1120": [ann("decision", "dec-gateway-idem", {"p-vikram": "proposer"})],
    "DOC-1015": [ann("decision", "dec-freq-cap", {"p-farah": "proposer"})],
    "DOC-1092": [ann("decision", "dec-revenue-consumption", {"p-meera": "proposer"})],
    "DOC-0702": [ann("workaround", "wk-vpn-reset", {"p-tom": "applier"})],
}
