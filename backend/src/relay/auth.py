"""Accounts and sessions.

Accounts live in their own FalkorDB graph (`<graph>_accounts`), so resetting the
demo workspace never signs anyone out. Passwords are hashed with scrypt and a
per-user salt. Session tokens are random, sent as an HTTP-only cookie, and
stored only as SHA-256 hashes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import timedelta
from functools import lru_cache

from falkordb import Graph

from . import db
from .config import now, settings

COOKIE = "relay_session"
SESSION_DAYS = 14
MIN_PASSWORD = 8
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}
_FAILS: dict[str, deque] = defaultdict(deque)
_FAIL_WINDOW = 15 * 60
_FAIL_LIMIT = 5
_lock = threading.Lock()


class AuthError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@lru_cache
def _g() -> Graph:
    g = db.graph(settings().graph_name + "_accounts")
    for label, prop in (("User", "id"), ("User", "email"), ("Session", "tokenHash")):
        try:
            g.query(f"CREATE INDEX FOR (n:{label}) ON (n.{prop})")
        except Exception:
            pass
    return g


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, dk = stored.split("$")
        got = hashlib.scrypt(password.encode(), salt=_unb64(salt), n=int(n), r=int(r), p=int(p), dklen=len(_unb64(dk)))
        return hmac.compare_digest(got, _unb64(dk))
    except Exception:
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def public(u: dict) -> dict:
    return {"id": u["id"], "name": u["name"], "email": u["email"], "createdAt": u.get("createdAt"),
            "avatarUrl": u.get("avatarUrl"), "sandbox": bool(u.get("sandbox"))}


def _user_by_email(email: str) -> dict | None:
    r = db.rows("MATCH (u:User {email: $e}) RETURN u", {"e": email.lower()}, g=_g(), readonly=True)
    return r[0]["u"] if r else None


def sign_up(name: str, email: str, password: str) -> dict:
    name, email = (name or "").strip(), (email or "").strip().lower()
    if len(name) < 2:
        raise AuthError("Please enter your name")
    if not _EMAIL_RE.match(email):
        raise AuthError("Please enter a valid email address")
    if len(password or "") < MIN_PASSWORD:
        raise AuthError(f"Use at least {MIN_PASSWORD} characters for your password")
    with _lock:
        if _user_by_email(email):
            raise AuthError("An account with this email already exists. Try signing in.", 409)
        user = {"id": "u-" + uuid.uuid4().hex[:12], "name": name, "email": email, "hash": hash_password(password),
                "at": now().isoformat(timespec="seconds")}
        db.run("""CREATE (:User {id: $id, name: $name, email: $email, passwordHash: $hash, createdAt: $at})""",
               user, g=_g())
    return public(_user_by_email(email))


def _rate_limited(key: str) -> bool:
    q = _FAILS[key]
    cutoff = time.monotonic() - _FAIL_WINDOW
    while q and q[0] < cutoff:
        q.popleft()
    return len(q) >= _FAIL_LIMIT


def sign_in(email: str, password: str) -> dict:
    email = (email or "").strip().lower()
    if _rate_limited(email):
        raise AuthError("Too many attempts. Wait a few minutes and try again.", 429)
    u = _user_by_email(email)
    # Same message (and a hash either way) whether or not the account exists.
    ok = verify_password(password or "", u["passwordHash"] if u and u.get("passwordHash") else hash_password("x" * 12))
    if u and not u.get("passwordHash") and u.get("googleSub"):
        raise AuthError("This account uses Google sign-in. Continue with Google instead.", 401)
    if not u or not ok:
        _FAILS[email].append(time.monotonic())
        raise AuthError("That email and password don't match", 401)
    _FAILS.pop(email, None)
    return public(u)


def create_session(user_id: str, user_agent: str | None = None) -> tuple[str, int]:
    token = secrets.token_urlsafe(32)
    ttl = int(timedelta(days=SESSION_DAYS).total_seconds())
    db.run("""MATCH (u:User {id: $uid})
              CREATE (u)<-[:FOR]-(:Session {tokenHash: $h, createdAt: $at, expiresAt: $exp, userAgent: $ua})""",
           {"uid": user_id, "h": _token_hash(token), "at": now().isoformat(timespec="seconds"),
            "exp": time.time() + ttl, "ua": (user_agent or "")[:200]}, g=_g())
    return token, ttl


def session_context(token: str | None) -> tuple[dict, str | None] | None:
    """(user, workspace id chosen for this session) for a valid token."""
    if not token:
        return None
    r = db.rows("""MATCH (s:Session {tokenHash: $h})-[:FOR]->(u:User) WHERE s.expiresAt > $now
                   RETURN u, s.workspaceId AS ws""", {"h": _token_hash(token), "now": time.time()}, g=_g(), readonly=True)
    return (public(r[0]["u"]), r[0]["ws"]) if r else None


def user_for_token(token: str | None) -> dict | None:
    ctx = session_context(token)
    return ctx[0] if ctx else None


def set_session_workspace(token: str | None, wid: str) -> None:
    if token:
        db.run("MATCH (s:Session {tokenHash: $h}) SET s.workspaceId = $w", {"h": _token_hash(token), "w": wid}, g=_g())


def upsert_google_user(sub: str, email: str, name: str | None, picture: str | None) -> dict:
    """Find the account for a Google identity (linking by verified email), or create one."""
    email = email.lower()
    with _lock:
        r = db.rows("MATCH (u:User) WHERE u.googleSub = $sub OR u.email = $email RETURN u",
                    {"sub": sub, "email": email}, g=_g(), readonly=True)
        if r:
            u = r[0]["u"]
            db.run("""MATCH (u:User {id: $id}) SET u.googleSub = $sub, u.avatarUrl = coalesce($pic, u.avatarUrl)""",
                   {"id": u["id"], "sub": sub, "pic": picture}, g=_g())
        else:
            db.run("""CREATE (:User {id: $id, name: $name, email: $email, googleSub: $sub, avatarUrl: $pic,
                      createdAt: $at})""",
                   {"id": "u-" + uuid.uuid4().hex[:12], "name": name or email.split("@")[0], "email": email,
                    "sub": sub, "pic": picture, "at": now().isoformat(timespec="seconds")}, g=_g())
    return public(_user_by_email(email))


def revoke(token: str | None) -> None:
    if token:
        db.run("MATCH (s:Session {tokenHash: $h}) DELETE s", {"h": _token_hash(token)}, g=_g())


def cookie_secure() -> bool:
    return os.getenv("RELAY_COOKIE_SECURE", "false").lower() in ("1", "true", "yes")
