"""Connections API: the connector catalog, live credential checks and MCP servers.

Mounted by relay.api under /api/connectors. Every connect makes one live call to the
provider before anything is stored; stored secrets are encrypted and never returned.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from . import connectors, workspaces
from .auth import AuthError

router = APIRouter(prefix="/api/connectors", tags=["connectors"])


class ConnectBody(BaseModel):
    fields: dict[str, Any] = Field(default_factory=dict)


class McpBody(BaseModel):
    name: str = Field(max_length=60)
    url: str = Field(max_length=500)
    token: str | None = Field(default=None, max_length=4000)


def _uid(request: Request) -> str:
    return request.state.user["id"]


def _wid(request: Request) -> str:
    ws = getattr(request.state, "ws", None)
    if not ws:
        raise AuthError("Create or join a workspace first", 403)
    return ws["id"]


@router.get("")
def catalog(request: Request) -> dict:
    workspaces.mark(_uid(request), "connections")
    return {**connectors.catalog(_uid(request), _wid(request)), "mcpUses": connectors.mcp_uses()}


@router.post("/mcp")
async def add_mcp(body: McpBody, request: Request) -> dict:
    return await connectors.add_mcp(_uid(request), _wid(request), body.name, body.url, body.token)


@router.delete("/mcp/{mid}")
def remove_mcp(mid: str, request: Request) -> dict:
    connectors.remove_mcp(_uid(request), _wid(request), mid)
    return {"ok": True}


@router.post("/{provider}")
def connect(provider: str, body: ConnectBody, request: Request) -> dict:
    return connectors.connect(_uid(request), _wid(request), provider, body.fields)


@router.delete("/{provider}")
def disconnect(provider: str, request: Request) -> dict:
    connectors.disconnect(_uid(request), _wid(request), provider)
    return {"ok": True}
