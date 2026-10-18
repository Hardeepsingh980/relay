"""Live ingest: one new message lands in the graph and is searchable at once.

In production this is the Slack Events webhook -> queue -> extraction path; the
demo posts a message through the same writer. FalkorDB's full-text indexes update
on write, so the next Ask sees it without a rebuild.
"""

from __future__ import annotations

import re
import time
from .. import db, textmatch
from ..config import now

KEY_RE = re.compile(r"\b(?:CHEER|LUM)-\d+\b")


def slack_message(channel: str, person_id: str, text: str) -> dict:
    t0 = time.perf_counter()
    ch = db.rows("MATCH (c:Channel) WHERE c.name = $n OR c.id = $n RETURN c.id AS id, c.name AS name", {"n": channel},
                 readonly=True)
    if not ch:
        raise ValueError(f"No channel {channel}")
    p = db.rows("MATCH (p:Person {id: $p}) RETURN p.name AS name", {"p": person_id}, readonly=True)
    if not p:
        raise ValueError(f"No person {person_id}")
    at = now()
    ts = f"{at.timestamp():.6f}"
    mid = f"{ch[0]['id']}:{ts}"
    db.run("""MATCH (c:Channel {id: $cid}), (p:Person {id: $p})
              CREATE (m:Message {id: $id, channel: $cid, channelName: $cname, t: $t, at: $at, text: $text, threadId: $id,
                                 isReply: false, substantive: true, live: true})
              CREATE (p)-[:SENT]->(m), (m)-[:IN_CHANNEL]->(c)""",
           {"cid": ch[0]["id"], "cname": ch[0]["name"], "p": person_id, "id": mid, "t": at.timestamp(),
            "at": at.isoformat(), "text": text})
    linked = []
    for m in textmatch.mentions(text):
        db.run(f"MATCH (m:Message {{id: $id}}), (x:{m['label']} {{id: $x}}) CREATE (m)-[:MENTIONS {{surface: $s}}]->(x)",
               {"id": mid, "x": m["id"], "s": m["surface"]})
        linked.append({"id": m["id"], "label": m["label"]})
    for key in sorted(set(KEY_RE.findall(text))):
        r = db.rows("MATCH (t:Ticket {id: $k}) RETURN t.id AS id", {"k": key}, readonly=True)
        if r:
            db.run("MATCH (m:Message {id: $id}), (t:Ticket {id: $k}) CREATE (m)-[:MENTIONS {surface: $k}]->(t)",
                   {"id": mid, "k": key})
            linked.append({"id": key, "label": "Ticket"})
    return {"id": mid, "channel": ch[0]["name"], "author": p[0]["name"], "at": at.isoformat(timespec="seconds"),
            "text": text, "linked": linked, "ms": round((time.perf_counter() - t0) * 1000, 1)}


def recent(limit: int = 10) -> list[dict]:
    return db.rows("""MATCH (p:Person)-[:SENT]->(m:Message {live: true})
                      RETURN m.id AS id, m.text AS text, m.at AS at, m.channelName AS channel, p.name AS author
                      ORDER BY m.t DESC LIMIT $n""", {"n": limit}, readonly=True)
