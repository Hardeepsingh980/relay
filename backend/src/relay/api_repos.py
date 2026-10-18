"""Repo knowledge API: analyze any public GitHub repository on real data.

Mounted by relay.api under /api/repos. Each analysis writes its own graph
(`repo_<owner>_<repo>`), independent of the signed-in workspace graph.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import llm, repos

router = APIRouter(prefix="/api/repos", tags=["repos"])


class StartBody(BaseModel):
    url: str = Field(max_length=300)


class AskBody(BaseModel):
    question: str = Field(max_length=500)


def _job(jid: str) -> dict:
    job = repos.get(jid)
    if not job:
        raise HTTPException(404, "No analysis with this id")
    return job


def _done(jid: str) -> dict:
    job = _job(jid)
    if job["status"] != "done":
        raise HTTPException(409, "This analysis has not finished yet")
    return job


@router.post("")
def start(body: StartBody) -> dict:
    try:
        job = repos.start(body.url)
    except repos.Busy as e:
        raise HTTPException(429, str(e)) from None
    except repos.RepoError as e:
        raise HTTPException(400, str(e)) from None
    return {"id": job["id"], "status": job["status"], "repo": job["repo"]}


@router.get("")
def recent() -> dict:
    return {"analyses": repos.recent()}


@router.get("/{jid}")
def status(jid: str) -> dict:
    return repos.public(_job(jid))


@router.get("/{jid}/departure")
def departure(jid: str, person: str) -> dict:
    job = _done(jid)
    try:
        return repos.departure(job["graph"], person)
    except LookupError as e:
        raise HTTPException(404, str(e)) from None
    except repos.RepoError as e:
        raise HTTPException(410, str(e)) from None


@router.post("/{jid}/ask")
def ask(jid: str, body: AskBody) -> dict:
    job = _done(jid)
    question = body.question.strip()
    if len(question) < 3:
        raise HTTPException(400, "Ask a question about this repository")
    try:
        return repos.ask(job["graph"], job["repo"], question)
    except llm.LLMUnavailable as e:
        msg = str(e) if not llm.available() else f"Gemini did not answer: {str(e)[:200]}"
        raise HTTPException(503, msg) from None
    except repos.RepoError as e:
        raise HTTPException(410, str(e)) from None
