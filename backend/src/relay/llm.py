"""Gemini access with a durable response cache.

Every call is keyed by (model, prompt, schema) and cached in SQLite, so a demo
replays identical answers and a rebuild never pays twice. Without an API key
`available()` is False and callers use their deterministic fallbacks.
"""

from __future__ import annotations

import hashlib
import json
import os
import logging
import sqlite3
import threading
import time
from functools import lru_cache
from typing import Any, TypeVar

from pydantic import BaseModel

from .config import CACHE_DIR, settings

log = logging.getLogger("relay.llm")
T = TypeVar("T", bound=BaseModel)


class LLMUnavailable(RuntimeError):
    pass


_lock = threading.Lock()


@lru_cache
def _db() -> sqlite3.Connection:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CACHE_DIR / "llm.sqlite", check_same_thread=False)
    conn.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    return conn


def _get(key: str) -> str | None:
    with _lock:
        row = _db().execute("SELECT value FROM cache WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def _put(key: str, value: str) -> None:
    with _lock:
        _db().execute("INSERT OR REPLACE INTO cache (key, value) VALUES (?, ?)", (key, value))
        _db().commit()


_client_lock = threading.Lock()
_client_instance = None


def _client(fresh: bool = False):
    """One shared Gemini client, created under a lock (concurrent creation let one get closed)."""
    global _client_instance
    with _client_lock:
        if _client_instance is None or fresh:
            from google import genai
            _client_instance = genai.Client(api_key=settings().gemini_api_key)
        return _client_instance


def available() -> bool:
    return settings().llm_enabled


def cached_only(prompt: str, schema: type[T], system: str | None = None, model: str | None = None) -> T | None:
    """Return a cached response without calling the API (for fallbacks)."""
    key = _key(model or settings().llm_model, system, prompt, schema)
    hit = _get(key)
    return schema.model_validate_json(hit) if hit else None


def _key(model: str, system: str | None, prompt: str, schema: type[BaseModel] | None) -> str:
    raw = json.dumps([model, system, prompt, schema.model_json_schema() if schema else None], sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def generate(prompt: str, schema: type[T], *, system: str | None = None, model: str | None = None,
             thinking: str = "low", cache: bool | None = None) -> T:
    """Structured JSON generation validated against a pydantic model.

    Only graph builds replay cached responses (`cache=True`), so a rebuild is repeatable. Anything a person
    asks or triggers in the app is a live model call, unless RELAY_LLM_CACHE=all (offline development).
    """
    model = model or settings().llm_model
    key = _key(model, system, prompt, schema)
    use_cache = cache if cache is not None else os.getenv("RELAY_LLM_CACHE", "build") == "all"
    hit = _get(key) if use_cache else None
    if hit:
        return schema.model_validate_json(hit)
    if not available():
        raise LLMUnavailable("GEMINI_API_KEY is not set")
    from google.genai import types
    config = types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json",
        response_json_schema=schema.model_json_schema(),
        thinking_config=types.ThinkingConfig(thinking_level=thinking.upper()),
    )
    last: Exception | None = None
    for attempt in range(4):
        try:
            resp = _client(fresh=attempt > 0 and "closed" in str(last)).models.generate_content(
                model=model, contents=prompt, config=config)
            parsed = schema.model_validate_json(resp.text or "")
            break
        except Exception as e:  # network, quota, malformed JSON: retry with backoff
            last = e
            time.sleep(1.5 * (2 ** attempt))
    else:
        log.warning("Gemini call failed after retries: %s", last)
        raise LLMUnavailable(str(last)) from last
    _put(key, parsed.model_dump_json())
    return parsed


def embed(texts: list[str], *, task: str = "RETRIEVAL_DOCUMENT", dims: int = 768) -> list[list[float]]:
    model = settings().embed_model
    out: list[list[float] | None] = [None] * len(texts)
    missing = []
    for i, t in enumerate(texts):
        hit = _get(_key(model, task, f"{dims}:{t}", None))
        if hit:
            out[i] = json.loads(hit)
        else:
            missing.append(i)
    if missing:
        if not available():
            raise LLMUnavailable("GEMINI_API_KEY is not set")
        from google.genai import types
        for start in range(0, len(missing), 50):
            chunk = missing[start:start + 50]
            try:
                resp = _client().models.embed_content(
                    model=model, contents=[texts[i] for i in chunk],
                    config=types.EmbedContentConfig(task_type=task, output_dimensionality=dims))
            except Exception as e:
                raise LLMUnavailable(str(e)) from e
            for i, emb in zip(chunk, resp.embeddings):
                out[i] = list(emb.values)
                _put(_key(model, task, f"{dims}:{texts[i]}", None), json.dumps(out[i]))
    return [o for o in out if o is not None]


def status() -> dict[str, Any]:
    s = settings()
    return {"enabled": available(), "model": s.llm_model, "embedModel": s.embed_model, "extractor": s.extractor}
