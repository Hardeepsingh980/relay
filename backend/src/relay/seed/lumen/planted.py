"""Hand-written sources that carry the Lumen storylines.

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


# ---------------------------------------------------------------------------
# Slack threads: (channel, [(person, minutes_after_root, text)], annotations)
# The first tuple is the root message.
# ---------------------------------------------------------------------------

SLACK_THREADS: list[dict] = [
    # Why settlement runs at 2 AM (decision, Rahul only)
    {"channel": "payments", "start": at("2026-04-08", "10:12"), "messages": [
        ("p-kavya", 0, "Why does the settlement job kick off at 2 AM? I was looking at moving it to midnight so Finance gets numbers earlier."),
        ("p-rahul", 6, "Please don't 🙂 Acme drops the daily statement file on the SFTP bridge around 01:30 IST. When we ran at midnight we were reconciling against the previous day's partial file, and Finance had to re-close the books twice in March."),
        ("p-rahul", 7, "02:00 gives Acme half an hour of slack and we still finish before the 06:00 ledger close. I moved the cron in settlement-batch last night (commit 4e1c9a2)."),
        ("p-kavya", 12, "Makes sense, thanks. Is that written down anywhere?"),
        ("p-rahul", 15, "Not really, it's in my head and in this thread. I'll add it to the runbook."),
    ], "annotations": [ann("decision", "dec-settle-2am", {"p-rahul": "proposer", "p-kavya": "ack"})]},

    # Stale settlement lock (workaround; the runbook is out of date)
    {"channel": "payments", "start": at("2026-08-27", "02:47"), "messages": [
        ("b-pagerduty", 0, "[PagerDuty] settlement-batch FAILED: batch 8812 aborted, lock held by previous run (settlement_locks)."),
        ("p-neha", 9, "Settlement failed overnight with 'lock held'. Followed the runbook and re-ran but it fails the same way."),
        ("p-rahul", 16, "The runbook is out of date, sorry. The previous run crashed without releasing its row in settlement_locks. Delete the stale row first: `DELETE FROM settlement_locks WHERE batch_id = 8812 AND released_at IS NULL;`"),
        ("p-rahul", 17, "Then resume with `settlement-batch run --resume-from 8812`. A plain re-run starts a new batch and double-counts the payouts that already went out."),
        ("p-neha", 31, "That worked, thank you! 🙏"),
    ], "annotations": [ann("workaround", "wk-settle-lock", {"p-rahul": "author", "p-neha": "ack"})]},
    {"channel": "payments", "start": at("2026-09-24", "03:05"), "messages": [
        ("p-omar", 0, "settlement-batch is stuck on 'lock held' again (batch 9140). The runbook says to just re-run it?"),
        ("p-rahul", 11, "Same fix as last month: clear the stale row in settlement_locks for 9140, then `settlement-batch run --resume-from 9140`. Don't start a fresh run, it double-counts payouts."),
        ("p-omar", 25, "Done, it's green now. Thanks"),
    ], "annotations": [ann("workaround", "wk-settle-lock", {"p-rahul": "author", "p-omar": "ack"})]},

    # Ledger replay after deploys (workaround, obsolete since LUM-412 shipped)
    {"channel": "payments", "start": at("2026-05-14", "11:20"), "messages": [
        ("p-arjun", 0, "Recon is showing ~300 mismatches after this morning's ledger-service deploy. Real or noise?"),
        ("p-rahul", 8, "Noise. The ledger drops events while it deploys (there's no outbox), so recon never sees them. Run `recon-cli replay --source ledger --window 24h` and they clear."),
        ("p-arjun", 20, "Cleared. We should fix the root cause though, I'll write up an outbox RFC."),
    ], "annotations": [ann("workaround", "wk-ledger-replay", {"p-rahul": "author", "p-arjun": "ack"})]},
    {"channel": "payments", "start": at("2026-07-02", "10:05"), "messages": [
        ("p-kavya", 0, "Recon dashboard went red right after the ledger deploy. Is it the replay thing again?"),
        ("p-rahul", 5, "Yep. `recon-cli replay --source ledger --window 24h`. It goes away for good once Arjun's outbox lands."),
        ("p-kavya", 14, "Ran it, all matched now 👍"),
    ], "annotations": [ann("workaround", "wk-ledger-replay", {"p-rahul": "author", "p-kavya": "ack"})]},

    # Acme webhook signatures (decision with Acme, Rahul only)
    {"channel": "ext-acme-bank", "start": at("2026-06-17", "16:40"), "messages": [
        ("c-daniel", 0, "Hi Rahul, our webhook signer is still on HMAC-SHA1. The SHA-256 (v2) cutover has slipped to Q1 next year. Can you keep accepting v1 until then?"),
        ("p-rahul", 14, "Yes. We'll keep the v1 verifier enabled on the acme-sftp-bridge for Acme only, behind the `acme_hmac_v1` flag. Everyone else stays on v2. I'll get a compliance exception logged on our side."),
        ("p-rahul", 15, "Mei, could you send the v2 test vectors when they're ready? We'll run both verifiers side by side for a week before switching."),
        ("c-mei", 40, "Will do, probably early January."),
    ], "annotations": [ann("decision", "dec-acme-hmac", {"p-rahul": "proposer"})]},

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
        ("b-pagerduty", 0, "[PagerDuty] buildkite: 6 jobs waiting > 15m, agent ci-runner-03 out of disk."),
        ("p-tom", 6, "ci-runner-03 is full again, should I just recycle the VM?"),
        ("p-vikram", 10, "Don't recycle it, the warm cache is what keeps builds under 8 minutes. Run `docker builder prune --filter until=72h -f` on the runner, then `docker image prune -a --filter until=168h`. It frees ~120 GB."),
        ("p-tom", 21, "Freed 118 GB, queue is draining."),
    ], "annotations": [ann("workaround", "wk-ci-disk", {"p-vikram": "author", "p-tom": "ack"})]},
    {"channel": "platform", "start": at("2026-09-15", "09:20"), "messages": [
        ("b-pagerduty", 0, "[PagerDuty] buildkite: agent ci-runner-01 out of disk."),
        ("p-vikram", 12, "Pruned the builder cache on ci-runner-01 (72h filter). We should automate this, but the prune flags matter: pruning everything kills the warm cache."),
    ], "annotations": [ann("workaround", "wk-ci-disk", {"p-vikram": "author"})]},

    # Meera: finance snapshot full refresh when Acme files are late
    {"channel": "eng", "start": at("2026-06-01", "09:35"), "messages": [
        ("p-lina", 0, "May revenue in the month-end report is short by about ₹40L vs Finance's number. Is the finance reporting model broken?"),
        ("p-meera", 9, "Acme's month-end statement landed late, so the incremental snapshot skipped the last day. Re-run `dbt run --select finance_snapshot --full-refresh`. Always do a full refresh on the 1st if Acme was late."),
        ("p-lina", 30, "Numbers tie out now, thanks Meera"),
    ], "annotations": [ann("workaround", "wk-finrep-refresh", {"p-meera": "author", "p-lina": "ack"})]},
    {"channel": "eng", "start": at("2026-09-01", "10:15"), "messages": [
        ("p-lina", 0, "August month-end report looks short again, the Acme file was late last night"),
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
    "Deploy blocked again: `test_concurrent_capture_refund` failed on the payments-api build. Looks unrelated to my change?",
    "payments-api build red on `test_concurrent_capture_refund`, passed locally. Flaky?",
    "Anyone seen `test_concurrent_capture_refund` fail with a Redis key collision? It's blocking my deploy.",
]
_FLAKY_FIXES = [
    "It's the flaky one. The test shares a Redis db with the idempotency tests, so it races when pytest-randomly puts them next to each other. Re-run just that job with `pytest -p no:randomly -k concurrent_capture` and it passes.",
    "Same flake. Re-run the job with `-p no:randomly`. The real fix is giving that test its own Redis db (LUM-449), I haven't had time.",
    "Known flake: random test ordering plus a shared Redis db. Re-run with `pytest -p no:randomly -k concurrent_capture_refund`, don't retry the whole pipeline.",
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

# Acme month-end statement BOM: every month-end, Rahul fixes it.
for day, oncall, fname in [("2026-07-01", "p-sana", "ACME_STMT_20260630.csv"),
                           ("2026-08-01", "p-dev", "ACME_STMT_20260731.csv"),
                           ("2026-09-01", "p-sana", "ACME_STMT_20260831.csv"),
                           ("2026-10-01", "p-tom", "ACME_STMT_20260930.csv")]:
    SLACK_THREADS.append({
        "channel": "incidents", "start": at(day, "02:31"), "messages": [
            ("b-pagerduty", 0, f"[PagerDuty] reconciliation-service: statement import failed: {fname}: invalid header '\\ufeffvalue_date'"),
            (oncall, 7, "recon import is failing on Acme's month-end file, the header looks garbled. Anyone know this one?"),
            ("p-rahul", 15, f"Month-end files from Acme come with a UTF-8 BOM and CRLF line endings (their month-end export runs on a different system). Run `recon-cli normalize --strip-bom --crlf {fname}` and re-import. It happens every month-end."),
            (oncall, 24, "👍 import went through"),
        ],
        "annotations": [ann("workaround", "wk-acme-bom", {"p-rahul": "author", oncall: "ack"})],
    })

# ---------------------------------------------------------------------------
# Meetings
# ---------------------------------------------------------------------------

MEETINGS: list[dict] = [
    {"id": "mtg-2026-03-12-payments-arch", "title": "Payments architecture review", "start": at("2026-03-12", "15:00"),
     "attendees": ["p-priya", "p-rahul", "p-arjun", "p-neha", "p-kavya", "p-isha"],
     "transcript": [
         ("p-priya", "Next item is idempotency key retention. Keys expire after 24 hours right now. Neha, you raised this after the Feb 18 duplicates?"),
         ("p-neha", "Yes. The duplicate credits on the 18th came from Acme retries that arrived after our key had already expired."),
         ("p-rahul", "I want to argue for 72 hours, not 48. Acme keeps retrying failed callbacks with backoff for up to 72 hours after an outage. It's in their integration annex, not in their public docs. And their weekend batch means a Friday-night failure can get retried on Monday morning."),
         ("p-arjun", "72 hours triples the Redis footprint for keys though."),
         ("p-rahul", "It's about 1.2 GB at current volume and we have headroom. A duplicate credit costs us far more than memory. Anything shorter than their retry window just moves the bug."),
         ("p-isha", "Do merchants see any difference?"),
         ("p-rahul", "No, it's invisible to them. It only changes how long we remember a request."),
         ("p-priya", "OK, let's go with 72 hours. Rahul, can you make the change?"),
         ("p-rahul", "Yes, I'll ship it this week."),
         ("p-priya", "Last thing: Kavya, the payout report export, where are we?"),
         ("p-kavya", "Merged yesterday, it goes out with Thursday's release."),
     ],
     "notes": "Decisions: idempotency key retention extended to 72h. Actions: Rahul to update the TTL in payments-api. Kavya to ship the payout report export.",
     "annotations": [ann("decision", "dec-idem-72h", {"p-rahul": "proposer", "p-priya": "approver", "p-neha": "ack", "p-arjun": "ack"})]},

    {"id": "mtg-2026-02-20-postmortem", "title": "Postmortem review: duplicate Acme credits (18 Feb)", "start": at("2026-02-20", "11:00"),
     "attendees": ["p-priya", "p-rahul", "p-neha", "p-arjun", "p-sana", "p-isha"],
     "transcript": [
         ("p-priya", "Timeline first. At 21:40 on the 18th Acme had an outage and queued their callbacks."),
         ("p-neha", "They came back about 26 hours later and we credited 41 payouts twice, because the keys had expired."),
         ("p-sana", "Alerting caught it from the ledger imbalance check about 40 minutes later."),
         ("p-rahul", "We reversed all 41 the same morning. I'd like to revisit the key TTL properly at the architecture review rather than patch it today."),
         ("p-priya", "Agreed. Action item: revisit idempotency TTL, owner Rahul."),
     ],
     "notes": "Root cause: Acme callback retries arrived after the 24h idempotency key expiry. Action: revisit TTL (owner: Rahul).",
     "annotations": []},

    {"id": "mtg-2026-06-09-gateway-idem", "title": "Gateway idempotency design", "start": at("2026-06-09", "14:00"),
     "attendees": ["p-vikram", "p-sana", "p-rahul", "p-ritu", "p-priya"],
     "transcript": [
         ("p-vikram", "Proposal: the gateway enforces the Idempotency-Key header on every POST to /payments and rejects duplicates at the edge."),
         ("p-rahul", "I'm in. We can reuse the payments-api keystore so the 72-hour window stays the same everywhere. Otherwise the gateway and the service disagree about what counts as a duplicate."),
         ("p-sana", "From an ops side I like it, since duplicates never reach the services. We need a dashboard for rejected keys."),
         ("p-vikram", "Agreed. Shared keystore, 72h TTL, a 409 with the original response for duplicates."),
         ("p-ritu", "I can take the Kong plugin."),
         ("p-priya", "Sounds good from Payments."),
     ],
     "notes": "Decision: enforce Idempotency-Key at the gateway using the shared payments keystore (72h). Ritu owns the plugin.",
     "annotations": [ann("decision", "dec-gateway-idem", {"p-vikram": "proposer", "p-rahul": "co-proposer", "p-sana": "supporter", "p-priya": "ack"})]},

    {"id": "mtg-2026-04-22-checkout-3ds", "title": "Checkout: 3-D Secure strategy", "start": at("2026-04-22", "16:00"),
     "attendees": ["p-nikhil", "p-maya", "p-farah", "p-rahul", "p-varun", "p-tara"],
     "transcript": [
         ("p-nikhil", "Drop-off on the 3DS challenge step is 18% for tickets under ₹2,000. I want frictionless by default below that line."),
         ("p-maya", "We tested it with two merchants and conversion went up 6 points without a change in chargebacks."),
         ("p-farah", "Fine from Risk as long as fraud rules still score every payment and we can force a challenge per merchant."),
         ("p-rahul", "On the payments side the capture flow doesn't change. We just pass the exemption flag through to the acquirer."),
         ("p-varun", "Let's ship it to all merchants next sprint."),
     ],
     "notes": "Decision: frictionless 3DS under ₹2,000; Risk can force challenges per merchant.",
     "annotations": [ann("decision", "dec-checkout-3ds", {"p-nikhil": "proposer", "p-maya": "co-proposer", "p-farah": "supporter", "p-rahul": "supporter"})]},

    {"id": "mtg-2026-07-28-outbox", "title": "RFC-019 review: ledger transactional outbox", "start": at("2026-07-28", "15:30"),
     "attendees": ["p-arjun", "p-rahul", "p-kavya", "p-priya", "p-neha"],
     "transcript": [
         ("p-arjun", "Ledger drops events while it deploys, which is what makes recon report phantom mismatches. The RFC proposes a transactional outbox table and a relay."),
         ("p-rahul", "Strong yes from recon. Today we paper over it with a 24-hour replay after every deploy. With an outbox recon can trust the event stream again."),
         ("p-kavya", "Sounds good to me."),
         ("p-priya", "Approved. Arjun, track it as LUM-412."),
     ],
     "notes": "Decision: adopt transactional outbox for ledger events (LUM-412, owner Arjun).",
     "annotations": [ann("decision", "dec-ledger-outbox", {"p-arjun": "proposer", "p-rahul": "supporter", "p-kavya": "ack", "p-priya": "ack"})]},

    {"id": "mtg-2026-05-05-ci-runners", "title": "CI runner strategy", "start": at("2026-05-05", "11:30"),
     "attendees": ["p-vikram", "p-ishaan", "p-sana", "p-tom"],
     "transcript": [
         ("p-ishaan", "Finance asked whether we can move CI to hosted runners to cut the VM bill."),
         ("p-vikram", "I'd keep self-hosted. The deploy pipeline holds production credentials for the cardholder environment, so hosted runners would pull the whole pipeline into PCI audit scope. The audit cost dwarfs the VM bill."),
         ("p-sana", "Makes sense."),
         ("p-ishaan", "OK, we stay self-hosted. Vikram, can you write up the cost comparison for Finance?"),
     ],
     "notes": "Decision: CI stays on self-hosted runners inside the PCI network.",
     "annotations": [ann("decision", "dec-ci-selfhosted", {"p-vikram": "proposer", "p-ishaan": "approver", "p-sana": "ack"})]},

    {"id": "mtg-2026-07-14-velocity", "title": "Fraud velocity limits review", "start": at("2026-07-14", "12:00"),
     "attendees": ["p-farah", "p-manish", "p-divya", "p-yusuf"],
     "transcript": [
         ("p-divya", "The June card-testing attacks are mostly blocked now, but we're still seeing bursts."),
         ("p-farah", "I want the device limit at 5 cards per 24 hours. The attacks used 6 to 12 cards per device, and families sharing a phone rarely go past 3. Anything lower starts hurting real customers."),
         ("p-manish", "Approved from compliance, as long as it's logged as a documented rule change."),
         ("p-divya", "I'll update the alert thresholds."),
     ],
     "notes": "Decision: velocity limit 5 cards/device/24h.",
     "annotations": [ann("decision", "dec-velocity-5", {"p-farah": "proposer", "p-manish": "approver", "p-divya": "ack"})]},

    {"id": "mtg-2026-04-30-revenue", "title": "Month-end revenue recognition", "start": at("2026-04-30", "17:00"),
     "attendees": ["p-meera", "p-sunil", "p-lina"],
     "transcript": [
         ("p-sunil", "The auditors flagged that our revenue report uses capture date."),
         ("p-meera", "I'll switch the finance reporting models to settlement date, meaning when Acme actually settles the funds. Captures that settle next month move into next month. It also lines up with the settlement report Finance already reconciles."),
         ("p-sunil", "Approved. Start from April close."),
     ],
     "notes": "Decision: month-end revenue on settlement date (Meera).",
     "annotations": [ann("decision", "dec-revenue-settle-date", {"p-meera": "proposer", "p-sunil": "approver", "p-lina": "ack"})]},
]

# ---------------------------------------------------------------------------
# Docs (Confluence-like). `systems` are page labels; `customers` likewise.
# ---------------------------------------------------------------------------

DOCS: list[dict] = [
    {"id": "DOC-1042", "title": "Runbook: Nightly settlement (settlement-batch)", "space": "PAY", "kind": "runbook",
     "author": "p-rahul", "created": at("2025-09-10"), "updated": at("2026-02-03", "18:20"),
     "systems": ["sys-settlement"], "customers": ["cust-acme"],
     "body": """# Runbook: Nightly settlement

