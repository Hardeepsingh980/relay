"""The Cheerio world: who works there, what they run, and what they know.

Cheerio is a WhatsApp-first marketing and commerce platform. Its product is the
real one (campaigns, templates, shared inbox, workflows, AI assistant, voice
agents, Shopify automations, wallet credits), but every person, customer,
message and number in this dataset is invented for the demo.

This module is the *generator's* ground truth. The ingestion pipeline never reads
it: it only sees the raw exports written by `generate.py`. Tests compare what the
pipeline reconstructs against the expectations declared here.
"""

from __future__ import annotations

COMPANY = "Cheerio"
DOMAIN = "cheerio.example"

# ---------------------------------------------------------------------------
# Org
# ---------------------------------------------------------------------------

TEAMS = [
    {"id": "team-leadership", "name": "Leadership"},
    {"id": "team-messaging", "name": "Messaging"},
    {"id": "team-platform", "name": "Platform"},
    {"id": "team-automations", "name": "Automations"},
    {"id": "team-trust", "name": "Trust & Compliance"},
    {"id": "team-data", "name": "Data"},
    {"id": "team-cs", "name": "Customer Success"},
    {"id": "team-sales", "name": "Sales"},
    {"id": "team-product", "name": "Product"},
    {"id": "team-finance", "name": "Finance"},
]

