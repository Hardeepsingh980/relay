"""Record the Relay demo, scene by scene, against the running app (web :3025, API :8020).

    uv run --project ../backend --with playwright python record.py              # every scene, fresh account
    uv run --project ../backend --with playwright python record.py --from call  # re-record from a scene on
    uv run --project ../backend --with playwright python record.py --only risk

A fresh run wipes the browser profile and signs up a new test account, which gets its own workspace graph.
Each scene keeps the state the previous one left, so --from needs the earlier scenes recorded in this profile.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import secrets
import shutil
import time
from pathlib import Path

from playwright.async_api import Page, async_playwright

import script
from rec import CURSOR_JS, Scene

HERE = Path(__file__).resolve().parent
CACHE = HERE / ".cache"
PROFILE = HERE / ".profile"
SCENES_DIR = CACHE / "scenes"
BASE = os.getenv("RELAY_DEMO_BASE", "http://localhost:3025")
API = "http://localhost:8020"
VIEWPORT = {"width": 1440, "height": 810}
NORTHWIND = "cust-northwind-foods"
MEETING = "evt-2026-10-19-northwind"


def rx(s: str) -> re.Pattern:
    return re.compile(s, re.I)


def account() -> dict:
    """The test account for this recording profile (written to the git-ignored cache, never printed)."""
    path = CACHE / "account.json"
    if path.exists():
        return json.loads(path.read_text())
    stamp = time.strftime("%m%d%H%M")
    acc = {"name": "Riya Desai", "email": f"riya.desai.{stamp}@relay.test", "password": secrets.token_urlsafe(12)}
    path.write_text(json.dumps(acc))
    return acc


async def view_as(s: Scene, name: str) -> None:
    """Switch person with the View as menu in the top bar, like a viewer would."""
    page = s.page
    await s.click(page.get_by_role("button", name=rx(r"^(View as|Signed in as)")))
    await asyncio.sleep(0.5)
    await s.click(page.get_by_role("menuitem", name=rx("^" + name)))
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(0.8)


# ------------------------------------------------------------------ scenes
async def intro(s: Scene) -> None:
    html = (HERE / "cards" / "card.html").read_text().replace('location.hash.slice(1) || "intro"', '"intro"')
    await s.page.set_content(html)
    await asyncio.sleep(0.6)
    await s.say("intro")
    await s.wait_done(0.8)


async def outro(s: Scene) -> None:
    html = (HERE / "cards" / "card.html").read_text().replace('location.hash.slice(1) || "intro"', '"outro"')
    await s.page.set_content(html)
    await asyncio.sleep(0.6)
    await s.say("outro")
    await s.wait_done(2.0)


async def landing(s: Scene) -> None:
    page = s.page
    s.chapter("1 · Sign in")
    await s.say("landing-1")
    await s.hover(page.get_by_role("heading", level=1), hold=1.0)
    await s.idle(1.5)
    await s.wait_done()
    await s.say("landing-2")
    await page.get_by_role("tab", name=rx("^Handovers")).wait_for(timeout=20000)
    await s.hover(page.get_by_role("tablist", name="What the agents found"), hold=1.2)
    await s.idle(2.0)
    await s.wait_done()
    await s.say("landing-3")
    try_it = page.get_by_role("link", name=rx("^Try it now")).first
    await s.hover(try_it, hold=0.8)
    await s.click(try_it)
    await page.wait_for_url("**/sign-in**", timeout=30000)
    arnav = page.get_by_role("button", name=rx("^Arnav Mehta"))
    await s.hover(arnav, hold=1.4)
    await s.click(arnav)
    await page.wait_for_url("**/home**", timeout=30000)
    await page.get_by_text("Northwind Foods").first.wait_for(timeout=30000)
    await asyncio.sleep(0.8)


async def signup(s: Scene) -> None:
    page = s.page
    acc = account()
    s.chapter("2 · Sign up and set up")
    await s.say("signup-1")
    await s.type(page.get_by_label("Full name"), acc["name"], cps=22)
    await s.type(page.get_by_label("Work email"), acc["email"], cps=30)
    await s.type(page.get_by_label("Password", exact=True), acc["password"], cps=32)
    await s.wait_done()
    await s.click(page.get_by_role("button", name=rx("^(create|sign up|get started)")))
    await page.wait_for_url("**/welcome**", timeout=20000)
    await asyncio.sleep(1.0)
    await s.say("signup-2")
    await s.click(page.get_by_role("button", name="Head of Customer Success"))
    await s.wait_done()
    await s.click(page.get_by_role("button", name=rx("^continue")))
    await page.get_by_text("Name your workspace.").wait_for()
    await s.say("signup-3")
    box = page.get_by_role("textbox").first
    await s.click(box)
    await page.keyboard.press("ControlOrMeta+A")
    await s.type(None, "Cheerio Customer Success")
    await s.hover(page.get_by_role("radio", name=rx("Cheerio")), hold=0.6)
    await s.click(page.get_by_role("radio", name=rx("Cheerio")))
    await s.wait_done()
    await s.click(page.get_by_role("button", name=rx("Create workspace")))
    await page.get_by_text("Connect your tools.").wait_for(timeout=30000)
    await asyncio.sleep(0.6)
    await s.say("signup-4")
    await s.idle(1.5)
    await s.wait_done()
    await s.click(page.get_by_role("button", name=rx("^continue")))
    await page.get_by_text("Invite your teammates.").wait_for()
    await asyncio.sleep(0.4)
    await s.click(page.get_by_role("button", name=rx("Skip for now")))
    await page.get_by_text("Where do you want to start?").wait_for()
    await s.say("signup-5")
    await s.click(page.get_by_role("button", name=rx("Arnav")))
    await s.wait_done()
    await s.click(page.get_by_role("button", name=rx("^Open Relay")))
    await page.wait_for_url("**/home**", timeout=20000)
    await page.get_by_text("Northwind Foods").first.wait_for(timeout=20000)
    await asyncio.sleep(0.8)


async def graph(s: Scene) -> None:
    page = s.page
    s.chapter("2 · The company graph")
    await s.say("graph-1")
    await s.click(page.get_by_role("link", name=rx("^Knowledge graph")).first)
    await page.wait_for_url("**/graph**")
    await page.get_by_text(rx(r"relationships in FalkorDB")).first.wait_for(timeout=30000)
    await s.idle(2.5)
    await s.wait_done()
    await s.say("graph-2")
    await s.click(page.get_by_role("tab", name="Everything"))
    await page.get_by_text(rx(r"Showing [\d,]{4,} nodes")).first.wait_for(timeout=30000)
    await s.idle(4.0)
    await s.wait_done()
    await s.say("graph-3")
    await s.type(page.get_by_label("Search the graph"), "Rahul", cps=12)
    await asyncio.sleep(0.6)
    await page.keyboard.press("Enter")
    await asyncio.sleep(2.5)
    await s.idle(2.0)
    await s.wait_done()
    await s.say("graph-4")
    await s.idle(2.0)
    await s.wait_done(0.4)
    await s.click(page.get_by_role("link", name=rx("^Home")).first)
    await page.wait_for_url("**/home**")
    await page.get_by_text("Northwind Foods").first.wait_for(timeout=30000)
    await asyncio.sleep(0.6)


async def risk(s: Scene) -> None:
    page = s.page
    s.chapter("3 · Find the customer at risk")
    hide = page.get_by_role("button", name="Hide checklist")
    if await hide.count():
        await s.say("risk-0")
        await s.hover(page.get_by_label("Getting started").first, hold=1.2)
        await s.wait_done()
        await s.click(hide)
        await asyncio.sleep(0.8)
    await s.say("risk-1")
    await s.idle(1.2)
    await s.wait_done()
    await s.say("risk-2")
    await s.hover(page.get_by_text(rx(r"silent risk")).first, hold=1.0)
    await s.wait_done()
    row = page.get_by_role("link", name=rx("Northwind Foods")).first
    await s.say("risk-3")
    await s.hover(row, hold=1.2)
    await s.wait_done()
    await s.click(row)
    await page.wait_for_url(f"**/accounts/{NORTHWIND}**")
    await page.get_by_role("button", name=rx("^Investigate$")).wait_for()
    await asyncio.sleep(0.8)
    await s.say("risk-4")
    await s.scroll(420, duration=1.6)
    await s.idle(2.5)
    await s.wait_done()
    await s.scroll(-420, duration=1.0)


async def investigate(s: Scene) -> None:
    page = s.page
    s.chapter("4 · Investigate and act")
    await s.say("inv-1")
    await s.click(page.get_by_role("button", name=rx("^Investigate$")))
    await s.wait_done()
    await s.say("inv-2")
    await page.get_by_text(rx("Relay's finding")).first.wait_for(timeout=90000)
    await s.wait_done()
    await asyncio.sleep(0.6)
    finding = page.get_by_text(rx("Relay's finding")).first
    await s.scroll_to(finding, offset=-110, duration=1.4)
    await s.say("inv-3")
    await s.idle(2.0)
    await s.wait_done()
    hit = page.get_by_text(rx("Other accounts hit")).first
    await s.scroll_to(hit, offset=-160, duration=1.2)
    await s.say("inv-4")
    await s.hover(hit, hold=1.0)
    await s.wait_done()
    plan = page.get_by_text("Save plan", exact=True).first
    await s.scroll_to(plan, offset=-260, duration=1.4)
    await s.say("inv-5")
    await s.idle(2.0)
    await s.wait_done()
    await s.scroll_to(plan, offset=-90, duration=1.0)
    approve = page.get_by_role("button", name=rx(r"^Approve all"))
    await s.say("inv-6")
    await s.hover(approve, hold=0.6)
    await s.click(approve)
    await page.get_by_text(rx("Saved in Relay")).first.wait_for(timeout=30000)
    await s.idle(2.5)
    await s.wait_done()
    await s.wait_done(0.6)


async def handover(s: Scene) -> None:
    page = s.page
    s.chapter("5 · Someone is leaving")
    await s.say("ho-1")
    await view_as(s, "Priya Raman")
    await s.click(page.get_by_role("link", name=rx("People")).first)
    await page.wait_for_url("**/people**")
    await asyncio.sleep(0.8)
    await s.click(page.get_by_role("link", name=rx("Rahul Verma")).first)
    await page.wait_for_url("**/people/p-rahul**")
    await s.wait_done()
    await s.say("ho-2")
    await s.click(page.get_by_role("button", name=rx("^Start handover")))
    await asyncio.sleep(0.8)
    dialog = page.get_by_role("dialog")
    await s.click(dialog.get_by_role("button", name=rx("^Start and analy")))
    await page.wait_for_url("**/handovers/**", timeout=20000)
    await s.wait_done()
    await s.say("ho-3")
    toggle = page.get_by_role("switch", name=rx("Preview departure"))
    await toggle.wait_for(timeout=30000)
    await page.wait_for_function("""() => {
        const t = document.querySelector('[role=switch][aria-label="Preview departure"]');
        return t && !t.disabled && !t.hasAttribute('data-disabled');
    }""", timeout=90000)
    await s.hover(page.get_by_text(rx(r"^\d+ things only Rahul knows")).first, hold=0.8)
    await s.wait_done()
    await s.say("ho-4")
    await s.click(toggle)
    await s.idle(3.0)
    await s.wait_done()
    impact = page.get_by_text(rx("Customer impact")).first
    await s.scroll_to(impact, offset=-160, duration=1.2)
    await s.say("ho-5")
    await s.hover(page.get_by_text("Northwind Foods").first, hold=1.5)
    await s.wait_done()
    accept = page.get_by_role("button", name=rx(r"^Accept"))
    if await accept.count():
        await s.scroll_to(accept.first, offset=-300, duration=1.0)
        await s.say("ho-6")
        await s.click(accept.first)
        await s.idle(0.8)
        await s.wait_done(0.2)


async def interview(s: Scene) -> None:
    page = s.page
    s.chapter("6 · Rahul answers")
    await s.say("iv-1")
    await view_as(s, "Rahul Verma")
    if "/interview" not in page.url:
        await page.goto(BASE + "/interview")
    start = page.get_by_role("button", name=rx("^Start"))
    await start.wait_for(timeout=20000)
    await s.hover(page.get_by_role("heading", level=1), hold=0.5)
    await s.click(start)
    box = page.get_by_role("textbox").first
    await box.wait_for(timeout=20000)
    await s.idle(1.5)
    await s.wait_done()
    await s.say("iv-2")
    await s.type(box, "Meta closes its pricing data on UTC days, at 05:30 IST. Midnight runs billed partial days. "
                      "Talk to Finance before you move it.", cps=38)
    await s.click(page.get_by_role("button", name=rx(r"^Save & next")))
    await asyncio.sleep(1.5)
    await s.wait_done(0.6)


async def brief(s: Scene) -> None:
    page = s.page
    s.chapter("7 · The renewal call")
    await s.say("brief-1")
    await view_as(s, "Sneha Bose")
    await s.click(page.get_by_role("link", name=rx("^Meetings")).first)
    await page.wait_for_url("**/meetings**")
    await asyncio.sleep(0.8)
    await s.click(page.get_by_role("link", name=rx("Northwind Foods")).first)
    await page.wait_for_url(f"**/meetings/{MEETING}**")
    await s.wait_done()
    await s.say("brief-2")
    await s.scroll(380, duration=1.6)
    await s.idle(2.5)
    await s.wait_done()
    await s.scroll(-380, duration=1.0)
    await s.say("brief-3")
    await s.hover(page.get_by_role("radio", name="1×"), hold=0.4)
    await s.wait_done()


async def call(s: Scene) -> None:
    """Start the replay and play each speaker's voice the moment their line appears."""
    page = s.page
    segments = script.call_segments()
    clips = [s.manifest[f"call:{i}"][0] for i in range(len(segments))]
    await s.click(page.get_by_role("button", name=rx("Start the call")))
    await page.get_by_text(rx("Recording")).first.wait_for(timeout=20000)
    seen = 0
    deadline = time.time() + 240
    while seen < len(segments) and time.time() < deadline:
        texts = await page.evaluate("""() => [...document.querySelectorAll('p')].map(p => p.textContent || '')""")
        for i in range(seen, len(segments)):
            if any(segments[i]["text"][:40] in t for t in texts):
                c = clips[i]
                s.audio(c["path"], c["duration"], segments[i]["text"], segments[i]["speaker_name"].split()[0])
                seen = i + 1
            else:
                break
        await asyncio.sleep(0.05)
    await asyncio.sleep(clips[-1]["duration"] + 0.5)
    await page.get_by_text(rx("summary ready|Call ended")).first.wait_for(timeout=60000)
    await asyncio.sleep(1.5)


