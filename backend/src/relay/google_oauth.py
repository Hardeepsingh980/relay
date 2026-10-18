"""Google OAuth 2.0 (authorization code flow) for sign-in and for connecting Calendar/Gmail.

Configured with GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET. When those are absent, a
workspace can save its own client in Settings › Connections (stored encrypted as the
`google_client` connection); it is then used to connect that workspace's Google account.
The redirect URI to register in Google Cloud is `<RELAY_API_PUBLIC_URL>/api/auth/google/callback`.
"""

from __future__ import annotations

import os
import secrets
import threading
import time
from contextvars import ContextVar
from urllib.parse import urlencode

import httpx

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
SIGN_IN_SCOPES = "openid email profile"
CONNECT_SCOPES = ("openid email https://www.googleapis.com/auth/calendar.events "
                  "https://www.googleapis.com/auth/gmail.compose")
STATE_TTL = 600

_states: dict[str, dict] = {}
_lock = threading.Lock()
# The workspace of the OAuth flow being completed (set by take_state, read by exchange).
_flow_workspace: ContextVar[str | None] = ContextVar("google_oauth_workspace", default=None)


def env_configured() -> bool:
    return bool(os.getenv("GOOGLE_OAUTH_CLIENT_ID") and os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"))


def client(workspace_id: str | None = None) -> tuple[str, str] | None:
    """(client_id, client_secret): the server's env vars, else the workspace's saved client."""
    if env_configured():
        return os.environ["GOOGLE_OAUTH_CLIENT_ID"], os.environ["GOOGLE_OAUTH_CLIENT_SECRET"]
    from . import db, workspaces
    wid = workspace_id or db.current_workspace_id()
    c = workspaces.secret(wid, "google_client") if wid else {}
    return (c["client_id"], c["client_secret"]) if c.get("client_id") and c.get("client_secret") else None


def configured() -> bool:
    return client() is not None


def api_url() -> str:
    return os.getenv("RELAY_API_PUBLIC_URL", "http://localhost:8020").rstrip("/")


def redirect_uri() -> str:
    return f"{api_url()}/api/auth/google/callback"


def start(purpose: str, **ctx) -> str:
    """Authorization URL for `purpose` ('sign-in' or 'connect'), remembering ctx under a one-time state."""
    state = secrets.token_urlsafe(24)
    with _lock:
        now = time.time()
        for k in [k for k, v in _states.items() if v["at"] < now - STATE_TTL]:
            del _states[k]
        _states[state] = {"purpose": purpose, "at": now, **ctx}
    params = {
        "client_id": client(ctx.get("workspace"))[0], "redirect_uri": redirect_uri(), "response_type": "code",
        "scope": SIGN_IN_SCOPES if purpose == "sign-in" else CONNECT_SCOPES, "state": state,
        "include_granted_scopes": "true", "prompt": "select_account" if purpose == "sign-in" else "consent",
    }
    if purpose == "connect":
        params["access_type"] = "offline"
    return f"{AUTH_URL}?{urlencode(params)}"


def take_state(state: str | None) -> dict | None:
    with _lock:
        s = _states.pop(state or "", None)
    _flow_workspace.set((s or {}).get("workspace"))
    return s if s and s["at"] > time.time() - STATE_TTL else None


def exchange(code: str) -> dict:
    cid, secret = client(_flow_workspace.get())
    r = httpx.post(TOKEN_URL, data={
        "code": code, "client_id": cid, "client_secret": secret, "redirect_uri": redirect_uri(),
        "grant_type": "authorization_code"}, timeout=15)
    r.raise_for_status()
    return r.json()


def userinfo(access_token: str) -> dict:
    r = httpx.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=15)
    r.raise_for_status()
    return r.json()


def refresh(refresh_token: str) -> str:
    cid, secret = client()
    r = httpx.post(TOKEN_URL, data={
        "client_id": cid, "client_secret": secret,
        "refresh_token": refresh_token, "grant_type": "refresh_token"}, timeout=15)
    r.raise_for_status()
    return r.json()["access_token"]