Owner: Rahul Verma. Last reviewed 3 Feb 2026.

## Schedule
settlement-batch runs nightly at 00:00 IST from the `settlement-nightly` cron and normally finishes in 25 to 40 minutes.

## Inputs
- Acme Bank statement file, pulled by the SFTP bridge.
- Ledger day-close snapshot.

## If the job fails
1. Check the PagerDuty alert for the failing batch id.
2. Re-run: `settlement-batch run --date <YYYY-MM-DD>`.
3. Confirm payouts on the ledger dashboard.
4. If it fails twice, page the Payments on-call.

## Contacts
Acme Bank integration: Rahul Verma."""},
    {"id": "DOC-1107", "title": "RFC-014: Reconciliation matching strategy", "space": "PAY", "kind": "rfc",
     "author": "p-rahul", "created": at("2026-05-18"), "updated": at("2026-05-20", "12:00"),
     "systems": ["sys-recon"], "customers": ["cust-acme"],
     "body": """# RFC-014: Reconciliation matching strategy

Status: Accepted (20 May 2026). Author: Rahul Verma. Reviewer: Arjun Nair.

## Problem
Exact amount matching between Acme statement lines and ledger entries flags about 2% of FX-converted payments as mismatches every night.

## Decision
Match on the bank reference first. Then match on amount with a tolerance of ±1 minor unit, for FX-converted payments only.

