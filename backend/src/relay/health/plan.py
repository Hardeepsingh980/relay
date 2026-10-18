"""Save plan: 2-4 actions prepared from a verdict, edited by a human, executed only after approval.

Adapters report honestly: a live delivery, a draft, or a clearly labelled simulation.
A simulated action is never reported as delivered. Customer-facing actions are
always drafts until a person sends them.

Live adapters (optional):
  Jira       workspace connection or JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN / JIRA_PROJECT_KEY
  Gmail      Google connection (drafts only, never sends)
  Slack      a workspace Slack bot ("slack_live" connection: chat.postMessage), else
             SLACK_WEBHOOK_URL (incoming webhook) or a workspace "slack" webhook connection
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass

import httpx

from .. import actions as relay_actions
from .. import db
from ..config import now
from .tools import inr, short_name

PRIORITY_UP = {"P4": "P2", "P3": "P1", "P2": "P1", "P1": "P1"}


@dataclass
class Outcome:
    status: str          # succeeded | failed | simulated | drafted
    message: str
    ref: str | None = None
    url: str | None = None


def _slack_webhook() -> str | None:
    from .. import workspaces
    c = workspaces.secret(db.current_workspace_id(), "slack")
    return (c or {}).get("webhook_url") or os.getenv("SLACK_WEBHOOK_URL") or None


def _slack_bot() -> dict:
    """The workspace's Slack bot (token + default channel), connected in Settings › Connections."""
    from .. import workspaces
    c = workspaces.secret(db.current_workspace_id(), "slack_live")
    return c if (c or {}).get("token") else {}


def _slack_channel() -> str:
    return _slack_bot().get("channel") or "#cs"


def _slack_post(bot: dict, channel: str, text: str) -> Outcome:
    """chat.postMessage to the action's channel; if the bot can't post there, to the default channel."""
    targets = [channel] + ([bot["channel"]] if bot.get("channel") and bot["channel"] != channel else [])
    errors: list[str] = []
    for ch in targets:
        try:
            r = httpx.post("https://slack.com/api/chat.postMessage", headers={"Authorization": f"Bearer {bot['token']}"},
                           json={"channel": ch, "text": text}, timeout=10)
            body = r.json()
        except (httpx.HTTPError, ValueError) as e:
            return Outcome("failed", f"Couldn't reach Slack: {e.__class__.__name__}")
        if body.get("ok"):
            note = f" ({targets[0]} failed: {errors[0]})" if errors else ""
            return Outcome("succeeded", f"Posted to {ch} in Slack{note}", ref=f"slack:{body.get('channel')}:{body.get('ts')}")
        errors.append(body.get("error") or f"HTTP {r.status_code}")
        if errors[-1] not in ("channel_not_found", "not_in_channel", "is_archived"):
            break
    return Outcome("failed", f"Slack did not post to {targets[0]}: {errors[0]}"
                             + (f"; {targets[1]}: {errors[1]}" if len(errors) > 1 else "")
                             + (". Invite the Relay bot to the channel." if "not_in_channel" in errors else ""))


def integration_status() -> dict:
    jira = relay_actions._jira_configured()
    google = relay_actions._google_configured()
    slack = bool(_slack_bot() or _slack_webhook())
    return {
        "jira": {"mode": "live" if jira else "simulated", "label": "Jira" if jira else "Relay tasks"},
        "gmail": {"mode": "live" if google else "draft", "label": "Gmail drafts" if google else "Relay drafts"},
        "slack": {"mode": "live" if slack else "simulated", "label": f"Slack {_slack_channel()}" if slack else "Relay inbox"},
    }


def _action(kind: str, title: str, summary: str, destination: dict, payload: dict, addresses: list[str],
            investigation_id: str, customer_facing: bool = False) -> dict:
    return {"id": f"act-{uuid.uuid4().hex[:10]}", "type": kind, "title": title, "summary": summary,
            "destination": destination, "payload": payload, "addresses": addresses, "status": "proposed",
            "investigationId": investigation_id, "customerFacing": customer_facing, "result": None,
            "approvedAt": None, "executedAt": None, "approvedBy": None}