async def followup(s: Scene) -> None:
    page = s.page
    await s.say("fu-1")
    await s.scroll_to(page.get_by_text("Summary", exact=True).first, offset=-120, duration=1.6)
    await s.idle(1.0)
    await s.wait_done()
    await s.say("fu-2")
    await s.hover(page.get_by_text("Account risk").first, hold=1.5)
    await s.wait_done()
    await s.scroll_to(page.get_by_role("heading", name="Follow-ups"), offset=-110, duration=1.6)
    await s.say("fu-3")
    await s.hover(page.get_by_text("Goes to customer").first, hold=1.2)
    await s.idle(1.0)
    await s.wait_done(0.6)


async def dayone(s: Scene) -> None:
    page = s.page
    s.chapter("8 · Aisha's first day")
    await s.say("d1-1")
    await view_as(s, "Aisha Khan")
    if "/day-one" not in page.url:
        await page.goto(BASE + "/day-one")
    await page.get_by_label("Meet these 5").wait_for(timeout=20000)
    await s.scroll_to(page.get_by_label("Meet these 5"), offset=-160, duration=1.4)
    await s.idle(2.0)
    await s.wait_done()
    await s.scroll(-2000, duration=1.0)
    await s.say("d1-2")
    await s.click(page.get_by_role("button", name=rx("Ask anything")).first)
    await asyncio.sleep(0.5)
    await s.type(None, "Why does wallet settlement run at 6 AM?", cps=20)
    await page.keyboard.press("Enter")
    await page.get_by_text(rx("How I found this")).first.wait_for(timeout=60000)
    await s.wait_done()
    await asyncio.sleep(0.6)
    await s.say("d1-3")
    await s.idle(3.0)
    await s.wait_done()
    await s.say("d1-4")
    await s.hover(page.get_by_text(rx("How I found this")).first, hold=1.5)
    await s.wait_done(0.6)
    await page.keyboard.press("Escape")


