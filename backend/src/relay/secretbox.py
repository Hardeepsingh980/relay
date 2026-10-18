"""Encrypt connection credentials at rest (Fernet, key from RELAY_SECRET_KEY)."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from .config import CACHE_DIR


@lru_cache
def _fernet() -> Fernet:
    raw = os.getenv("RELAY_SECRET_KEY")
    if not raw:
        # Local development: a generated key in the git-ignored cache directory.
        path = CACHE_DIR / "secret.key"
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(secrets.token_urlsafe(48))
            path.chmod(0o600)
        raw = path.read_text().strip()
    key = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())
    return Fernet(key)


def seal(data: dict) -> str:
    return _fernet().encrypt(json.dumps(data).encode()).decode()


def open_sealed(token: str | None) -> dict:
    if not token:
        return {}
    try:
        return json.loads(_fernet().decrypt(token.encode()))
    except (InvalidToken, ValueError):
        return {}