# (id, name, role, team, manager, start_date)
_PEOPLE = [
    ("p-ananya", "Ananya Iyengar", "CEO & Co-founder", "team-leadership", None, "2021-06-01"),
    ("p-sameer", "Sameer Kulkarni", "CTO & Co-founder", "team-leadership", "p-ananya", "2021-06-01"),
    ("p-leela", "Leela Thomas", "Head of People & Ops", "team-leadership", "p-ananya", "2023-01-09"),
    ("p-priya", "Priya Raman", "Engineering Manager, Messaging", "team-messaging", "p-sameer", "2023-04-03"),
    ("p-rahul", "Rahul Verma", "Senior Backend Engineer", "team-messaging", "p-priya", "2023-02-06"),
    ("p-neha", "Neha Iyer", "Backend Engineer", "team-messaging", "p-priya", "2024-01-15"),
    ("p-arjun", "Arjun Nair", "Senior Backend Engineer", "team-messaging", "p-priya", "2023-08-21"),
    ("p-kavya", "Kavya Reddy", "Backend Engineer", "team-messaging", "p-priya", "2024-06-10"),
    ("p-omar", "Omar Siddiqui", "Backend Engineer", "team-messaging", "p-priya", "2026-07-06"),
    ("p-aisha", "Aisha Khan", "Backend Engineer", "team-messaging", "p-priya", "2026-10-19"),
    ("p-ishaan", "Ishaan Gupta", "Engineering Manager, Platform", "team-platform", "p-sameer", "2023-03-13"),
    ("p-vikram", "Vikram Sethi", "Staff Engineer", "team-platform", "p-ishaan", "2022-07-18"),
    ("p-sana", "Sana Mirza", "Site Reliability Engineer", "team-platform", "p-ishaan", "2023-10-02"),
    ("p-dev", "Dev Malhotra", "Backend & Infra Engineer", "team-platform", "p-ishaan", "2024-02-12"),
    ("p-ritu", "Ritu Bansal", "Voice AI Engineer", "team-platform", "p-ishaan", "2024-05-06"),
    ("p-tom", "Tom Fernandes", "Software Engineer", "team-platform", "p-ishaan", "2025-01-13"),
    ("p-maya", "Maya Pillai", "Engineering Manager, Automations", "team-automations", "p-sameer", "2023-05-22"),
    ("p-nikhil", "Nikhil Joshi", "Senior Engineer", "team-automations", "p-maya", "2022-11-07"),
    ("p-zoya", "Zoya Ahmed", "Software Engineer", "team-automations", "p-maya", "2024-03-04"),
    ("p-rohan", "Rohan Das", "AI Engineer", "team-automations", "p-maya", "2024-09-16"),
    ("p-gautam", "Gautam Bhatt", "Frontend Engineer", "team-automations", "p-maya", "2025-02-03"),
    ("p-tara", "Tara Menon", "Product Designer", "team-automations", "p-maya", "2024-04-15"),
    ("p-farah", "Farah Qureshi", "Head of Trust & Compliance", "team-trust", "p-ananya", "2022-09-05"),
    ("p-manish", "Manish Agarwal", "Compliance Lead", "team-trust", "p-farah", "2023-06-12"),
    ("p-divya", "Divya Krishnan", "Messaging Quality Analyst", "team-trust", "p-farah", "2024-08-19"),
    ("p-yusuf", "Yusuf Ali", "Trust Engineer", "team-trust", "p-farah", "2024-01-08"),
    ("p-elena", "Elena D'Souza", "Compliance Analyst", "team-trust", "p-farah", "2025-03-17"),
    ("p-meera", "Meera Kaul", "Analytics Engineer", "team-data", "p-sameer", "2023-07-10"),
    ("p-karthik", "Karthik Subramanian", "Data Engineer", "team-data", "p-meera", "2024-02-26"),
    ("p-lina", "Lina George", "Data Analyst", "team-data", "p-meera", "2024-11-04"),
    ("p-pranav", "Pranav Kapoor", "Data Scientist", "team-data", "p-meera", "2025-04-21"),
    ("p-arnav", "Arnav Mehta", "Head of Customer Success", "team-cs", "p-ananya", "2022-10-03"),
    ("p-jay", "Jay Patel", "Solutions Engineer", "team-cs", "p-arnav", "2023-11-20"),
    ("p-sneha", "Sneha Bose", "Customer Success Manager", "team-cs", "p-arnav", "2024-04-01"),
    ("p-rhea", "Rhea Malik", "Customer Success Manager", "team-cs", "p-arnav", "2024-09-02"),
    ("p-vivek", "Vivek Chandra", "Customer Success Manager", "team-cs", "p-arnav", "2025-02-17"),
    ("p-riya", "Riya Sen", "Support Specialist", "team-cs", "p-arnav", "2025-06-09"),
    ("p-kabir", "Kabir Anand", "Account Executive", "team-sales", "p-ananya", "2023-09-11"),
    ("p-simran", "Simran Gill", "Account Executive", "team-sales", "p-kabir", "2025-05-05"),
    ("p-neel", "Neel Banerjee", "Partner Sales Manager", "team-sales", "p-kabir", "2024-11-11"),
    ("p-naina", "Naina Kohli", "Head of Product", "team-product", "p-ananya", "2023-02-20"),
    ("p-isha", "Isha Chawla", "Product Manager, Messaging", "team-product", "p-naina", "2024-07-01"),
    ("p-varun", "Varun Desai", "Product Manager, Automations", "team-product", "p-naina", "2024-10-14"),
    ("p-sunil", "Sunil Arora", "Finance Controller", "team-finance", "p-ananya", "2023-03-27"),
]

# Rahul's last day is Friday of demo week.
LEAVER_LAST_DAY = "2026-10-23"

PEOPLE = [
    {
        "id": pid, "name": name, "role": role, "team": team, "managerId": mgr,
        "startDate": start, "endDate": LEAVER_LAST_DAY if pid == "p-rahul" else None,
        "status": "joining" if pid == "p-aisha" else "active",
        "email": name.lower().replace(" ", ".").replace("'", "") + "@" + DOMAIN,
    }
    for pid, name, role, team, mgr, start in _PEOPLE
]

# A former engineer whose old commits still sit in billing-reconciler history.
FORMER_PEOPLE = [
    {"id": "p-karan", "name": "Karan Shah", "role": "Senior Backend Engineer", "team": "team-messaging",
     "managerId": "p-priya", "startDate": "2022-01-10", "endDate": "2025-12-19", "status": "left",
     "email": "karan.shah@" + DOMAIN},
]