## Why
Acme rounds FX conversions half-up. Our ledger uses banker's rounding (half-even). The two disagree by at most one minor unit. Widening the tolerance for everything would hide real errors, so the tolerance applies to FX lines only.

## Rollout
Shipped in reconciliation-service behind `match_v2`, enabled 28 May."""},
    {"id": "DOC-0981", "title": "Acme Bank integration notes", "space": "PAY", "kind": "design",
     "author": "p-rahul", "created": at("2025-11-03"), "updated": at("2026-01-15", "10:30"),
     "systems": ["sys-acme-bridge", "sys-recon"], "customers": ["cust-acme"],
     "body": """# Acme Bank integration notes

- Statement files: `ACME_STMT_<YYYYMMDD>.csv`, pulled by acme-sftp-bridge from `sftp.acmebank.example`.
- Webhooks: payout status callbacks, signed by Acme.
- Escalation: Daniel Okafor (Integration Lead), Mei Lin (Platform Engineer). Shared channel #ext-acme-bank.
- Technical contact on our side: Rahul Verma."""},
    {"id": "DOC-0612", "title": "reconciliation-service: architecture overview", "space": "PAY", "kind": "design",
     "author": "p-karan", "created": at("2025-03-04"), "updated": at("2025-08-12", "16:00"),
     "systems": ["sys-recon"], "customers": [],
     "body": """# reconciliation-service: architecture overview

