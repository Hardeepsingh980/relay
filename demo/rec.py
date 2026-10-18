"""Recording helpers: a CDP screencast per scene, a visible cursor, human-paced mouse and keyboard,
and a beat log that ties each narration line to the moment it starts on screen.
"""

from __future__ import annotations

import asyncio
import base64
import json
import math
import random
import time
from pathlib import Path

from playwright.async_api import Locator, Page

CURSOR_JS = r"""
(() => {
  if (window.__demoCursorInstalled) return;
  window.__demoCursorInstalled = true;
  const svg = `<svg width="28" height="28" viewBox="0 0 28 28" xmlns="http://www.w3.org/2000/svg">
    <path d="M6 3 L6 22 L10.8 17.6 L14.2 25 L17.6 23.4 L14.3 16.2 L21 16.2 Z" fill="#111827" stroke="#ffffff"
      stroke-width="1.8" stroke-linejoin="round"/></svg>`;
  const ensure = () => {
    let c = document.getElementById('__demo_cursor');
    if (!c) {
      c = document.createElement('div');
      c.id = '__demo_cursor';
      c.innerHTML = svg;
      Object.assign(c.style, {position: 'fixed', left: '0px', top: '0px', zIndex: '2147483647',
        pointerEvents: 'none', willChange: 'transform', filter: 'drop-shadow(0 2px 3px rgba(0,0,0,.35))'});
      document.documentElement.appendChild(c);
    }
    return c;
  };
  const place = (x, y) => {
    ensure().style.transform = `translate(${x - 6}px, ${y - 3}px)`;
    try { sessionStorage.setItem('__demo_cursor', JSON.stringify([x, y])); } catch (e) {}
  };
  addEventListener('mousemove', (e) => place(e.clientX, e.clientY), true);
  addEventListener('mousedown', (e) => {
    const r = document.createElement('div');
    Object.assign(r.style, {position: 'fixed', left: (e.clientX - 18) + 'px', top: (e.clientY - 18) + 'px',
      width: '36px', height: '36px', borderRadius: '50%', border: '3px solid rgba(0,138,232,.85)',
      background: 'rgba(0,138,232,.18)', zIndex: '2147483646', pointerEvents: 'none',
      transition: 'transform .45s ease-out, opacity .45s ease-out', transform: 'scale(.4)', opacity: '1'});
    document.documentElement.appendChild(r);
    requestAnimationFrame(() => { r.style.transform = 'scale(1.5)'; r.style.opacity = '0'; });
    setTimeout(() => r.remove(), 600);
  }, true);
  const restore = () => {
    let p = [760, 430];
    try { p = JSON.parse(sessionStorage.getItem('__demo_cursor') || 'null') || p; } catch (e) {}
    place(p[0], p[1]);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', restore); else restore();
  setInterval(() => { if (!document.getElementById('__demo_cursor')) restore(); }, 500);
})();
"""


SCROLL_JS = r"""
async ({dy, ms}) => {
  const se = document.scrollingElement;
  let el = se;
  if (se.scrollHeight <= innerHeight + 2) {
    el = [...document.querySelectorAll('main, div, section')]
      .filter((e) => /(auto|scroll)/.test(getComputedStyle(e).overflowY) && e.scrollHeight > e.clientHeight + 2)
      .sort((a, b) => b.clientHeight - a.clientHeight)[0] || se;
  }
  const start = el.scrollTop;
  const end = Math.max(0, Math.min(el.scrollHeight - el.clientHeight, start + dy));
  const t0 = performance.now();
  await new Promise((done) => {
    const step = (t) => {
      const u = Math.min(1, (t - t0) / ms);
      const e = u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2;
      el.scrollTo({top: start + (end - start) * e, behavior: 'instant'});
      if (u < 1) requestAnimationFrame(step); else done();
    };
    requestAnimationFrame(step);
  });
}
"""