LEAVER = "p-rahul"
MANAGER = "p-priya"
JOINER = "p-aisha"
HEAD_OF_CS = "p-arnav"
CSM = "p-sneha"
AE = "p-kabir"

# People outside Cheerio who appear in shared channels and DMs.
CONTACTS = [
    {"id": "c-siddharth", "name": "Siddharth Kale", "role": "Integration Lead", "customer": "cust-kairo"},
    {"id": "c-pooja", "name": "Pooja Natarajan", "role": "Platform Engineer", "customer": "cust-kairo"},
    {"id": "c-sofia", "name": "Sofia Mathew", "role": "Head of CRM", "customer": "cust-glowra"},
    {"id": "c-tarun", "name": "Tarun Bajaj", "role": "CTO", "customer": "cust-crestline"},
]

BOTS = [
    {"id": "b-betterstack", "name": "Better Stack"},
    {"id": "b-deploybot", "name": "deploybot"},
]

# ---------------------------------------------------------------------------
# Systems and the four integration-heavy accounts (service catalog + CRM)
# ---------------------------------------------------------------------------

SYSTEMS = [
    {"id": "sys-reconciler", "name": "billing-reconciler", "team": "team-messaging", "criticality": "critical",
     "repo": "cheerio/billing-reconciler", "serviceOwner": "p-rahul",
     "aliases": ["billing-reconciler", "billing reconciler", "the reconciler", "recon job", "recon-cli", "recon"],
     "summary": "Matches Meta's daily pricing records against wallet debits for every workspace."},
    {"id": "sys-settlement", "name": "wallet-settlement", "team": "team-messaging", "criticality": "critical",
     "repo": "cheerio/wallet-settlement", "serviceOwner": "p-rahul",
     "aliases": ["wallet-settlement", "wallet settlement", "settlement job", "nightly settlement",
                 "settlement run", "settlement cron"],
     "summary": "Nightly job that settles workspace wallets against the day's usage and raises GST invoices."},
    {"id": "sys-kairo-bridge", "name": "kairo-erp-bridge", "team": "team-messaging", "criticality": "high",
     "repo": None, "serviceOwner": "p-rahul",
     "aliases": ["kairo-erp-bridge", "kairo erp bridge", "erp bridge", "kairo bridge", "kairo sftp"],
     "summary": "Pulls Kairo Living's nightly order files over SFTP and verifies their order-event webhooks."},
    {"id": "sys-msg-api", "name": "messaging-api", "team": "team-messaging", "criticality": "critical",
     "repo": "cheerio/messaging-api", "serviceOwner": "p-arjun",
     "aliases": ["messaging-api", "messaging api", "send api", "msg-api"],
     "summary": "Public API for sending WhatsApp template and session messages, with delivery webhooks."},
    {"id": "sys-ledger", "name": "wallet-ledger", "team": "team-messaging", "criticality": "critical",
     "repo": "cheerio/wallet-ledger", "serviceOwner": "p-arjun",
     "aliases": ["wallet-ledger", "wallet ledger", "ledger"],
     "summary": "Ledger of every wallet top-up, message debit and refund."},
    {"id": "sys-gateway", "name": "api-gateway", "team": "team-platform", "criticality": "critical",
     "repo": "cheerio/api-gateway", "serviceOwner": "p-vikram",
     "aliases": ["api-gateway", "api gateway", "gateway", "kong"],
     "summary": "Kong-based edge gateway: API keys, rate limits, idempotency headers."},
    {"id": "sys-workflows", "name": "workflow-engine", "team": "team-automations", "criticality": "high",
     "repo": "cheerio/workflow-engine", "serviceOwner": "p-nikhil",
     "aliases": ["workflow-engine", "workflow engine", "workflow builder", "flow runner"],
     "summary": "Runs customer workflows: Shopify triggers, abandoned-cart and COD flows, AI assistant hand-offs."},
    {"id": "sys-ci", "name": "ci-pipeline", "team": "team-platform", "criticality": "high",
     "repo": None, "serviceOwner": "p-vikram",
     "aliases": ["ci-pipeline", "ci pipeline", "github actions", "ci runners", "ci runner"],
     "summary": "Self-hosted GitHub Actions runners and the deploy pipeline."},
    {"id": "sys-voice", "name": "voice-gateway", "team": "team-platform", "criticality": "high",
     "repo": None, "serviceOwner": "p-ritu",
     "aliases": ["voice-gateway", "voice gateway", "sip bridge", "sip trunk"],
     "summary": "SIP bridge and media pipeline behind Voice AI calls and voice campaigns."},
    {"id": "sys-staging", "name": "staging-env", "team": "team-platform", "criticality": "medium",
     "repo": None, "serviceOwner": "p-dev",
     "aliases": ["staging-env", "staging env", "staging environment", "staging db", "staging"],
     "summary": "Shared staging environment and its nightly database snapshots."},
    {"id": "sys-onboarding", "name": "waba-onboarding", "team": "team-trust", "criticality": "high",
     "repo": None, "serviceOwner": "p-yusuf",
     "aliases": ["waba-onboarding", "waba onboarding", "embedded signup", "business verification"],
     "summary": "Embedded signup, Meta business verification, display-name and green-tick requests."},
    {"id": "sys-sendguard", "name": "send-guard", "team": "team-trust", "criticality": "high",
     "repo": None, "serviceOwner": "p-farah",
     "aliases": ["send-guard", "send guard", "frequency caps", "policy checks"],
     "summary": "Frequency caps and Meta policy checks applied to every campaign before it sends."},
    {"id": "sys-dwh", "name": "data-warehouse", "team": "team-data", "criticality": "medium",
     "repo": None, "serviceOwner": "p-karthik",
     "aliases": ["data-warehouse", "data warehouse", "warehouse", "bigquery"],
     "summary": "BigQuery warehouse fed by CDC from production and the Amplitude export."},
    {"id": "sys-finrep", "name": "finance-reporting", "team": "team-data", "criticality": "high",
     "repo": None, "serviceOwner": "p-meera",
     "aliases": ["finance-reporting", "finance reporting", "month-end report", "finance dbt models",
                 "revenue models"],
     "summary": "dbt models behind month-end revenue, wallet liability and GST reports."},
]