def _contact_email(name: str, account_id: str) -> str:
    r = db.rows("MATCH (c:Contact {name: $n})-[:WORKS_AT]->(:Account {id: $a}) RETURN c.email AS e",
                {"n": name, "a": account_id}, readonly=True)
    return r[0]["e"] if r else ""


def prepare(investigation_id: str, verdict: dict, data: dict) -> list[dict]:
    status = integration_status()
    acc = data["account_overview"]["account"]
    csm = data["account_overview"].get("csm") or {}
    ae = data["account_overview"].get("ae") or {}
    short = short_name(acc["name"])
    out: list[dict] = []
    blast = data.get("blast_radius")
    bug_id = verdict.get("bugId")
    cluster = next((c for c in data.get("ticket_root_causes", {}).get("clusters", []) if c["bugId"] == bug_id), None)

    if bug_id and cluster:
        impact = (f"{blast['accountCount']} other accounts ({inr(blast['totalArr'])} ARR) also have this bug, "
                  f"{inr(blast['totalArr'] + acc['arr'])} ARR in total." if blast else "")
        new_priority = PRIORITY_UP.get(cluster["bugPriority"], "P1")
        comment = (f"Raising {bug_id} ({cluster['bugTitle']}) from {cluster['bugPriority']} to {new_priority}.\n\n"
                   f"Customer impact: {acc['name']} ({inr(acc['arr'])} ARR) renews in {verdict['renewalInDays']} days. "
                   f"They raised {len(cluster['tickets'])} tickets about this bug "
                   f"({', '.join(t['id'] for t in cluster['tickets'])}). "
                   f"{impact}\n\nOwner: {cluster['owner'] or 'unassigned'}. Please share a fix date with the CS team by "
                   f"Thursday.\nEvidence: Relay investigation {investigation_id}.")
        out.append(_action("bug.escalate", f"Escalate {bug_id} to {new_priority}",
                           f"Raise the priority, show the ARR at stake and ask {cluster['owner'] or 'the owner'} for a fix date",
                           {"system": "Jira", "mode": status["jira"]["mode"], "target": bug_id},
                           {"issueKey": bug_id, "issueTitle": cluster["bugTitle"], "currentPriority": cluster["bugPriority"],
                            "proposedPriority": new_priority, "assignee": cluster["owner"], "comment": comment},
                           [bug_id], investigation_id))

    champ = data.get("champion_changes", {})
    departed = next((d for d in champ.get("departures", []) if d["champion"]), None)
    recipient = departed["successor"] if departed and departed.get("successor") else (
        {"name": cluster["reporters"][0]} if cluster and cluster["reporters"] else None)
    if recipient:
        to = _contact_email(recipient["name"], acc["id"])
        fname = recipient["name"].split()[0]
        sender = csm.get("name") or "Your Cheerio team"
        fix = (f"We raised the priority of the {cluster['bugKeyword']} issue behind your recent tickets "
               f"({', '.join(t['id'] for t in cluster['tickets'])}). I will send you a fix date by Friday."
               if cluster else "I want to check how things are going since you took over.")
        work = (f"Until then, here is a workaround: {cluster['bugWorkaround'][0].lower()}{cluster['bugWorkaround'][1:]}\n\n"
                if cluster and cluster.get("bugWorkaround") else "")
        body = (f"Hi {fname},\n\nThank you for your patience over the last few weeks. {fix}\n\n{work}"
                f"You are the new admin, so I want to offer you a 30-minute session. We can go through campaign reports "
                f"and the workflows your team uses. Does Thursday or Friday work for you?\n\nBest,\n{sender}")
        out.append(_action("email.draft", f"Draft recovery email to {fname}",
                           f"A promised fix date, a workaround and an admin session for {recipient['name']}",
                           {"system": "Gmail", "mode": status["gmail"]["mode"], "target": to},
                           {"to": [to], "subject": f"Your {cluster['bugKeyword'] if cluster else 'Cheerio'} issue and a short admin session",
                            "body": body, "send": False}, [acc["id"]], investigation_id, customer_facing=True))

    for p in verdict.get("promisesAtRisk", [])[:1]:
        owner = p.get("madeBy") or ae.get("name") or "the account owner"
        reason = p["why"].rsplit("(", 1)[-1].rstrip(")") if "(" in p["why"] else p["why"]
        note = (f"“{p['text']}” is at risk ({reason}). Before the renewal call, reset the expectation. Give the new "
                f"quarter, not a date we cannot keep, and confirm it in writing.")
        out.append(_action("task.create", f"Reset the promise with {owner.split()[0]}",
                           f"{reason[:1].upper()}{reason[1:]}. Reset “{p['text']}” before the renewal call",
                           {"system": "Jira", "mode": status["jira"]["mode"], "target": owner},
                           {"assignee": owner, "title": f"{short}: reset expectation on '{p['text']}'", "description": note,
                            "due": "before the renewal call"}, [p["id"], acc["id"]], investigation_id))

    for p in verdict.get("ownersLeaving", [])[:1]:
        rel = ", ".join(p["relations"]) or "owner"
        out.append(_action("task.create", f"Name a new {rel} for {short}",
                           f"{p['name']} leaves {p['lastDay']}. Pick the next owner and introduce them",
                           {"system": "Jira", "mode": status["jira"]["mode"], "target": "Engineering manager"},
                           {"assignee": "Priya Raman", "title": f"{short}: new {rel} before {p['lastDay']}",
                            "description": f"{p['name']} is {short}'s {rel} and leaves on {p['lastDay']}. Pick the next "
                                           f"owner from the handover and send the customer an intro.",
                            "due": p["lastDay"]}, [p["id"], acc["id"]], investigation_id))

    chain = " → ".join(s["title"] for s in verdict["chain"]) or "see the investigation"
    msg = (f"*{acc['name']}*: {verdict['risk']}% risk of leaving vs HubSpot health {acc['crmHealthScore']}. "
           f"Renewal in {verdict['renewalInDays']} days, {inr(acc['arr'])} ARR.\nWhy: {verdict['headline']}\n"
           f"How it connects: {chain}\nOwner: {csm.get('name', 'CSM')}. Next step: a call with their executive "
           f"sponsor this week.")
    channel = _slack_channel()
    out.append(_action("slack.post", "Brief the CS channel", f"Post the risk summary for {short} to {channel}",
                       {"system": "Slack", "mode": status["slack"]["mode"], "target": channel},
                       {"channel": channel, "message": msg}, [acc["id"]], investigation_id))
    return out[:4]


