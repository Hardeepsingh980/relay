"""The fictional Lumen world: who works there, what they run, and what they know.

This module is the *generator's* ground truth. The ingestion pipeline never reads
it: it only sees the raw exports written by `generate.py` (Slack, docs, tickets,
meetings, GitHub, HR). Tests compare what the pipeline reconstructs against the
expectations declared here.

Everything is fictional. Names are invented for a synthetic demo company.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Org
# ---------------------------------------------------------------------------

TEAMS = [
    {"id": "team-leadership", "name": "Leadership"},
    {"id": "team-payments", "name": "Payments"},
    {"id": "team-platform", "name": "Platform"},
    {"id": "team-checkout", "name": "Checkout"},
    {"id": "team-risk", "name": "Risk & Compliance"},
    {"id": "team-data", "name": "Data"},
    {"id": "team-partners", "name": "Partnerships"},
    {"id": "team-product", "name": "Product"},
    {"id": "team-finance", "name": "Finance"},
]

# (id, name, role, team, manager, start_date)
_PEOPLE = [
    ("p-ananya", "Ananya Rao", "CEO & Co-founder", "team-leadership", None, "2022-03-01"),
    ("p-sameer", "Sameer Kulkarni", "CTO & Co-founder", "team-leadership", "p-ananya", "2022-03-01"),
    ("p-leela", "Leela Thomas", "Head of People", "team-leadership", "p-ananya", "2023-01-09"),
    ("p-priya", "Priya Raman", "Engineering Manager", "team-payments", "p-sameer", "2023-04-03"),
    ("p-rahul", "Rahul Verma", "Senior Engineer", "team-payments", "p-priya", "2023-02-06"),
    ("p-neha", "Neha Iyer", "Software Engineer", "team-payments", "p-priya", "2024-01-15"),
    ("p-arjun", "Arjun Nair", "Senior Engineer", "team-payments", "p-priya", "2023-08-21"),
    ("p-kavya", "Kavya Reddy", "Software Engineer", "team-payments", "p-priya", "2024-06-10"),
    ("p-omar", "Omar Siddiqui", "Software Engineer", "team-payments", "p-priya", "2026-07-06"),
    ("p-aisha", "Aisha Khan", "Software Engineer", "team-payments", "p-priya", "2026-10-19"),
    ("p-ishaan", "Ishaan Gupta", "Engineering Manager", "team-platform", "p-sameer", "2023-03-13"),
    ("p-vikram", "Vikram Sethi", "Staff Engineer", "team-platform", "p-ishaan", "2022-07-18"),
    ("p-sana", "Sana Mirza", "Site Reliability Engineer", "team-platform", "p-ishaan", "2023-10-02"),
    ("p-dev", "Dev Malhotra", "Infrastructure Engineer", "team-platform", "p-ishaan", "2024-02-12"),
    ("p-ritu", "Ritu Bansal", "Software Engineer", "team-platform", "p-ishaan", "2024-05-06"),
    ("p-tom", "Tom Fernandes", "Software Engineer", "team-platform", "p-ishaan", "2025-01-13"),
    ("p-maya", "Maya Pillai", "Engineering Manager", "team-checkout", "p-sameer", "2023-05-22"),
    ("p-nikhil", "Nikhil Joshi", "Senior Engineer", "team-checkout", "p-maya", "2022-11-07"),
    ("p-zoya", "Zoya Ahmed", "Software Engineer", "team-checkout", "p-maya", "2024-03-04"),
    ("p-rohan", "Rohan Das", "Software Engineer", "team-checkout", "p-maya", "2024-09-16"),
    ("p-gautam", "Gautam Bhatt", "Frontend Engineer", "team-checkout", "p-maya", "2025-02-03"),
    ("p-tara", "Tara Menon", "Product Designer", "team-checkout", "p-maya", "2024-04-15"),
    ("p-farah", "Farah Qureshi", "Head of Risk", "team-risk", "p-ananya", "2022-09-05"),
    ("p-manish", "Manish Agarwal", "Compliance Lead", "team-risk", "p-farah", "2023-06-12"),
    ("p-divya", "Divya Krishnan", "Fraud Analyst", "team-risk", "p-farah", "2024-08-19"),
    ("p-yusuf", "Yusuf Ali", "Risk Engineer", "team-risk", "p-farah", "2024-01-08"),
    ("p-elena", "Elena D'Souza", "Compliance Analyst", "team-risk", "p-farah", "2025-03-17"),
    ("p-meera", "Meera Shah", "Analytics Engineer", "team-data", "p-sameer", "2023-07-10"),
    ("p-karthik", "Karthik Subramanian", "Data Engineer", "team-data", "p-meera", "2024-02-26"),
    ("p-lina", "Lina George", "Data Analyst", "team-data", "p-meera", "2024-11-04"),
    ("p-pranav", "Pranav Kapoor", "Data Scientist", "team-data", "p-meera", "2025-04-21"),
    ("p-arnav", "Arnav Mehta", "Head of Partnerships", "team-partners", "p-ananya", "2022-10-03"),
    ("p-kabir", "Kabir Anand", "Partnerships Manager", "team-partners", "p-arnav", "2023-09-11"),
    ("p-jay", "Jay Patel", "Solutions Engineer", "team-partners", "p-arnav", "2023-11-20"),
    ("p-sneha", "Sneha Bose", "Customer Success Manager", "team-partners", "p-arnav", "2024-04-01"),
    ("p-riya", "Riya Sen", "Support Specialist", "team-partners", "p-arnav", "2025-06-09"),
    ("p-naina", "Naina Kohli", "Head of Product", "team-product", "p-ananya", "2023-02-20"),
    ("p-isha", "Isha Chawla", "Product Manager, Payments", "team-product", "p-naina", "2024-07-01"),
    ("p-varun", "Varun Desai", "Product Manager, Checkout", "team-product", "p-naina", "2024-10-14"),
    ("p-sunil", "Sunil Arora", "Finance Controller", "team-finance", "p-ananya", "2023-03-27"),
]

PEOPLE = [
    {
        "id": pid, "name": name, "role": role, "team": team, "managerId": mgr,
        "startDate": start, "endDate": None,
        "status": "joining" if pid == "p-aisha" else "active",
        "email": name.lower().replace(" ", ".").replace("'", "") + "@lumen.example",
    }
    for pid, name, role, team, mgr, start in _PEOPLE
]

# A former engineer whose old commits still sit in reconciliation-service history.
FORMER_PEOPLE = [
    {"id": "p-karan", "name": "Karan Shah", "role": "Senior Engineer", "team": "team-payments",
     "managerId": "p-priya", "startDate": "2022-06-06", "endDate": "2025-12-19", "status": "left",
     "email": "karan.shah@lumen.example"},
]

LEAVER = "p-rahul"
MANAGER = "p-priya"
JOINER = "p-aisha"

# People outside Lumen who appear in shared channels and DMs.
CONTACTS = [
    {"id": "c-daniel", "name": "Daniel Okafor", "role": "Integration Lead", "customer": "cust-acme"},
    {"id": "c-mei", "name": "Mei Lin", "role": "Platform Engineer", "customer": "cust-acme"},
    {"id": "c-sofia", "name": "Sofia Marquez", "role": "Payouts Ops Lead", "customer": "cust-globex"},
    {"id": "c-tom-b", "name": "Tom Bradley", "role": "CTO", "customer": "cust-initech"},
]

BOTS = [
    {"id": "b-pagerduty", "name": "PagerDuty"},
    {"id": "b-deploybot", "name": "deploybot"},
]

# ---------------------------------------------------------------------------
# Systems and customers (service catalog + CRM export)
# ---------------------------------------------------------------------------

SYSTEMS = [
    {"id": "sys-recon", "name": "reconciliation-service", "team": "team-payments", "criticality": "critical",
     "repo": "lumen/reconciliation-service", "serviceOwner": "p-rahul",
     "aliases": ["reconciliation-service", "reconciliation service", "recon-service", "recon service",
                 "recon-svc", "recon-cli", "recon"],
     "summary": "Matches Acme Bank statement lines against ledger entries every night."},
    {"id": "sys-settlement", "name": "settlement-batch", "team": "team-payments", "criticality": "critical",
     "repo": "lumen/settlement-batch", "serviceOwner": "p-rahul",
     "aliases": ["settlement-batch", "settlement batch", "settlement job", "nightly settlement",
                 "settlement run", "settlement cron"],
     "summary": "Nightly job that settles merchant payouts and closes the day in the ledger."},
    {"id": "sys-acme-bridge", "name": "acme-sftp-bridge", "team": "team-payments", "criticality": "high",
     "repo": None, "serviceOwner": "p-rahul",
     "aliases": ["acme-sftp-bridge", "acme sftp bridge", "sftp bridge", "acme bridge", "acme sftp"],
     "summary": "Pulls Acme Bank statement files over SFTP and verifies Acme webhooks."},
    {"id": "sys-payments-api", "name": "payments-api", "team": "team-payments", "criticality": "critical",
     "repo": "lumen/payments-api", "serviceOwner": "p-arjun",
     "aliases": ["payments-api", "payments api", "pay-api"],
     "summary": "Public API for creating, capturing and refunding payments."},
    {"id": "sys-ledger", "name": "ledger-service", "team": "team-payments", "criticality": "critical",
     "repo": "lumen/ledger-service", "serviceOwner": "p-arjun",
     "aliases": ["ledger-service", "ledger service", "ledger"],
     "summary": "Double-entry ledger of every money movement."},
    {"id": "sys-gateway", "name": "api-gateway", "team": "team-platform", "criticality": "critical",
     "repo": "lumen/api-gateway", "serviceOwner": "p-vikram",
     "aliases": ["api-gateway", "api gateway", "gateway", "kong"],
     "summary": "Kong-based edge gateway: auth, rate limits, idempotency headers."},
    {"id": "sys-checkout", "name": "checkout-web", "team": "team-checkout", "criticality": "high",
     "repo": "lumen/checkout-web", "serviceOwner": "p-nikhil",
     "aliases": ["checkout-web", "checkout web", "checkout flow", "checkout page", "checkout"],
     "summary": "Hosted checkout pages and the card/UPI payment flow."},
    {"id": "sys-ci", "name": "ci-pipeline", "team": "team-platform", "criticality": "high",
     "repo": None, "serviceOwner": "p-vikram",
     "aliases": ["ci-pipeline", "ci pipeline", "buildkite", "ci runners", "ci runner"],
     "summary": "Self-hosted Buildkite runners and deploy pipeline."},
    {"id": "sys-flags", "name": "feature-flags", "team": "team-platform", "criticality": "medium",
     "repo": None, "serviceOwner": "p-ritu",
     "aliases": ["feature-flags", "feature flags", "flag service", "unleash"],
     "summary": "Unleash-backed feature flag service."},
    {"id": "sys-staging", "name": "staging-env", "team": "team-platform", "criticality": "medium",
     "repo": None, "serviceOwner": "p-dev",
     "aliases": ["staging-env", "staging env", "staging environment", "staging db", "staging"],
     "summary": "Shared staging environment and its nightly database snapshots."},
    {"id": "sys-kyc", "name": "kyc-pipeline", "team": "team-risk", "criticality": "high",
     "repo": None, "serviceOwner": "p-yusuf",
     "aliases": ["kyc-pipeline", "kyc pipeline", "kyc checks", "kyc"],
     "summary": "Merchant onboarding and KYC verification pipeline."},
    {"id": "sys-fraud", "name": "fraud-rules", "team": "team-risk", "criticality": "high",
     "repo": None, "serviceOwner": "p-farah",
     "aliases": ["fraud-rules", "fraud rules", "rules engine", "fraud engine"],
     "summary": "Real-time fraud rules evaluated on every card payment."},
    {"id": "sys-dwh", "name": "data-warehouse", "team": "team-data", "criticality": "medium",
     "repo": None, "serviceOwner": "p-karthik",
     "aliases": ["data-warehouse", "data warehouse", "warehouse", "bigquery"],
     "summary": "BigQuery warehouse fed by CDC from production databases."},
    {"id": "sys-finrep", "name": "finance-reporting", "team": "team-data", "criticality": "high",
     "repo": None, "serviceOwner": "p-meera",
     "aliases": ["finance-reporting", "finance reporting", "month-end report", "finance dbt models",
                 "revenue models"],
     "summary": "dbt models behind month-end revenue and settlement reports."},
]

CUSTOMERS = [
    {"id": "cust-acme", "name": "Acme Bank", "tier": "sponsor bank", "integrationOwner": "p-rahul",
     "aliases": ["acme bank", "acme"],
     "summary": "Sponsor bank: holds settlement accounts, sends daily statement files."},
    {"id": "cust-globex", "name": "Globex Pay", "tier": "payout partner", "integrationOwner": "p-kabir",
     "aliases": ["globex pay", "globex"],
     "summary": "Cross-border payout partner for merchant withdrawals."},
    {"id": "cust-initech", "name": "Initech Lending", "tier": "enterprise merchant", "integrationOwner": "p-jay",
     "aliases": ["initech lending", "initech"],
     "summary": "Lending platform using payments-api for EMI collections."},
    {"id": "cust-umbrella", "name": "Umbrella Retail", "tier": "enterprise merchant", "integrationOwner": "p-sneha",
     "aliases": ["umbrella retail", "umbrella"],
     "summary": "Retail chain on hosted checkout across 140 stores."},
]

# ---------------------------------------------------------------------------
# Expertise targets: how strongly each person is connected to each system or
# customer. The generator turns these into commits, reviews, thread answers,
# tickets and docs; the pipeline has to rediscover them from that activity.
#   O = owner-level, S = strong, C = credible alternate, W = weak/peripheral
# ---------------------------------------------------------------------------

EXPERTISE: dict[str, dict[str, str]] = {
    # Rahul's unique systems: nobody else above "weak".
    "sys-recon": {"p-rahul": "O", "p-arjun": "W", "p-neha": "W"},
    "sys-settlement": {"p-rahul": "O", "p-neha": "W", "p-omar": "W"},
    "sys-acme-bridge": {"p-rahul": "O", "p-jay": "W", "p-sana": "W"},
    # Decoys: Rahul is strong, but so are others.
    "sys-payments-api": {"p-rahul": "S", "p-neha": "S", "p-arjun": "S", "p-kavya": "C", "p-omar": "W"},
    "sys-ledger": {"p-arjun": "O", "p-rahul": "S", "p-kavya": "C"},
    "sys-gateway": {"p-vikram": "O", "p-sana": "S", "p-rahul": "S", "p-ritu": "C", "p-tom": "W"},
    "sys-checkout": {"p-nikhil": "O", "p-zoya": "S", "p-rohan": "S", "p-gautam": "S", "p-rahul": "S"},
    # Vikram is the only strong link on CI.
    "sys-ci": {"p-vikram": "O", "p-sana": "W", "p-dev": "W", "p-tom": "W"},
    "sys-flags": {"p-ritu": "S", "p-tom": "S", "p-vikram": "C"},
    "sys-staging": {"p-dev": "S", "p-sana": "S", "p-tom": "C"},
    "sys-kyc": {"p-yusuf": "S", "p-farah": "S", "p-manish": "C"},
    "sys-fraud": {"p-farah": "O", "p-divya": "W", "p-yusuf": "W"},
    "sys-dwh": {"p-karthik": "S", "p-pranav": "S", "p-meera": "S", "p-lina": "C"},
    "sys-finrep": {"p-meera": "O", "p-lina": "W", "p-karthik": "W"},
    # Customers
    "cust-acme": {"p-rahul": "O", "p-jay": "W", "p-arnav": "W"},
    "cust-globex": {"p-kabir": "O", "p-sneha": "W"},
    "cust-initech": {"p-jay": "S", "p-sneha": "S", "p-rahul": "C"},
    "cust-umbrella": {"p-sneha": "S", "p-nikhil": "C", "p-riya": "C"},
}

# ---------------------------------------------------------------------------
# Decisions and workarounds. `roles` say how each person relates to the item
# in the planted sources (proposer > co-proposer > supporter > approver > ack).
# ---------------------------------------------------------------------------

DECISIONS = [
    # --- Rahul's four (unique) ---
    {"id": "dec-idem-72h", "summary": "Retain payment idempotency keys for 72 hours",
     "about": ["sys-payments-api", "cust-acme"], "decidedAt": "2026-03-12",
     "rationale": "Acme Bank retries failed callbacks for up to 72 hours after an outage; shorter TTLs caused the Feb 18 duplicate credits.",
     "roles": {"p-rahul": "proposer", "p-priya": "approver", "p-neha": "ack", "p-arjun": "ack"}},
    {"id": "dec-settle-2am", "summary": "Run nightly settlement at 02:00 IST",
     "about": ["sys-settlement", "cust-acme"], "decidedAt": "2026-04-07",
     "rationale": "Acme drops the statement file around 01:30 IST and Finance needs the ledger closed by 06:00; midnight runs used partial files.",
     "roles": {"p-rahul": "proposer", "p-kavya": "ack"}},
    {"id": "dec-recon-matching", "summary": "Reconcile on bank reference first, then amount with ±1 minor-unit FX tolerance",
     "about": ["sys-recon"], "decidedAt": "2026-05-20",
     "rationale": "Acme rounds FX conversions half-up while the ledger uses banker's rounding, so exact amount matching flags false mismatches.",
     "roles": {"p-rahul": "proposer", "p-arjun": "ack"}},
    {"id": "dec-acme-hmac", "summary": "Keep accepting Acme's HMAC-SHA1 webhook signatures until their v2 cutover",
     "about": ["sys-acme-bridge", "cust-acme"], "decidedAt": "2026-06-17",
     "rationale": "Acme's SHA-256 signer slipped to Q1 2027; v1 stays enabled behind the acme_hmac_v1 flag, for Acme only.",
     "roles": {"p-rahul": "proposer", "p-manish": "approver"}},
    # --- decoys: Rahul involved, but others hold the reasoning too ---
    {"id": "dec-gateway-idem", "summary": "Enforce Idempotency-Key headers at the API gateway",
     "about": ["sys-gateway", "sys-payments-api"], "decidedAt": "2026-06-09",
     "rationale": "Reject duplicate POSTs at the edge instead of in every service.",
     "roles": {"p-vikram": "proposer", "p-rahul": "co-proposer", "p-sana": "supporter", "p-priya": "ack"}},
    {"id": "dec-checkout-3ds", "summary": "Use frictionless 3-D Secure for card payments under ₹2,000",
     "about": ["sys-checkout", "sys-fraud"], "decidedAt": "2026-04-22",
     "rationale": "Cuts checkout drop-off on small tickets while fraud rules still score every payment.",
     "roles": {"p-nikhil": "proposer", "p-maya": "co-proposer", "p-farah": "supporter", "p-rahul": "supporter"}},
    {"id": "dec-ledger-outbox", "summary": "Emit ledger events through a transactional outbox",
     "about": ["sys-ledger", "sys-recon"], "decidedAt": "2026-07-28",
     "rationale": "Deploys were dropping events, which made reconciliation report phantom mismatches.",
     "roles": {"p-arjun": "proposer", "p-rahul": "supporter", "p-kavya": "ack"}},
    # --- other people's unique decisions (company-wide risk) ---
    {"id": "dec-ci-selfhosted", "summary": "Keep CI on self-hosted runners inside the PCI network",
     "about": ["sys-ci"], "decidedAt": "2026-05-05",
     "rationale": "Hosted runners would pull the deploy pipeline into PCI audit scope.",
     "roles": {"p-vikram": "proposer", "p-ishaan": "approver", "p-sana": "ack"}},
    {"id": "dec-velocity-5", "summary": "Limit card attempts to 5 cards per device per 24 hours",
     "about": ["sys-fraud"], "decidedAt": "2026-07-14",
     "rationale": "Card-testing attacks in June used 6–12 cards per device; 5 blocks them without hurting families sharing a phone.",
     "roles": {"p-farah": "proposer", "p-manish": "approver", "p-divya": "ack"}},
    {"id": "dec-revenue-settle-date", "summary": "Recognise month-end revenue on settlement date, not capture date",
     "about": ["sys-finrep"], "decidedAt": "2026-04-30",
     "rationale": "Auditors asked revenue to follow when funds actually settle at Acme.",
     "roles": {"p-meera": "proposer", "p-sunil": "approver", "p-lina": "ack"}},
]

WORKAROUNDS = [
    # --- Rahul's four (unique) ---
    {"id": "wk-settle-lock", "summary": "Clear the stale settlement lock, then resume the batch instead of re-running",
     "about": ["sys-settlement"],
     "roles": {"p-rahul": "author", "p-neha": "ack", "p-omar": "ack"}},
    {"id": "wk-flaky-test", "summary": "Re-run the flaky test_concurrent_capture_refund job without random ordering",
     "about": ["sys-payments-api", "sys-ci"],
     "roles": {"p-rahul": "author", "p-omar": "ack", "p-kavya": "ack"}},
    {"id": "wk-acme-bom", "summary": "Strip the BOM and CRLFs from Acme's month-end statement before import",
     "about": ["sys-recon", "cust-acme"],
     "roles": {"p-rahul": "author", "p-sana": "ack"}},
    {"id": "wk-ledger-replay", "summary": "Replay 24h of ledger events into recon after a ledger deploy",
     "about": ["sys-recon", "sys-ledger"],
     "roles": {"p-rahul": "author", "p-arjun": "ack"},
     "obsoleteBy": "LUM-412"},
    # --- decoy: Rahul posted it first, but it is common knowledge ---
    {"id": "wk-vpn-reset", "summary": "Reset Tailscale when the staging VPN drops",
     "about": ["sys-staging"],
     "roles": {"p-rahul": "author", "p-sana": "author", "p-tom": "applier", "p-ritu": "applier"}},
    # --- other people's unique workarounds ---
    {"id": "wk-ci-disk", "summary": "Prune the Docker layer cache when CI runners run out of disk",
     "about": ["sys-ci"], "roles": {"p-vikram": "author", "p-tom": "ack"}},
    {"id": "wk-kong-reload", "summary": "Do a rolling restart after changing Kong plugins; reload is not enough",
     "about": ["sys-gateway"], "roles": {"p-vikram": "author", "p-ritu": "ack"}},
    {"id": "wk-finrep-refresh", "summary": "Run the finance snapshot with --full-refresh on the 1st when Acme files are late",
     "about": ["sys-finrep", "cust-acme"], "roles": {"p-meera": "author", "p-lina": "ack"}},
    {"id": "wk-pgcron-restore", "summary": "Disable pg_cron before restoring the staging snapshot or jobs double-fire",
     "about": ["sys-staging"], "roles": {"p-dev": "author", "p-sana": "ack"}},
]

# Ground truth for the precision test in the PRD's demo-success criteria.
PLANTED_UNIQUE = ["sys-recon", "wk-settle-lock", "cust-acme", "dec-idem-72h", "wk-flaky-test"]
DECOYS = ["sys-gateway", "sys-checkout", "sys-payments-api", "sys-ledger", "cust-initech",
          "dec-gateway-idem", "dec-checkout-3ds", "dec-ledger-outbox", "wk-vpn-reset"]
EXPECTED_RAHUL_COUNTS = {"System": 3, "Account": 1, "Decision": 4, "Workaround": 4}
EXPECTED_COMPANY_SPOF = 23
EXPECTED_SPOF_BY_PERSON = {"p-rahul": 12, "p-vikram": 4, "p-meera": 3, "p-farah": 2, "p-kabir": 1, "p-dev": 1}
