"""Vocabulary for bulk synthetic activity.

Rule for this file: a system's phrases must not contain another system's or a
customer's aliases, otherwise generated threads would leak expertise credit.
"""

from __future__ import annotations

# alias forms used when people talk about a system casually
SPOKEN = {
    "sys-recon": ["recon", "reconciliation-service", "the recon service"],
    "sys-settlement": ["the settlement job", "settlement-batch", "nightly settlement"],
    "sys-acme-bridge": ["the SFTP bridge", "acme-sftp-bridge"],
    "sys-payments-api": ["payments-api", "the payments API"],
    "sys-ledger": ["ledger-service", "the ledger"],
    "sys-gateway": ["the gateway", "api-gateway", "Kong"],
    "sys-checkout": ["checkout-web", "the checkout flow"],
    "sys-ci": ["Buildkite", "the CI pipeline", "the CI runners"],
    "sys-flags": ["feature flags", "Unleash", "the flag service"],
    "sys-staging": ["staging", "the staging env"],
    "sys-kyc": ["KYC", "the KYC pipeline"],
    "sys-fraud": ["the fraud rules", "the rules engine"],
    "sys-dwh": ["the warehouse", "BigQuery"],
    "sys-finrep": ["the finance reporting models", "the month-end report"],
    "cust-acme": ["Acme", "Acme Bank"],
    "cust-globex": ["Globex", "Globex Pay"],
    "cust-initech": ["Initech", "Initech Lending"],
    "cust-umbrella": ["Umbrella", "Umbrella Retail"],
}

