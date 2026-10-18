"""Repo knowledge: who knows what in any public GitHub repository, on real data.

A job clones the repository (bare, blobless, last two years), parses `git log`,
writes Person / Module / Commit nodes into a graph of its own (`repo_<owner>_<repo>`)
and then lets Cypher do the work: decayed expertise per person and module, bus
factor, modules only one person knows, the departure preview and PageRank
centrality over a co-work projection. Every query keeps its Cypher text and
timing so the UI can show it.

Jobs run in background threads (at most two at a time). Their metadata and the
finished summary are kept in memory and in one JSON file per job under
`.cache/repos/`, so finished analyses survive a restart.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from . import db, llm
from .config import CACHE_DIR, settings

log = logging.getLogger("relay.repos")

# ---------------------------------------------------------------- limits and thresholds

MAX_COMMITS = 3000
CLONE_TIMEOUT_S = 90
LOG_TIMEOUT_S = 60
MAX_CLONE_BYTES = 300 * 1024 * 1024
FRESH_FOR_S = 6 * 3600
MAX_RUNNING = 2
MAX_WAITING = 8
HALF_LIFE_DAYS = 120.0
SATURATION = 4.0          # score = 1 - exp(-raw / SATURATION)
STRONG = 0.6              # strong link
CREDIBLE = 0.35           # credible alternate
MODULE_ROWS = 300
PEOPLE_ROWS = 150

RUNNING = ("queued", "cloning", "parsing", "scoring")
SOURCE_ROOTS = {"src", "lib", "packages", "apps", "services", "backend", "frontend"}
IGNORED_DIRS = {"node_modules", "vendor", "dist", "build", "__pycache__", "bower_components", ".yarn"}
IGNORED_FILES = {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "go.sum", "npm-shrinkwrap.json"}
IGNORED_SUFFIXES = (".lock", ".min.js", ".min.css", ".js.map", ".css.map")
BOT_NAMES = {"dependabot", "renovate", "renovate bot", "github-actions", "github actions", "pre-commit-ci",
             "greenkeeper", "snyk bot", "imgbot", "allcontributors", "semantic-release-bot", "copilot", "github"}
GENERIC_NAMES = {"", "unknown", "root", "user", "admin", "ubuntu", "your name", "none", "anonymous"}
_BOT_EMAIL = re.compile(r"\[bot\]|(^|[-_.+])bot@|^noreply@github\.com$|^actions?@github\.com$|^github-actions@"
                        r"|^bot@|copilot@users\.noreply\.github\.com$")
_GITHUB = re.compile(r"^https://github\.com/([A-Za-z0-9][A-Za-z0-9-]{0,38})/([A-Za-z0-9._-]{1,100}?)(?:\.git)?/?$")


class RepoError(Exception):
    """A failure we can explain to the person (bad URL, not found, too large, no history)."""


class Busy(RepoError):
    pass


# ---------------------------------------------------------------- source URL


@dataclass(frozen=True)
class Source:
    owner: str
    name: str
    clone_url: str
    web_url: str

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def graph(self) -> str:
        return graph_name(self.owner, self.name)


def graph_name(owner: str, name: str) -> str:
    return ("repo_" + re.sub(r"[^a-z0-9]+", "_", f"{owner}_{name}".lower()).strip("_"))[:120]


def parse_source(url: str) -> Source:
    """Only `https://github.com/<owner>/<repo>` (optional .git or /). Local paths only for tests."""
    url = (url or "").strip()
    m = _GITHUB.match(url)
    if m:
        owner, name = m.group(1), m.group(2)
        if name in (".", "..") or name.endswith(".git"):
            raise RepoError("Use a GitHub repository URL like https://github.com/owner/repo")
        return Source(owner, name, f"https://github.com/{owner}/{name}.git", f"https://github.com/{owner}/{name}")
    if os.getenv("RELAY_REPOS_ALLOW_LOCAL") == "1" and (url.startswith("file://") or os.path.isabs(url)):
        path = Path(url.removeprefix("file://")).resolve()
        if not path.is_dir():
            raise RepoError(f"No local repository at {path}")
        return Source("local", path.name, path.as_uri(), path.as_uri())
    raise RepoError("Use a public GitHub repository URL like https://github.com/owner/repo")


# ---------------------------------------------------------------- git


def _git_env() -> dict[str, str]:
    """No prompts, no credential helpers and no user/system config (no insteadOf rewrites to SSH):
    only anonymous access to public repositories."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="", SSH_ASKPASS="", GCM_INTERACTIVE="never",
               GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, LC_ALL="C")
    return env


_GIT = ["git", "-c", "credential.helper=", "-c", "core.askPass=", "-c", "protocol.version=2"]
_NOT_FOUND = ("repository not found", "could not read username", "terminal prompts disabled", "authentication failed",
              "does not appear to be a git repository", "not found", "access denied")


def _dir_size(path: str) -> int:
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return total


class _CloneFailed(Exception):
    def __init__(self, stderr: str):
        super().__init__(stderr)
        self.stderr = stderr