The service imports bank statements, normalises them into statement lines and matches them against ledger entries. Mismatches are written to `recon_exceptions` and surfaced on the recon dashboard.

Components: importer, matcher, exception writer, `recon-cli` for operators."""},
    {"id": "DOC-1063", "title": "payments-api: idempotency keys", "space": "PAY", "kind": "design",
     "author": "p-neha", "created": at("2026-03-18"), "updated": at("2026-03-20", "14:10"),
     "systems": ["sys-payments-api"], "customers": [],
     "body": """# payments-api: idempotency keys

Clients send an `Idempotency-Key` header on POST requests. Keys and the original response live in Redis with a 72-hour TTL. A repeated key returns the stored response with status 200 and header `Idempotent-Replayed: true`."""},
    {"id": "DOC-1031", "title": "Postmortem: duplicate Acme credits (18 Feb 2026)", "space": "PAY", "kind": "postmortem",
     "author": "p-priya", "created": at("2026-02-19"), "updated": at("2026-02-20", "13:00"),
     "systems": ["sys-payments-api", "sys-ledger"], "customers": ["cust-acme"],
     "body": """# Postmortem: duplicate Acme credits (18 Feb 2026)

Impact: 41 payouts credited twice and reversed within 12 hours.
Root cause: Acme callback retries arrived after the 24h idempotency key expiry.
Action items: revisit idempotency TTL (owner: Rahul Verma)."""},
    {"id": "DOC-1188", "title": "RFC-019: Ledger transactional outbox", "space": "PAY", "kind": "rfc",
     "author": "p-arjun", "created": at("2026-07-20"), "updated": at("2026-07-29", "11:00"),
     "systems": ["sys-ledger", "sys-recon"], "customers": [],
     "body": """# RFC-019: Ledger transactional outbox