def validate_payload(action: dict) -> list[str]:
    p, errs = action["payload"], []
    if action["type"] == "slack.post" and not p.get("message", "").strip():
        errs.append("Slack message is empty")
    if action["type"] == "bug.escalate":
        if p.get("proposedPriority") not in ("P1", "P2", "P3", "P4"):
            errs.append("Priority must be P1, P2, P3 or P4")
        if not p.get("comment", "").strip():
            errs.append("Escalation comment is empty")
    if action["type"] == "email.draft":
        if not p.get("to") or "@" not in p["to"][0]:
            errs.append("Recipient email is missing")
        if not p.get("subject", "").strip() or not p.get("body", "").strip():
            errs.append("Subject and body are required")
    if action["type"] == "task.create" and not p.get("title", "").strip():
        errs.append("Task title is empty")
    return errs


def _jira_task(summary: str, description: str) -> Outcome:
    c = relay_actions._creds("jira_live")
    base = c["base_url"].rstrip("/")
    body = {"fields": {"project": {"key": c["project"]}, "issuetype": {"name": "Task"}, "summary": summary,
                       "description": {"type": "doc", "version": 1, "content": [
                           {"type": "paragraph", "content": [{"type": "text", "text": description}]}]}}}
    r = httpx.post(f"{base}/rest/api/3/issue", auth=(c["email"], c["token"]), json=body, timeout=20)
    r.raise_for_status()
    key = r.json()["key"]
    return Outcome("succeeded", f"Created {key} in Jira", ref=key, url=f"{base}/browse/{key}")