def _clone_once(src: Source, dest: str, *, shallow_since: bool, deadline: float, on: Callable) -> None:
    args = [*_GIT, "clone", "--bare", "--filter=blob:none", "--single-branch", "--no-tags", "--quiet"]
    args.append("--shallow-since=2 years ago" if shallow_since else f"--depth={MAX_COMMITS + 1}")
    args += ["--", src.clone_url, dest]
    with tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=err, env=_git_env())
        t0 = time.monotonic()
        try:
            while proc.poll() is None:
                time.sleep(0.4)
                size = _dir_size(dest) if os.path.isdir(dest) else 0
                on("cloning", f"Cloning {src.slug}", mb=round(size / 1e6, 1), seconds=round(time.monotonic() - t0))
                if size > MAX_CLONE_BYTES:
                    raise RepoError("This repository is too large to analyze here (more than 300 MB of history).")
                if time.monotonic() > deadline:
                    raise RepoError("Cloning took longer than 90 seconds. Try a smaller repository.")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        if proc.returncode != 0:
            err.seek(0)
            raise _CloneFailed(err.read().decode("utf-8", "replace")[-2000:])


def _fetch(src: Source, dest: str, on: Callable) -> bool:
    """Clone the last two years; fall back to the newest commits for a quiet repository.
    Returns True when the fallback was used."""
    deadline = time.monotonic() + CLONE_TIMEOUT_S
    try:
        _clone_once(src, dest, shallow_since=True, deadline=deadline, on=on)
        return False
    except _CloneFailed as e:
        low = e.stderr.lower()
        if any(s in low for s in _NOT_FOUND):
            raise RepoError("GitHub says this repository does not exist or is not public.") from None
        log.info("shallow-since clone of %s failed, retrying without it: %s", src.slug, e.stderr.strip()[:300])
    shutil.rmtree(dest, ignore_errors=True)
    try:
        _clone_once(src, dest, shallow_since=False, deadline=deadline, on=on)
    except _CloneFailed as e:
        raise RepoError(f"git could not clone this repository: {e.stderr.strip().splitlines()[-1][:200] if e.stderr.strip() else 'unknown error'}") from None
    return True


LOG_FORMAT = "%x1e%H%x1f%an%x1f%ae%x1f%at%x1f%s"


def _git_log(gitdir: str) -> str:
    args = [*_GIT, "-c", "core.quotePath=false", "--git-dir", gitdir, "log", "--no-merges", "--no-renames",
            f"-n{MAX_COMMITS}", f"--pretty=format:{LOG_FORMAT}", "--name-only"]
    env = _git_env() | {"GIT_NO_LAZY_FETCH": "1"}   # a blobless clone must never fetch file contents here
    try:
        r = subprocess.run(args, capture_output=True, timeout=LOG_TIMEOUT_S, env=env, check=False)
    except subprocess.TimeoutExpired:
        raise RepoError("Reading the commit history took too long.") from None
    if r.returncode != 0:
        msg = r.stderr.decode("utf-8", "replace")
        if "does not have any commits" in msg or "bad default revision" in msg:
            raise RepoError("This repository has no commits.")
        raise RepoError(f"git log failed: {msg.strip()[:200]}")
    return r.stdout.decode("utf-8", "replace")


def _shallow_boundary(gitdir: str) -> set[str]:
    """Commits whose parents were cut off by the shallow clone: their file lists would show the whole tree."""
    p = Path(gitdir) / "shallow"
    return set(p.read_text().split()) if p.exists() else set()


# ---------------------------------------------------------------- parsing


@dataclass
class RawCommit:
    sha: str
    name: str
    email: str
    t: int
    subject: str
    files: list[str]


def parse_log(text: str) -> list[RawCommit]:
    out = []
    for chunk in text.split("\x1e"):
        if not chunk.strip():
            continue
        lines = chunk.split("\n")
        head = lines[0].split("\x1f")
        if len(head) < 5:
            continue
        try:
            t = int(head[3])
        except ValueError:
            continue
        files = [ln.rstrip("\r") for ln in lines[1:] if ln.strip()]
        out.append(RawCommit(head[0].strip(), head[1].strip(), head[2].strip(), t, "\x1f".join(head[4:]).strip(), files))
    return out


def module_of(path: str) -> str | None:
    """First two segments under a common source root, else the first segment; root files go to (root).
    None for lockfiles, vendored and generated paths."""
    parts = [p for p in path.strip().strip('"').split("/") if p]
    if not parts:
        return None
    base = parts[-1].lower()
    if base in IGNORED_FILES or base.endswith(IGNORED_SUFFIXES):
        return None
    if any(p.lower() in IGNORED_DIRS for p in parts[:-1]):
        return None
    if len(parts) == 1:
        return "(root)"
    if parts[0].lower() in SOURCE_ROOTS and len(parts) >= 3:
        return f"{parts[0]}/{parts[1]}"
    return parts[0]


def is_bot(name: str, email: str) -> bool:
    n, e = name.strip().lower(), email.strip().lower()
    if n.endswith(("[bot]", " bot", "-bot")) or n in BOT_NAMES:
        return True
    return bool(_BOT_EMAIL.search(e))


def _norm_name(name: str) -> str:
    return " ".join(name.lower().split())


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:24] or "person"


@dataclass
class Dataset:
    people: list[dict] = field(default_factory=list)
    modules: list[dict] = field(default_factory=list)
    commits: list[dict] = field(default_factory=list)
    touches: list[dict] = field(default_factory=list)
    skipped: dict = field(default_factory=dict)