async def live(s: Scene) -> None:
    page = s.page
    s.chapter("9 · Knowledge stays current")
    q = "When will the campaign report export bug be fixed?"

    async def ask() -> None:
        await s.click(page.get_by_role("button", name=rx("Ask anything")).first)
        await asyncio.sleep(0.4)
        await s.type(None, q, cps=22)
        await page.keyboard.press("Enter")
        await page.get_by_text(rx("How I found this")).first.wait_for(timeout=60000)

    await s.say("live-1")
    await ask()
    await s.wait_done(1.0)
    await page.keyboard.press("Escape")
    await asyncio.sleep(0.4)
    await s.say("live-2")
    await s.click(page.get_by_role("link", name=rx("How it works")).first)
    await page.wait_for_url("**/settings/system**")
    card = page.get_by_text(rx("Send a Slack message into the graph")).first
    await card.wait_for(timeout=20000)
    await s.scroll_to(card, offset=-120, duration=1.2)
    await s.click(page.get_by_role("button", name=rx("^Send to Relay")))
    await page.get_by_text(rx("^In the graph")).first.wait_for(timeout=20000)
    await s.wait_done(0.6)
    await s.say("live-3")
    await s.click(page.get_by_role("button", name=rx("^Ask about it")))
    await page.get_by_text(rx("How I found this")).first.wait_for(timeout=60000)
    await s.idle(1.5)
    await s.wait_done(0.6)
    await page.keyboard.press("Escape")


