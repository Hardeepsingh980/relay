"""Repo knowledge on a tiny local git repository: clone, parse, score and departure (no network)."""

import os
import subprocess
import time
import uuid

import pytest

DAY = 86400


def _git(repo, *args, env=None):
    base = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, env={**base, **(env or {})})


def _commit(repo, name, email, files, days_ago, msg="change"):
    for path, content in files.items():
        p = repo / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    _git(repo, "add", "-A")
    when = f"@{int(time.time() - days_ago * DAY)} +0000"
    _git(repo, "commit", "-q", "-m", msg, env={"GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email, "GIT_AUTHOR_DATE": when,
                                              "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email,
                                              "GIT_COMMITTER_DATE": when})


@pytest.fixture()
def tiny_repo(tmp_path, monkeypatch):
    """Alice alone knows src/core (Bob touched it once); Bob and Carol both know src/api; a bot is ignored."""
    monkeypatch.setenv("RELAY_REPOS_ALLOW_LOCAL", "1")
    monkeypatch.setenv("RELAY_REPOS_DIR", str(tmp_path / "jobs"))
    repo = tmp_path / f"relaytest-{uuid.uuid4().hex[:8]}"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _commit(repo, "Bob Ray", "bob@example.com", {"README.md": "hello"}, 30, "initial")
    _commit(repo, "Carol Diaz", "carol@example.com", {"docs/guide.md": "old"}, 400, "old docs")
    for i in range(5):
        _commit(repo, "Alice Smith", "alice@work.example", {"src/core/engine.py": f"v{i}"}, 1 + i)
    _commit(repo, "Alice Smith", "alice@personal.example", {"src/core/engine.py": "alias"}, 2)   # same person
    _commit(repo, "Bob Ray", "bob@example.com", {"src/core/engine.py": "bob"}, 10)
    for i in range(5):
        _commit(repo, "Bob Ray", "bob@example.com", {"src/api/routes.py": f"b{i}"}, 1 + i)
        _commit(repo, "Carol Diaz", "carol@example.com", {"src/api/routes.py": f"c{i}"}, 1 + i)
        _commit(repo, "dependabot[bot]", "49699333+dependabot[bot]@users.noreply.github.com",
                {"src/api/routes.py": f"bot{i}"}, 1 + i)
    _commit(repo, "Bob Ray", "bob@example.com", {"package-lock.json": "{}"}, 3)                    # lockfile only
    _commit(repo, "Bob Ray", "bob@example.com", {"node_modules/x/index.js": "x", "src/api/routes.py": "b5"}, 2)
    yield repo
    from relay import db, repos
    name = repos.parse_source(str(repo)).graph
    if db.exists(name):
        db.graph(name).delete()


def test_parse_source_accepts_only_github_urls(monkeypatch):
    from relay import repos
    for url in ("https://github.com/pallets/click", "https://github.com/pallets/click/", "https://github.com/pallets/click.git",
                " https://github.com/pallets/click.git/ "):
        s = repos.parse_source(url)
        assert (s.slug, s.clone_url, s.graph) == ("pallets/click", "https://github.com/pallets/click.git", "repo_pallets_click")
    assert repos.parse_source("https://github.com/FalkorDB/falkordb-py").graph == "repo_falkordb_falkordb_py"
    monkeypatch.delenv("RELAY_REPOS_ALLOW_LOCAL", raising=False)
    for bad in ("http://github.com/a/b", "https://gitlab.com/a/b", "https://github.com/a", "https://github.com/a/b/tree/main",
                "git@github.com:a/b.git", "https://github.com/-a/b", "/tmp/somewhere", "file:///tmp/x", ""):
        with pytest.raises(repos.RepoError):
            repos.parse_source(bad)


def test_modules_and_bots():
    from relay import repos
    assert repos.module_of("src/click/core.py") == "src/click"
    assert repos.module_of("packages/ui/src/button.tsx") == "packages/ui"
    assert repos.module_of("docs/index.md") == "docs"
    assert repos.module_of("README.md") == "(root)"
    assert repos.module_of("src/main.py") == "src"
    for ignored in ("package-lock.json", "web/pnpm-lock.yaml", "go.sum", "Cargo.lock", "node_modules/a/b.js",
                    "vendor/x/y.go", "dist/app.js", "app/build/out.js"):
        assert repos.module_of(ignored) is None, ignored
    assert repos.is_bot("dependabot[bot]", "49699333+dependabot[bot]@users.noreply.github.com")
    assert repos.is_bot("github-actions", "41898282+github-actions[bot]@users.noreply.github.com")
    assert repos.is_bot("Renovate Bot", "bot@renovateapp.com")
    assert not repos.is_bot("Jane Doe", "1234+jane@users.noreply.github.com")