def build_dataset(raw: list[RawCommit], boundary: set[str] = frozenset()) -> Dataset:
    """Filter bots and generated files, merge identities (same email or same display name), map modules."""
    skipped = Counter(read=len(raw))
    kept: list[tuple[RawCommit, dict[str, int]]] = []
    for c in raw:
        if c.sha in boundary:
            skipped["boundary"] += 1
            continue
        if is_bot(c.name, c.email):
            skipped["bots"] += 1
            continue
        mods = Counter(m for m in (module_of(f) for f in c.files) if m)
        if not mods:
            skipped["noSourceFiles"] += 1
            continue
        kept.append((c, dict(mods)))

    # Union-find over identity keys: an email and a display name seen on one commit are one person.
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    def keys(c: RawCommit) -> list[str]:
        ks = []
        if c.email:
            ks.append("e:" + c.email.lower())
        if _norm_name(c.name) not in GENERIC_NAMES:
            ks.append("n:" + _norm_name(c.name))
        return ks or ["n:unknown"]

    for c, _ in kept:
        ks = keys(c)
        for k in ks[1:]:
            union(ks[0], k)

    groups: dict[str, dict] = {}
    for c, _ in kept:
        root = find(keys(c)[0])
        g = groups.setdefault(root, {"names": Counter(), "emails": Counter()})
        g["names"][c.name or "Unknown"] += 1
        if c.email:
            g["emails"][c.email.lower()] += 1

    person_of: dict[str, str] = {}
    people = []
    used: set[str] = set()
    for root, g in groups.items():
        name = g["names"].most_common(1)[0][0]
        email = g["emails"].most_common(1)[0][0] if g["emails"] else ""
        pid = f"{_slug(name)}-{hashlib.sha1(root.encode()).hexdigest()[:6]}"
        while pid in used:
            pid += "x"
        used.add(pid)
        person_of[root] = pid
        people.append({"id": pid, "name": name, "email": email})

    commits, touches, modules = [], [], set()
    for c, mods in kept:
        commits.append({"sha": c.sha, "t": c.t, "message": c.subject[:200], "p": person_of[find(keys(c)[0])]})
        for m, n in mods.items():
            modules.add(m)
            touches.append({"sha": c.sha, "m": m, "files": n})
    return Dataset(people=people, modules=[{"id": m, "path": m} for m in sorted(modules)], commits=commits,
                   touches=touches, skipped=dict(skipped))


# ---------------------------------------------------------------- Cypher

Q_INDEXES = ["CREATE INDEX FOR (p:Person) ON (p.id)", "CREATE INDEX FOR (m:Module) ON (m.id)",
             "CREATE INDEX FOR (c:Commit) ON (c.sha)"]
Q_PEOPLE = "UNWIND $rows AS r CREATE (:Person {id: r.id, name: r.name, email: r.email})"
Q_MODULES = "UNWIND $rows AS r CREATE (:Module {id: r.id, path: r.path})"
Q_COMMITS = """UNWIND $rows AS r
MATCH (p:Person {id: r.p})
CREATE (p)-[:AUTHORED]->(:Commit {sha: r.sha, t: r.t, message: r.message})"""
Q_TOUCHES = """UNWIND $rows AS r
MATCH (c:Commit {sha: r.sha}), (m:Module {id: r.m})
CREATE (c)-[:TOUCHES {files: r.files}]->(m)"""
Q_MODULE_STATS = """MATCH (c:Commit)-[:TOUCHES]->(m:Module)
WITH m, count(c) AS n, min(c.t) AS first, max(c.t) AS last
SET m.commits = n, m.firstCommit = first, m.lastCommit = last"""

Q_EXPERTISE = """// Expertise: every commit adds 0.5^(age_days / 120); the sum saturates as 1 - exp(-raw / 4)
MATCH (p:Person)-[:AUTHORED]->(c:Commit)-[:TOUCHES]->(m:Module)
WITH p, m, c, CASE WHEN $now > c.t THEN ($now - c.t) / 86400.0 ELSE 0.0 END AS ageDays
WITH p, m, count(c) AS commits, max(c.t) AS lastSeen, sum(0.5 ^ (ageDays / $halfLife)) AS raw
CREATE (p)-[k:KNOWS {raw: raw, score: 1 - exp(-raw / $saturation), commits: commits, lastSeen: lastSeen}]->(m)
RETURN count(k) AS links,
       sum(CASE WHEN k.score > $strong THEN 1 ELSE 0 END) AS strongLinks,
       sum(CASE WHEN k.score > $credible THEN 1 ELSE 0 END) AS credibleLinks"""

Q_WORKS_WITH = """// Co-work projection: a WORKS_WITH b when both touched the same module and b credibly knows it
MATCH (a:Person)-[:KNOWS]->(m:Module)<-[kb:KNOWS]-(b:Person)
WHERE a <> b AND kb.score > $credible
WITH a, b, count(m) AS shared, sum(kb.score) AS weight
CREATE (a)-[r:WORKS_WITH {weight: weight, shared: shared}]->(b)
RETURN count(r) AS edges"""

Q_PAGERANK = """CALL algo.pageRank('Person', 'WORKS_WITH') YIELD node, score
SET node.centrality = score
RETURN node.id AS id, node.name AS name, score
ORDER BY score DESC"""

