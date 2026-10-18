# Relay: live demo script

**Runtime:** about 6 minutes (a 3-minute version is at the end).
**Live app:** https://relay.34-100-245-68.sslip.io

**The story in one line:** one Monday at Cheerio. A customer that looks happy is about to leave. The engineer they depend on quits on Friday. And the renewal call is about to repeat a promise the roadmap already broke. Relay catches all three, because they sit in one graph.

**Make the audience track three things:**
1. **The clock.** Every act is a time on the same Monday.
2. **Friday.** It's Rahul's last day.
3. **Northwind's risk: 78, then 84, then 79.** Say the number out loud every time it moves.

How to read this script: **DO** is what you click. Lines in quotes are what you say. Everything else is a note to you.

---

## Setup (15 minutes before)

- [ ] Phone hotspot on and ready, in case the venue Wi-Fi drops.
- [ ] Chrome, normal window, zoom 110%, sound on, notifications off.
- [ ] Typing on stage is dead air. Add three macOS text replacements (System Settings → Keyboard → Text Replacements). In Chrome, also tick **Edit → Substitutions → Text Replacement**. Each one expands after you press space; test all three. If they don't work, keep the lines in a Notes window and paste them.
  - `;q1` → `What should Sneha avoid promising on the renewal call?`
  - `;q2` → `Why does wallet settlement run at 6 AM?`
  - `;repo` → `https://github.com/FalkorDB/falkordb-py`
- [ ] Rehearse the whole thing once with a timer.
- [ ] Then, top-right menu → **Reset workspace…** (Northwind goes back to 78).
- [ ] **More** → **Repo knowledge** → analyze falkordb-py. The result stays cached for 6 hours, so on stage it opens instantly.
- [ ] Switch to Arnav and hide the checklist on Home. Then **Sign out**.
- [ ] Open the landing page. Have `demo/out/relay-demo.mp4` open in a player behind it, as a backup.

---

## 0:00 · Hook (35 s)

**DO:** On the landing page, click **Account Health** on the story card. The graph lights up each story as you tell it; keep your mouse off the card.

*(Northwind lights up)*
"Monday. Northwind Foods pays Cheerio 9.6 lakh rupees a year. HubSpot says they're happy. They're about to leave."

*(the card moves to Rahul)*
"Same Monday. Rahul, their technical contact, resigns. Friday is his last day."

*(the card moves to SSO; rest your mouse on the card to hold it)*
"At three, the renewal call. Sales promised them SSO by December. The roadmap now says next year."

"No tool sees how these connect. Relay puts them in one FalkorDB graph, and agents act on it. Cheerio is real. The people and numbers here are synthetic, so I can show you everything.

Let's live through that Monday."

---

## 0:35 · 9:30 AM: Arnav, Head of Customer Success (100 s)

**DO:** **Try it now** → **Arnav Mehta**.

**DO:** Point at the **Silent risk** list.

"Relay scored all 120 customers this morning. Four look fine in HubSpot but are at risk: 30 lakh rupees a year, about 35,000 dollars. Northwind is the biggest. Remember this number: **78**."

**DO:** **Northwind Foods** → **Investigate**. The steps stream in for about 10 seconds.

"One graph query per step. Ritika, the main contact, left in September. Aman, who replaced her, filed three tickets. All one bug, CHEER-2547: the campaign report export. And campaign report usage is down 70 percent."

**DO:** On the step that links the tickets to the bug, click **Show Cypher**.

"Tickets to bug: one query, [read the ms] milliseconds. Fourteen steps like this build the finding. Every sentence links to the record behind it. If a claim can't, it's dropped."

**DO:** Scroll to **Other accounts hit**.

"And this is what no person finds on a Monday morning. The same bug hits four more customers, 15.6 lakh a year. One fix protects five accounts."

**DO:** **Approve all.**

"Approved. Four tasks, saved in Relay. Connect Jira and Slack, and the same click files them there."

**DO:** In **Ask a follow-up**, type `;q1`, press space, then Enter. It takes about 13 seconds; talk over it.

"Now Gemini, live. It can only use what this investigation found. There's also a mode where Gemini picks the graph tools itself, over MCP."

**DO:** When the answer appears, point at it.

"Don't commit to December. SSO slipped to Q1. Hold on to that for three o'clock."

---

## 2:15 · 11:00 AM: Priya, engineering manager (55 s)

**DO:** Top-right menu → **Priya Raman** → **People** → **Rahul Verma** → **Start handover**.

"Priya runs Rahul's team. She hands his work to Aisha, who joined today."

**DO:** **Start and analyze**. The analysis runs for about 8 seconds.

"Relay reads everything Rahul touched: commits, threads, tickets, meetings. Then it takes him out of the graph and asks: what is nobody else connected to?"

**DO:** Turn on **Preview departure**.

"Red leaves on Friday. Grey is safe, because someone else knows it. Twelve things only Rahul knows. Look at this one: *why the settlement job runs at 6 AM*. Hold that thought too."

**DO:** Point at Northwind in the customer impact panel.