def test_analysis_bus_factor_only_one_and_departure(tiny_repo):
    from relay import repos
    job = repos.start(str(tiny_repo), wait=True)
    assert job["status"] == "done", job["message"]
    s = job["summary"]
    assert s["people"] == 3                      # Alice's two emails merged by name; the bot is ignored
    assert s["skipped"]["bots"] == 5 and s["skipped"]["noSourceFiles"] == 1
    mods = {m["path"]: m for m in s["modulesTable"]}
    assert set(mods) == {"(root)", "docs", "src/core", "src/api"}
    assert mods["src/core"]["busFactor"] == 1 and mods["src/core"]["knowers"][0]["name"] == "Alice Smith"
    assert mods["src/core"]["knowers"][0]["commits"] == 6
    assert mods["src/api"]["busFactor"] == 2
    assert mods["docs"]["busFactor"] == 0        # one commit 400 days ago has decayed away

    assert [(o["path"], o["person"]) for o in s["onlyOne"]] == [("src/core", "Alice Smith")]
    assert s["onlyOne"][0]["nextBest"]["name"] == "Bob Ray"
    people = {p["name"]: p for p in s["peopleTable"]}
    assert people["Alice Smith"]["onlyThey"] == 1 and people["Bob Ray"]["onlyThey"] == 0
    assert all(p["centrality"] is not None for p in s["peopleTable"])
    assert {q["name"] for q in s["queries"]} >= {"expertise", "worksWith", "pageRank", "modules", "onlyOne", "people"}
    assert all(q["cypher"] and q["ms"] >= 0 for q in s["queries"])

    alice = repos.departure(s["graph"], people["Alice Smith"]["id"])
    assert [m["path"] for m in alice["orphaned"]] == ["src/core"]
    assert alice["orphaned"][0]["nextBest"]["name"] == "Bob Ray" and alice["orphaned"][0]["nextBest"]["score"] < 0.35
    bob = repos.departure(s["graph"], people["Bob Ray"]["id"])
    assert bob["orphaned"] == []                 # Carol still covers src/api
    assert [(c["path"], c["busFactorAfter"], c["coveredBy"][0]["name"]) for c in bob["covered"]] == [("src/api", 1, "Carol Diaz")]
    with pytest.raises(LookupError):
        repos.departure(s["graph"], "nobody")

    # A finished analysis under six hours old is reused, and it survives a restart (reloaded from JSON).
    assert repos.start(str(tiny_repo))["id"] == job["id"]
    repos._loaded_from = None
    assert repos.get(job["id"])["summary"]["onlyOneCount"] == 1


def test_api_routes(tiny_repo):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from relay.api_repos import router
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    assert c.post("/api/repos", json={"url": "https://gitlab.com/a/b"}).status_code == 400
    r = c.post("/api/repos", json={"url": str(tiny_repo)})
    assert r.status_code == 200, r.text
    jid = r.json()["id"]
    for _ in range(120):
        body = c.get(f"/api/repos/{jid}").json()
        if body["status"] in ("done", "failed"):
            break
        time.sleep(0.25)
    assert body["status"] == "done", body["message"]
    assert body["summary"]["onlyOneCount"] == 1
    assert any(a["id"] == jid for a in c.get("/api/repos").json()["analyses"])
    alice = next(p for p in body["summary"]["peopleTable"] if p["name"] == "Alice Smith")
    dep = c.get(f"/api/repos/{jid}/departure", params={"person": alice["id"]}).json()
    assert [m["path"] for m in dep["orphaned"]] == ["src/core"]
    assert c.get("/api/repos/nope").status_code == 404
    # No Gemini key in tests: a clear 503, never a made-up answer.
    r = c.post(f"/api/repos/{jid}/ask", json={"question": "Who knows src/core?"})
    assert r.status_code == 503 and "GEMINI_API_KEY" in r.json()["detail"]
