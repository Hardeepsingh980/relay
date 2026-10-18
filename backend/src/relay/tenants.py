"""Sample companies Relay can be built from. Each tenant gets its own, isolated graph.

    cheerio  WhatsApp marketing SaaS (fictional people and customers) - the main demo
    lumen    a fictional fintech - the second tenant, to show graphs side by side

A workspace graph name always starts with its tenant id (`cheerio`, `cheerio_base`,
`cheerio_ws_<id>`), so any request can tell which tenant it is on.
"""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import ModuleType

from .config import REPO_ROOT


@dataclass(frozen=True)
class Tenant:
    id: str
    name: str
    tagline: str
    seed_module: str

    @property
    def data_dir(self) -> Path:
        return REPO_ROOT / "data" / self.id

    @property
    def graph(self) -> str:
        return self.id

    @property
    def base_graph(self) -> str:
        return self.id + "_base"

    @property
    def world(self) -> ModuleType:
        return importlib.import_module(f"relay.seed.{self.seed_module}.world")

    def generator(self) -> ModuleType:
        return importlib.import_module(f"relay.seed.{self.seed_module}.generate")


TENANTS = {
    "cheerio": Tenant("cheerio", "Cheerio", "WhatsApp marketing & commerce platform", "cheerio"),
    "lumen": Tenant("lumen", "Lumen", "Payments fintech", "lumen"),
}


def default_id() -> str:
    return os.getenv("RELAY_TENANT", "cheerio")


def get(tid: str | None = None) -> Tenant:
    return TENANTS[tid or default_id()]


@lru_cache(maxsize=256)
def for_graph(graph_name: str) -> Tenant:
    """The tenant a graph belongs to, from its name prefix."""
    head = graph_name.split("_", 1)[0]
    return TENANTS.get(head) or get()


def current() -> Tenant:
    from . import db
    return for_graph(db.current_graph_name())
