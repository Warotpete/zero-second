"""Zero Second MCP server: Stats Engine and Season Memory as tools for agents.

Mounted on the API at /mcp (streamable HTTP). The Foundry Editor agent calls these
tools through Microsoft Agent Framework's MCPStreamableHTTPTool. Any MCP client
(e.g. GitHub Copilot agent mode, Claude, VS Code) can connect too.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.server.mcpserver import MCPServer

if TYPE_CHECKING:
    from .runtime import Rooms

mcp = MCPServer(
    name="zerosecond",
    instructions="Football match context for Zero Second rooms: live stats (xG windows, scores) and Season Memory "
    "(player arcs, milestones, head-to-head, clean-sheet streaks, late winners). Every value is computed, not generated.",
)
_rooms: "Rooms | None" = None


def bind(rooms: "Rooms") -> None:
    global _rooms
    _rooms = rooms


def _rt(room: str):
    assert _rooms is not None, "MCP server not bound to rooms"
    return _rooms.get(room or "demo")


def _tid(rt, team: str) -> str:
    """Accept a team id, full name or short name."""
    t = team.strip().lower()
    for tm in rt.world.teams.values():
        if t in (tm.id.lower(), tm.name.lower(), tm.short.lower()):
            return tm.id
    raise ValueError(f"unknown team {team!r}; use one of {rt.home}, {rt.away}")


def _pid(rt, player: str) -> str:
    """Accept a player id, initials or surname."""
    player = player.strip()
    cands = [p for t in (rt.home, rt.away) for p in rt.world.teams[t].players]
    for p in cands:
        if player in (p.id, p.initials) or player.lower() in (p.name.lower(), p.name.split()[-1].lower()):
            return p.id
    raise ValueError(f"unknown player {player!r}")


@mcp.tool(description="Live match state: score, clock, team stats.")
def get_match_state(room: str = "demo") -> dict:
    rt = _rt(room)
    return {"clock": rt.snapshot()["match"]["clock"], "score": rt.stats.score, "teamStats": rt.stats.team_stats()}


@mcp.tool(description="A team's expected goals (xG) over the last N minutes of the live match.")
def stats_xg_window(team: str, minutes: int = 15, room: str = "demo") -> dict:
    rt = _rt(room)
    tid = _tid(rt, team)
    return {"team": tid, "minutes": minutes, "xg": rt.stats.xg_window(tid, minutes), "shots": rt.stats.shots_window(tid, minutes)}


@mcp.tool(description="Season Memory: a player's arc (club goals, season goals, dropped/returned, signed).")
def memory_player_arc(player: str, room: str = "demo") -> dict:
    rt = _rt(room)
    return rt.memory.player_arc(_pid(rt, player))


@mcp.tool(description="Season Memory: the player's next club-goal milestone if one goal away.")
def memory_milestones(player: str, room: str = "demo") -> dict:
    rt = _rt(room)
    pid = _pid(rt, player)
    return {"player": pid, "milestone": rt.memory.milestone(pid), "seasonTally": rt.memory.season_tally_target(pid)}


@mcp.tool(description="Season Memory: head-to-head results between two teams (this and last season).")
def memory_h2h(team: str, opponent: str, room: str = "demo") -> list[dict]:
    rt = _rt(room)
    return rt.memory.h2h(_tid(rt, team), _tid(rt, opponent))


@mcp.tool(description="Season Memory: current clean-sheet streak of a team's goalkeeper.")
def memory_clean_sheets(team: str, room: str = "demo") -> dict:
    rt = _rt(room)
    return rt.memory.clean_sheet_streak(_tid(rt, team))


@mcp.tool(description="Season Memory: wins this season decided by a goal after the 80th minute.")
def memory_late_winners(team: str, room: str = "demo") -> dict:
    rt = _rt(room)
    return rt.memory.late_winners(_tid(rt, team))


@mcp.tool(description="Story Radar: current ranked storylines with probability, impact and lifecycle status.")
def radar_storylines(room: str = "demo") -> list[dict]:
    rt = _rt(room)
    return [
        {k: d[k] for k in ("id", "title", "pct", "impact", "status", "why", "memoryLine")}
        for d in (s.public(rt.stats.t) for s in rt.radar.ranked())
    ]
