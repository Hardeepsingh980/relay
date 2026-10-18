"""What the demo video says: narration beats (one TTS clip per line) and the voices for the recorded call.

Narration follows the simple-english rules: short sentences, active voice, plain words, no hype.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CALL_FILE = HERE.parent / "data" / "cheerio" / "calls" / "call-northwind-renewal.json"

NARRATOR = "Sulafat"
NARRATOR_TEMPO = 1.06
CALL_VOICES = {
    "sneha.bose@cheerio.example": "Aoede",
    "kabir.anand@cheerio.example": "Puck",
    "aman.khurana@northwindfoods.example": "Achird",
    "mohit.bhalla@northwindfoods.example": "Orus",
}


def call_segments() -> list[dict]:
    return json.loads(CALL_FILE.read_text())["segments"]


SCENE_ORDER = ["intro", "landing", "graph", "risk", "investigate", "handover", "interview", "brief", "call",
               "followup", "dayone", "repos", "outro"]

# Each beat is one or more lines. Each line becomes one TTS clip and one caption.
BEATS: list[dict] = [
    # ------------------------------------------------------------ intro card
    {"id": "intro", "lines": [
        "This is Relay.",
        "Relay puts a company's customers, people and work into one graph. A graph is a map of how things connect.",
        "AI agents read that map. They find problems, show the proof, and act when you approve.",
    ]},
    # ------------------------------------------------------------ landing
    {"id": "landing-1", "lines": [
        "Our sample company is Cheerio. Cheerio sells WhatsApp marketing to online brands.",
        "Its people, customers and numbers are synthetic. Everything Relay shows is computed from them, live.",
    ]},
    {"id": "landing-2", "lines": [
        "The graph here is a real slice of Cheerio's graph. Each agent's finding lights up as a path, one hop at a time.",
    ]},
    {"id": "landing-3", "lines": [
        "To start, pick someone on the team. Each visitor gets a private copy of the workspace.",
    ]},
    # ------------------------------------------------------------ knowledge graph
    {"id": "graph-1", "lines": [
        "This is everything Relay knows about Cheerio, in one FalkorDB graph.",
    ]},
    {"id": "graph-2", "lines": [
        "People, teams, systems, customers, tickets, decisions and meetings, joined by tens of thousands of relationships.",
    ]},
    {"id": "graph-3", "lines": [
        "Pick anyone, and you see what they know, who they work with, and which customers depend on them.",
    ]},
    {"id": "graph-4", "lines": [
        "Every screen in Relay is a query on this graph, and every agent reads and writes it.",
    ]},
    # ------------------------------------------------------------ risk radar
    {"id": "risk-0", "lines": [
        "This is Arnav's home page. A short checklist shows what to try. We hide it for now.",
    ]},
    {"id": "risk-1", "lines": [
        "Relay scored all 120 customer accounts this morning.",
    ]},
    {"id": "risk-2", "lines": [
        "Four accounts look healthy in HubSpot, but they are at risk. Together they bring in 30 lakh rupees a year.",
    ]},
    {"id": "risk-3", "lines": [
        "Northwind Foods is the biggest. HubSpot gives it 82 out of 100. Relay gives it a 78 percent risk of leaving.",
    ]},
    {"id": "risk-4", "lines": [
        "The account page shows the reasons. The main contact left. Three support tickets point to one bug. Usage is down.",
    ]},
    # ------------------------------------------------------------ investigation
    {"id": "inv-1", "lines": [
        "Arnav clicks Investigate. The Detective agent now works step by step, and you can watch it.",
    ]},
    {"id": "inv-2", "lines": [
        "Each step is a query on the graph. It goes from the contact who left, to her tickets, to the bug, to the feature they stopped using.",
    ]},
    {"id": "inv-3", "lines": [
        "Here is the finding. Every claim links to its source, so you can check it.",
    ]},
    {"id": "inv-4", "lines": [
        "The same bug hits four more customers, worth 15.6 lakh rupees a year. One fix protects five accounts.",
    ]},
    {"id": "inv-5", "lines": [
        "Relay remembers what worked for a similar customer. It uses that playbook to write a save plan.",
    ]},
    {"id": "inv-6", "lines": [
        "Arnav approves the plan. Jira and Slack are not connected here, so Relay saves each step as a task, and says so.",
    ]},
    # ------------------------------------------------------------ handover
    {"id": "ho-1", "lines": [
        "Now we see the app as Priya, an engineering manager. Rahul, a senior engineer on her team, leaves on Friday.",
    ]},
    {"id": "ho-2", "lines": ["Priya starts Rahul's handover. Aisha joined today, and she takes over his work."]},
    {"id": "ho-3", "lines": [
        "Relay takes Rahul out of the graph and looks for what nobody else knows.",
        "It reads his commits, threads, tickets and meetings, and finds 12 things.",
    ]},
    {"id": "ho-4", "lines": [
        "With Preview departure on, his items turn red. Shared items stay grey, because other people know them too.",
    ]},
    {"id": "ho-5", "lines": [
        "The Handover agent also tells the Account Health agent. Rahul is the technical contact for Northwind, so its risk goes up from 78 to 84 percent.",
    ]},
    {"id": "ho-6", "lines": ["Priya accepts the suggested next owners in one click."]},
    # ------------------------------------------------------------ interview
    {"id": "iv-1", "lines": [
        "Rahul gets short questions about his own work. Each question shows the source it came from.",
    ]},
    {"id": "iv-2", "lines": [
        "He answers in his own words. The answer goes into the graph, next to the system it explains.",
    ]},
    # ------------------------------------------------------------ brief
    {"id": "brief-1", "lines": [
        "Now we are Sneha, the account manager for Northwind. The renewal call is at three today.",
    ]},
    {"id": "brief-2", "lines": [
        "Relay wrote her a brief: the open bug, the SSO date that moved, and the promise she must not repeat.",
    ]},
    {"id": "brief-3", "lines": [
        "Sneha joins with Sales Assist. Relay listens, and cards appear that only she can see. Let us listen.",
    ]},
    # ------------------------------------------------------------ after the call
    {"id": "fu-1", "lines": [
        "The call is over. Relay saved the summary, the decisions and four new promises.",
    ]},
    {"id": "fu-2", "lines": [
        "The old December promise for SSO is now replaced, so Northwind's risk drops from 84 to 79 percent.",
    ]},
    {"id": "fu-3", "lines": [
        "The follow-up email is ready as a draft. A person sends it, not Relay.",
    ]},
    # ------------------------------------------------------------ day one
    {"id": "d1-1", "lines": [
        "This is Aisha's first day. Her Day One page lists the systems she now owns and five people to meet first.",
    ]},
    {"id": "d1-2", "lines": ["She asks Relay why wallet settlement runs at 6 AM. Relay reads the graph and writes a short answer."]},
    {"id": "d1-3", "lines": [
        "The answer is short, and each claim shows its source. It also warns that the old runbook is out of date.",
    ]},
    {"id": "d1-4", "lines": ["How I found this shows the path Relay took through the graph."]},
    # ------------------------------------------------------------ live update
    {"id": "live-1", "lines": [
        "Knowledge changes every day. Right now, Relay has no fix date for the export bug.",
    ]},
    {"id": "live-2", "lines": ["On How it works, we send a new Slack message from Dev, the engineer who owns the bug."]},
    {"id": "live-3", "lines": [
        "Relay reads it into the graph in milliseconds. Ask again, and the answer has the new date, with Dev's message as the source.",
    ]},
    # ------------------------------------------------------------ how it works
    {"id": "how-1", "lines": [
        {"text": "Under every screen is FalkorDB. Cheerio and a second sample company, Lumen, each have their own graph.",
         "say": "Under every screen is Falkor DB. Cheerio and a second sample company, Lumen, each have their own graph."},
    ]},
    {"id": "how-2", "lines": ["You can run the same graph queries the agents use."]},
    {"id": "how-3", "lines": [
        "Here a load test runs while the agents keep working. Other AI agents can use the same tools through MCP.",
    ]},
    # ------------------------------------------------------------ repo knowledge
    {"id": "repos-1", "lines": [
        "Relay also works on real data you choose. Paste any public GitHub repo, and Relay reads its history into a graph.",
    ]},
    {"id": "repos-2", "lines": [
        "In FalkorDB's own Python client, two modules have only one strong owner.",
    ]},
    {"id": "repos-3", "lines": ["Preview his departure, and you see what nobody else could pick up."]},
    {"id": "repos-4", "lines": ["Ask a question, and Gemini answers from the graph facts Relay found."]},
    {"id": "repos-5", "lines": ["The answer lists the facts it used, and how long the model took."]},
    # ------------------------------------------------------------ outro card
    {"id": "outro", "lines": [
        "Relay keeps your customers, and it keeps what your people know.",
        "Every answer has a source. Every action waits for a person.",
    ]},
]