Q_OVERVIEW = """MATCH (c:Commit)
WITH count(c) AS commits, min(c.t) AS first, max(c.t) AS last
MATCH (p:Person)
WITH commits, first, last, count(p) AS people
MATCH (m:Module)
RETURN commits, first, last, people, count(m) AS modules"""

Q_MODULE_TABLE = """MATCH (p:Person)-[k:KNOWS]->(m:Module)
WITH m, p, k ORDER BY k.score DESC
WITH m, collect({id: p.id, name: p.name, score: k.score, commits: k.commits, lastSeen: k.lastSeen}) AS knowers
RETURN m.id AS id, m.path AS path, m.commits AS commits, m.lastCommit AS lastCommit,
       size(knowers) AS people,
       size([x IN knowers WHERE x.score > $credible]) AS busFactor,
       size([x IN knowers WHERE x.score > $strong]) AS strong,
       knowers[0..5] AS knowers
ORDER BY commits DESC
LIMIT $limit"""

Q_ONLY_ONE = """// Only one person knows: exactly one strong knower and nobody else above the credible line
MATCH (p:Person)-[k:KNOWS]->(m:Module) WHERE k.score > $strong
OPTIONAL MATCH (o:Person)-[k2:KNOWS]->(m) WHERE o <> p
WITH p, k, m, o, k2 ORDER BY k2.score DESC
WITH p, k, m, collect(CASE WHEN o IS NULL THEN NULL ELSE {id: o.id, name: o.name, score: k2.score} END) AS others
WHERE size([x IN others WHERE x.score > $credible]) = 0
RETURN m.id AS id, m.path AS path, m.commits AS commits, m.lastCommit AS lastCommit,
       p.id AS personId, p.name AS person, k.score AS score, k.commits AS personCommits, others[0] AS nextBest
ORDER BY commits DESC"""

Q_PEOPLE_TABLE = """MATCH (p:Person)-[k:KNOWS]->(m:Module)
OPTIONAL MATCH (o:Person)-[k2:KNOWS]->(m) WHERE o <> p AND k2.score > $credible
WITH p, k, m, count(o) AS others ORDER BY k.score DESC
WITH p,
     sum(CASE WHEN k.score > $credible THEN 1 ELSE 0 END) AS modulesKnown,
     sum(CASE WHEN k.score > $strong THEN 1 ELSE 0 END) AS strongIn,
     sum(CASE WHEN k.score > $strong AND others = 0 THEN 1 ELSE 0 END) AS onlyThey,
     max(k.lastSeen) AS lastSeen,
     collect(CASE WHEN k.score > $credible THEN {path: m.path, score: k.score} ELSE NULL END) AS known
MATCH (p)-[:AUTHORED]->(c:Commit)
WITH p, modulesKnown, strongIn, onlyThey, lastSeen, known, count(c) AS commits
RETURN p.id AS id, p.name AS name, commits, lastSeen, modulesKnown, strongIn, onlyThey,
       p.centrality AS centrality, known[0..5] AS topModules
ORDER BY onlyThey DESC, modulesKnown DESC, commits DESC
LIMIT $limit"""

Q_DEPARTURE = """// Remove one person: modules where they are strong and no OTHER person is above the credible line
MATCH (p:Person {id: $person})-[k:KNOWS]->(m:Module) WHERE k.score > $strong
OPTIONAL MATCH (o:Person)-[k2:KNOWS]->(m) WHERE o <> p
WITH p, k, m, o, k2 ORDER BY k2.score DESC
WITH p, k, m, collect(CASE WHEN o IS NULL THEN NULL ELSE {id: o.id, name: o.name, score: k2.score,
     commits: k2.commits, lastSeen: k2.lastSeen} END) AS others
WHERE size([x IN others WHERE x.score > $credible]) = 0
RETURN m.id AS id, m.path AS path, m.commits AS commits, m.lastCommit AS lastCommit,
       k.score AS score, k.commits AS personCommits, k.lastSeen AS lastSeen, others[0] AS nextBest
ORDER BY commits DESC"""

Q_DEPARTURE_COVERED = """// Modules they know that stay covered, and how many credible people remain
MATCH (p:Person {id: $person})-[k:KNOWS]->(m:Module) WHERE k.score > $credible
OPTIONAL MATCH (o:Person)-[k2:KNOWS]->(m) WHERE o <> p AND k2.score > $credible
WITH m, k, o, k2 ORDER BY k2.score DESC
WITH m, k, collect(CASE WHEN o IS NULL THEN NULL ELSE {id: o.id, name: o.name, score: k2.score} END) AS cover
WHERE size(cover) > 0
RETURN m.id AS id, m.path AS path, m.commits AS commits, k.score AS score,
       size(cover) AS busFactorAfter, cover[0..3] AS coveredBy
ORDER BY busFactorAfter ASC, commits DESC"""

Q_PERSON = """MATCH (p:Person {id: $person})-[:AUTHORED]->(c:Commit)
RETURN p.id AS id, p.name AS name, p.centrality AS centrality, count(c) AS commits, max(c.t) AS lastCommit"""

Q_FIND_MODULES = """MATCH (p:Person)-[k:KNOWS]->(m:Module)
WHERE any(t IN $terms WHERE toLower(m.path) CONTAINS t)
WITH m, p, k ORDER BY k.score DESC
WITH m, collect({name: p.name, score: k.score, commits: k.commits, lastSeen: k.lastSeen}) AS knowers
RETURN m.path AS path, m.commits AS commits, m.lastCommit AS lastCommit,
       size([x IN knowers WHERE x.score > $credible]) AS busFactor, knowers[0..3] AS knowers
ORDER BY commits DESC LIMIT 6"""