VOCAB: dict[str, dict[str, list[str]]] = {
    "sys-recon": {
        "symptom": ["flagging a spike of exceptions this morning", "slow on the morning run", "showing duplicate exceptions for one merchant", "stuck on the import step"],
        "cause": ["a late statement file; the importer retries every 15 minutes", "the matcher starting before the import had finished", "a reversed payout that hasn't posted yet", "an expired import credential"],
        "fix": ["re-run the matcher for that value date once the import is green", "wait for the 07:00 retry, it clears itself", "mark them as timing exceptions; they auto-close on the next run", "rotate the import credential in Vault and re-run the import"],
    },
    "sys-settlement": {
        "symptom": ["running long tonight", "showing fewer payouts than expected", "skipping one merchant", "late to finish"],
        "cause": ["a very large merchant batch, the run time scales with payout count", "a merchant flagged on hold in the payouts table", "the day-close snapshot arriving late"],
        "fix": ["let it finish; it parallelises per merchant after the first 10 minutes", "check `payout_holds` and release the hold with ops approval", "look at the run summary in Grafana before touching anything"],
    },
    "sys-acme-bridge": {
        "symptom": ["timing out on the morning pull", "rejecting a webhook signature", "pulling the same file twice"],
        "cause": ["the remote host rotating its key", "a clock skew on the callback timestamp", "the done-marker file not being written on their side"],
        "fix": ["update the known_hosts entry from the bridge config repo", "check the timestamp tolerance; it's 5 minutes", "the bridge dedupes by checksum, so the second pull is harmless"],
    },
    "sys-payments-api": {
        "symptom": ["returning 409s on refunds", "slow on capture since the last deploy", "rejecting a client's idempotency header", "throwing 500s on partial refunds"],
        "cause": ["a client reusing keys across different payloads", "a missing index on captures by merchant", "a header with whitespace that the validator rejects", "partial refunds on a payment that's still authorising"],
        "fix": ["return the stored response and tell the client to generate a fresh key", "the index migration is in the next release", "trim the header in the client SDK", "wait for capture to settle before refunding"],
    },
    "sys-ledger": {
        "symptom": ["showing an imbalance alert", "lagging on the event stream", "rejecting a journal entry"],
        "cause": ["a reversal posted on one side only", "a consumer stuck on a poison message", "a currency without a configured account"],
        "fix": ["post the compensating entry through the admin tool, never by hand", "skip the message with the DLQ tool and file a ticket", "add the account mapping and replay the entry"],
    },
    "sys-gateway": {
        "symptom": ["rate limiting a merchant too aggressively", "adding latency on auth", "returning 502s for one route"],
        "cause": ["the merchant sharing a key across environments", "the JWKS cache expiring at the same time on every pod", "an upstream health check pointing at the wrong port"],
        "fix": ["give them a separate sandbox key", "the jitter on the JWKS refresh fixes it", "fix the upstream target in the declarative config"],
    },
    "sys-checkout": {
        "symptom": ["showing a blank page on old Safari", "dropping UPI intents on Android", "double-submitting the pay button"],
        "cause": ["a polyfill missing from the legacy bundle", "the intent URL getting encoded twice", "a slow network plus a missing disabled state"],
        "fix": ["ship the legacy bundle flag", "decode once in the redirect handler", "disable the button on first click and show the spinner"],
    },
    "sys-ci": {
        "symptom": ["queueing builds for ages", "failing on the docker login step", "running the wrong pipeline for a branch"],
        "cause": ["all agents busy with nightly jobs", "an expired registry token on the agents", "a stale pipeline upload from a renamed branch"],
        "fix": ["bump the agent pool for the day in the autoscaler", "rotate the registry token in the agent secrets", "re-upload the pipeline from the branch"],
    },
    "sys-flags": {
        "symptom": ["not picking up a toggle change", "showing different values per pod"],
        "cause": ["the SDK cache refreshing every 60 seconds", "a pod pinned to an old SDK version"],
        "fix": ["wait a minute or force a refresh from the admin UI", "roll the deployment so every pod has the same SDK"],
    },
    "sys-staging": {
        "symptom": ["missing yesterday's data", "out of disk", "slow to deploy"],
        "cause": ["the nightly snapshot job running late", "old preview environments never torn down", "image pulls from the wrong registry mirror"],
        "fix": ["trigger the snapshot job manually", "run the preview cleanup job", "point the namespace at the local mirror"],
    },
    "sys-kyc": {
        "symptom": ["stuck on document review for a merchant", "rejecting valid PAN numbers"],
        "cause": ["the vendor callback not arriving", "a format check that is too strict on older PANs"],
        "fix": ["re-trigger the vendor check from the admin panel", "the relaxed validator is behind a flag, enable it for that merchant"],
    },
    "sys-fraud": {
        "symptom": ["blocking a merchant's legit customers", "scoring slower than usual"],
        "cause": ["the device fingerprint rule firing on a shared office network", "a rule querying a cold cache after deploy"],
        "fix": ["add the merchant's network to the allowlist with an expiry", "warm the cache before routing traffic"],
    },
    "sys-dwh": {
        "symptom": ["missing yesterday's rows", "showing duplicate events"],
        "cause": ["the CDC connector restarting overnight", "at-least-once delivery from the stream"],
        "fix": ["backfill the partition from the connector offsets", "dedupe on event id in the base model"],
    },
    "sys-finrep": {
        "symptom": ["not matching Finance's revenue number", "taking hours to build"],
        "cause": ["a late upstream partition", "the full model rebuilding instead of incremental"],
        "fix": ["rebuild the affected day only", "check that the incremental filter is on the settlement column"],
    },
    "cust-acme": {
        "symptom": ["statement file arrived after the cutoff", "callback signature rejected overnight", "host key rotation scheduled", "test file with a new column order"],
        "cause": ["a maintenance window on their side", "a re-serialised body before signing", "their annual key rotation", "an FX section change in their export"],
        "fix": ["confirm the late file was picked up before the run", "ask them to sign the raw bytes", "update known_hosts before the rotation", "validate the test file against the importer"],
    },
    "cust-globex": {
        "symptom": ["asking why a payout corridor is delayed", "asking for a new settlement report column", "reporting a failed payout batch"],
        "cause": ["their cutoff for that corridor being 14:00 local time", "the report schema living on their side", "a beneficiary bank rejecting the IFSC"],
        "fix": ["resend before their cutoff tomorrow", "send them the column spec and they'll add it", "correct the beneficiary details and resubmit"],
    },
    "cust-initech": {
        "symptom": ["asking about EMI collection retries", "seeing duplicate mandate notifications", "asking for higher API rate limits"],
        "cause": ["our retry schedule being 3 attempts over 5 days", "them subscribing to both webhook versions", "their nightly batch bursting at 02:00"],
        "fix": ["share the retry schedule doc", "unsubscribe the v1 webhook", "spread the batch or move to the bulk endpoint"],
    },
    "cust-umbrella": {
        "symptom": ["asking for store-level reporting", "seeing slow terminals at peak hours", "asking about refunds to expired cards"],
        "cause": ["store ids missing from their metadata", "their store network, not our API", "network rules that route refunds to the new card"],
        "fix": ["ask them to pass store_id in metadata", "share the latency dashboard so they can see it's on their side", "explain that refunds follow the card network's account updater"],
    },
}