"And look: **78 is now 84**. The handover agent wrote one fact into the graph: Northwind's technical contact is leaving. Account Health read it and re-scored. Nobody told it to."

**DO:** **Accept all suggestions.**

"Every item now has a next owner."

---

## 3:10 · 3:00 PM: Sneha, account manager (85 s)

**DO:** Top-right menu → **Sneha Bose** → **Meetings** → **Northwind Foods <> Cheerio: renewal**.

"Three o'clock. Sneha and Kabir from sales, the one who promised December, are on with Northwind. Her brief already warns: the export bug is open, SSO moved, don't repeat December. Listen for a complaint, and a date."

**DO:** Leave speed at **1×** → **Start the call**. Then stop talking. Point at each card as it appears:
- the **CHEER-2547** bug card, when Aman complains about exports,
- **SSO moved to Q1 2027** and **Promise at risk**, when Mohit asks about December,
- **Promise logged**, when Kabir says he'll confirm Q1 in writing.

**DO:** As soon as **Promise logged** appears (about 1 minute in), click **End call**.

"Kabir didn't repeat December. He said Q1, and Relay logged it as a new promise that replaces the old one. So the risk drops: **84 to 79**. The follow-up email is a draft. A person sends it, not Relay."

---

## 4:35 · 5:00 PM: Aisha, first day (40 s)

**DO:** Top-right menu → **Aisha Khan**. Press **⌘K**, type `;q2`, press space, then Enter.

"Aisha takes over Rahul's work. Remember the 6 AM job? She asks why."

**DO:** Point at the sources, then **How I found this**.

"Gemini again, live, with sources: the runbook, and Rahul's own commit and Slack reply. It flags the old runbook as wrong."

"So: this morning, HubSpot said Northwind was fine. By five, the bug has a plan, Rahul's twelve things have owners, nobody repeated a broken promise, and the 6 AM reason will outlast Rahul."

---

## 5:15 · Under the hood (30 s)

**DO:** Left menu → **Knowledge graph** → **Everything**.

"Every screen today was a query on this graph: 31,645 nodes and 68,264 relationships in FalkorDB. Its 23 tools are open to any AI agent over MCP."

**DO:** **More** → **Repo knowledge** → type `;repo`, press space, then Enter.

"And it isn't only sample data. This is FalkorDB's own Python client: real commits, PageRank running inside FalkorDB, and the modules that have only one strong owner. [read one module name]"

---

## 5:45 · Close (15 s)

"Northwind went 78, 84, 79, and every move has a source. Rahul leaves Friday. What he knows doesn't.

That's Relay. Everything you saw runs, and the judge login is in our README. Thank you."

---

## If something goes wrong

| Problem | Say | Do |
|---|---|---|
| A step is slow | "The agent is still reading the graph." | Wait up to 10 seconds. Don't refresh during the handover or the call; the 84 and the 79 depend on them. |
| 84 doesn't show | "The re-score lands right after the analysis." | Open **Accounts** → Northwind. It shows 84. |
| You missed the **Promise logged** card | "The call is still running." | Let it finish. A full call also gives 79. |
| Gemini is slow | "Gemini is answering live, from the graph." | After 20 seconds, move on and come back to it. |
| The internet is down | "Here's the same flow, recorded." | Switch to the hotspot, or play the video. |

---

## The 3-minute version

| Time | Beat | Keep | Skip |
|---|---|---|---|
| 0:00 | Hook | All four lines | |
| 0:30 | Arnav | Silent risk, Investigate, **Other accounts hit**, Approve all | Show Cypher, the follow-up |
| 1:20 | Priya | Start handover, Preview departure, **78 → 84**, Accept all | |
| 2:05 | Sneha | Open the brief: "Her brief already warns: don't repeat December." | The call. Say instead: "During the call, Relay shows cards live and logs every promise." |
| 2:25 | Aisha | ⌘K question, then the recap without "nobody repeated a broken promise" | |
| 2:50 | Close | "Rahul leaves Friday. What he knows doesn't. That's Relay." | The graph and the repo |

---

## Questions judges may ask

- **Why a graph and not a normal database?**
  "Every question here is a path: contact, ticket, bug, feature, account. Or person, system, customer. Those are joins five tables deep. FalkorDB walks them in milliseconds, and every workspace is its own graph."
- **Is the data real?**
  "The product is real. The people, customers and calls are synthetic. Repo knowledge runs on any real public GitHub repo."
- **How do you stop hallucinations?**
  "The finding is built only from evidence the queries returned, and a claim without evidence is dropped. Gemini answers only from graph facts, and shows its sources."
- **Do the agents really act?**
  "They write to the graph, and other agents react: the handover raised Northwind's risk. They create tasks, drafts and pings. With Jira or Slack connected, approval files them there. Anything customer-facing waits for a person."
- **Can it connect to real tools?**
  "Settings → Connections checks real HubSpot, Zendesk, Slack, Jira and GitHub credentials live, and connects MCP servers."
- **Is Gemini doing everything?**
  "No. The graph does the finding. Gemini plans when you ask it to, answers questions, and writes from the evidence it's given."