Q_FIND_PEOPLE = """MATCH (p:Person)-[k:KNOWS]->(m:Module)
WHERE any(t IN $terms WHERE toLower(p.name) CONTAINS t)
WITH p, m, k ORDER BY k.score DESC
WITH p, collect({path: m.path, score: k.score, commits: k.commits}) AS known
MATCH (p)-[:AUTHORED]->(c:Commit)
RETURN p.id AS id, p.name AS name, p.centrality AS centrality, count(c) AS commits, max(c.t) AS lastCommit,
       [x IN known WHERE x.score > $credible][0..6] AS known
ORDER BY commits DESC LIMIT 4"""

PARAMS = {"strong": STRONG, "credible": CREDIBLE}


def _day(t: Any) -> str | None:
    if t is None:
        return None
    return datetime.fromtimestamp(int(t), tz=UTC).strftime("%Y-%m-%d")


def _r(x: Any, n: int = 3) -> Any:
    return round(float(x), n) if isinstance(x, (int, float)) else x


class _Log:
    """Collects every query's Cypher and timing for "Show Cypher"."""

    def __init__(self, g):
        self.g = g
        self.queries: list[dict] = []

    def run(self, name: str, title: str, cypher: str, params: dict | None = None, *, write: bool = False,
            keep: bool = True) -> list[dict]:
        res = db.timed(cypher, params, g=self.g, readonly=not write, timeout=120000 if write else 60000)
        if keep:
            shown = {k: v for k, v in (params or {}).items() if k != "rows"}
            self.queries.append({"name": name, "title": title, "cypher": res.cypher, "params": shown,
                                 "ms": res.ms, "rows": len(res.rows)})
        return res.rows


def write_graph(name: str, data: Dataset, on: Callable = lambda *a, **k: None) -> dict:
    """Replace the repo graph with Person, Module and Commit nodes (UNWIND batches)."""
    if db.exists(name):
        db.graph(name).delete()
    g = db.graph(name)
    t0 = time.perf_counter()
    for q in Q_INDEXES:
        db.run(q, g=g)
    db.batched(Q_PEOPLE, data.people, g=g)
    db.batched(Q_MODULES, data.modules, g=g)
    on("scoring", f"Writing {len(data.commits):,} commits to the graph", written=0)
    done = 0
    for i in range(0, len(data.commits), 500):
        db.batched(Q_COMMITS, data.commits[i:i + 500], g=g)
        done += len(data.commits[i:i + 500])
        on("scoring", f"Writing {len(data.commits):,} commits to the graph", written=done)
    db.batched(Q_TOUCHES, data.touches, g=g, size=1000)
    db.run(Q_MODULE_STATS, g=g, timeout=120000)
    return {"ms": round((time.perf_counter() - t0) * 1000, 1), "nodes": len(data.people) + len(data.modules) + len(data.commits),
            "edges": len(data.commits) + len(data.touches)}


def score_graph(name: str, now: float) -> tuple[list[dict], dict]:
    """Expertise, co-work projection and PageRank, all in Cypher on the repo graph."""
    log_ = _Log(db.graph(name))
    exp_rows = log_.run("expertise", "Score expertise (KNOWS) from decayed commits", Q_EXPERTISE,
                        {"now": int(now), "halfLife": HALF_LIFE_DAYS, "saturation": SATURATION, **PARAMS}, write=True)
    ww = log_.run("worksWith", "Project co-work edges (WORKS_WITH) toward credible knowers of shared modules",
                  Q_WORKS_WITH, PARAMS, write=True)
    pr = log_.run("pageRank", "PageRank centrality over WORKS_WITH", Q_PAGERANK, write=True)
    stats = {k: int(v or 0) for k, v in (exp_rows[0] if exp_rows else {}).items()}
    stats["worksWith"] = int(ww[0]["edges"]) if ww else 0
    return log_.queries, {"stats": stats, "pageRank": pr}


def summarize(name: str) -> tuple[dict, list[dict]]:
    """The read queries behind the results page."""
    log_ = _Log(db.graph(name))
    ov = log_.run("overview", "Overview: commits, people, modules", Q_OVERVIEW)
    mods = log_.run("modules", "Modules: knowers by score and bus factor", Q_MODULE_TABLE, {**PARAMS, "limit": MODULE_ROWS})
    only = log_.run("onlyOne", "Modules only one person knows", Q_ONLY_ONE, PARAMS)
    ppl = log_.run("people", "People: modules known and modules only they know", Q_PEOPLE_TABLE,
                   {**PARAMS, "limit": PEOPLE_ROWS})
    o = ov[0] if ov else {}
    summary = {
        "commits": o.get("commits", 0), "people": o.get("people", 0), "modules": o.get("modules", 0),
        "firstCommit": _day(o.get("first")), "lastCommit": _day(o.get("last")),
        "onlyOneCount": len(only),
        "modulesTable": [{**m, "lastCommit": _day(m["lastCommit"]),
                          "knowers": [{**k, "score": _r(k["score"]), "lastSeen": _day(k["lastSeen"])} for k in m["knowers"]]}
                         for m in mods],
        "onlyOne": [{**r, "score": _r(r["score"]), "lastCommit": _day(r["lastCommit"]),
                     "nextBest": ({**r["nextBest"], "score": _r(r["nextBest"]["score"])} if r.get("nextBest") else None)}
                    for r in only],
        "peopleTable": [{**p, **{k: int(p[k] or 0) for k in ("modulesKnown", "strongIn", "onlyThey")},
                         "centrality": _r(p.get("centrality"), 4), "lastSeen": _day(p["lastSeen"]),
                         "topModules": [{**k, "score": _r(k["score"])} for k in p["topModules"]]} for p in ppl],
    }
    return summary, log_.queries