QUESTION_TEMPLATES = [
    "Does anyone know why {s} is {symptom}?",
    "Quick one: {s} is {symptom}. Is that expected?",
    "{S} has been {symptom} since this morning. Who knows this area?",
    "Seeing {s} {symptom}. Anything I should check before I dig in?",
]
ANSWER_TEMPLATES = [
    "That's usually {cause}. Easiest fix is to {fix}.",
    "Seen this before: it's {cause}. {Fix}.",
    "It's {cause}. You can {fix}, and I'll add a note to the doc.",
    "Most likely {cause}. {Fix} and it should clear.",
]
CUSTOMER_Q_TEMPLATES = [
    "{S} is {symptom}. Who can pick this up?",
    "Heads up: {s} is {symptom}. Anyone have context?",
]
ACKS = ["Thanks!", "That was it, thanks", "👍", "Perfect, thank you", "Got it, thanks", "Makes sense 🙏"]

ACME_ROOTS = [
    ("c-daniel", "Today's statement file will be about 20 minutes late, we have a maintenance window until 01:45."),
    ("c-mei", "Can you confirm you received ACME_STMT_{d}? Our side shows it delivered at 01:32."),
    ("c-daniel", "We're rotating our SFTP host key on {d2}. New fingerprint attached in the portal."),
    ("c-mei", "We're seeing 3 callbacks rejected on our side overnight. Can you check what you received?"),
    ("c-daniel", "Reminder: no statement file on the bank holiday, the next file covers two value dates."),
    ("c-mei", "We changed the column order for the FX section in our test file. Can you validate before we push to prod?"),
]
ACME_REPLIES = [
    "Received, thanks. Recon picked it up at 02:10 and matched clean.",
    "Thanks for the heads up. Settlement starts at 02:00 so we'll have it in time.",
    "Got it. I'll update the known_hosts on the bridge before your rotation and confirm here.",
    "We received all three, but the signatures were computed on a re-serialised body. Can you sign the raw bytes like before?",
    "Noted, the next run will reconcile both value dates.",
    "Validated against your test file. The importer handles the new order, so you're good to push.",
]

STANDUPS = [
    "Yesterday: finished the review queue on {s}. Today: pairing on {s2} and an interview at 4.",
    "Today: picking up the {s} ticket from planning, then on-call handover.",
    "Status: {s} change is in review, should merge tomorrow. Blocked on nothing.",
    "Out after lunch for a doctor's appointment. {S} PR is ready for review if anyone has time.",
]
DEPLOYS = [
    "Deploying {repo} {ver} to production (triggered by {who}).",
    "{repo} {ver} rolled out to 100% (triggered by {who}).",
]
ALERTS = [
    "[PagerDuty] {name}: p95 latency above threshold for 10m (resolved automatically).",
    "[PagerDuty] {name}: error rate 2.1% for 5m (resolved).",
    "[PagerDuty] {name}: disk usage 81% on primary (acknowledged).",
]
SOCIAL = [
    "Lunch is here 🍕 Kitchen on 3.",
    "Reminder: all-hands at 4 pm today, Q&A doc is pinned.",
    "Happy birthday {name}! 🎉",
    "Anyone up for badminton on Thursday?",
    "Please submit expense claims for September by Friday.",
    "The office Wi-Fi password changed, it's on the board near reception.",
    "Welcome to the team {name}! 👋",
    "Coffee machine on 2 is fixed ☕",
    "Reminder: performance self-reviews are due next Wednesday.",
    "Who left a blue umbrella in the meeting room? 😄",
]

COMMIT_TEMPLATES = [
    "Fix {thing}", "Add {thing}", "Refactor {thing}", "Handle {thing}", "Improve {thing}",
    "Tests for {thing}", "Clean up {thing}", "Log {thing}",
]
COMMIT_THINGS = {
    "lumen/reconciliation-service": ["statement importer retries", "matcher edge case for reversals", "exception writer batching", "recon-cli date parsing", "FX line normalisation", "duplicate exception suppression", "import metrics", "matcher timeouts"],
    "lumen/settlement-batch": ["payout grouping per merchant", "run summary metrics", "hold release flow", "batch resume bookkeeping", "settlement report columns", "lock acquisition"],
    "lumen/payments-api": ["refund validation", "capture idempotency", "partial refund flow", "webhook signing", "API error codes", "merchant rate limits", "OpenAPI spec"],
    "lumen/ledger-service": ["journal validation", "currency account mapping", "event consumer backoff", "admin reversal tool", "balance snapshot job"],
    "lumen/api-gateway": ["JWKS refresh jitter", "rate limit plugin config", "route health checks", "request id propagation", "idempotency plugin"],
    "lumen/checkout-web": ["UPI intent redirect", "legacy bundle polyfills", "pay button double submit", "3DS iframe sizing", "card form validation", "checkout analytics events"],
}
TICKET_TEMPLATES = [
    "{n}: {fix_short}", "{n}: investigate {symptom_short}", "{n}: {thing}",
]