Status: Accepted. Tracking: LUM-412.

ledger-service writes events to an `outbox` table in the same transaction as the ledger entry. A relay publishes them with at-least-once delivery, keyed by event id. This removes the event loss during deploys that causes phantom reconciliation mismatches."""},
    {"id": "DOC-0870", "title": "Payments team onboarding", "space": "PAY", "kind": "onboarding",
     "author": "p-priya", "created": at("2025-05-12"), "updated": at("2025-06-30", "10:00"),
     "systems": ["sys-payments-api", "sys-ledger", "sys-recon", "sys-settlement"], "customers": [],
     "body": """# Payments team onboarding

1. Get access to Buildkite, PagerDuty and the payments Grafana folder.
2. Read the ledger-service and payments-api READMEs.
3. Shadow one on-call week before joining the rotation.
4. Ask Rahul about reconciliation and settlement."""},
    {"id": "DOC-1120", "title": "api-gateway: Idempotency-Key enforcement", "space": "PLAT", "kind": "design",
     "author": "p-vikram", "created": at("2026-06-11"), "updated": at("2026-06-15", "15:00"),
     "systems": ["sys-gateway", "sys-payments-api"], "customers": [],
     "body": """# api-gateway: Idempotency-Key enforcement

The gateway enforces `Idempotency-Key` on POST /payments using the shared payments keystore (72h TTL). Duplicates get a 409 with the original response. Plugin owner: Ritu Bansal."""},
    {"id": "DOC-0745", "title": "CI pipeline guide", "space": "PLAT", "kind": "runbook",
     "author": "p-vikram", "created": at("2025-08-01"), "updated": at("2025-11-20", "12:00"),
     "systems": ["sys-ci"], "customers": [],
     "body": """# CI pipeline guide