async def how(s: Scene) -> None:
    page = s.page
    s.chapter("10 · How it works")
    await s.say("how-1")
    if "/settings/system" not in page.url:
        await s.click(page.get_by_role("link", name=rx("How it works")).first)
        await page.wait_for_url("**/settings/system**")
    await asyncio.sleep(0.5)
    graphs = page.get_by_role("heading", name=rx("Company graphs"))
    await s.scroll_to(graphs, offset=-110, duration=1.4)
    await s.idle(1.5)
    await s.wait_done()
    console = page.get_by_role("heading", name="Cypher console")
    await s.scroll_to(console, offset=-110, duration=1.2)
    await s.say("how-2")
    await s.click(page.get_by_role("button", name="Who knows each system"))
    await asyncio.sleep(0.4)
    await s.click(page.get_by_role("button", name=rx(r"^Run read-only")).first)
    await s.idle(1.5)
    await s.wait_done()
    meter = page.get_by_role("heading", name="Throughput")
    await s.scroll_to(meter, offset=-110, duration=1.2)
    await s.say("how-3")
    await s.click(page.get_by_role("button", name=rx(r"Run a 10 s load test")))
    await s.idle(4.0)
    await s.wait_done(1.0)


async def repos(s: Scene) -> None:
    page = s.page
    s.chapter("11 · Your own repo, real data")
    await s.say("repos-1")
    await s.click(page.get_by_role("link", name=rx("Repo knowledge")).first)
    await page.wait_for_url("**/repos**")
    box = page.get_by_label("GitHub repository URL")
    await box.wait_for(timeout=20000)
    await s.type(box, "https://github.com/FalkorDB/falkordb-py", cps=26)
    await s.click(page.get_by_role("button", name=rx("^Analyze")))
    only = page.get_by_text("Only one person knows", exact=True).last
    await only.wait_for(timeout=120000)
    await s.wait_done(0.4)
    await s.scroll_to(only, offset=-160, duration=1.4)
    await s.say("repos-2")
    await s.idle(2.0)
    await s.wait_done()
    dep = page.get_by_role("button", name=rx("Preview departure")).first
    await s.scroll_to(dep, offset=-300, duration=1.2)
    await s.say("repos-3")
    await s.click(dep)
    await s.idle(2.0)
    await s.wait_done()
    q = page.get_by_label("Question about this repository")
    await s.scroll_to(q, offset=-300, duration=1.2)
    await s.say("repos-4")
    await s.type(q, "Who should take over the falkordb module if its owner leaves?", cps=24)
    await s.click(page.get_by_role("button", name=rx("^Ask$")).last)
    await page.get_by_text(rx(r"gemini-[\d.]+-flash.*ms")).first.wait_for(timeout=60000)
    await s.wait_done(0.3)
    await s.say("repos-5")
    await s.hover(page.get_by_text(rx(r"gemini-[\d.]+-flash.*ms")).first, hold=1.0)
    await s.wait_done(0.6)


