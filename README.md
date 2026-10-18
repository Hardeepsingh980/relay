# Relay

**One graph per company that knows its customers, its people and its product, and agents that act on it.**

Relay puts Account Health, Knowledge Continuity and Sales Assist on a single FalkorDB graph per company.
Five agents read and write that graph. They never message each other: when one writes a risk, a promise
or a handover answer, the others pick it up on their next read.

- **Account Health:** finds accounts that look healthy in the CRM but aren't, explains why with a
  multi-hop evidence chain, finds the other accounts the same bug hits and drafts a save plan that runs only
  after approval.
- **Knowledge Continuity:** when someone gives notice, removes them from the graph to find what only
  they know, interviews them, hands the answers to their successor and shows which customers are exposed.
- **Sales Assist:** builds a pre-call brief, then raises cards live during the call (roadmap changes,
  known bugs, product answers, objections, who to ask), logs promises and sends them back to the graph.
- **Ask (⌘K):** 2–4 sentence answers with a source on every claim and the graph path that led there.
- **Repo knowledge:** paste any public GitHub repo. Relay reads its history into a graph of who changed
  what, and shows what only one person knows and what leaves when they do.

**Hackathon:** FalkorDB × WeMakeDevs *Graph Hacks*, **Track 01: Agents That Act on Connected Data**.
The same build also shows the Memory & Coordination and Company Brain focus areas (see
[Track coverage](#track-coverage)).

## Try it

**Live app: https://relay.34-100-245-68.sslip.io**

| How to sign in | What you get |
|---|---|
| **One click:** pick a Cheerio teammate on the sign-in page (Arnav, Sneha, Priya, Rahul or Aisha) | Your own private copy of the Cheerio workspace. Switch teammates from the menu in the top right. Nothing you do affects other visitors. |
| **Test login:** `judge@relay.app` / `relay-graph-hacks` | A shared Cheerio workspace (use *Reset workspace* in the top-right menu to start over). |
| **Your own account:** *Sign in with email* → *Create an account* | A new workspace with the sample company of your choice. |

What to try, and what runs underneath:

1. **Knowledge graph** (left menu): the whole Cheerio graph in WebGL. Search for anyone, filter by type,
   click a node to see its neighbours. Every node and link comes from FalkorDB when the page loads.
2. **Sign in as Arnav → Accounts → Northwind Foods → Investigate.** The agent runs 14 graph tools
   live, then writes the finding. *Investigate with Gemini* lets Gemini pick the tools through MCP.
   Every step has *Show Cypher*.
3. **Approve all** on the save plan. Each action is saved in Relay, and goes to Jira, Slack or Gmail only
   when those are connected (Settings → Connections). Relay never says something was sent when it was not.
4. **Switch to Priya → People → Rahul Verma → Start handover → Preview departure.** Relay takes Rahul
   out of the graph and finds what nobody else knows. Northwind's risk goes up because he is its
   technical contact.
5. **Switch to Sneha → Meetings → Northwind renewal.** *Start the call* replays a recorded call with
   audio. *Start a live call* lets you type or speak your own lines: every line goes through the same
   triggers and graph lookups, and an open question gets a live Gemini answer.
6. **Switch to Aisha → ⌘K** and ask anything, for example "Why does wallet settlement run at 6 AM?".
7. **Repo knowledge:** paste any public GitHub repo (for example `https://github.com/FalkorDB/falkordb-py`).
   This uses real public data, real graph queries (including FalkorDB `algo.pageRank`) and real
   Gemini answers.
8. **Settings → Connections:** add real credentials (API key or OAuth client) for HubSpot, Zendesk, Slack,
   Jira, GitHub and others, or an MCP server. Relay checks each one with a live call before it saves it.

What is real and what is sample data:

- **Every number on screen is computed** by Cypher on FalkorDB when you open the page. No screen shows a
  hardcoded result. The landing page's graph and the three agent paths it lights up come from
  `GET /api/public/graph`, a read-only query on the sample graph.
- **Every AI answer is a live Gemini call** (`gemini-3.8-flash`). Only the one-off extraction during the
  graph build replays a response cache, so a rebuild gives the same graph.
- **Cheerio is a sample company with synthetic data.** The product (WhatsApp marketing) is real, but its
  45 people, 120 customers, messages, tickets and calls are generated (`backend/src/relay/seed/`). The
  recorded call is a scripted conversation voiced with Gemini text-to-speech. No real personal or customer
  data is used.
- **Repo knowledge runs on real public GitHub data** that you choose.

---

## The demo story (about 4 minutes)

Today is **Mon 19 Oct 2026, 09:30 IST** in the demo, and the clock runs from there.

| Time | Module | On screen |
|---|---|---|
| 0:00 | **Home** (Arnav, Head of CS) | 4 silent risks worth ₹30L ARR. **Northwind Foods:** HubSpot says 82/100 healthy, Relay says **78% risk**. Rahul (engineer) leaves Friday. |
| 0:20 | **Account Health** | *Investigate* streams live: the main contact, Ritika Sharma, left → the person who took over raised 3 tickets → all point to one bug, **CHEER-2547** (campaign report CSV export) → campaign-report usage down 70%. Relay's finding with sources, then *Other accounts hit*: the same bug hits **4 other accounts, ₹15.6L ARR**. A playbook from a past save and a 4-step save plan. |
| 1:00 | **Handovers** (Priya, eng manager) | Rahul's handover: *Preview departure* turns the 12 things only he knows red. The Handover agent writes owner-leaving risks: **Northwind 78 → 84**, Kairo Living 6 → 12. Rahul answers the 06:00 settlement question. |
| 1:40 | **Sales Assist** (Sneha, CSM) | The 15:00 renewal call replays through the live pipeline. Customer asks "Is SSO coming in December?" → card *SSO moved to Q1 2027, don't commit*. Export complaint → bug card with owner, and *Ask Dev* with the shortest working path to him. Sneha says "I'll confirm the Q1 timeline in writing this week" → promise logged. |
| 2:40 | **Follow-through** | Summary, follow-up email draft, CRM note. The old SSO promise is superseded, so Northwind drops **84 → 79** (78 → 73 if you ran the call before the handover). |
| 3:00 | **Day One** (Aisha, joiner) | Systems she inherits, *Meet these 5*, Rahul's answers. ⌘K "Why does wallet settlement run at 6 AM?" → answer, sources, the stale runbook flagged, and the path. |
| 3:30 | **Knowledge graph** | The whole company graph in WebGL: search, filter by type, click any node to see what it links to. Show Cypher on any card. |

The onboarding checklist (*Run the Relay demo, end to end*) walks through these steps and switches
persona for you. **Reset demo** in the demo menu restores the seeded state.

---

## Demo video

`demo/` records the demo video from the running app. Gemini text-to-speech voices the narrator and the four
people on the recorded call, and the captions are burned in. The recorder signs up a new account, then
goes through every scene above in a headless browser. It logs when each line starts, so the voices and
captions line up with the screen. See [demo/README.md](demo/README.md).

All UI text follows plain-English rules (the `simple-english` skill, based on ASD-STE100): short sentences,
active voice, no jargon, and one word for one meaning across the app.

---

## Deployment

The live app runs on one GCE VM in project `cheerio-app` (zone `asia-south1-a`): the single container from
`deploy/Dockerfile` (FalkorDB, the API and the web app behind an internal Caddy) plus Caddy for HTTPS.
All resources are named `relay-*` and labelled `app=relay-hackathon`.

```bash
deploy/gce/up.sh      # create the VPC, firewall, static IP, VM, then deploy
deploy/gce/push.sh    # upload the current source and rebuild after a change
deploy/gce/down.sh    # delete every relay-* resource
```

The same image also runs on Railway or any Docker host (see `deploy/README.md`).

## Quick start

Requirements: Docker, Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 20.9+ with pnpm.

```bash
docker compose up -d                          # FalkorDB 6.0.2 on :6395, FalkorDB Browser on :3015
cd backend
uv sync
uv run relay --tenant cheerio build           # exports -> extraction -> scoring -> risk scan -> graph
uv run relay --tenant lumen build             # second tenant (knowledge modules only)
uv run relay --tenant cheerio eval            # readiness checks against the planted story
uv run relay serve --port 8020                # API
```

```bash
cd frontend
pnpm install
pnpm dev --port 3025                          # http://localhost:3025
```

Open http://localhost:3025, choose **Get started**, create an account and pick **Cheerio** as the
sample company. Each workspace gets its own copy of the tenant graph. The local test account used
while building is in `backend/tests/LOCAL_TEST_ACCOUNT.md`.

The synthetic exports in `data/cheerio` and `data/lumen` are committed. `uv run relay --tenant cheerio
seed` regenerates them deterministically.

**Gemini (optional).** Copy `.env.example` to `.env` and set `GEMINI_API_KEY`. Gemini then plans
investigations (choosing MCP tools itself), writes cited Ask answers, interview questions and runbook
rewrites. With `RELAY_EXTRACTOR=gemini` it also extracts decisions and workarounds from meetings, docs
and threads; `relay eval` passes on that build too. Every response is cached in `.cache/llm.sqlite`,
so rebuilds and demos replay identically. Without a key everything still works: the guided
investigation plan, the seed annotations for extraction, curated questions and extractive Ask.

`RELAY_STEP_DELAY` (seconds, default 0) slows the investigation feed down for a live demo.

---

## Five agents, one shared memory

| Agent | Code | Reads | Writes | Hands off to |
|---|---|---|---|---|
| **Ingest** | `relay/ingest/` | Slack, Confluence, Jira, support desk, CRM, billing, product usage, calendar, call recordings, GitHub, HR | People, accounts, contacts, tickets, bugs, usage, signals, decisions, expertise (`KNOWS`) | Everyone |
| **Detective** | `relay/health/` | Accounts, contacts, tickets, bugs, usage, invoices, signals, promises, owner risks | `Risk`, `Investigation`, `Episode`, `Action` | Sales Assist (risks in the brief) |
| **Handover** | `relay/handover.py`, `analysis.py`, `health/handoff.py` | A leaver's unique knowledge and accounts | `RiskItem`, `Knowledge`, successor links, owner-leaving `Risk` on accounts | Detective, Onboarding |
| **Onboarding** | `relay/onboarding.py` | The joiner's area subgraph, verified answers | Checklist progress, `FAMILIAR_WITH` | Ask |
| **Sales Assist** | `relay/sales/` | Account context, roadmap, release notes, FAQ, bugs, experts, past calls | `Promise`, `Signal`, held `Meeting`, `Episode`, follow-up actions | Detective (promises and signals rescored) |

Hand-offs are graph writes:

- **Handover → Detective.** Analysing a departure writes
  `(:Risk {kind: 'internal_owner_leaving'})-[:ON]->(:Account)` for every account where the leaver is the
  technical contact, CS owner, sales POC or only knower, then rescans those accounts.
- **Sales Assist → Detective.** Promises from the call land as `(:Meeting)-[:PRODUCED]->(:Promise)-[:TO]->(:Account)`,
  with `DEPENDS_ON` the roadmap item or bug. A newer promise `SUPERSEDED_BY`-links the old one, and the
  account is rescanned.
- **Live ingest → Ask.** *Post Dev's Slack update* (demo menu) ingests a new message. Ask "When will
  the campaign report export bug be fixed?" changes from "no fix date" to the new date, with the
  message on the path.

**Memory.** Episodic: every investigation and call is an `Episode` on the account timeline.
Semantic: account, person and system facts, kept current as sources change (stale docs are flagged).
Procedural: `Playbook` nodes with `WORKED_FOR` accounts, reused by the next investigation.

---

## Graph data model

One FalkorDB graph per tenant: `cheerio` and `lumen` (working), `<tenant>_base` (pristine build,
restored with `GRAPH.COPY`), and `<tenant>_ws_<id>` per workspace. Users, sessions and workspaces live
in a separate `<graph>_accounts` graph.

**Nodes**

| Label | Key properties | From |
|---|---|---|
| `Company` | id, name, builtAt, extraction | build |
| `Person`, `Team` | name, role, team, status, endDate, slackId | HR |
| `Account` | name, arr, plan, renewalDate, crmHealthScore, detectiveRisk, previousRisk, riskFactors, silentRisk | CRM + scan |
| `Contact` | name, email, title, isChampion | CRM (customer-side people) |
| `System`, `Feature` | name, aliases, criticality / name, key | service catalog, product |
| `Ticket` (`source: 'support'`) | title, status, createdAt | support desk |
| `Ticket:Bug` | title, priority, status, jiraStatus | Jira |
| `UsageWeek` | weekIndex, metric, value | product analytics |
| `Invoice` | amount, dueDate, paidAt | billing |
| `Conversation`, `Signal` | occurredAt / type, quote, confidence | CS conversations |
| `Meeting` | kind (customer / internal), status (scheduled / held), transcript, recording | calendar, recorder |
| `Promise` | text, due, status | meetings, live calls |
| `RoadmapItem` | status, eta, etaLabel, originalLabel | roadmap |
| `Message`, `Channel`, `Doc`, `Commit`, `PullRequest` | text, t / title, kind, freshness | Slack, Confluence, GitHub |
| `Decision`, `Workaround` | summary, rationale, firstSeen | extraction |
| `Knowledge` | question, answer, verifiedAt | handover answers |
| `Risk` | kind, source (detective / handover), points, open | Detective, Handover |
| `Investigation`, `Episode`, `Action`, `Playbook` | verdict / outcome / status, approvedBy / trigger | agents |

**Key relationships**

| Edge | Meaning |
|---|---|
| `(Contact)-[:WORKS_AT {from, to, role}]->(Account)`, `(Contact)-[:SUCCEEDED]->(Contact)` | customer-side people, including who left and who replaced them |
| `(Contact)-[:RAISED]->(Ticket)-[:CONCERNS]->(Account)` | support tickets |
| `(Ticket)-[:SYMPTOM_OF {confidence, method}]->(Bug)-[:AFFECTS]->(Feature)` | different complaints, one root cause |
| `(Account)-[:USES]->(Feature)`, `(UsageWeek)-[:OF_ACCOUNT\|OF_FEATURE]->(…)` | usage and its trend |
| `(Conversation)-[:WITH_ACCOUNT]->(Account)`, `(Conversation)-[:EXPRESSES]->(Signal)` | competitor, budget, frustration signals |
| `(Meeting)-[:WITH]->(Account)`, `(Meeting)-[:PRODUCED]->(Promise)-[:DEPENDS_ON]->(RoadmapItem\|Bug)` | promises tied to what engineering is building |
| `(Person)-[:MANAGES {role}]->(Account)`, `(Person)-[:TECH_CONTACT_FOR]->(Account)` | internal owners |
| `(Person)-[:KNOWS {score, …signals}]->(System\|Account\|Decision\|Workaround)` | expertise, rebuilt from evidence with time decay |
| `(Decision\|Workaround)-[:SOURCED_FROM]->(Message\|Meeting\|Doc\|Commit)` | why things are the way they are |
| `(Knowledge)-[:EXPLAINS]->(item)`, `(Person)-[:VERIFIED]->(Knowledge)` | captured handover answers |
| `(Risk)-[:ON]->(Account)`, `(Risk)-[:CAUSED_BY]->(evidence)` | a verdict and its evidence chain |
| `(Investigation)-[:INVESTIGATED]->(Account)`, `-[:CITED]->(evidence)`; `(Episode)-[:FOR_ACCOUNT]->(Account)` | episodic memory |
| `(Playbook)-[:WORKED_FOR]->(Account)`, `-[:SOURCED_FROM]->(Doc)` | procedural memory |

---

## Key Cypher queries

All of these run as agent tools; every card, verdict step and answer can show the exact Cypher and its
timing.

**Multi-hop causal chain** (contact → tickets → shared bug → feature the account uses, plus the
champion they replaced and risk signals in the same window):

```cypher
MATCH (a:Account {id: $accountId})<-[:CONCERNS]-(t:Ticket {source: 'support'})<-[:RAISED]-(reporter:Contact),
      (t)-[s:SYMPTOM_OF]->(b:Bug)-[:AFFECTS]->(f:Feature)<-[:USES]-(a)
WHERE t.createdAt >= $since AND b.status <> 'Done' AND s.confidence >= $minLink
OPTIONAL MATCH (reporter)-[h:SUCCEEDED]->(former:Contact)-[w:WORKS_AT]->(a)
WHERE w.to >= $departureSince
OPTIONAL MATCH (a)<-[:WITH_ACCOUNT]-(cv:Conversation)-[:EXPRESSES]->(sig:Signal)
WHERE cv.occurredAt >= $since AND sig.type IN $riskSignals AND sig.confidence >= $minSignal
RETURN b.id AS bugId, f.id AS featureId, collect(DISTINCT t.id) AS tickets,
       avg(s.confidence) AS linkConfidence, collect(DISTINCT former.id) AS formerChampions, …
```

Candidate chains are ranked by `linkConfidence × (0.4 + 0.6 × featureDecline) × (0.5 + 0.5 × recency) ×
(1 + 0.25 × corroborating sources)`.

**Blast radius** (who else the same bug hurts):

```cypher
MATCH (b:Bug {id: $bugId})<-[s:SYMPTOM_OF]-(t:Ticket)-[:CONCERNS]->(a:Account)
WHERE s.confidence >= $minLink
OPTIONAL MATCH (c:Contact)-[:RAISED]->(t)
WITH b, a, collect(DISTINCT {id: t.id, title: t.title, raisedBy: c.name}) AS tickets
RETURN b, a, tickets ORDER BY a.arr DESC
```

**Costliest bugs** (open bugs ranked by distinct affected ARR, deduplicated per account):

```cypher
MATCH (b:Bug)<-[s:SYMPTOM_OF]-(t:Ticket)-[:CONCERNS]->(a:Account)
WHERE s.confidence >= $minLink AND b.status <> 'Done'
WITH b, a, count(t) AS tickets
OPTIONAL MATCH (b)-[:OWNED_BY]->(o:Person)
WITH b, o, count(a) AS accounts, sum(a.arr) AS arr, sum(tickets) AS tickets
RETURN b.id, b.title, b.priority, o.name, accounts, arr, tickets ORDER BY arr DESC LIMIT $limit
```

**Shortest working path to an expert** (Sales Assist *Ask Dev* card and the `experts` MCP tool).
Only working links count, so a shared all-hands doesn't make two people "close":

```cypher
MATCH (a:Person {id: $a}), (b:Person {id: $b})
WITH shortestPath((a)-[:ASSIGNED_TO|OWNED_BY|REPORTED_BY|MEMBER_OF|REPORTS_TO*..4]-(b)) AS p
WHERE p IS NOT NULL
RETURN [n IN nodes(p) | {label: labels(n)[0], id: n.id, name: coalesce(n.name, n.title, n.id)}] AS hops
```

**Promises at risk** (feeds the brief, the risk score and the live *Promise at risk* card):

```cypher
MATCH (p:Promise)-[:TO]->(a:Account)
WHERE p.status = 'open'
OPTIONAL MATCH (p)-[:DEPENDS_ON]->(d)
OPTIONAL MATCH (maker:Person)-[:MADE]->(p)
RETURN a.id, p.text, p.due, labels(d), d.status, d.eta, d.etaLabel, maker.name
```

A promise is at risk when what it depends on is delayed or cut past the promised date, or a bug it
depends on has no fix date.

**Accounts exposed by a departure** (Handover → Detective):

```cypher
MATCH (p:Person {id: $leaver})-[x:TECH_CONTACT_FOR|MANAGES|KNOWS]->(a:Account)
WHERE a.crmHealthScore IS NOT NULL
RETURN a.id, a.name, type(x) AS rel, x.role, x.score
```

`KNOWS` links count only when no other active person knows the account (`score > 0.4`).

**Remove-person analysis** (what only the leaver knows). FalkorDB 6.0 has no `EXISTS {}`
subqueries, so alternates are counted:

```cypher
MATCH (r:Person {id: $pid})-[k:KNOWS|CONTACT_FOR|DECIDED]->(item)
WHERE k.score > $strong AND (item:System OR item:Account OR item:Decision OR item:Workaround)
OPTIONAL MATCH (other:Person)-[k2:KNOWS|CONTACT_FOR|DECIDED]->(item)
WHERE other.id <> r.id AND other.status IN ['active', 'joining'] AND k2.score > $alt
WITH r, k, item, count(other) AS alternates
WHERE alternates = 0
RETURN labels(item)[0] AS type, item.id AS id, coalesce(item.name, item.summary) AS title, k.score AS score
ORDER BY score DESC
```

**Ask retrieval:** FalkorDB full-text indexes (`db.idx.fulltext.queryNodes`) over decisions,
workarounds, docs, messages, tickets, roadmap items and promises, then a graph walk from the linked
entities. Structured questions (risk, promises, bug fix dates, roadmap) are answered straight from the
graph by `ask_graph.py`.

### Risk score

The Detective recomputes every account from the graph on each scan (`relay/health/risk.py`):

| Factor | Points |
|---|---|
| Base | 6 |
| Champion left in the last 90 days | 18 |
| Unresolved support ticket linked to an open bug | 6 each, up to 3 |
| Weekly active users vs baseline | 25 per 100% drop (from 10%), cap 15 |
| Feature usage vs baseline | 15 per 100% drop (from 20%), cap 12 |
| Competitor evaluation signal | 12 |
| Budget pressure signal | 6 |
| Frustration signals | 4 each, cap 8 |
| Positive signals | −6 each, cap −12 |
| Latest invoice paid more than 7 days late | 3 |
| Promise at risk | 5 each, cap 10 |
| Internal owner leaving (written by the Handover agent) | 6 |
| Wallet balance under ₹5,000 | 4 |

Clamped to 5–95. **Silent risk** = CRM health ≥ 70 and Relay risk ≥ 60.
Northwind: 6 + 18 + 18 + 8 + 11 + 12 + 5 = **78**.

### Sales Assist triggers

Each transcript segment runs through rules, then graph lookups (median well under 50 ms; target under
3 s end to end):

| Heard | Card |
|---|---|
| A complaint about a feature | Known bug, status, owner, other accounts hit |
| A roadmap question | Current ETA vs what was promised, plus *Promise at risk* if a promise depends on it |
| A product question | Answer from release notes or the FAQ with the source, or "Not sure, ask <owner>" |
| A price or competitor objection | The playbook that worked before |
| "When will it be fixed?" | *Ask <owner>* with a draft Slack ping and the shortest working path |
| "I'll … by <day>" from our side | Promise logged with a resolved due date |
| Competitor, budget, frustration | Red risk card, with the earlier mention if there was one |

---

## MCP

The agent tools are exposed through an MCP server (`relay/health/mcp_server.py`), one tenant per
process:

```bash
uv run relay --tenant cheerio mcp              # stdio
uv run relay --tenant cheerio mcp --http       # streamable HTTP on 127.0.0.1:8721
```

Tools: `risk_radar`, `account_overview`, `champion_changes`, `ticket_root_causes`, `usage_trend`,
`signals`, `billing_events`, `risk_breakdown`, `causal_chain`, `blast_radius`, `costliest_bugs`,
`timeline`, `promises`, `internal_owners`, `roadmap_status`, `experts`, `memory`, `unique_knowledge`,
`who_knows`, `meeting_brief`, `ask`, `investigate`, `approve_action`.

For Claude Desktop or any MCP client:

```json
{
  "mcpServers": {
    "relay-cheerio": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/company_brain/backend", "relay", "--tenant", "cheerio", "mcp"]
    }
  }
}
```

*Investigate with Gemini* runs the Gemini planner over an in-memory MCP client: Gemini sees the tool
list, picks tools itself, and every call appears in the reasoning feed. The guided plan runs the same
tools in a fixed order when no key is set.

---

## Actions and approval

Every action is proposed with its destination and payload and runs only after a person approves it.
Customer-facing messages are drafts. Approvals are logged on the graph as `Action {approvedBy}`.

| Action | Live with | Without credentials |
|---|---|---|
| Escalate a bug, create a task (Jira) | `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY` | **Saved in Relay** as a task; Jira is not changed |
| Follow-up email (Gmail **draft**, never sent) | Google OAuth (`gmail.compose`) | Draft saved in Relay |
| Slack post, expert ping | `SLACK_WEBHOOK_URL` | **Saved in Relay**; nothing is posted to Slack |
| Calendar intro (Day One) | Google OAuth (`calendar.events`) | Saved in Relay; no invite is sent |

Relay never shows an action as delivered unless the tool confirmed it. Credentials can be added on the Connections page; Relay checks them with a live call before it stores them.

---

## Track coverage

| Focus area | Where it shows |
|---|---|
| Multi-hop reasoning | Causal chain: champion left → successor's tickets → one bug → feature → usage drop |
| Graph queries as agent tools | 23 MCP tools; causal chain, blast radius, costliest bugs, shortest working path, remove-person |
| Tool selection through MCP | *Investigate with Gemini*: the model picks MCP tools; each call is visible with its Cypher |
| Actions driven by the graph | Save plan, bug escalation, Slack ping, follow-up draft, CRM note, all approval-gated |
| Explainable results | Evidence drawer, source pills, *How I found this* path, *Show Cypher* on every card |
| Memory and hand-offs | Episodes, playbooks, Handover → Detective owner risks, Sales Assist → Detective promises |
| Concurrency | *Rescan all accounts* scores all 120 accounts while a call streams; every visitor works in their own graph copy at the same time |
| Separate memory per tenant | Every workspace (and every team sign-in) gets its own copy of the company graph; nothing is shared between them |
| Company brain | Slack, docs, Jira, meetings, CRM and support in one graph; live Slack ingest changes an Ask answer |

---

## Accounts, workspaces and sign-in

- Email and password (scrypt hashes, hashed session tokens in an HTTP-only cookie, rate-limited
  sign-in) or Google sign-in.
- Each workspace has its own graph, copied from the tenant build in milliseconds. Nothing leaks
  between workspaces or tenants.
- Teammates are invited by email with a role (admin or member).
- Credentials are encrypted at rest with `RELAY_SECRET_KEY` (a generated key in `.cache/` if unset).

To enable Google, create a Web OAuth client with the redirect URI
`http://localhost:8020/api/auth/google/callback` and set `GOOGLE_OAUTH_CLIENT_ID`,
`GOOGLE_OAUTH_CLIENT_SECRET`, `RELAY_PUBLIC_URL` and `RELAY_API_PUBLIC_URL` (see `.env.example`).

## Expertise scoring

Every `KNOWS` link is rebuilt from raw evidence. Team membership alone never counts.

```
raw   = Σ weight(signal) · 0.5^(age_days / 120)  +  3 if named owner
score = 1 − exp(−raw / 10)

commit 0.3 · review 0.3 · doc 3.0 · substantive thread answer 0.6 · resolved ticket 1.5
open ticket 0.75 · conversation with the customer's own people 0.5
```

Strong > 0.6; any other active person above 0.4 is a credible alternate. People who have left never
count as alternates.

---

## Synthetic data

`backend/src/relay/seed/<tenant>/` generates each tenant's exports deterministically.

**Cheerio:** 45 people in 10 teams, 120 customer accounts (INR), 466 customer contacts, 3,000 Slack
messages, 68 docs, 464 Jira issues (64 bugs), 1,083 support tickets, 57 meetings, 1,113 commits, 26
weeks of usage (23,375 rows), 372 CS conversations, 360 invoices, a roadmap, a calendar and a
21-segment recorded renewal call. Planted stories, all checked by tests and `relay eval`:

- Northwind Foods: silent risk at 78 vs CRM 82 (main contact left, CHEER-2547, usage down, competitor,
  a promise that depends on SSO, now delayed to Q1 2027)
- the same bug across 4 more accounts; three more silent risks (Saffron Threads, Banyan Home, Medora
  Wellness); decoys that look risky in one signal but aren't
- Rahul's 12 unique items (billing-reconciler, the Kairo Living integration, why wallet settlement runs
  at 06:00 IST, a stale settlement runbook) and the accounts he's the technical contact for

A second sample tenant (`backend/src/relay/seed/lumen/`) is used only by the tests, to check that graphs
stay isolated. The app shows Cheerio only.

## Tests

```bash
cd backend && uv run pytest -q          # 25 tests: graph logic, auth, workspaces, isolation, both tenants end to end
uv run relay --tenant cheerio eval      # demo-readiness checks
cd frontend && pnpm lint && pnpm exec tsc --noEmit && pnpm build
```

`tests/test_cheerio.py` builds an isolated graph and runs the full story: silent risk, investigation
and approval (simulated or drafted only, never "sent"), the Handover → Detective hand-off, the live
call with promise supersession, Ask with live ingest, tenant isolation and the MCP tools.

## Layout

```
backend/src/relay/
  ingest/      load.py, accounts.py, extract.py, llm_extract.py, score.py, pipeline.py, live.py
  health/      risk.py, tools.py, investigator.py, verdict.py, plan.py, gemini.py, mcp_server.py, handoff.py
  sales/       brief.py, triggers.py, live.py, summary.py
  seed/        cheerio/, lumen/ (deterministic generators)
  api.py, api_relay.py, ask.py, ask_graph.py, analysis.py, handover.py, onboarding.py, tenants.py
frontend/      Next.js 16, Tailwind v4, shadcn/ui, SWR, Cytoscape.js
data/          cheerio/, lumen/ (synthetic exports)
docker-compose.yml   FalkorDB 6.0.2
```

## AI assistance

This project was built with an AI coding assistant (Claude Code). At runtime, Relay optionally uses
Google Gemini for investigation planning, extraction and answer writing, as described above.