Buildkite agents run on self-hosted VMs (ci-runner-01..04). Pipelines live in `.buildkite/`. Deploys need an approval step for production."""},
    {"id": "DOC-1015", "title": "Fraud rules engine: rule catalogue", "space": "RISK", "kind": "design",
     "author": "p-farah", "created": at("2026-02-25"), "updated": at("2026-07-16", "10:00"),
     "systems": ["sys-fraud"], "customers": [],
     "body": """# Fraud rules engine: rule catalogue

Rules are evaluated on every card payment, in priority order. Velocity: at most 5 distinct cards per device per 24h (since July 2026). Risk can force a 3DS challenge per merchant."""},
    {"id": "DOC-1092", "title": "Finance reporting models", "space": "DATA", "kind": "design",
     "author": "p-meera", "created": at("2026-05-02"), "updated": at("2026-05-06", "09:00"),
     "systems": ["sys-finrep", "sys-dwh"], "customers": ["cust-acme"],
     "body": """# Finance reporting models

Month-end revenue is recognised on settlement date, not capture date (since April 2026 close). Models: `finance_snapshot`, `revenue_monthly`, `settlement_daily`."""},
    {"id": "DOC-0702", "title": "Developer environment setup", "space": "ENG", "kind": "onboarding",
     "author": "p-tom", "created": at("2025-07-14"), "updated": at("2026-07-16", "11:00"),
     "systems": ["sys-staging"], "customers": [],
     "body": """# Developer environment setup