def execute(action: dict) -> Outcome:
    p, mode = action["payload"], action["destination"]["mode"]
    t = action["type"]
    if t == "bug.escalate":
        if mode != "live":
            return Outcome("simulated", f"Saved in Relay: raise {p['issueKey']} to {p['proposedPriority']}. "
                                        f"Connect Jira to change the issue there too.")
        return _jira_task(f"[Relay] Escalate {p['issueKey']} to {p['proposedPriority']}: {p['issueTitle']}",
                          p["comment"])
    if t == "task.create":
        if mode != "live":
            return Outcome("simulated", f"Saved in Relay as a task for {p['assignee']}: {p['title']}. "
                                        f"Connect Jira to create it there too.")
        return _jira_task(f"[Relay] {p['title']}", p["description"])
    if t == "email.draft":
        if mode == "live":
            r = relay_actions._live_gmail({"to": p["to"], "subject": p["subject"], "body": p["body"]})
            return Outcome("drafted", r["message"], ref=r["externalId"], url=r["url"])
        return Outcome("drafted", f"Draft saved in Relay for {', '.join(p['to'])}. Open it in your email to send it.",
                       ref=f"draft:{action['id']}")
    if t == "slack.post":
        bot, hook = _slack_bot(), _slack_webhook()
        if mode != "live" or not (bot or hook):
            return Outcome("simulated", f"Saved in Relay for {p['channel']}. Connect Slack to post it there too.")
        if bot:
            return _slack_post(bot, p.get("channel") or bot.get("channel") or "#cs", p["message"])
        resp = httpx.post(hook, json={"text": p["message"]}, timeout=10)
        if resp.status_code == 200:
            return Outcome("succeeded", f"Posted to {p['channel']}", ref=f"slack:{resp.status_code}")
        return Outcome("failed", f"Slack returned {resp.status_code}: {resp.text[:120]}")
    return Outcome("failed", f"Unknown action type {t}")


def persist(action: dict) -> None:
    """Record the executed action with its approver: (:Action)-[:ADDRESSES]->(Bug|Account|Promise|Person)."""
    db.run("""
MERGE (x:Action {id: $id})
SET x.type = $type, x.title = $title, x.status = $status, x.payload = $payload, x.approvedAt = $approvedAt,
    x.approvedBy = $approvedBy, x.executedAt = $executedAt, x.resultRef = $ref, x.mode = $mode,
    x.investigationId = $inv, x.origin = 'account-health', x.customerFacing = $cf, x.message = $msg
WITH x
OPTIONAL MATCH (i:Investigation {id: $inv})
FOREACH (_ IN CASE WHEN i IS NULL THEN [] ELSE [1] END | MERGE (i)-[:PROPOSED]->(x))
WITH x
UNWIND $addresses AS target
MATCH (t) WHERE (t:Bug OR t:Account OR t:Promise OR t:Person) AND t.id = target
MERGE (x)-[:ADDRESSES]->(t)
""", {"id": action["id"], "type": action["type"], "title": action["title"], "status": action["status"],
      "payload": json.dumps(action["payload"]), "approvedAt": action["approvedAt"], "approvedBy": action["approvedBy"],
      "executedAt": action["executedAt"], "ref": (action.get("result") or {}).get("ref"),
      "mode": action["destination"]["mode"], "inv": action["investigationId"], "cf": action.get("customerFacing", False),
      "msg": (action.get("result") or {}).get("message"), "addresses": action["addresses"]})


def log(limit: int = 50) -> list[dict]:
    """Every Account Health action with its approver (PRD: every action is logged with who approved it)."""
    return [{**r, "at": r["at"] or r["approvedAt"]} for r in db.rows("""
MATCH (x:Action {origin: 'account-health'})
OPTIONAL MATCH (x)-[:ADDRESSES]->(a:Account)
RETURN x.id AS id, x.title AS title, x.type AS type, x.status AS status, x.mode AS mode, x.approvedBy AS approvedBy,
       x.approvedAt AS approvedAt, x.executedAt AS at, x.message AS message, a.name AS account, a.id AS accountId
ORDER BY x.executedAt DESC LIMIT $n""", {"n": limit}, readonly=True)]


def stamp() -> str:
    return now().isoformat(timespec="seconds")
