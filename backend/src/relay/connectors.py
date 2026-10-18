"""Connector catalog: real credential checks for the tools a team uses, plus MCP servers.

Every provider has one `verify(fields)` that makes ONE live HTTPS call to the provider.
Only after that call succeeds does Relay store the credentials, encrypted with
RELAY_SECRET_KEY (see secretbox). `uses` says, in one honest sentence, what Relay
does with the connection today. Secrets never leave the server: views mask them.

Live connections are stored as (:Connection {provider: '<id>_live'}) rows in the
accounts graph, so the sample-data rows (`mode: 'demo'`) for the same tool stay as
they are. Jira keeps its existing `jira_live` row and Google its `google` row, which
the action adapters already read.
"""

from __future__ import annotations

import base64
import json
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import anyio
import httpx

from . import db, google_oauth, secretbox, workspaces
from .auth import AuthError, _g

TIMEOUT = 10.0
CATEGORIES = ["CRM", "Support", "Chat", "Issues", "Docs", "Code", "Meetings", "Email & calendar"]
NOT_IMPORTED = "this workspace uses imported sample data."


@dataclass
class Field:
    key: str
    label: str
    secret: bool = False
    placeholder: str = ""
    help: str = ""
    optional: bool = False

    def view(self) -> dict:
        return {"key": self.key, "label": self.label, "secret": self.secret, "placeholder": self.placeholder,
                "help": self.help, "optional": self.optional}


@dataclass
class Provider:
    id: str
    name: str
    category: str
    color: str
    auth: str                      # api_key | oauth
    description: str
    fields: list[Field]
    docs: str
    docs_label: str
    uses: str
    verify: Callable[[dict], dict]
    store_as: str = ""             # Connection.provider for the live row
    sample: list[str] = field(default_factory=list)   # SOURCES ids this tool's sample data came from

    def __post_init__(self) -> None:
        self.store_as = self.store_as or f"{self.id}_live"


# ------------------------------------------------------------------ helpers

def _ok(account: str, detail: str) -> dict:
    return {"ok": True, "account": account, "detail": detail}


def _fail(detail: str) -> dict:
    return {"ok": False, "account": None, "detail": detail}


