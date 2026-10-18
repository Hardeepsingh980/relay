"""Vocabulary for bulk synthetic activity in the Cheerio world.

Rule for this file: a system's phrases must not contain another system's or an
account's aliases, otherwise generated threads would leak expertise credit.
Style follows how the team writes: short, action-first, the odd "pls".
"""

from __future__ import annotations

# alias forms used when people talk about a system casually
SPOKEN = {
    "sys-reconciler": ["recon", "billing-reconciler", "the reconciler"],
    "sys-settlement": ["the settlement job", "wallet-settlement", "nightly settlement"],
    "sys-kairo-bridge": ["the ERP bridge", "kairo-erp-bridge"],
    "sys-msg-api": ["messaging-api", "the send API"],
    "sys-ledger": ["wallet-ledger", "the ledger"],
    "sys-gateway": ["the gateway", "api-gateway", "Kong"],
    "sys-workflows": ["workflow-engine", "the workflow engine"],
    "sys-ci": ["GitHub Actions", "the CI pipeline", "the CI runners"],
    "sys-voice": ["the voice gateway", "voice-gateway", "the SIP trunk"],
    "sys-staging": ["staging", "the staging env"],
    "sys-onboarding": ["embedded signup", "waba-onboarding"],
    "sys-sendguard": ["send-guard", "the frequency caps"],
    "sys-dwh": ["the warehouse", "BigQuery"],
    "sys-finrep": ["the finance reporting models", "the month-end report"],
    "cust-kairo": ["Kairo", "Kairo Living"],
    "cust-glowra": ["Glowra", "Glowra Beauty"],
    "cust-crestline": ["Crestline", "Crestline Finance"],
    "cust-northwind": ["Northwind", "Northwind Foods"],
}