CUSTOMERS = [
    {"id": "cust-kairo", "name": "Kairo Living", "tier": "Enterprise", "integrationOwner": "p-rahul",
     "technicalContact": "p-rahul", "aliases": ["kairo living", "kairo"],
     "summary": "Home-furnishings retailer with 140 stores; order and delivery updates go out on WhatsApp from their ERP."},
    {"id": "cust-glowra", "name": "Glowra Beauty", "tier": "Pro", "integrationOwner": "p-kabir",
     "technicalContact": "p-jay", "aliases": ["glowra beauty", "glowra"],
     "summary": "D2C skincare brand; broadcast-heavy, runs festive sale campaigns to two million contacts."},
    {"id": "cust-crestline", "name": "Crestline Finance", "tier": "Enterprise", "integrationOwner": "p-jay",
     "technicalContact": "p-jay", "aliases": ["crestline finance", "crestline"],
     "summary": "Lending company sending EMI due-date and overdue reminders over WhatsApp."},
    {"id": "cust-northwind", "name": "Northwind Foods", "tier": "Pro", "integrationOwner": "p-sneha",
     "technicalContact": "p-rahul", "aliases": ["northwind foods", "northwind"],
     "summary": "D2C snacks and pantry brand on Shopify: abandoned-cart, COD confirmation and festive broadcasts."},
]

# ---------------------------------------------------------------------------
# Expertise targets: how strongly each person is connected to each system or
# account. The generator turns these into commits, reviews, thread answers,
# tickets and docs; the pipeline has to rediscover them from that activity.
#   O = owner-level, S = strong, C = credible alternate, W = weak/peripheral
# ---------------------------------------------------------------------------

