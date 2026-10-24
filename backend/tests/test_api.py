"""API and MCP smoke tests."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from zerosecond import mcp_server
from zerosecond.api import app


def test_api_room_lifecycle():
    with TestClient(app) as c:
        assert c.get("/api/health").json()["ok"]
        assert c.post("/api/rooms/t1/new", json={"seed": 4821}).json()["seed"] == 4821
        assert c.post("/api/rooms/t1/jump", json={"minute": 30}).json()["ok"]
        s = c.get("/api/rooms/t1/state").json()
        assert s["match"]["minute"] >= 30 and s["storylines"]
        assert c.get("/api/rooms/t1/memory").json()["table"]
        assert "cues" in c.get("/api/rooms/t1/overlays.json").json()
        assert c.get("/api/rooms/t1/events?limit=5").json()["events"]


def test_mcp_tools_registered():
    tools = asyncio.run(mcp_server.mcp.list_tools())
    names = {t.name for t in tools}
    assert {"stats_xg_window", "memory_player_arc", "memory_h2h", "radar_storylines"} <= names
