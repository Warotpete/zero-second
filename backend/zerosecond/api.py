"""HTTP API (FastAPI) + live stream (SSE) + MCP endpoint + static web app."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel

from . import mcp_server
from .agents import foundry
from .runtime import Rooms

def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines); real environment variables win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if v.strip():
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


_load_dotenv(Path(__file__).resolve().parent.parent / ".env")
logging.basicConfig(level=os.getenv("ZS_LOG", "INFO"))
log = logging.getLogger("zerosecond.api")

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "data"
WEB = Path(os.getenv("ZS_WEB_DIR", ROOT.parent.parent / "frontend" / "dist"))

mcp_app = mcp_server.mcp.streamable_http_app(
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)
rooms = Rooms()
mcp_server.bind(rooms)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp_server.mcp.session_manager.run():
        agents = None
        if foundry.enabled():
            port = os.getenv("PORT", "8000")
            agents = foundry.FoundryAgents(os.getenv("ZS_MCP_URL", f"http://127.0.0.1:{port}/mcp/"))
            try:
                await agents.start()
                log.info("Foundry agents ready (model %s)", agents.model)
            except Exception:
                log.exception("Foundry agents failed to start; using local writer")
                agents = None
        rooms.agents = agents
        rooms.get("demo")
        loop = asyncio.create_task(rooms.run())
        try:
            yield
        finally:
            loop.cancel()
            if agents:
                await agents.stop()


app = FastAPI(title="Zero Second", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/mcp", mcp_app)


class NewRoom(BaseModel):
    seed: int | None = None


class Control(BaseModel):
    action: str
    value: float | None = None


class Jump(BaseModel):
    minute: float


class EditBody(BaseModel):
    key: str
    text: str


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True, "backend": "foundry" if rooms.agents else "local", "rooms": list(rooms.rooms)}


@app.get("/api/about")
async def about() -> dict:
    return {
        "name": "Zero Second",
        "tagline": "Ready before it happens.",
        "backend": f"Microsoft Foundry ({rooms.agents.model}) via Microsoft Agent Framework" if rooms.agents else "Local deterministic writer (set FOUNDRY_PROJECT_ENDPOINT to use Foundry)",
        "mcp": "/mcp/",
    }


@app.post("/api/rooms/{room}/new")
async def new_room(room: str, body: NewRoom) -> dict:
    from .pitchforge.scenario import SCENARIO_SEED

    rt = rooms.new(room, body.seed if body.seed is not None else SCENARIO_SEED)
    return {"room": room, "seed": rt.seed, "match": rt.cfg.match_id}


@app.get("/api/rooms/{room}/state")
async def state(room: str) -> dict:
    return rooms.get(room).snapshot()


@app.get("/api/rooms/{room}/stream")
async def stream(room: str) -> StreamingResponse:
    async def gen():
        last = -1
        idle = 0
        while True:
            rt = rooms.get(room)
            if rt.version != last or idle >= 20:
                last, idle = rt.version, 0
                yield f"data: {json.dumps(rt.snapshot(), ensure_ascii=False)}\n\n"
            else:
                idle += 1
            await asyncio.sleep(0.4)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/rooms/{room}/control")
async def control(room: str, body: Control) -> dict:
    rt = rooms.get(room)
    rt.control(body.action, body.value)
    rt.version += 1
    return {"ok": True}


@app.post("/api/rooms/{room}/jump")
async def jump(room: str, body: Jump) -> dict:
    rt = rooms.get(room)
    if body.minute * 60 < rt.clock:
        seed = rt.seed
        rt = rooms.new(room, seed)
    await rt.jump(body.minute)
    return {"ok": True, "clock": rt.clock}


@app.post("/api/rooms/{room}/storylines/{sid}/{action}")
async def storyline_action(room: str, sid: str, action: str) -> dict:
    o = rooms.get(room).orch
    fn = {"approve": o.approve, "hold": o.hold, "revoke": o.revoke}.get(action)
    if not fn:
        raise HTTPException(404, "unknown action")
    ok = fn(sid)
    rooms.get(room).version += 1
    return {"ok": ok}


@app.post("/api/rooms/{room}/storylines/{sid}/edit")
async def storyline_edit(room: str, sid: str, body: EditBody) -> dict:
    ok, issues = rooms.get(room).orch.edit(sid, body.key, body.text)
    rooms.get(room).version += 1
    return {"ok": ok, "issues": issues}


@app.post("/api/rooms/{room}/recap/approve")
async def recap_approve(room: str) -> dict:
    return {"ok": rooms.get(room).orch.approve_recap()}


@app.get("/api/rooms/{room}/memory")
async def memory(room: str) -> dict:
    rt = rooms.get(room)
    out = rt.memory.summary(rt.home, rt.away)
    out["names"] = {p.id: p.name for p in rt.world.all_players()}
    out["teams"] = {t.id: t.public() for t in rt.world.teams.values()}
    return out


@app.get("/api/rooms/{room}/lineups")
async def lineups(room: str) -> dict:
    return rooms.get(room).lineups()


@app.get("/api/rooms/{room}/events")
async def events(room: str, limit: int = 200) -> dict:
    """The raw Opta-style feed ingested so far (newest last)."""
    rt = rooms.get(room)
    return {"count": rt.cursor, "events": rt.events[max(0, rt.cursor - limit): rt.cursor]}


@app.get("/api/rooms/{room}/overlays.json")
async def overlays(room: str) -> JSONResponse:
    rt = rooms.get(room)
    return JSONResponse({"match": rt.cfg.match_id, "format": "zerosecond.overlay/v1", "cues": rt.orch.overlays})


@app.get("/api/calibration")
async def calibration() -> JSONResponse:
    f = DATA / "calibration.json"
    if not f.exists():
        return JSONResponse({"available": False})
    return JSONResponse(json.loads(f.read_text(encoding="utf-8")))


if WEB.exists():
    app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")

    @app.get("/{path:path}")
    async def spa(path: str):
        f = WEB / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(WEB / "index.html")