EXPERTISE: dict[str, dict[str, str]] = {
    # Rahul's unique systems: nobody else above "weak".
    "sys-reconciler": {"p-rahul": "O", "p-arjun": "W", "p-neha": "W"},
    "sys-settlement": {"p-rahul": "O", "p-neha": "W", "p-omar": "W"},
    "sys-kairo-bridge": {"p-rahul": "O", "p-jay": "W", "p-sana": "W"},
    # Decoys: Rahul is strong, but so are others.
    "sys-msg-api": {"p-rahul": "S", "p-neha": "S", "p-arjun": "S", "p-kavya": "C", "p-omar": "W"},
    "sys-ledger": {"p-arjun": "O", "p-rahul": "S", "p-kavya": "C"},
    "sys-gateway": {"p-vikram": "O", "p-sana": "S", "p-rahul": "S", "p-ritu": "C", "p-tom": "W"},
    "sys-workflows": {"p-nikhil": "O", "p-zoya": "S", "p-rohan": "S", "p-gautam": "S", "p-rahul": "S"},
    # Vikram is the only strong link on CI.
    "sys-ci": {"p-vikram": "O", "p-sana": "W", "p-dev": "W", "p-tom": "W"},
    "sys-voice": {"p-ritu": "S", "p-tom": "S", "p-vikram": "C"},
    "sys-staging": {"p-dev": "S", "p-sana": "S", "p-tom": "C"},
    "sys-onboarding": {"p-yusuf": "S", "p-farah": "S", "p-manish": "C"},
    "sys-sendguard": {"p-farah": "O", "p-divya": "W", "p-yusuf": "W"},
    "sys-dwh": {"p-karthik": "S", "p-pranav": "S", "p-meera": "S", "p-lina": "C"},
    "sys-finrep": {"p-meera": "O", "p-lina": "W", "p-karthik": "W"},
    # Accounts
    "cust-kairo": {"p-rahul": "O", "p-jay": "W", "p-arnav": "W"},
    "cust-glowra": {"p-kabir": "O", "p-sneha": "W"},
    "cust-crestline": {"p-jay": "S", "p-sneha": "S", "p-rahul": "C"},
    "cust-northwind": {"p-sneha": "S", "p-rahul": "C", "p-riya": "C"},
}

# ---------------------------------------------------------------------------
# Decisions and workarounds. `roles` say how each person relates to the item
# in the planted sources (proposer > co-proposer > supporter > approver > ack).
# ---------------------------------------------------------------------------