VOCAB: dict[str, dict[str, list[str]]] = {
    "sys-reconciler": {
        "symptom": ["flagging a spike of mismatches this morning", "slow on the morning run", "showing duplicate mismatches for one workspace", "stuck on the pricing import step"],
        "cause": ["Meta's pricing export landing late; the importer retries every 15 minutes", "the matcher starting before the import had finished", "a refund for failed messages that hasn't posted yet", "an expired Meta system-user token on the importer"],
        "fix": ["re-run the matcher for that date once the import is green", "wait for the 07:30 retry, it clears itself", "mark them as timing mismatches; they auto-close on the next run", "rotate the token in Vault and re-run the import"],
    },
    "sys-settlement": {
        "symptom": ["running long tonight", "showing fewer invoices than expected", "skipping one workspace", "late to finish"],
        "cause": ["a huge festive-sale day, run time scales with message count", "a workspace flagged on credit hold", "the day's usage snapshot arriving late"],
        "fix": ["let it finish; it parallelises per workspace after the first 10 minutes", "check `credit_holds` and release the hold with Finance approval", "look at the run summary in Grafana before touching anything"],
    },
    "sys-kairo-bridge": {
        "symptom": ["timing out on the morning pull", "rejecting a webhook signature", "pulling the same order file twice"],
        "cause": ["the remote host rotating its key", "clock skew on the webhook timestamp", "the done-marker file not being written on their side"],
        "fix": ["update the known_hosts entry from the bridge config repo", "check the timestamp tolerance; it's 5 minutes", "the bridge dedupes by checksum, so the second pull is harmless"],
    },
    "sys-msg-api": {
        "symptom": ["returning 409s on template sends", "slow on bulk sends since the last deploy", "rejecting a client's idempotency header", "throwing 500s on media messages"],
        "cause": ["a client reusing keys across different payloads", "a missing index on sends by workspace", "a header with whitespace that the validator rejects", "media URLs that expire before Meta fetches them"],
        "fix": ["return the stored response and tell the client to generate a fresh key", "the index migration is in the next release", "trim the header in the client SDK", "ask them to host media for at least 10 minutes or upload it first"],
    },
    "sys-ledger": {
        "symptom": ["showing a balance mismatch alert", "lagging on the event stream", "rejecting a refund entry"],
        "cause": ["a refund posted on one side only", "a consumer stuck on a poison message", "a currency without a configured wallet account"],
        "fix": ["post the compensating entry through the admin tool, never by hand", "skip the message with the DLQ tool and file a ticket", "add the account mapping and replay the entry"],
    },
    "sys-gateway": {
        "symptom": ["rate limiting a workspace too aggressively", "adding latency on auth", "returning 502s for one route"],
        "cause": ["the workspace sharing an API key across environments", "the JWKS cache expiring at the same time on every pod", "an upstream health check pointing at the wrong port"],
        "fix": ["give them a separate sandbox key", "the jitter on the JWKS refresh fixes it", "fix the upstream target in the declarative config"],
    },
    "sys-workflows": {
        "symptom": ["firing the abandoned-cart message after the order was placed", "skipping the COD confirmation node", "double-sending a welcome message"],
        "cause": ["the Shopify order webhook arriving after the cart timer", "a draft order with no payment gateway set", "a retry on a node that already succeeded"],
        "fix": ["check the order lookup before the cart timer fires", "skip draft orders in the COD trigger", "make the send node idempotent on the run id"],
    },
    "sys-ci": {
        "symptom": ["queueing builds for ages", "failing on the docker login step", "running the wrong workflow for a branch"],
        "cause": ["all runners busy with nightly jobs", "an expired registry token on the runners", "a stale workflow file from a renamed branch"],
        "fix": ["bump the runner pool for the day in the autoscaler", "rotate the registry token in the runner secrets", "re-push the workflow from the branch"],
    },
    "sys-voice": {
        "symptom": ["dropping calls after 30 seconds", "sounding robotic on outbound calls", "only triggering a third of a voice campaign"],
        "cause": ["the carrier's session timer not being refreshed", "audio being downsampled to 8 kHz on the trunk", "the per-second call limit on the carrier account"],
        "fix": ["send a re-INVITE before the session timer runs out", "force the wideband codec on the trunk profile", "pace the campaign under the carrier's calls-per-second limit"],
    },
    "sys-staging": {
        "symptom": ["missing yesterday's data", "out of disk", "slow to deploy"],
        "cause": ["the nightly snapshot job running late", "old preview environments never torn down", "image pulls from the wrong registry mirror"],
        "fix": ["trigger the snapshot job manually", "run the preview cleanup job", "point the namespace at the local mirror"],
    },
    "sys-onboarding": {
        "symptom": ["stuck on display-name review for a workspace", "failing at the phone OTP step"],
        "cause": ["Meta's review queue, not anything on our side", "a number still registered on the WhatsApp Business app"],
        "fix": ["resubmit with the brand's website in the business profile", "ask them to delete the number from the Business app first, then retry"],
    },
    "sys-sendguard": {
        "symptom": ["blocking a workspace's festive campaign", "scoring campaigns slower than usual"],
        "cause": ["the weekly cap counting test sends to the brand's own team", "a rule querying a cold cache after deploy"],
        "fix": ["exclude the brand's internal test audience from the cap", "warm the cache before routing traffic"],
    },
    "sys-dwh": {
        "symptom": ["missing yesterday's rows", "showing duplicate events"],
        "cause": ["the CDC connector restarting overnight", "at-least-once delivery from the Amplitude export"],
        "fix": ["backfill the partition from the connector offsets", "dedupe on event id in the base model"],
    },
    "sys-finrep": {
        "symptom": ["not matching Finance's revenue number", "taking hours to build"],
        "cause": ["a late upstream partition", "the full model rebuilding instead of incremental"],
        "fix": ["rebuild the affected day only", "check that the incremental filter is on the billed-at column"],
    },
    "cust-kairo": {
        "symptom": ["order file arrived after the cutoff", "webhook signature rejected overnight", "host key rotation scheduled", "test file with a new column order"],
        "cause": ["a maintenance window on their side", "a re-serialised body before signing", "their annual key rotation", "a store-code change in their export"],
        "fix": ["confirm the late file was picked up before the morning sends", "ask them to sign the raw bytes", "update known_hosts before the rotation", "validate the test file against the importer"],
    },
    "cust-glowra": {
        "symptom": ["asking why a festive broadcast is paused", "asking for a new column in the campaign report", "reporting a template stuck in review"],
        "cause": ["the weekly marketing cap for part of the audience", "the report schema living in the export job", "Meta reviewing a template with a discount code in the header"],
        "fix": ["split the audience and send the rest after the cap resets", "send them the column spec and we'll add it", "move the discount code into the body and resubmit"],
    },
    "cust-crestline": {
        "symptom": ["asking about EMI reminder retries", "seeing duplicate overdue notifications", "asking for higher API rate limits"],
        "cause": ["our retry schedule being 3 attempts over 2 days", "them subscribing to both webhook versions", "their nightly batch bursting at 09:00"],
        "fix": ["share the retry schedule doc", "unsubscribe the v1 webhook", "spread the batch or move to the bulk endpoint"],
    },
    "cust-northwind": {
        "symptom": ["asking for store-level campaign reports", "seeing slow inbox loads during sale hours", "asking about COD confirmation copy"],
        "cause": ["store tags missing from their contacts", "their agents keeping 40 chats open at once", "the template being approved in English only"],
        "fix": ["ask them to tag contacts with store_id on import", "share the inbox auto-close setting", "submit a Hindi version of the template"],
    },
}