def analyze(src: Source, *, now: float | None = None, on: Callable = lambda *a, **k: None) -> dict:
    """Clone, parse, write, score and summarize one repository. Returns the summary."""
    timings: dict[str, float] = {}
    workdir = tempfile.mkdtemp(prefix="relay-repo-")
    try:
        gitdir = os.path.join(workdir, "repo.git")
        t0 = time.perf_counter()
        on("cloning", f"Cloning {src.slug}", mb=0, seconds=0)
        fallback = _fetch(src, gitdir, on)
        timings["cloneMs"] = round((time.perf_counter() - t0) * 1000)
        on("parsing", "Reading the commit history")
        t0 = time.perf_counter()
        text = _git_log(gitdir)
        boundary = _shallow_boundary(gitdir)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    raw = parse_log(text)
    data = build_dataset(raw, boundary)
    timings["parseMs"] = round((time.perf_counter() - t0) * 1000)
    on("parsing", f"Parsed {len(raw):,} commits", commits=len(data.commits), people=len(data.people),
       modules=len(data.modules), read=len(raw))
    if not data.commits:
        raise RepoError("No commits by people that change source files were found in this repository's recent history.")

    now = now or time.time()
    name = src.graph
    t0 = time.perf_counter()
    written = write_graph(name, data, on)
    timings["writeMs"] = round((time.perf_counter() - t0) * 1000)
    on("scoring", "Scoring expertise in Cypher")
    t0 = time.perf_counter()
    score_queries, scored = score_graph(name, now)
    timings["scoreMs"] = round((time.perf_counter() - t0) * 1000)
    on("scoring", "Running the result queries")
    summary, read_queries = summarize(name)
    names = {p["id"]: p for p in summary["peopleTable"]}
    central = [{"id": r["id"], "name": r["name"], "centrality": _r(r["score"], 4),
                "modulesKnown": names.get(r["id"], {}).get("modulesKnown"),
                "commits": names.get(r["id"], {}).get("commits")} for r in scored["pageRank"][:10]]
    return {
        "repo": src.slug, "url": src.web_url, "graph": name, "asOf": datetime.fromtimestamp(now, tz=UTC).isoformat(),
        "historyWindow": f"newest {MAX_COMMITS:,} commits" if fallback else f"last 2 years (up to {MAX_COMMITS:,} commits)",
        **summary,
        "central": central,
        "skipped": data.skipped,
        "graphSize": written,
        "scoring": scored["stats"],
        "thresholds": {"strong": STRONG, "credible": CREDIBLE, "halfLifeDays": HALF_LIFE_DAYS, "saturation": SATURATION},
        "queries": score_queries + read_queries,
        "timings": timings,
    }


# ---------------------------------------------------------------- departure and ask


def departure(name: str, person: str) -> dict:
    if not db.exists(name):
        raise RepoError("The graph for this analysis is gone. Run the analysis again.")
    log_ = _Log(db.graph(name))
    who = log_.run("person", "The person", Q_PERSON, {"person": person})
    if not who or who[0]["id"] is None:
        raise LookupError("No such person in this repository")
    orphaned = log_.run("departure", "Remove the person: modules nobody else credibly knows", Q_DEPARTURE,
                        {**PARAMS, "person": person})
    covered = log_.run("covered", "Modules they know that stay covered", Q_DEPARTURE_COVERED, {**PARAMS, "person": person})
    w = who[0]
    return {
        "person": {"id": w["id"], "name": w["name"], "commits": w["commits"], "lastCommit": _day(w["lastCommit"]),
                   "centrality": _r(w.get("centrality"), 4)},
        "orphaned": [{**r, "score": _r(r["score"]), "lastCommit": _day(r["lastCommit"]), "lastSeen": _day(r["lastSeen"]),
                      "nextBest": ({**r["nextBest"], "score": _r(r["nextBest"]["score"]),
                                    "lastSeen": _day(r["nextBest"]["lastSeen"])} if r.get("nextBest") else None)}
                     for r in orphaned],
        "covered": [{**r, "score": _r(r["score"]), "coveredBy": [{**c, "score": _r(c["score"])} for c in r["coveredBy"]]}
                    for r in covered],
        "queries": log_.queries,
    }


_STOP = set("""a an and are about any can could did does do for from has have how if in into is it its know knows
knowledge leave leaves left me my of on or our out repo repository should tell than that the their them then there
these they this those to was we what when where which who whom why will with would you your most more much many best
code module modules person people someone anyone happens happen only one owns owner work works working need ask""".split())  # noqa: SIM905