DECISIONS = [
    # --- Rahul's four (unique) ---
    {"id": "dec-idem-72h", "summary": "Keep send-request idempotency keys for 72 hours",
     "about": ["sys-msg-api", "cust-kairo"], "decidedAt": "2026-03-12",
     "rationale": "Kairo's ERP retries failed order events for up to 72 hours after an outage; the 24-hour TTL caused the 18 Feb duplicate order confirmations.",
     "roles": {"p-rahul": "proposer", "p-priya": "approver", "p-neha": "ack", "p-arjun": "ack"}},
    {"id": "dec-settle-6am", "summary": "Run nightly wallet settlement at 06:00 IST",
     "about": ["sys-settlement"], "decidedAt": "2026-04-07",
     "rationale": "Meta's pricing analytics close on UTC days (05:30 IST). Midnight runs billed partial days, and Finance had to re-issue invoices twice in March.",
     "roles": {"p-rahul": "proposer", "p-kavya": "ack"}},
    {"id": "dec-recon-matching", "summary": "Reconcile on message ID first, then amount with ±0.01 USD tolerance for FX-converted debits",
     "about": ["sys-reconciler"], "decidedAt": "2026-05-20",
     "rationale": "Meta bills in USD and rounds conversions half-up, while wallets debit in INR with banker's rounding, so exact matching flagged about 2% of debits every night.",
     "roles": {"p-rahul": "proposer", "p-arjun": "ack"}},
    {"id": "dec-kairo-hmac", "summary": "Keep accepting Kairo's HMAC-SHA1 webhook signatures until their v2 cutover",
     "about": ["sys-kairo-bridge", "cust-kairo"], "decidedAt": "2026-06-17",
     "rationale": "Kairo's SHA-256 signer slipped to Q1 2027; v1 stays enabled behind the kairo_hmac_v1 flag, for Kairo only.",
     "roles": {"p-rahul": "proposer", "p-manish": "approver"}},
    # --- decoys: Rahul involved, but others hold the reasoning too ---
    {"id": "dec-gateway-idem", "summary": "Enforce Idempotency-Key headers at the API gateway",
     "about": ["sys-gateway", "sys-msg-api"], "decidedAt": "2026-06-09",
     "rationale": "Reject duplicate sends at the edge instead of in every service.",
     "roles": {"p-vikram": "proposer", "p-rahul": "co-proposer", "p-sana": "supporter", "p-priya": "ack"}},
    {"id": "dec-cart-30min", "summary": "Send the first abandoned-cart reminder after 30 minutes and cap cart reminders at two",
     "about": ["sys-workflows", "sys-sendguard"], "decidedAt": "2026-04-22",
     "rationale": "15-minute reminders reached shoppers still paying by UPI and raised block rates; 30 minutes kept recovery flat with fewer blocks.",
     "roles": {"p-nikhil": "proposer", "p-maya": "co-proposer", "p-farah": "supporter", "p-rahul": "supporter"}},
    {"id": "dec-ledger-outbox", "summary": "Emit wallet-ledger events through a transactional outbox",
     "about": ["sys-ledger", "sys-reconciler"], "decidedAt": "2026-07-28",
     "rationale": "Deploys were dropping debit events, which made the reconciler report phantom mismatches.",
     "roles": {"p-arjun": "proposer", "p-rahul": "supporter", "p-kavya": "ack"}},
    # --- other people's unique decisions (company-wide risk) ---
    {"id": "dec-ci-selfhosted", "summary": "Keep CI on self-hosted runners inside the production VPC",
     "about": ["sys-ci"], "decidedAt": "2026-05-05",
     "rationale": "The deploy pipeline holds every customer's Meta system-user tokens; hosted runners would put them outside our SOC 2 boundary.",
     "roles": {"p-vikram": "proposer", "p-ishaan": "approver", "p-sana": "ack"}},
    {"id": "dec-freq-cap", "summary": "Cap marketing messages at 5 per recipient per 7 days by default",
     "about": ["sys-sendguard"], "decidedAt": "2026-07-14",
     "rationale": "Workspaces sending 6–12 marketing messages a week saw block rates triple in June and two numbers drop to Low quality; 5 keeps festive campaigns workable.",
     "roles": {"p-farah": "proposer", "p-manish": "approver", "p-divya": "ack"}},
    {"id": "dec-revenue-consumption", "summary": "Recognise message revenue when Meta bills the conversation, not at wallet top-up",
     "about": ["sys-finrep"], "decidedAt": "2026-04-30",
     "rationale": "Auditors asked for revenue to follow consumption; unspent top-ups are a liability.",
     "roles": {"p-meera": "proposer", "p-sunil": "approver", "p-lina": "ack"}},
]

