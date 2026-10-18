# Relay

Relay is a set of AI agents for software companies. It puts customers, people and work into one FalkorDB graph, and the agents act on that graph. They find customers who are about to leave, find what a leaving engineer knows that nobody else does, and help sales teams during live calls. Every finding shows its source, and every action waits for a person to approve it.

Built for FalkorDB × WeMakeDevs Graph Hacks, Track 01: Agents That Act on Connected Data.

Live app: https://relay.34-100-245-68.sslip.io

## The problem

A customer can look healthy in the CRM while it gets ready to leave. The signs are in different tools. The main contact left (CRM). Her replacement raised three tickets (support). All three tickets point to one bug (Jira). Use of the feature dropped (product analytics). No single tool sees the whole chain.

People leave too. When an engineer resigns, the reasons behind his systems leave with him. And on a sales call, nobody remembers that the roadmap changed after the last promise.

Relay connects these facts in a graph, so an agent can follow the chain from one fact to the next.

## Try it

Open the live app and sign in one of three ways:

- Pick a teammate at Cheerio on the sign-in page. You get a private copy of the workspace, and nothing you do affects other visitors.
- Use the test login `judge@relay.app` / `relay-graph-hacks`. This workspace is shared. To start again, open the menu in the top right and choose Reset workspace.
- Create your own account with Sign in with email.

Then try these steps in order:

1. As Arnav, open Accounts → Northwind Foods → Investigate. HubSpot gives Northwind 82 out of 100, but Relay gives it a 78% risk. It shows why: the main contact left, her replacement raised 3 tickets, and all 3 point to one bug, CHEER-2547. Each step has Show Cypher.
2. Click Approve all on the save plan. Relay saves each task. If Jira or Slack is connected, the same click also creates the task there.
3. Switch to Priya in the top-right menu. Open People → Rahul Verma → Start handover, then turn on Preview departure. Relay takes Rahul out of the graph and finds 12 things that nobody else knows. Northwind's risk goes up to 84, because Rahul is its technical contact.
4. Switch to Sneha. Open Meetings → Northwind Foods <> Cheerio: renewal → Start the call. Cards appear while the customer talks. When the call ends, the new promise replaces the old one, and the risk drops to 79. Start a live call lets you type or speak your own lines.
5. Switch to Aisha. Press ⌘K and ask "Why does wallet settlement run at 6 AM?". Gemini answers from the graph and shows its sources.
6. Open Knowledge graph to see the whole company graph. Then open Repo knowledge and paste any public GitHub repo, for example `https://github.com/FalkorDB/falkordb-py`.

Cheerio is a real product, but its people, customers and numbers here are synthetic. Every number on screen comes from a Cypher query when the page loads. Every AI answer is a live Gemini call. Repo knowledge uses real public GitHub data.

## How it works

Relay keeps one FalkorDB graph for each company. Five agents read and write it:

- Ingest loads Slack, Jira, support tickets, CRM, product usage, docs, meetings and GitHub into the graph.
- Account Health scores every account and investigates the risky ones.
- Handover finds what a leaving person alone knows, and asks them short questions before they go.
- Onboarding gives the new joiner a Day One page with the systems and people that matter.
- Sales Assist writes a brief before a call, shows cards during it, and logs promises after it.

The agents pass work through the graph. When the Handover agent finds that Rahul is Northwind's technical contact, it writes an "owner is leaving" risk on the account. The next Account Health scan reads that risk, and Northwind's score goes from 78 to 84. When a call logs a new promise, a `SUPERSEDED_BY` edge replaces the old one, and the score drops again.

## How Relay uses FalkorDB

If you take FalkorDB out, Relay does not work. Every screen, agent step and answer is a Cypher query. These are the main jobs it does, with times from the live app:

1. Multi-hop search. The Account Health investigation follows the chain from the account to the contact who left, her replacement, the tickets, the bug and the feature. It runs 23 Cypher queries in 14 steps, and all 23 take 62 ms in the database.
2. Blast radius. One more hop from the bug finds every other account that it hits. For CHEER-2547, that is 4 more accounts worth ₹15.6 lakh a year.
3. Remove a person. The Handover agent finds each system, decision and workaround where the leaver is the only strong link.
4. Shortest path. A `shortestPath` query finds the quickest working route through colleagues to the owner of a bug.
5. Full-text search. Full-text indexes on 8 node types give the Ask agent its facts. Gemini writes the answer only from those facts and cites each one.
6. Live calls. Each line of a call runs graph lookups and becomes a card in about 70 ms.
7. A private graph for each visitor. At sign-in, `GRAPH.COPY` copies the whole company graph (31,645 nodes and 68,264 relationships) in about half a second.
8. Graph algorithms. Repo knowledge runs `algo.pageRank` on real GitHub history to find the central contributors.
9. MCP. The 23 graph tools are open to any AI agent over MCP. In Investigate with Gemini, the model picks the tools itself.

One FalkorDB instance holds all of these graphs:

- `cheerio`: the working graph.
- `cheerio_base`: the clean build, used to reset and to copy.
- `cheerio_ws_<id>`: one copy for each workspace.
- `cheerio_accounts`: users, sessions and workspaces.
- `repo_<owner>_<name>`: one graph for each GitHub repo that someone analyzes.

## Graph model

These are the main paths that the agents walk:

```
(Contact)-[:SUCCEEDED]->(Contact)-[:WORKS_AT]->(Account)
(Contact)-[:RAISED]->(Ticket)-[:CONCERNS]->(Account)
(Ticket)-[:SYMPTOM_OF]->(Bug)-[:AFFECTS]->(Feature)<-[:USES]-(Account)
(Person)-[:KNOWS {score}]->(System | Account | Decision | Workaround)
(Person)-[:TECH_CONTACT_FOR]->(Account)
(Person)-[:MADE]->(Promise)-[:TO]->(Account)
(Promise)-[:DEPENDS_ON]->(RoadmapItem | Bug)
(Promise)-[:SUPERSEDED_BY]->(Promise)
(Decision | Workaround)-[:SOURCED_FROM]->(Message | Doc | Meeting | Commit)
(Risk)-[:ON]->(Account)
```

Each `KNOWS` score comes from evidence: commits, reviews, docs, Slack answers and tickets. Older evidence counts less, and team membership alone never counts. A score above 0.6 is a strong link. Other labels include Team, Meeting, Message, Doc, Commit, Signal, UsageWeek, Invoice, Knowledge, Investigation, Action and Playbook.

## Key Cypher queries

The causal chain finds the tickets, the shared bug and the feature, plus the contact who left:

```cypher
MATCH (a:Account {id: $accountId})<-[:CONCERNS]-(t:Ticket {source: 'support'})<-[:RAISED]-(reporter:Contact),
      (t)-[s:SYMPTOM_OF]->(b:Bug)-[:AFFECTS]->(f:Feature)<-[:USES]-(a)
WHERE t.createdAt >= $since AND b.status <> 'Done' AND s.confidence >= $minLink
OPTIONAL MATCH (reporter)-[h:SUCCEEDED]->(former:Contact)-[w:WORKS_AT]->(a)
WHERE w.to >= $departureSince
RETURN b.id AS bugId, f.id AS featureId, collect(DISTINCT t.id) AS tickets,
       avg(s.confidence) AS linkConfidence, collect(DISTINCT former.id) AS formerChampions
```

The blast radius finds every account that the same bug hurts:

```cypher
MATCH (b:Bug {id: $bugId})<-[s:SYMPTOM_OF]-(t:Ticket)-[:CONCERNS]->(a:Account)
WHERE s.confidence >= $minLink
OPTIONAL MATCH (c:Contact)-[:RAISED]->(t)
WITH b, a, collect(DISTINCT {id: t.id, title: t.title, raisedBy: c.name}) AS tickets
RETURN b, a, tickets ORDER BY a.arr DESC
```

The remove-person query finds what only the leaver knows. FalkorDB 6.0 has no `EXISTS {}` subqueries, so the query counts the other people instead:

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

The shortest working path finds who can reach a bug owner fastest. Only working links count, so a shared all-hands meeting does not make two people close:

```cypher
MATCH (a:Person {id: $a}), (b:Person {id: $b})
WITH shortestPath((a)-[:ASSIGNED_TO|OWNED_BY|REPORTED_BY|MEMBER_OF|REPORTS_TO*..4]-(b)) AS p
WHERE p IS NOT NULL
RETURN [n IN nodes(p) | {label: labels(n)[0], id: n.id, name: coalesce(n.name, n.title, n.id)}] AS hops
```

## Run it locally

You need Docker, Python 3.12 with [uv](https://docs.astral.sh/uv/), and Node 20.9 or later with pnpm.

```bash
docker compose up -d                     # FalkorDB on port 6395
cd backend
uv sync
uv run relay --tenant cheerio build      # build the Cheerio graph from data/cheerio
uv run relay serve --port 8020           # the API
```

In a second terminal:

```bash
cd frontend
pnpm install
pnpm dev --port 3025
```

Open http://localhost:3025 and pick a teammate on the sign-in page.

Gemini is optional. To turn it on, copy `.env.example` to `.env` and set `GEMINI_API_KEY`. Without a key, the app still runs. Investigations use a fixed plan, and Ask returns the matching facts instead of a written answer.

## MCP

The 23 agent tools also run as an MCP server. Claude Desktop or any other MCP client can use them:

```bash
cd backend
uv run relay --tenant cheerio mcp           # stdio
uv run relay --tenant cheerio mcp --http    # HTTP on 127.0.0.1:8721
```

The tools include `risk_radar`, `causal_chain`, `blast_radius`, `costliest_bugs`, `experts`, `unique_knowledge`, `who_knows`, `meeting_brief`, `ask` and `investigate`.

## Deploy

The live app runs as one Docker container on a Google Cloud VM. The container holds FalkorDB, the API and the web app, and Caddy adds HTTPS. Three scripts manage it:

```bash
deploy/gce/up.sh      # create the VM and the network, then deploy
deploy/gce/push.sh    # upload the code and rebuild after a change
deploy/gce/down.sh    # delete everything
```

## Tests

The backend tests build an isolated graph and run the whole story: the risk, the investigation, the handover, the call and Ask. The eval command checks the demo numbers on the real build.

```bash
cd backend
uv run pytest -q
uv run relay --tenant cheerio eval
cd ../frontend
pnpm lint && pnpm exec tsc --noEmit
```

## Data and AI

Cheerio is a real product (WhatsApp marketing), but the company inside Relay is synthetic. The generators in `backend/src/relay/seed/` create 45 people, 120 customers, 3,000 Slack messages, 1,083 support tickets, 1,113 commits and a recorded renewal call. Relay uses no real personal or customer data.

At runtime, Relay uses Google Gemini to plan investigations, answer questions and write interview questions. The voices in the demo video come from Gemini text-to-speech, and the `demo/` folder records the video from the running app.

We built Relay with an AI coding assistant (Claude Code).