FLOWS = {"graph": graph, "repos": repos, "intro": intro, "landing": landing, "signup": signup, "risk": risk, "investigate": investigate,
         "handover": handover, "interview": interview, "brief": brief, "call": call, "followup": followup,
         "dayone": dayone, "live": live, "how": how, "outro": outro}


async def main(start: str | None, only: str | None, headed: bool, stop: str | None = None) -> None:
    manifest = json.loads((CACHE / "manifest.json").read_text())
    order = script.SCENE_ORDER
    todo = [only] if only else order[order.index(start):] if start else order
    if stop:
        todo = todo[: todo.index(stop) + 1]
    if not only and (not start or start in ("intro", "landing")):
        shutil.rmtree(PROFILE, ignore_errors=True)
        (CACHE / "account.json").unlink(missing_ok=True)
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            str(PROFILE), headless=not headed, viewport=VIEWPORT, device_scale_factor=4 / 3,
            args=["--hide-scrollbars", "--disable-features=Translate"])
        await ctx.add_init_script(CURSOR_JS)
        await ctx.add_init_script("try { localStorage.setItem('relay.tour.dismissed', '1') } catch (e) {}")
        app = ctx.pages[0] if ctx.pages else await ctx.new_page()
        for name in todo:
            card = name in ("intro", "outro")
            page = await ctx.new_page() if card else app
            if not card:
                await page.bring_to_front()
                if name == "landing":
                    await page.goto(BASE + "/")
                    await page.wait_for_load_state("networkidle")
                elif page.url in ("about:blank", ""):
                    await page.goto(BASE + "/home")
                    await page.wait_for_load_state("networkidle")
            print(f"recording {name}", flush=True)
            try:
                async with Scene(page, SCENES_DIR, name, manifest) as s:
                    await FLOWS[name](s)
            except Exception:
                shot = CACHE / f"fail-{name}.png"
                await page.screenshot(path=str(shot))
                print(f"  failed in {name}; screenshot {shot}", flush=True)
                raise
            if card:
                await page.close()
        await ctx.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start")
    ap.add_argument("--only")
    ap.add_argument("--to", dest="stop")
    ap.add_argument("--headed", action="store_true")
    a = ap.parse_args()
    asyncio.run(main(a.start, a.only, a.headed, a.stop))
