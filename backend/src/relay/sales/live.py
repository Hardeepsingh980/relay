"""The live call: a session that feeds transcript segments through the trigger pipeline.

A real deployment feeds segments from a meeting bot's streaming transcription. The
demo replays a pre-recorded call through exactly the same path (PRD cut line: real
bot -> pre-recorded call), at real time or faster. The panel shows cards within
milliseconds of the segment; the measured latency is on every card.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import date

from .. import db, tenants
from . import summary, triggers


def now() -> str:
    """Demo clock (DEMO_NOW + time since boot), so records line up with the seeded world."""
    from ..config import now as demo_now
    return demo_now().isoformat(timespec="milliseconds")


def load_recording(recording_id: str) -> dict:
    path = tenants.current().data_dir / "calls" / f"{recording_id}.json"
    if not path.exists():
        raise KeyError(recording_id)
    return json.loads(path.read_text())


class CallSession:
    def __init__(self, meeting_id: str, speed: float = 1.0, actor: str | None = None, live: bool = False):
        m = db.rows("""MATCH (m:Meeting {id: $id})-[:WITH]->(a:Account)
                       OPTIONAL MATCH (p:Person)-[:INVITED_TO]->(m)
                       OPTIONAL MATCH (host:Person)-[:HOSTS]->(m)
                       RETURN m, a, collect(p.email) AS internal, head(collect(DISTINCT host.id)) AS host""",
                    {"id": meeting_id}, readonly=True)
        if not m:
            raise KeyError(meeting_id)
        self.meeting, self.account = m[0]["m"], m[0]["a"]
        self.live = live
        if live:
            # No recording: every line comes from the person in the call, typed or spoken.
            self.recording = {"segments": [], "duration_s": 0, "consent": True,
                              "source": "Live call: lines typed or spoken in Relay"}
        elif not self.meeting.get("recording"):
            raise ValueError("This meeting has no recording to replay")
        else:
            self.recording = load_recording(self.meeting["recording"])
        self.id = f"call-{uuid.uuid4().hex[:10]}"
        self.graph = db.current_graph_name()
        self.workspace = db.current_workspace_id()
        self.actor = actor
        self.speed = max(0.5, min(speed, 20.0))
        self.status = "ready"
        self.events: list[dict] = []
        self.cond = asyncio.Condition()
        self.transcript: list[dict] = []
        self.cards: list[dict] = []
        self.started_at: str | None = None
        self.ended_at: str | None = None
        self.result: dict | None = None
        self.task: asyncio.Task | None = None
        call_day = date.fromisoformat(self.meeting["date"][:10])
        self.ctx = triggers.CallContext(self.account["id"], self.account["name"], call_day, set(m[0]["internal"]),
                                        rep_id=m[0]["host"])
        self._closed = asyncio.Event()
        self._t0 = time.monotonic()
        self.speakers = self._speakers(m[0]["host"])

    def _speakers(self, host: str | None) -> dict[str, dict]:
        """Who a typed or spoken line belongs to: the rep hosting the call, or the customer's main contact."""
        rep = db.rows("MATCH (p:Person {id: $p}) RETURN p.name AS name, p.email AS email", {"p": host}, readonly=True) if host else []
        cust = db.rows("""MATCH (c:Contact)-[w:WORKS_AT]->(:Account {id: $a}) WHERE w.to IS NULL
                          RETURN c.name AS name, c.email AS email ORDER BY coalesce(c.isChampion, false) DESC, c.name LIMIT 1""",
                       {"a": self.account["id"]}, readonly=True)
        out = {}
        if rep:
            out["rep"] = rep[0]
            self.ctx.internal_emails.add(rep[0]["email"])
        if cust:
            out["customer"] = cust[0]
        return out

    async def _process(self, seg: dict) -> None:
        i = len(self.transcript)
        entry = {**seg, "i": i, "internal": seg["speaker_email"] in self.ctx.internal_emails}
        self.transcript.append(entry)
        await self.emit("transcript.segment", {"segment": entry})
        started = time.perf_counter()
        cards = await asyncio.to_thread(triggers.detect, self.ctx, seg, i)
        for c in cards:
            c["id"] = f"card-{len(self.cards) + 1}"
            c["endToEndMs"] = round((time.perf_counter() - started) * 1000, 1)
            self.cards.append(c)
            await self.emit("card.added", {"card": c})

    async def say(self, text: str, who: str) -> dict:
        """A line typed or spoken during the call goes through the same pipeline as the recording."""
        if self.status != "live":
            raise ValueError("The call is not live")
        sp = self.speakers.get(who)
        if not sp:
            raise ValueError(f"No {who} on this call")
        text = " ".join(text.split())[:600]
        if not text:
            raise ValueError("Say something first")
        seg = {"t": round((time.monotonic() - self._t0) * self.speed, 1), "speaker_email": sp["email"],
               "speaker_name": sp["name"], "text": text, "typed": True}
        before = len(self.cards)
        await self._process(seg)
        return {"segment": self.transcript[-1], "cards": self.cards[before:]}

    async def emit(self, type_: str, payload: dict) -> None:
        async with self.cond:
            self.events.append({"id": len(self.events), "type": type_, "ts": now(), "payload": payload})
            self.cond.notify_all()

    def snapshot(self) -> dict:
        return {"id": self.id, "meetingId": self.meeting["id"], "title": self.meeting["title"],
                "accountId": self.account["id"], "account": self.account["name"], "status": self.status,
                "speed": self.speed, "startedAt": self.started_at, "endedAt": self.ended_at,
                "duration": self.recording["duration_s"], "consent": self.recording.get("consent", False),
                "source": self.recording.get("source"), "transcript": self.transcript, "cards": self.cards,
                "result": self.result, "lastEventId": len(self.events) - 1, "live": self.live,
                "speakers": {k: v["name"] for k, v in self.speakers.items()}}

    async def run(self) -> None:
        self.status, self.started_at = "live", now()
        await self.emit("call.started", {"callId": self.id, "duration": self.recording["duration_s"], "speed": self.speed,
                                         "consent": self.recording.get("consent", False), "live": self.live,
                                         "recording": None if self.live else self.meeting.get("recording"),
                                         "speakers": {k: v["name"] for k, v in self.speakers.items()}})
        t0 = self._t0 = time.monotonic()
        try:
            if self.live:
                await self._closed.wait()   # lines arrive through say() until the person ends the call
                return
            for r, seg in enumerate(self.recording["segments"]):
                wait = seg["t"] / self.speed - (time.monotonic() - t0)
                if wait > 0:
                    await asyncio.sleep(wait)
                if self.status != "live":
                    break
                await self._process({**seg, "r": r})
            await asyncio.sleep(0.4)
            if self.status == "live":
                await self.end()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            self.status = "failed"
            await self.emit("call.failed", {"error": f"{type(exc).__name__}: {exc}"[:300]})

    async def end(self) -> dict:
        self._closed.set()
        if self.status in ("ended", "summarised"):
            return self.result or {}
        self.status, self.ended_at = "ended", now()
        await self.emit("call.ended", {"callId": self.id, "segments": len(self.transcript), "cards": len(self.cards)})
        self.result = await asyncio.to_thread(summary.finalize, self)
        self.status = "summarised"
        await self.emit("call.summarised", {"result": self.result})
        return self.result

    async def ping(self, card_id: str, actor: str) -> dict:
        card = next(c for c in self.cards if c["id"] == card_id)
        out = await asyncio.to_thread(summary.ping_expert, card, actor)
        card["pinged"] = out
        await self.emit("card.updated", {"card": card})
        return out


SESSIONS: dict[str, CallSession] = {}


def start(meeting_id: str, speed: float = 1.0, actor: str | None = None, live: bool = False) -> CallSession:
    s = CallSession(meeting_id, speed, actor, live=live)
    SESSIONS[s.id] = s
    s.task = asyncio.create_task(s.run())
    return s


def get(call_id: str) -> CallSession:
    s = SESSIONS.get(call_id)
    if not s or s.graph != db.current_graph_name():
        raise KeyError(call_id)
    return s


def for_meeting(meeting_id: str) -> CallSession | None:
    found = [s for s in SESSIONS.values() if s.meeting["id"] == meeting_id and s.graph == db.current_graph_name()]
    return found[-1] if found else None


def reset(graph: str | None = None) -> None:
    for sid, s in list(SESSIONS.items()):
        if graph is not None and s.graph != graph:
            continue
        if s.task and not s.task.done():
            s.task.cancel()
        del SESSIONS[sid]
