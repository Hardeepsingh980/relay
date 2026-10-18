"""Runtime settings, read once from the environment (and the repo-root .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "backend"
CACHE_DIR = REPO_ROOT / ".cache"

load_dotenv(REPO_ROOT / ".env")

IST = timezone(timedelta(hours=5, minutes=30))

# The demo world is frozen at this moment: Monday of Rahul's last week (both sample companies).
# Expertise decay, "days ago" labels and handover dates are all relative to it.
DEMO_NOW = datetime(2026, 10, 19, 9, 30, tzinfo=IST)
_BOOT = datetime.now(IST)


def now() -> datetime:
    """Demo clock: starts at DEMO_NOW when the process boots and runs forward in real time."""
    return DEMO_NOW + (datetime.now(IST) - _BOOT)


@dataclass(frozen=True)
class Settings:
    falkor_host: str
    falkor_port: int
    graph_name: str
    gemini_api_key: str | None
    llm_model: str
    embed_model: str
    extractor: str  # "gemini" | "seed"
    cors_origins: tuple[str, ...]

    @property
    def llm_enabled(self) -> bool:
        return bool(self.gemini_api_key)


@lru_cache
def settings() -> Settings:
    key = os.getenv("GEMINI_API_KEY") or None
    # Seed annotations by default: deterministic and matches the planted story exactly.
    # Gemini extraction is opt-in (RELAY_EXTRACTOR=gemini or `relay build --extractor gemini`).
    extractor = os.getenv("RELAY_EXTRACTOR", "seed")
    origins = os.getenv("RELAY_CORS_ORIGINS", "http://localhost:3025,http://127.0.0.1:3025")
    return Settings(
        falkor_host=os.getenv("FALKORDB_HOST", "localhost"),
        falkor_port=int(os.getenv("FALKORDB_PORT", "6395")),
        graph_name=os.getenv("RELAY_GRAPH", "cheerio"),
        gemini_api_key=key,
        llm_model=os.getenv("RELAY_LLM_MODEL", "gemini-3.8-flash"),
        embed_model=os.getenv("RELAY_EMBED_MODEL", "gemini-embedding-2"),
        extractor=extractor,
        cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
    )