QUESTION_TEMPLATES = [
    "Does anyone know why {s} is {symptom}?",
    "Quick one: {s} is {symptom}. Is that expected?",
    "{S} has been {symptom} since morning. Who knows this area?",
    "Seeing {s} {symptom}. Anything I should check before I dig in?",
]
ANSWER_TEMPLATES = [
    "That's usually {cause}. Easiest fix is to {fix}.",
    "Seen this before: it's {cause}. {Fix}.",
    "It's {cause}. You can {fix}, I'll add a note to the doc.",
    "Most likely {cause}. {Fix} and it should clear.",
]
CUSTOMER_Q_TEMPLATES = [
    "{S} is {symptom}. Who can pick this up?",
    "Heads up: {s} is {symptom}. Anyone have context?",
]
ACKS = ["Thanks!", "That was it, thanks", "👍", "Perfect, thank you", "Got it, thanks", "Makes sense 🙏"]

KAIRO_ROOTS = [
    ("c-siddharth", "Today's order file will be about 20 minutes late, we have a maintenance window until 01:45."),
    ("c-pooja", "Can you confirm you received KAIRO_ORDERS_{d}? Our side shows it delivered at 01:32."),
    ("c-siddharth", "We're rotating our SFTP host key on {d2}. New fingerprint is in the portal."),
    ("c-pooja", "We're seeing 3 order webhooks rejected on our side overnight. Can you check what you received?"),
    ("c-siddharth", "Reminder: no order file on the store holiday, the next file covers two days."),
    ("c-pooja", "We changed the column order for the store section in our test file. Can you validate before we push to prod?"),
]
KAIRO_REPLIES = [
    "Received, thanks. The bridge picked it up at 02:10 and the delivery updates went out clean.",
    "Thanks for the heads up. Morning sends start at 08:00 so we'll have it in time.",
    "Got it. I'll update the known_hosts on the bridge before your rotation and confirm here.",
    "We received all three, but the signatures were computed on a re-serialised body. Can you sign the raw bytes like before?",
    "Noted, the next import will cover both days.",
    "Validated against your test file. The importer handles the new order, so you're good to push.",
]

STANDUPS = [
    "Yesterday: finished the review queue on {s}. Today: pairing on {s2}, interview at 4.",
    "Today: picking up the {s} ticket from sprint planning, then on-call handover.",
    "Status: {s} change is PR REQUESTED, should be on stage tomorrow. No blockers.",
    "Out after lunch, doctor's appointment. {S} PR is ready for review if anyone has time.",
]
DEPLOYS = [
    "Deploying {repo} {ver} to production (triggered by {who}).",
    "{repo} {ver} rolled out to 100% (triggered by {who}).",
]
ALERTS = [
    "[Better Stack] {name}: p95 latency above threshold for 10m (resolved automatically).",
    "[Better Stack] {name}: error rate 2.1% for 5m (resolved).",
    "[Better Stack] {name}: disk usage 81% on primary (acknowledged).",
]
SOCIAL = [
    "Lunch is here 🍕 pantry on 3.",
    "Reminder: all-hands at 4 pm today, Q&A doc is pinned.",
    "Happy birthday {name}! 🎉",
    "Anyone up for badminton on Thursday?",
    "Pls submit September expense claims by Friday.",
    "Office Wi-Fi password changed, it's on the board near reception.",
    "Welcome to the team {name}! 👋",
    "Coffee machine on 2 is fixed ☕",
    "Reminder: self-reviews are due next Wednesday.",
    "Who left a blue umbrella in the Diwali room? 😄",
]

COMMIT_TEMPLATES = [
    "Fix {thing}", "Add {thing}", "Refactor {thing}", "Handle {thing}", "Improve {thing}",
    "Tests for {thing}", "Clean up {thing}", "Log {thing}",
]
COMMIT_THINGS = {
    "cheerio/billing-reconciler": ["pricing importer retries", "matcher edge case for refunds", "mismatch writer batching", "recon-cli date parsing", "FX debit normalisation", "duplicate mismatch suppression", "import metrics", "matcher timeouts"],
    "cheerio/wallet-settlement": ["invoice grouping per workspace", "run summary metrics", "credit hold release flow", "run resume bookkeeping", "GST invoice columns", "lock acquisition"],
    "cheerio/messaging-api": ["template send validation", "send idempotency", "media message flow", "webhook signing", "API error codes", "workspace rate limits", "OpenAPI spec"],
    "cheerio/wallet-ledger": ["entry validation", "currency account mapping", "event consumer backoff", "admin refund tool", "balance snapshot job"],
    "cheerio/api-gateway": ["JWKS refresh jitter", "rate limit plugin config", "route health checks", "request id propagation", "idempotency plugin"],
    "cheerio/workflow-engine": ["cart timer lookup", "COD trigger filters", "node retry idempotency", "Shopify variable mapping", "AI assistant hand-off node", "workflow analytics events"],
}
