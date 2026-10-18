import os

# Isolated graph, no LLM, no artificial streaming delay.
os.environ["RELAY_GRAPH"] = "lumen_test"
os.environ["RELAY_ANALYSIS_DELAY"] = "0"
os.environ["RELAY_EXTRACTOR"] = "seed"
os.environ["GEMINI_API_KEY"] = ""

import uuid  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def built():
    from relay import db
    from relay.ingest.pipeline import build
    yield build(progress=lambda *_: None, extractor="seed")
    # Drop the per-test workspace graphs and the test accounts graph.
    for name in db._client().list_graphs():
        if name.startswith("lumen_test_ws_") or name == "lumen_test_accounts":
            db.graph(name).delete()


@pytest.fixture()
def fresh(built):
    from relay.events import bus
    from relay.ingest.pipeline import reset
    reset()
    bus.reset()
    yield


def new_client(name: str = "Test Presenter", workspace: str | None = "Test Co"):
    """A signed-in API client with its own account (and, by default, its own workspace)."""
    from fastapi.testclient import TestClient

    from relay.api import app
    c = TestClient(app)
    c.email = f"t-{uuid.uuid4().hex[:8]}@example.com"
    r = c.post("/api/auth/sign-up", json={"name": name, "email": c.email, "password": "correct horse battery"})
    assert r.status_code == 201, r.text
    if workspace:
        r = c.post("/api/workspaces", json={"name": workspace})
        assert r.status_code == 200, r.text
    return c


@pytest.fixture()
def client(fresh):
    return new_client()