1. Install the Lumen CLI and Tailscale.
2. VPN: if staging drops, run `tailscale down && tailscale up --reset`.
3. Request staging DB read access in #platform."""},
    {"id": "DOC-0655", "title": "On-call policy", "space": "ENG", "kind": "policy",
     "author": "p-ishaan", "created": at("2025-04-01"), "updated": at("2026-03-02", "10:00"),
     "systems": [], "customers": [],
     "body": "# On-call policy\n\nWeekly rotations per team, handover on Mondays at 11:00. Page within 5 minutes for P1."},
    {"id": "DOC-1150", "title": "Globex Pay payouts integration", "space": "PART", "kind": "design",
     "author": "p-kabir", "created": at("2026-03-10"), "updated": at("2026-06-24", "10:00"),
     "systems": [], "customers": ["cust-globex"],
     "body": "# Globex Pay payouts integration\n\nCross-border payout corridors, cutoff times, and the escalation path to Sofia Marquez."},
]

# ---------------------------------------------------------------------------
# Tickets (Jira-like)
# ---------------------------------------------------------------------------

TICKETS: list[dict] = [
    {"key": "LUM-412", "summary": "ledger-service: transactional outbox for event emission",
     "status": "Done", "assignee": "p-arjun", "reporter": "p-arjun", "components": ["sys-ledger"],
     "created": at("2026-07-29"), "resolved": at("2026-09-15", "17:30"), "customer": None,
     "description": "Implement RFC-019. Removes event loss during deploys (and the 24h recon replay we do after every ledger deploy).",
     "comments": [("p-arjun", at("2026-09-15", "17:30"), "Shipped to prod. Recon replay after deploys is no longer needed.")]},
    {"key": "LUM-433", "summary": "Compliance exception: Acme HMAC-SHA1 webhook signatures",
     "status": "Done", "assignee": "p-manish", "reporter": "p-rahul", "components": ["sys-acme-bridge"],
     "created": at("2026-06-18"), "resolved": at("2026-06-25"), "customer": "cust-acme",
     "description": "Acme cannot sign with SHA-256 until Q1 2027. Keep v1 verification for Acme only, behind acme_hmac_v1.",
     "comments": [("p-manish", at("2026-06-25"), "Exception approved until 31 Mar 2027.")]},
    {"key": "LUM-449", "summary": "payments-api: give test_concurrent_capture_refund its own Redis db",
     "status": "To Do", "assignee": "p-rahul", "reporter": "p-rahul", "components": ["sys-payments-api"],
     "created": at("2026-06-17"), "resolved": None, "customer": None,
     "description": "The test shares a Redis db with the idempotency suite and fails under random ordering about once a week, blocking deploys.",
     "comments": []},
    {"key": "LUM-458", "summary": "settlement-batch: alert when a lock is older than 30 minutes",
     "status": "To Do", "assignee": "p-rahul", "reporter": "p-neha", "components": ["sys-settlement"],
     "created": at("2026-08-28"), "resolved": None, "customer": None,
     "description": "Stale rows in settlement_locks block the nightly run. Alert before the job fails.",
     "comments": []},
    {"key": "LUM-466", "summary": "recon: handle partial Acme statement files",
     "status": "In Progress", "assignee": "p-rahul", "reporter": "p-rahul", "components": ["sys-recon"],
     "created": at("2026-09-08"), "resolved": None, "customer": "cust-acme",
     "description": "Detect truncated statement files and wait for the complete file instead of matching early.",
     "comments": [("p-rahul", at("2026-10-12"), "Detection is done; retry/wait logic still to do.")]},
    {"key": "LUM-471", "summary": "acme-sftp-bridge: migrate Acme webhooks to HMAC-SHA256 (v2)",
     "status": "Backlog", "assignee": "p-rahul", "reporter": "p-rahul", "components": ["sys-acme-bridge"],
     "created": at("2026-06-18"), "resolved": None, "customer": "cust-acme",
     "description": "Run v1 and v2 verifiers side by side for a week once Acme sends test vectors (expected Jan 2027), then remove acme_hmac_v1.",
     "comments": []},
    {"key": "LUM-480", "summary": "settlement-batch: add --dry-run to --resume-from",
     "status": "To Do", "assignee": None, "reporter": "p-priya", "components": ["sys-settlement"],
     "created": at("2026-10-14"), "resolved": None, "customer": None, "labels": ["good-first-issue"],
     "description": "Print which payouts a resume would process without writing anything. A good starter ticket for a new teammate.",
     "comments": []},
]