def _basic(user: str, password: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


def _provider_message(r: httpx.Response) -> str:
    """The provider's own error text, if the body has one."""
    try:
        body = r.json()
    except ValueError:
        return (r.text or "").strip()[:160]
    if isinstance(body, dict):
        for k in ("message", "error_description", "description", "error", "errorMessages", "errors", "detail"):
            v = body.get(k)
            if isinstance(v, list) and v:
                v = v[0]
            if isinstance(v, dict):
                v = v.get("message") or v.get("title") or v.get("detail") or json.dumps(v)[:160]
            if isinstance(v, str) and v.strip():
                return v.strip()[:160]
    return ""


def _call(name: str, method: str, url: str, **kw) -> httpx.Response | dict:
    """One HTTPS call. Returns the response, or a failure dict when the provider can't be reached."""
    try:
        return httpx.request(method, url, timeout=TIMEOUT, **kw)
    except httpx.TimeoutException:
        return _fail(f"{name} did not answer within {int(TIMEOUT)} seconds.")
    except httpx.HTTPError as e:
        return _fail(f"Couldn't reach {name}: {e.__class__.__name__}. Check the address.")


def _first_sentence(text: str) -> str:
    text = text.strip()
    cut = text.find(". ")
    return text[:cut + 1] if 0 < cut < len(text) - 2 else text


def _rejected(name: str, r: httpx.Response, what: str = "those credentials") -> dict:
    msg = _first_sentence(_provider_message(r)).rstrip(".")
    if r.status_code == 404:
        return _fail(f"{name} has nothing at that address (HTTP 404{': ' + msg if msg else ''}). Check the site or subdomain.")
    return _fail(f"{name} rejected {what} (HTTP {r.status_code}{': ' + msg if msg else ''}).")


def _need(fields: dict, *keys: str) -> dict:
    out = {k: (fields.get(k) or "").strip() for k in keys}
    missing = [k for k, v in out.items() if not v]
    if missing:
        raise AuthError(f"Fill in: {', '.join(missing)}")
    return out


def _subdomain(raw: str, suffix: str) -> str:
    """'acme', 'acme.zendesk.com' or 'https://acme.zendesk.com/agent' -> 'acme'."""
    s = re.sub(r"^https?://", "", raw.strip().lower()).split("/")[0]
    s = s.removesuffix(suffix)
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", s):
        raise AuthError(f"Use just your subdomain, like “acme” for acme{suffix}")
    return s


def _public_host(host: str) -> None:
    """On a public server (RELAY_BLOCK_PRIVATE_URLS=1), refuse hosts that resolve to private, loopback or
    link-local addresses, so a pasted URL cannot reach the server's own network or cloud metadata."""
    import ipaddress
    import os
    import socket
    if os.getenv("RELAY_BLOCK_PRIVATE_URLS") != "1":
        return
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        raise AuthError(f"Relay cannot find {host}") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise AuthError(f"{host} is a private address. Use a public URL.")


def _https_site(raw: str, example: str) -> str:
    s = (raw or "").strip().rstrip("/")
    s = s.removesuffix("/wiki")
    u = urlparse(s)
    if u.scheme != "https" or not re.fullmatch(r"[\w.-]+(:\d+)?", u.netloc or "") or u.path not in ("", "/"):
        raise AuthError(f"Use your site address, like {example}")
    _public_host(u.hostname or "")
    return f"https://{u.netloc}"


# ------------------------------------------------------------------ verifiers

def verify_hubspot(f: dict) -> dict:
    v = _need(f, "token")
    r = _call("HubSpot", "GET", "https://api.hubapi.com/crm/v3/objects/companies?limit=1",
              headers={"Authorization": f"Bearer {v['token']}"})
    if isinstance(r, dict):
        return r
    if r.status_code != 200:
        return _rejected("HubSpot", r, "this token")
    n = len(r.json().get("results", []))
    return _ok(f"Private app ····{v['token'][-4:]}",
               "Read access to companies works." + ("" if n else " The portal has no companies yet."))


def verify_zendesk(f: dict) -> dict:
    v = _need(f, "subdomain", "email", "token")
    sub = _subdomain(v["subdomain"], ".zendesk.com")
    r = _call("Zendesk", "GET", f"https://{sub}.zendesk.com/api/v2/users/me.json",
              headers={"Authorization": _basic(f"{v['email']}/token", v["token"])})
    if isinstance(r, dict):
        return r
    if r.status_code != 200:
        return _rejected("Zendesk", r)
    user = r.json().get("user") or {}
    if not user.get("id"):   # Zendesk answers anonymous requests with an anonymous user
        return _fail("Zendesk did not accept the email and API token (it treated the request as anonymous).")
    return _ok(f"{user.get('email') or v['email']} · {sub}.zendesk.com", f"Signed in as {user.get('name')} ({user.get('role')}).")


def verify_intercom(f: dict) -> dict:
    v = _need(f, "token")
    r = _call("Intercom", "GET", "https://api.intercom.io/me",
              headers={"Authorization": f"Bearer {v['token']}", "Accept": "application/json"})
    if isinstance(r, dict):
        return r
    if r.status_code != 200:
        return _rejected("Intercom", r, "this access token")
    me = r.json()
    app = (me.get("app") or {}).get("name")
    return _ok(" · ".join(x for x in (me.get("email"), app) if x) or "Intercom workspace", f"Signed in as {me.get('name')}.")


def verify_freshdesk(f: dict) -> dict:
    v = _need(f, "domain", "api_key")
    dom = _subdomain(v["domain"], ".freshdesk.com")
    r = _call("Freshdesk", "GET", f"https://{dom}.freshdesk.com/api/v2/agents/me",
              headers={"Authorization": _basic(v["api_key"], "X")})
    if isinstance(r, dict):
        return r
    if r.status_code != 200:
        return _rejected("Freshdesk", r, "this API key")
    c = r.json().get("contact") or {}
    return _ok(f"{c.get('email') or c.get('name') or 'agent'} · {dom}.freshdesk.com", f"Signed in as {c.get('name')}.")


def _channel(raw: str) -> str:
    s = (raw or "").strip()
    if re.fullmatch(r"[CGD][A-Z0-9]{6,}", s):   # a channel ID
        return s
    s = "#" + s.lstrip("#").lower()
    if not re.fullmatch(r"#[a-z0-9][a-z0-9._-]{0,79}", s):
        raise AuthError("Use a channel name like #customer-success, or a channel ID like C0123ABCD")
    return s


def verify_slack(f: dict) -> dict:
    v = _need(f, "token", "channel")
    if not v["token"].startswith("xoxb-"):
        return _fail("Use a bot token. It starts with xoxb- and is on your Slack app's OAuth & Permissions page.")
    _channel(v["channel"])
    r = _call("Slack", "POST", "https://slack.com/api/auth.test", headers={"Authorization": f"Bearer {v['token']}"})
    if isinstance(r, dict):
        return r
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code != 200 or not body.get("ok"):
        return _fail(f"Slack rejected this token ({body.get('error') or f'HTTP {r.status_code}'}).")
    return _ok(f"{body.get('user')} in {body.get('team')}",
               f"Bot user {body.get('user')} in the {body.get('team')} workspace. Invite it to {_channel(v['channel'])} "
               f"so it can post there.")


def verify_jira(f: dict) -> dict:
    v = _need(f, "base_url", "email", "token")
    site = _https_site(v["base_url"], "https://your-team.atlassian.net")
    r = _call("Jira", "GET", f"{site}/rest/api/3/myself", headers={"Authorization": _basic(v["email"], v["token"]),
                                                                    "Accept": "application/json"})
    if isinstance(r, dict):
        return r
    if r.status_code != 200:
        return _rejected("Jira", r)
    me = r.json()
    return _ok(f"{me.get('emailAddress') or v['email']} · {site.removeprefix('https://')}", f"Signed in as {me.get('displayName')}.")


def verify_linear(f: dict) -> dict:
    v = _need(f, "api_key")
    r = _call("Linear", "POST", "https://api.linear.app/graphql", json={"query": "{ viewer { id name } }"},
              headers={"Authorization": v["api_key"], "Content-Type": "application/json"})
    if isinstance(r, dict):
        return r
    body = r.json() if "json" in r.headers.get("content-type", "") else {}
    viewer = ((body.get("data") or {}).get("viewer")) or {}
    if r.status_code != 200 or not viewer.get("id"):
        msg = ((body.get("errors") or [{}])[0]).get("message") or f"HTTP {r.status_code}"
        return _fail(f"Linear rejected this API key ({msg}).")
    return _ok(viewer.get("name") or "Linear user", f"Signed in as {viewer.get('name')}.")


def verify_confluence(f: dict) -> dict:
    v = _need(f, "site", "email", "token")
    site = _https_site(v["site"], "https://your-team.atlassian.net")
    r = _call("Confluence", "GET", f"{site}/wiki/rest/api/user/current",
              headers={"Authorization": _basic(v["email"], v["token"]), "Accept": "application/json"})
    if isinstance(r, dict):
        return r
    if r.status_code != 200:
        return _rejected("Confluence", r)
    me = r.json()
    if me.get("type") == "anonymous" or not me.get("accountId"):
        return _fail("Confluence treated the request as anonymous. Check the email and API token.")
    return _ok(f"{me.get('displayName') or me.get('publicName')} · {site.removeprefix('https://')}",
               f"Signed in as {me.get('displayName')}.")


def verify_notion(f: dict) -> dict:
    v = _need(f, "token")
    r = _call("Notion", "GET", "https://api.notion.com/v1/users/me",
              headers={"Authorization": f"Bearer {v['token']}", "Notion-Version": "2022-06-28"})
    if isinstance(r, dict):
        return r
    if r.status_code != 200:
        return _rejected("Notion", r, "this token")
    me = r.json()
    ws = (me.get("bot") or {}).get("workspace_name")
    return _ok(" · ".join(x for x in (me.get("name"), ws) if x) or "Notion integration",
               "Notion only shares pages you add to the integration with ⋯ › Connections.")


def verify_github(f: dict) -> dict:
    v = _need(f, "token")
    r = _call("GitHub", "GET", "https://api.github.com/user",
              headers={"Authorization": f"Bearer {v['token']}", "Accept": "application/vnd.github+json",
                       "X-GitHub-Api-Version": "2022-11-28"})
    if isinstance(r, dict):
        return r
    if r.status_code != 200:
        return _rejected("GitHub", r, "this token")
    me = r.json()
    scopes = r.headers.get("x-oauth-scopes")
    return _ok(me.get("login") or "GitHub user",
               f"Signed in as {me.get('login')}." + (f" Token scopes: {scopes}." if scopes else ""))


def verify_fireflies(f: dict) -> dict:
    v = _need(f, "api_key")
    r = _call("Fireflies", "POST", "https://api.fireflies.ai/graphql", json={"query": "{ user { email name } }"},
              headers={"Authorization": f"Bearer {v['api_key']}", "Content-Type": "application/json"})
    if isinstance(r, dict):
        return r
    body = r.json() if "json" in r.headers.get("content-type", "") else {}
    user = ((body.get("data") or {}).get("user")) or {}
    if r.status_code != 200 or not user:
        msg = ((body.get("errors") or [{}])[0]).get("message") or f"HTTP {r.status_code}"
        return _fail(f"Fireflies rejected this API key ({msg}).")
    return _ok(user.get("email") or user.get("name") or "Fireflies user", f"Signed in as {user.get('name')}.")


def verify_gong(f: dict) -> dict:
    v = _need(f, "access_key", "secret")
    base = (f.get("base_url") or "").strip().rstrip("/") or "https://api.gong.io"
    host = urlparse(base).hostname or ""
    if not base.startswith("https://") or not (host == "gong.io" or host.endswith(".gong.io")):
        raise AuthError("The API base URL must be a gong.io address, like https://api.gong.io")
    r = _call("Gong", "GET", f"{base}/v2/users", headers={"Authorization": _basic(v["access_key"], v["secret"])})
    if isinstance(r, dict):
        return r
    if r.status_code != 200:
        return _rejected("Gong", r, "this access key and secret")
    total = (r.json().get("records") or {}).get("totalRecords")
    return _ok(f"Gong · {total} users" if total is not None else "Gong", "Read access to users works.")


def verify_google_client(f: dict) -> dict:
    """Checks a client ID/secret pair against Google's token endpoint with a dummy code.

    A real client gets `invalid_grant` (the code is fake); a wrong one gets `invalid_client`.
    """
    v = _need(f, "client_id", "client_secret")
    if not v["client_id"].endswith(".apps.googleusercontent.com"):
        return _fail("A Google OAuth client ID ends with .apps.googleusercontent.com.")
    r = _call("Google", "POST", google_oauth.TOKEN_URL, data={
        "code": "relay-credential-check", "client_id": v["client_id"], "client_secret": v["client_secret"],
        "redirect_uri": google_oauth.redirect_uri(), "grant_type": "authorization_code"})
    if isinstance(r, dict):
        return r
    try:
        err = r.json().get("error")
    except ValueError:
        err = None
    if err in ("invalid_grant", "redirect_uri_mismatch"):
        return _ok(f"OAuth client ····{v['client_id'].split('.')[0][-6:]}",
                   "Google recognises this client ID and secret. Next, authorize a Google account.")
    if err in ("invalid_client", "unauthorized_client"):
        return _fail(f"Google does not recognise this client ID and secret ({err}).")
    return _fail(f"Google answered HTTP {r.status_code}{': ' + err if err else ''}.")


# ------------------------------------------------------------------ catalog

def _not_built(what: str) -> str:
    return f"Relay checks and stores these credentials. {what} is not built yet; {NOT_IMPORTED}"


CATALOG: list[Provider] = [
    Provider("hubspot", "HubSpot", "CRM", "#FF7A59", "api_key",
             "Accounts, ARR, renewal dates, health scores and contacts.",
             [Field("token", "Private app access token", True, "pat-na1-…",
                    "Settings › Integrations › Private apps. Give it crm.objects.companies.read.")],
             "https://developers.hubspot.com/docs/api/private-apps", "Create a private app",
             _not_built("Importing HubSpot data"), verify_hubspot, sample=["hubspot"]),
    Provider("zendesk", "Zendesk", "Support", "#03363D", "api_key",
             "Customer tickets and who answered them.",
             [Field("subdomain", "Subdomain", False, "acme", "The part before .zendesk.com."),
              Field("email", "Agent email", False, "you@company.com"),
              Field("token", "API token", True, "", "Admin Center › Apps and integrations › Zendesk API.")],
             "https://support.zendesk.com/hc/en-us/articles/4408889192858", "Create an API token",
             _not_built("Importing Zendesk tickets"), verify_zendesk),
    Provider("intercom", "Intercom", "Support", "#1F1F1F", "api_key",
             "Conversations with customers and the admins who handled them.",
             [Field("token", "Access token", True, "", "Developer Hub › your app › Configure › Authentication.")],
             "https://developers.intercom.com/docs/build-an-integration/learn-more/authentication", "Get an access token",
             _not_built("Importing Intercom conversations"), verify_intercom),
    Provider("freshdesk", "Freshdesk", "Support", "#25C16F", "api_key",
             "Customer tickets, priorities and resolution times.",
             [Field("domain", "Domain", False, "acme", "The part before .freshdesk.com."),
              Field("api_key", "API key", True, "", "Profile settings › View API key.")],
             "https://support.freshdesk.com/support/solutions/articles/215517", "Find your API key",
             _not_built("Importing Freshdesk tickets"), verify_freshdesk),
    Provider("slack", "Slack", "Chat", "#4A154B", "api_key",
             "Channels and threads. With a bot, approved briefs post to your channel.",
             [Field("token", "Bot token", True, "xoxb-…",
                    "Create an app, add the chat:write scope, install it, then copy the Bot User OAuth Token."),
              Field("channel", "Default channel", False, "#customer-success",
                    "Where Relay posts approved briefs. Invite the bot to this channel.")],
             "https://api.slack.com/apps", "Create a Slack app",
             "When you approve a “Brief the CS channel” action, Relay posts it to Slack with this bot. "
             "Importing Slack history is not built yet; " + NOT_IMPORTED, verify_slack, sample=["slack"]),
    Provider("jira", "Jira", "Issues", "#0052CC", "api_key",
             "Issues, owners and resolved work. Relay can also create tasks here.",
             [Field("base_url", "Site URL", False, "https://your-team.atlassian.net"),
              Field("email", "Account email", False, "you@company.com"),
              Field("token", "API token", True, "", "Atlassian account › Security › API tokens."),
              Field("project", "Project key", False, "CS", "Relay creates approved tasks in this project.")],
             "https://id.atlassian.com/manage-profile/security/api-tokens", "Create an API token",
             "When you approve a handover ticket move or an Account Health task, Relay creates the issue in this "
             "project. Importing Jira history is not built yet; " + NOT_IMPORTED,
             verify_jira, store_as="jira_live", sample=["jira"]),
    Provider("linear", "Linear", "Issues", "#5E6AD2", "api_key",
             "Issues, projects and who resolves them.",
             [Field("api_key", "Personal API key", True, "lin_api_…", "Settings › Security & access › Personal API keys.")],
             "https://linear.app/settings/account/security", "Create an API key",
             "Relay checks and stores this key. Creating and importing Linear issues is not built yet.", verify_linear),
    Provider("confluence", "Confluence", "Docs", "#172B4D", "api_key",
             "Runbooks, RFCs and design docs, with freshness checks.",
             [Field("site", "Site URL", False, "https://your-team.atlassian.net"),
              Field("email", "Account email", False, "you@company.com"),
              Field("token", "API token", True, "", "Atlassian account › Security › API tokens.")],
             "https://id.atlassian.com/manage-profile/security/api-tokens", "Create an API token",
             _not_built("Importing Confluence pages"), verify_confluence, sample=["confluence"]),
    Provider("notion", "Notion", "Docs", "#000000", "api_key",
             "Team wikis and docs shared with the integration.",
             [Field("token", "Internal integration secret", True, "ntn_…", "Create an internal integration, then share pages with it.")],
             "https://www.notion.so/profile/integrations", "Create an integration",
             "Relay checks and stores this token. Importing Notion pages is not built yet.", verify_notion),
    Provider("github", "GitHub", "Code", "#181717", "api_key",
             "Commits and reviews: the strongest signal of who knows a system.",
             [Field("token", "Personal access token", True, "github_pat_…", "Fine-grained, read-only access to the repos you want.")],
             "https://github.com/settings/personal-access-tokens/new", "Create a token",
             _not_built("Importing commits from your organization"), verify_github, sample=["github"]),
    Provider("fireflies", "Fireflies", "Meetings", "#E8336D", "api_key",
             "Meeting transcripts where decisions and their reasons are recorded.",
             [Field("api_key", "API key", True, "", "Settings › Developer settings › API key.")],
             "https://app.fireflies.ai/settings", "Find your API key",
             _not_built("Importing Fireflies transcripts"), verify_fireflies),
    Provider("gong", "Gong", "Meetings", "#8039DF", "api_key",
             "Customer call recordings and transcripts.",
             [Field("access_key", "Access key", False, "", "Company settings › Ecosystem › API › Create."),
              Field("secret", "Access key secret", True),
              Field("base_url", "API base URL", False, "https://api.gong.io", "Only if Gong shows a different one.", True)],
             "https://help.gong.io/docs/receive-access-to-the-api", "Create an access key",
             _not_built("Importing Gong calls"), verify_gong),
    Provider("google", "Google Workspace", "Email & calendar", "#4285F4", "oauth",
             "Calendar events and Gmail drafts, after you approve them.",
             [Field("client_id", "OAuth client ID", False, "…apps.googleusercontent.com",
                    "Google Cloud › APIs & Services › Credentials › OAuth client ID (Web application)."),
              Field("client_secret", "OAuth client secret", True, "GOCSPX-…")],
             "https://console.cloud.google.com/apis/credentials", "Create an OAuth client",
             "When you approve a Day One intro or a customer email, Relay books the Calendar event or saves the Gmail "
             "draft in this Google account. It never sends email. Importing Meet notes is not built yet; " + NOT_IMPORTED,
             verify_google_client, store_as="google", sample=["meetings", "calendar"]),
]
BY_ID = {p.id: p for p in CATALOG}


# ------------------------------------------------------------------ state

def _stamp() -> str:
    """Wall-clock time (the app's now() is a demo clock), for "verified at"."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def _mark_verified(wid: str, provider: str) -> None:
    db.run("MATCH (c:Connection {provider: $p})-[:IN]->(:Workspace {id: $w}) SET c.verifiedAt = $at",
           {"p": provider, "w": wid, "at": _stamp()}, g=_g())


def mask(value: str | None) -> str:
    v = value or ""
    return "••••" + v[-4:] if len(v) > 8 else "••••"


def _rows(wid: str) -> dict[str, dict]:
    return workspaces._connection_rows(wid)


def _values(p: Provider, secret: dict) -> dict:
    """What the browser may see of stored fields: plain values, secrets masked."""
    out = {}
    for f in p.fields:
        v = secret.get(f.key)
        if v:
            out[f.key] = mask(v) if f.secret else v
    return out


def _sample_line(p: Provider, sample: dict[str, dict]) -> str | None:
    hits = [sample[s] for s in p.sample if s in sample]
    return " · ".join(h["demo"] for h in hits if h.get("demo")) if hits else None


def provider_view(p: Provider, rows: dict[str, dict], sample: dict[str, dict]) -> dict:
    view = {"id": p.id, "name": p.name, "category": p.category, "color": p.color, "auth": p.auth,
            "description": p.description, "fields": [f.view() for f in p.fields], "docs": p.docs,
            "docsLabel": p.docs_label, "uses": p.uses, "sample": _sample_line(p, sample),
            "connected": False, "account": None, "verifiedAt": None, "values": {}}
    if p.id == "google":
        client = rows.get("google_client") or {}
        auth = rows.get("google") or {}
        server_client = google_oauth.env_configured()
        view |= {"redirectUri": google_oauth.redirect_uri(), "serverClient": server_client,
                 "clientSaved": bool(client) or server_client, "clientAccount": client.get("account"),
                 "clientVerifiedAt": client.get("verifiedAt") or client.get("connectedAt"),
                 "values": _values(p, secretbox.open_sealed(client.get("secret"))) if client else {}}
        if auth.get("status") == "connected" and auth.get("mode") == "live":
            view |= {"connected": True, "account": auth.get("account"),
                     "verifiedAt": auth.get("verifiedAt") or auth.get("connectedAt")}
        return view
    row = rows.get(p.store_as) or {}
    if row.get("status") == "connected" and row.get("mode") == "live":
        view |= {"connected": True, "account": row.get("account"),
                 "verifiedAt": row.get("verifiedAt") or row.get("connectedAt"),
                 "values": _values(p, secretbox.open_sealed(row.get("secret")))}
    return view


def _sample(wid: str) -> dict[str, dict]:
    """The sample-data sources imported into this workspace (Connection rows with mode 'demo')."""
    return {c["id"]: c for c in workspaces.connections(wid)
            if c.get("kind") == "source" and c.get("mode") == "demo" and c.get("status") == "connected"}


def catalog(user_id: str, wid: str) -> dict:
    from . import tenants
    rows = _rows(wid)
    sample = _sample(wid)
    providers = [provider_view(p, rows, sample) for p in CATALOG]
    return {
        "company": tenants.for_graph(workspaces._workspace(wid)["graph"]).name,
        "canManage": workspaces.role_in(user_id, wid) in ("owner", "admin"),
        "sample": [{"id": s["id"], "name": s["name"], "size": s.get("demo")} for s in sample.values()],
        "categories": [{"name": c, "providers": [v for v in providers if v["category"] == c]} for c in CATEGORIES],
        "mcp": mcp_servers(wid),
    }


def connect(user_id: str, wid: str, provider: str, fields: dict[str, Any]) -> dict:
    """Verify with one live call, then store encrypted. Raises AuthError with the provider's reason on failure."""
    workspaces.require_admin(user_id, wid)
    p = BY_ID.get(provider)
    if not p:
        raise AuthError("Unknown connection", 404)
    clean = {f.key: str(fields.get(f.key) or "").strip() for f in p.fields}
    for f in p.fields:
        if not f.optional and not clean[f.key]:
            raise AuthError(f"Fill in {f.label.lower()}")
    if provider == "jira":
        # The existing Jira connection, which the live ticket actions read.
        workspaces.connect_jira(user_id, wid, clean["base_url"], clean["email"], clean["token"], clean["project"])
        _mark_verified(wid, p.store_as)
    else:
        result = p.verify(clean)
        if not result["ok"]:
            raise AuthError(result["detail"], 400)
        if provider == "slack":
            clean["channel"] = _channel(clean["channel"])
        elif provider in ("zendesk", "freshdesk"):
            key = "subdomain" if provider == "zendesk" else "domain"
            clean[key] = _subdomain(clean[key], f".{provider}.com")
        elif provider == "confluence":
            clean["site"] = _https_site(clean["site"], "https://your-team.atlassian.net")
        store = "google_client" if provider == "google" else p.store_as
        workspaces._store(wid, store, {k: v for k, v in clean.items() if v}, result["account"], user_id)
        _mark_verified(wid, store)
        if provider == "google":
            # A new client invalidates any account authorized through the old one.
            db.run("MATCH (c:Connection {provider: 'google'})-[:IN]->(:Workspace {id: $w}) DETACH DELETE c", {"w": wid}, g=_g())
    return provider_view(p, _rows(wid), _sample(wid))


def disconnect(user_id: str, wid: str, provider: str) -> None:
    workspaces.require_admin(user_id, wid)
    p = BY_ID.get(provider)
    if not p:
        raise AuthError("Unknown connection", 404)
    keys = ["google", "google_client"] if provider == "google" else [p.store_as]
    db.run("""MATCH (c:Connection)-[:IN]->(:Workspace {id: $w})
              WHERE c.provider IN $keys AND c.mode = 'live' DETACH DELETE c""", {"w": wid, "keys": keys}, g=_g())


# ------------------------------------------------------------------ MCP servers

def mcp_servers(wid: str) -> list[dict]:
    rows = db.rows("MATCH (m:McpServer)-[:IN]->(:Workspace {id: $w}) RETURN m ORDER BY m.addedAt",
                   {"w": wid}, g=_g(), readonly=True)
    out = []
    for r in rows:
        m = r["m"]
        tok = secretbox.open_sealed(m.get("secret")).get("token")
        out.append({"id": m["id"], "name": m["name"], "url": m["url"], "transport": m.get("transport"),
                    "tools": json.loads(m.get("tools") or "[]"), "server": m.get("serverName"),
                    "token": mask(tok) if tok else None, "verifiedAt": m.get("addedAt")})
    return out


def _mcp_url(raw: str) -> tuple[str, str]:
    url = (raw or "").strip()
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.netloc:
        raise AuthError("Use the server's full URL, like https://example.com/mcp")
    _public_host(u.hostname or "")
    transport = "sse" if u.path.rstrip("/").endswith("/sse") else "streamable-http"
    return url, transport


async def list_mcp_tools(url: str, token: str | None = None, timeout: float = 15.0) -> tuple[str, list[dict], str | None]:
    """Connect to an MCP server over HTTP, list its tools. Returns (transport, tools, server name)."""
    import httpx2
    from mcp import Client
    from mcp.client.sse import sse_client
    from mcp.client.streamable_http import streamable_http_client

    url, transport = _mcp_url(url)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with anyio.fail_after(timeout):
        if transport == "sse":
            client = Client(sse_client(url, headers=headers, timeout=timeout))
            async with client as c:
                res = await c.list_tools()
                info = getattr(c, "server_info", None)
        else:
            http = httpx2.AsyncClient(headers=headers, timeout=httpx2.Timeout(timeout))
            async with http, Client(streamable_http_client(url, http_client=http)) as c:
                res = await c.list_tools()
                info = getattr(c, "server_info", None)
    tools = [{"name": t.name, "description": (t.description or "").strip().split("\n")[0][:160]} for t in res.tools]
    return transport, tools, getattr(info, "name", None)


def _mcp_error(e: BaseException) -> str:
    while isinstance(e, BaseExceptionGroup) and e.exceptions:
        e = e.exceptions[0]
    if isinstance(e, TimeoutError):
        return "The server did not answer within 15 seconds."
    text = str(e).strip() or e.__class__.__name__
    if "401" in text or "403" in text:
        return f"The server refused the connection ({text[:140]}). Check the bearer token."
    return f"Couldn't connect: {text[:200]}"


async def add_mcp(user_id: str, wid: str, name: str, url: str, token: str | None) -> dict:
    workspaces.require_admin(user_id, wid)
    name = (name or "").strip()
    if not name:
        raise AuthError("Give the server a name")
    token = (token or "").strip() or None
    try:
        transport, tools, server_name = await list_mcp_tools(url, token)
    except AuthError:
        raise
    except BaseException as e:   # connection errors arrive as exception groups from anyio
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise
        raise AuthError(_mcp_error(e), 400) from None
    mid = "mcp-" + uuid.uuid4().hex[:10]
    db.run("""MATCH (w:Workspace {id: $w})
              CREATE (:McpServer {id: $id, name: $name, url: $url, transport: $transport, tools: $tools,
                                  serverName: $server, secret: $secret, addedAt: $at, addedBy: $by})-[:IN]->(w)""",
           {"w": wid, "id": mid, "name": name[:60], "url": url.strip(), "transport": transport,
            "tools": json.dumps(tools), "server": server_name, "secret": secretbox.seal({"token": token}) if token else None,
            "at": _stamp(), "by": user_id}, g=_g())
    return next(m for m in mcp_servers(wid) if m["id"] == mid)


def remove_mcp(user_id: str, wid: str, mid: str) -> None:
    workspaces.require_admin(user_id, wid)
    db.run("MATCH (m:McpServer {id: $id})-[:IN]->(:Workspace {id: $w}) DETACH DELETE m", {"id": mid, "w": wid}, g=_g())


def mcp_uses() -> str:
    return ("Relay connects to the server, lists its tools and stores them. Relay's agents do not call tools on "
            "added servers yet.")