def _terms(question: str) -> list[str]:
    words = re.findall(r"[a-z0-9][a-z0-9_.\-/]{2,}", question.lower())
    return [w.strip("./-") for w in words if w not in _STOP and len(w.strip("./-")) >= 3][:12]


class AskAnswer(BaseModel):
    answer: str = Field(description="Plain short answer, at most 120 words, grounded only in the facts")
    used: list[str] = Field(description="Ids of the facts the answer relies on, like F3")


ASK_SYSTEM = """You answer questions about who knows what in one code repository.
Use only the numbered facts. They come from a knowledge graph built from the repository's git history.
Cite the fact ids you rely on in `used`. Do not invent people, modules, numbers or dates.
If the facts do not answer the question, say so plainly and say what the facts do show.
Scores run from 0 to 1: above 0.6 means a strong link, above 0.35 a credible alternate.
Bus factor is the number of people above 0.35 on a module. Write plain short English, no markdown headings."""


def ask(name: str, repo: str, question: str) -> dict:
    if not llm.available():
        raise llm.LLMUnavailable("Gemini is not configured on this server (GEMINI_API_KEY is not set), "
                                 "so Relay cannot answer questions here. The analysis itself does not need it.")
    if not db.exists(name):
        raise RepoError("The graph for this analysis is gone. Run the analysis again.")
    log_ = _Log(db.graph(name))
    terms = _terms(question)
    facts: list[dict] = []

    def fact(kind: str, text: str) -> None:
        facts.append({"id": f"F{len(facts) + 1}", "kind": kind, "text": text})

    ov = log_.run("overview", "Overview", Q_OVERVIEW)
    if ov:
        o = ov[0]
        fact("repo", f"{repo}: {o['commits']} commits analyzed from {_day(o['first'])} to {_day(o['last'])}, "
                     f"{o['people']} people, {o['modules']} modules.")
    mods = log_.run("findModules", "Modules whose path matches the question", Q_FIND_MODULES,
                    {**PARAMS, "terms": terms}) if terms else []
    for m in mods:
        ks = ", ".join(f"{k['name']} ({_r(k['score'], 2)}, {k['commits']} commits, last {_day(k['lastSeen'])})"
                       for k in m["knowers"])
        fact("module", f"Module {m['path']}: {m['commits']} commits, last commit {_day(m['lastCommit'])}, "
                       f"bus factor {m['busFactor']}. Top knowers: {ks}.")
    ppl = log_.run("findPeople", "People whose name matches the question", Q_FIND_PEOPLE,
                   {**PARAMS, "terms": terms}) if terms else []
    for p in ppl:
        known = ", ".join(f"{k['path']} ({_r(k['score'], 2)})" for k in p["known"]) or "no module above 0.35"
        fact("person", f"{p['name']}: {p['commits']} commits, last commit {_day(p['lastCommit'])}, "
                       f"PageRank centrality {_r(p.get('centrality'), 4)}. Knows: {known}.")
        gone = log_.run("departure", f"If {p['name']} leaves", Q_DEPARTURE, {**PARAMS, "person": p["id"]})
        if gone:
            parts = []
            for r in gone[:8]:
                nb = r.get("nextBest")
                parts.append(f"{r['path']} (next best: {nb['name']} at {_r(nb['score'], 2)})" if nb else
                             f"{r['path']} (nobody else has touched it)")
            fact("departure", f"If {p['name']} leaves, {len(gone)} module(s) have nobody else above 0.35: " + "; ".join(parts) + ".")
        else:
            fact("departure", f"If {p['name']} leaves, every module they know strongly still has another credible person.")
    only = log_.run("onlyOne", "Modules only one person knows", Q_ONLY_ONE, PARAMS)
    if only:
        fact("onlyOne", f"{len(only)} module(s) are known strongly by only one person: " +
             "; ".join(f"{r['path']} ({r['person']}, {_r(r['score'], 2)})" for r in only[:10]) + ".")
    else:
        fact("onlyOne", "No module is known strongly by only one person.")
    central = db.timed("""MATCH (p:Person) WHERE p.centrality IS NOT NULL
RETURN p.name AS name, p.centrality AS c ORDER BY c DESC LIMIT 5""", g=log_.g)
    log_.queries.append({"name": "central", "title": "Most central people (PageRank)", "cypher": central.cypher,
                         "params": {}, "ms": central.ms, "rows": len(central.rows)})
    if central.rows:
        fact("central", "Most central people by PageRank over co-work: " +
             ", ".join(f"{r['name']} ({_r(r['c'], 4)})" for r in central.rows) + ".")
    if not mods:
        top = log_.run("topModules", "Busiest modules", Q_MODULE_TABLE, {**PARAMS, "limit": 8})
        for m in top:
            ks = ", ".join(f"{k['name']} ({_r(k['score'], 2)})" for k in m["knowers"][:3])
            fact("module", f"Module {m['path']}: {m['commits']} commits, last commit {_day(m['lastCommit'])}, "
                           f"bus factor {m['busFactor']}. Top knowers: {ks}.")

    prompt = (f"Repository: {repo}\nQuestion: {question.strip()}\n\nFacts:\n" +
              "\n".join(f"{f['id']}. {f['text']}" for f in facts))
    kwargs: dict[str, Any] = {"system": ASK_SYSTEM}
    if "cache" in inspect.signature(llm.generate).parameters:
        kwargs["cache"] = False
    t0 = time.perf_counter()
    out = llm.generate(prompt, AskAnswer, **kwargs)
    used = [f for f in facts if f["id"] in set(out.used)]
    return {"answer": out.answer.strip(), "facts": used, "factsConsidered": len(facts), "allFacts": facts,
            "terms": terms, "model": settings().llm_model, "ms": round((time.perf_counter() - t0) * 1000),
            "queries": log_.queries}