class Scene:
    """One continuous screencast with a log of narration beats and timed audio events."""

    def __init__(self, page: Page, root: Path, name: str, manifest: dict):
        self.page, self.name, self.manifest = page, name, manifest
        self.dir = root / name
        self.frames_dir = self.dir / "frames"
        self.frames: list[tuple[int, float]] = []
        self.events: list[dict] = []
        self.t0: float | None = None
        self._busy_until = 0.0

    # -------------------------------------------------------------- capture
    async def __aenter__(self) -> "Scene":
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)
        self.frames_dir.mkdir(parents=True)
        self.cdp = await self.page.context.new_cdp_session(self.page)
        self.cdp.on("Page.screencastFrame", self._frame)
        await self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "maxWidth": 1920,
                                                     "maxHeight": 1080, "everyNthFrame": 1})
        self.t0 = time.time()
        await self.page.mouse.move(*(await self._cursor()))  # force a first frame
        await asyncio.sleep(0.3)
        return self

    async def __aexit__(self, *exc) -> None:
        await self.wait_done()
        await asyncio.sleep(0.6)
        self.t_end = time.time()
        await self.cdp.send("Page.stopScreencast")
        await self.cdp.detach()
        (self.dir / "timeline.json").write_text(json.dumps({
            "t0": self.t0, "t_end": self.t_end, "frames": self.frames, "events": self.events}, indent=1))
        print(f"  scene {self.name}: {self.t_end - self.t0:.1f}s, {len(self.frames)} frames", flush=True)

    def _frame(self, params: dict) -> None:
        n = len(self.frames)
        (self.frames_dir / f"{n:06d}.jpg").write_bytes(base64.b64decode(params["data"]))
        ts = params.get("metadata", {}).get("timestamp") or time.time()
        self.frames.append((n, ts))
        asyncio.ensure_future(self._ack(params["sessionId"]))

    async def _ack(self, session_id: int) -> None:
        try:
            await self.cdp.send("Page.screencastFrameAck", {"sessionId": session_id})
        except Exception:  # noqa: BLE001 - the page closed while a frame was in flight
            pass

    def now(self) -> float:
        return time.time() - (self.t0 or time.time())

    # -------------------------------------------------------------- narration
    async def say(self, beat_id: str, gap: float = 0.28) -> float:
        """Start narration beat `beat_id` now (after any beat still playing). Returns its length."""
        await self.wait_done()
        lines = self.manifest[beat_id]
        t = self.now()
        for ln in lines:
            self.events.append({"kind": "narration", "beat": beat_id, "t": round(t, 3), "text": ln["text"],
                                "path": ln["path"], "duration": ln["duration"]})
            t += ln["duration"] + gap
        self._busy_until = time.time() + (t - self.now())
        return t - self.now()

    async def wait_done(self, extra: float = 0.0) -> None:
        delay = self._busy_until - time.time() + extra
        if delay > 0:
            await asyncio.sleep(delay)

    def audio(self, path: str, duration: float, text: str, speaker: str) -> None:
        """A voice that starts now (the call participants)."""
        self.events.append({"kind": "voice", "t": round(self.now(), 3), "text": text, "speaker": speaker,
                            "path": path, "duration": duration})

    def chapter(self, title: str) -> None:
        self.events.append({"kind": "chapter", "t": round(self.now(), 3), "text": title})

    # -------------------------------------------------------------- input
    async def _cursor(self) -> tuple[float, float]:
        try:
            p = await self.page.evaluate("JSON.parse(sessionStorage.getItem('__demo_cursor') || '[760,430]')")
            return float(p[0]), float(p[1])
        except Exception:  # noqa: BLE001 - page mid-navigation
            return 760.0, 430.0

    async def move(self, x: float, y: float, duration: float | None = None) -> None:
        sx, sy = await self._cursor()
        dist = math.hypot(x - sx, y - sy)
        duration = duration if duration is not None else min(0.95, 0.28 + dist / 1800)
        steps = max(8, int(duration * 60))
        # A slight arc reads as a hand, a straight line reads as a robot.
        bend = random.uniform(-0.12, 0.12) * dist
        nx, ny = (-(y - sy) / dist, (x - sx) / dist) if dist else (0, 0)
        for i in range(1, steps + 1):
            u = i / steps
            e = u * u * (3 - 2 * u)
            arc = math.sin(math.pi * u) * bend
            await self.page.mouse.move(sx + (x - sx) * e + nx * arc, sy + (y - sy) * e + ny * arc)
            await asyncio.sleep(duration / steps)

    async def point(self, target: Locator, dx: float = 0.0, dy: float = 0.0) -> tuple[float, float]:
        await target.scroll_into_view_if_needed()
        box = await target.bounding_box()
        if not box:
            raise RuntimeError(f"no box for {target}")
        x = box["x"] + box["width"] / 2 + dx
        y = box["y"] + box["height"] / 2 + dy
        await self.move(x, y)
        return x, y

    async def click(self, target: Locator, pause: float = 0.25, **kw) -> None:
        await self.point(target, **kw)
        await asyncio.sleep(pause)
        self.events.append({"kind": "click", "t": round(self.now(), 3)})
        await self.page.mouse.down()
        await asyncio.sleep(0.07)
        await self.page.mouse.up()
        await asyncio.sleep(0.25)

    async def hover(self, target: Locator, hold: float = 0.6) -> None:
        await self.point(target)
        await asyncio.sleep(hold)

    async def type(self, target: Locator | None, text: str, cps: float = 16.0) -> None:
        if target is not None:
            await self.click(target)
        for ch in text:
            await self.page.keyboard.type(ch)
            await asyncio.sleep(random.uniform(0.6, 1.4) / cps)

    async def scroll(self, dy: float, duration: float = 1.0) -> None:
        """Smooth scroll of the page (or its main scroll container). The wheel would zoom any graph
        canvas under the cursor instead, so this animates scrollTop directly."""
        await self.page.evaluate(SCROLL_JS, {"dy": dy, "ms": duration * 1000})

    async def scroll_to(self, target: Locator, offset: float = -140, duration: float = 1.0) -> None:
        """Smooth-scroll until `target` sits `-offset` pixels below the top of the viewport."""
        await target.wait_for(state="attached")
        box = await target.bounding_box()
        if not box:
            await target.scroll_into_view_if_needed()
            return
        await self.scroll(box["y"] + offset, duration)

    async def idle(self, seconds: float) -> None:
        """Small, natural cursor drift while the narrator talks over a still screen."""
        end = time.time() + seconds
        while time.time() < end:
            x, y = await self._cursor()
            await self.move(x + random.uniform(-40, 40), y + random.uniform(-25, 25), duration=0.8)
            await asyncio.sleep(min(1.2, max(0, end - time.time())))