WORKAROUNDS = [
    # --- Rahul's four (unique) ---
    {"id": "wk-settle-lock", "summary": "Clear the stale settlement lock, then resume the run instead of re-running",
     "about": ["sys-settlement"],
     "roles": {"p-rahul": "author", "p-neha": "ack", "p-omar": "ack"}},
    {"id": "wk-flaky-test", "summary": "Re-run the flaky test_concurrent_send_refund job without random ordering",
     "about": ["sys-msg-api", "sys-ci"],
     "roles": {"p-rahul": "author", "p-omar": "ack", "p-kavya": "ack"}},
    {"id": "wk-kairo-bom", "summary": "Strip the BOM and CRLFs from Kairo's month-end order file before import",
     "about": ["sys-kairo-bridge", "cust-kairo"],
     "roles": {"p-rahul": "author", "p-sana": "ack"}},
    {"id": "wk-ledger-replay", "summary": "Replay 24h of wallet-ledger events into the reconciler after a ledger deploy",
     "about": ["sys-reconciler", "sys-ledger"],
     "roles": {"p-rahul": "author", "p-arjun": "ack"},
     "obsoleteBy": "CHEER-2412"},
    # --- decoy: Rahul posted it first, but it is common knowledge ---
    {"id": "wk-vpn-reset", "summary": "Reset Tailscale when the staging VPN drops",
     "about": ["sys-staging"],
     "roles": {"p-rahul": "author", "p-sana": "author", "p-tom": "applier", "p-ritu": "applier"}},
    # --- other people's unique workarounds ---
    {"id": "wk-ci-disk", "summary": "Prune the Docker layer cache when CI runners run out of disk",
     "about": ["sys-ci"], "roles": {"p-vikram": "author", "p-tom": "ack"}},
    {"id": "wk-kong-reload", "summary": "Do a rolling restart after changing Kong plugins; reload is not enough",
     "about": ["sys-gateway"], "roles": {"p-vikram": "author", "p-ritu": "ack"}},
    {"id": "wk-finrep-refresh", "summary": "Run the finance snapshot with --full-refresh on the 1st when Meta's pricing export is late",
     "about": ["sys-finrep"], "roles": {"p-meera": "author", "p-lina": "ack"}},
    {"id": "wk-pgcron-restore", "summary": "Disable pg_cron before restoring the staging snapshot or jobs double-fire",
     "about": ["sys-staging"], "roles": {"p-dev": "author", "p-sana": "ack"}},
]

# Ground truth for the precision test in the PRD's demo-success criteria.
PLANTED_UNIQUE = ["sys-reconciler", "wk-settle-lock", "cust-kairo", "dec-idem-72h", "wk-flaky-test"]
DECOYS = ["sys-gateway", "sys-workflows", "sys-msg-api", "sys-ledger", "cust-crestline",
          "dec-gateway-idem", "dec-cart-30min", "dec-ledger-outbox", "wk-vpn-reset"]
EXPECTED_RAHUL_COUNTS = {"System": 3, "Account": 1, "Decision": 4, "Workaround": 4}
EXPECTED_COMPANY_SPOF = 23
EXPECTED_SPOF_BY_PERSON = {"p-rahul": 12, "p-vikram": 4, "p-meera": 3, "p-farah": 2, "p-kabir": 1, "p-dev": 1}
STALE_RUNBOOK = "DOC-1042"

# Account Health and Sales Assist expectations (checked by `relay eval`).
EXPECTED_HEALTH = {
    "hero": "Northwind Foods", "hero_risk": 78, "hero_crm": 82,
    "silent": ["Northwind Foods", "Saffron Threads", "Banyan Home", "Medora Wellness"],
    "bug": "CHEER-2547", "bug_accounts": 5, "promise_at_risk": "prm-northwind-sso",
}

# Demo personas (X-Relay-Persona) and where each one lands.
PERSONAS = [
    {"id": "p-arnav", "persona": "head_cs", "home": "/home"},
    {"id": "p-sneha", "persona": "csm", "home": "/meetings"},
    {"id": "p-priya", "persona": "manager", "home": "/home"},
    {"id": "p-rahul", "persona": "leaver", "home": "/interview"},
    {"id": "p-aisha", "persona": "joiner", "home": "/day-one"},
]

# Suggested questions for Ask (⌘K and the Ask page).
ASK_SUGGESTIONS = [
    "Why is Northwind Foods at risk?",
    "Why does wallet settlement run at 6 AM?",
    "Is SSO coming in December?",
    "When will the campaign report export bug be fixed?",
    "Who else understands billing-reconciler?",
    "What did we promise Northwind Foods?",
]