# ---------------------------------------------------------------- jobs

_lock = threading.Lock()
_slots = threading.BoundedSemaphore(MAX_RUNNING)
_jobs: dict[str, dict] = {}
_loaded_from: Path | None = None


def _dir() -> Path:
    return Path(os.getenv("RELAY_REPOS_DIR") or CACHE_DIR / "repos")


def _save(job: dict) -> None:
    d = _dir()
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f".{job['id']}.tmp"
    tmp.write_text(json.dumps(job, default=str))
    os.replace(tmp, d / f"{job['id']}.json")


def _ensure_loaded() -> None:
    global _loaded_from
    d = _dir()
    with _lock:
        if _loaded_from == d:
            return
        _jobs.clear()
        interrupted = []
        for f in sorted(d.glob("*.json")) if d.exists() else []:
            try:
                job = json.loads(f.read_text())
            except (OSError, ValueError):
                continue
            if job.get("status") in RUNNING:
                job.update(status="failed", message="Stopped by a server restart. Run it again.",
                           finishedAt=job.get("finishedAt") or time.time())
                interrupted.append(job)
            _jobs[job["id"]] = job
        _loaded_from = d
    for job in interrupted:
        _save(job)


def _update(jid: str, *, persist: bool = False, progress: dict | None = None, **fields) -> None:
    with _lock:
        job = _jobs.get(jid)
        if not job:
            return
        status_changed = "status" in fields and fields["status"] != job.get("status")
        job.update(fields)
        if progress:
            job["progress"] = {**job.get("progress", {}), **progress}
        snapshot = dict(job)
    if persist or status_changed:
        _save(snapshot)


def _run(jid: str, src: Source) -> None:
    with _slots:
        _update(jid, status="cloning", message=f"Cloning {src.slug}", startedAt=time.time())
        try:
            summary = analyze(src, on=lambda stage, msg, **counts: _update(jid, status=stage, message=msg, progress=counts))
            _update(jid, status="done", message=f"Analyzed {summary['commits']:,} commits", summary=summary,
                    finishedAt=time.time(), persist=True)
        except RepoError as e:
            _update(jid, status="failed", message=str(e), finishedAt=time.time(), persist=True)
        except Exception as e:  # unexpected: keep the detail in the record, show a plain message
            log.exception("repo analysis %s failed", src.slug)
            _update(jid, status="failed", message="Something went wrong while analyzing this repository.",
                    error=repr(e)[:500], finishedAt=time.time(), persist=True)


def start(url: str, *, wait: bool = False) -> dict:
    """Start (or reuse) an analysis. Reuses a running job, or a finished one under 6 hours old."""
    src = parse_source(url)
    _ensure_loaded()
    with _lock:
        same = sorted((j for j in _jobs.values() if j["repo"] == src.slug), key=lambda j: j["createdAt"], reverse=True)
        waiting = sum(1 for j in _jobs.values() if j["status"] in RUNNING)
    for j in same:
        if j["status"] in RUNNING:
            return j
        if j["status"] == "done" and time.time() - (j.get("finishedAt") or 0) < FRESH_FOR_S and db.exists(j["graph"]):
            return j
    if waiting >= MAX_RUNNING + MAX_WAITING:
        raise Busy("Too many analyses are running right now. Try again in a minute.")
    job = {"id": uuid.uuid4().hex[:12], "repo": src.slug, "url": src.web_url, "graph": src.graph, "status": "queued",
           "message": "Waiting for a free slot", "progress": {}, "createdAt": time.time(), "startedAt": None,
           "finishedAt": None, "summary": None}
    with _lock:
        _jobs[job["id"]] = job
    _save(job)
    t = threading.Thread(target=_run, args=(job["id"], src), name=f"repo-{job['id']}", daemon=True)
    t.start()
    if wait:
        t.join()
    return get(job["id"]) or job


def get(jid: str) -> dict | None:
    _ensure_loaded()
    with _lock:
        job = _jobs.get(jid)
        return dict(job) if job else None


def public(job: dict) -> dict:
    out = {k: job.get(k) for k in ("id", "repo", "url", "status", "message", "progress", "createdAt", "startedAt",
                                   "finishedAt")}
    out["summary"] = job.get("summary") if job.get("status") == "done" else None
    return out


def recent(limit: int = 20) -> list[dict]:
    _ensure_loaded()
    with _lock:
        jobs = sorted(_jobs.values(), key=lambda j: j["createdAt"], reverse=True)[:limit]
        return [{"id": j["id"], "repo": j["repo"], "url": j.get("url"), "status": j["status"],
                 "message": j.get("message"), "createdAt": j["createdAt"], "finishedAt": j.get("finishedAt"),
                 "commits": (j.get("summary") or {}).get("commits"), "people": (j.get("summary") or {}).get("people"),
                 "onlyOneCount": (j.get("summary") or {}).get("onlyOneCount")} for j in jobs]