# ---------------------------------------------------------------------------
# Specific commits (counted inside each author's totals)
# ---------------------------------------------------------------------------

COMMITS: list[dict] = [
    {"repo": "lumen/settlement-batch", "author": "p-rahul", "date": at("2026-04-07", "23:40"),
     "sha": "4e1c9a2f7b0d", "message": "Move nightly settlement cron to 02:00 IST (Acme statement lands ~01:30)",
     "annotations": [ann("decision", "dec-settle-2am", {"p-rahul": "proposer"})]},
    {"repo": "lumen/payments-api", "author": "p-rahul", "date": at("2026-03-16", "19:05"),
     "sha": "9b77e01c3a54", "message": "Extend idempotency key TTL to 72h (payments arch review, 12 Mar)",
     "annotations": []},
    {"repo": "lumen/reconciliation-service", "author": "p-rahul", "date": at("2026-05-28", "18:10"),
     "sha": "c0ffee14ab12", "message": "match_v2: bank reference first, ±1 minor unit tolerance for FX lines (RFC-014)",
     "annotations": [ann("decision", "dec-recon-matching", {"p-rahul": "proposer"})]},
]

# RFC-014 records the decision; Arjun reviewed it.
DOC_ANNOTATIONS = {
    "DOC-1107": [ann("decision", "dec-recon-matching", {"p-rahul": "proposer", "p-arjun": "ack"})],
    "DOC-1188": [ann("decision", "dec-ledger-outbox", {"p-arjun": "proposer"})],
    "DOC-1120": [ann("decision", "dec-gateway-idem", {"p-vikram": "proposer"})],
    "DOC-1015": [ann("decision", "dec-velocity-5", {"p-farah": "proposer"})],
    "DOC-1092": [ann("decision", "dec-revenue-settle-date", {"p-meera": "proposer"})],
    "DOC-0702": [ann("workaround", "wk-vpn-reset", {"p-tom": "applier"})],
}
