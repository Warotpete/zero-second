"""Match runtime: replays a PitchForge match as a live feed and runs the whole pipeline.

Ingest (events up to the match clock) -> Stats Engine -> Story Radar -> Orchestrator.
Each "room" is an independent match, so several viewers/judges can run their own.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict

from .agents.orchestrator import Orchestrator
from .memory.store import SeasonMemory
from .pitchforge.match import FULL, MatchConfig, simulate
from .pitchforge.scenario import SCENARIO_SEED, build_scenario_history, build_scenario_world, scenario_config
from .pitchforge.season import build_history
from .pitchforge.world import build_world
from .radar.radar import StoryRadar
from .stats.engine import StatsEngine
from .util import clock, make_rng, short_name

log = logging.getLogger("zerosecond.runtime")

SPEEDS = [1, 10, 20, 40, 90]  # match seconds per real second
DEFAULT_SPEED = 20


class MatchRuntime:
    def __init__(self, room: str, seed: int = SCENARIO_SEED, agents=None):
        self.room = room
        self.seed = seed
        self.scenario = seed == SCENARIO_SEED
        if self.scenario:
            self.world = build_scenario_world()
            history = build_scenario_history(self.world)
            cfg = scenario_config(seed)
        else:
            self.world = build_world(seed)
            history = build_history(self.world)
            home, away = make_rng(seed, "fixture").choice(history.fixtures)
            cfg = MatchConfig(seed, home, away, f"mw{history.current_mw}-{home}-{away}", history.current_mw)
        self.cfg = cfg
        self.home, self.away = cfg.home, cfg.away
        self.matchweek = cfg.matchweek
        self.memory = SeasonMemory(self.world, history)
        self.events = simulate(self.world, cfg)
        self.stats = StatsEngine(self.home, self.away)
        self.stats.names = {p.id: short_name(p.name) for p in self.world.all_players()}
        self.stats.team_names = {t.id: t.short for t in self.world.teams.values()}
        self.radar = StoryRadar(self.world, self.memory, self.stats, self.home, self.away)
        self.extra_lines: dict = {}
        self.orch = Orchestrator(self, agents)
        self.cursor = 0
        self.clock = 0.0
        self.speed = DEFAULT_SPEED
        self.playing = False
        self.created = time.time()
        self.touched = time.time()
        self.recap_started = False
        self._last_tick = time.monotonic()
        self.version = 0

    # ------------------------------------------------------------------ clock
    def ingest_until(self, t: float) -> None:
        while self.cursor < len(self.events) and self.events[self.cursor]["t"] <= t:
            e = self.events[self.cursor]
            self.cursor += 1
            self.stats.ingest(e)
            fired = self.radar.on_event(e)
            for s in fired:
                self.orch.on_trigger(s, e)
            if e["type"] == "shot" and e["outcome"] == "goal" and not any(s.player == e["player"] for s in fired):
                self.orch.reactive_goal(e)
            if e["type"] in ("shot", "substitution", "card", "full_time", "period_start"):
                self.radar.update()
        self.clock = max(self.clock, min(t, self.events[-1]["t"]))
        self.radar.update()
        self.orch.plan()
        if self.stats.finished and not self.recap_started:
            self.recap_started = True
            self.orch._spawn(self.orch.build_recap())
        self.version += 1

    def tick(self) -> None:
        now = time.monotonic()
        dt, self._last_tick = now - self._last_tick, now
        if not self.playing or self.finished:
            return
        self.ingest_until(self.clock + dt * self.speed)

    @property
    def finished(self) -> bool:
        return self.cursor >= len(self.events)

    async def jump(self, minute: float) -> None:
        """Fast-forward, letting agents work at each minute so the state is realistic."""
        target = min(minute * 60, FULL + 1)
        t = self.clock
        while t < target:
            t = min(target, t + 60)
            self.ingest_until(t)
            if self.orch.tasks:
                await asyncio.wait(list(self.orch.tasks), timeout=0.05 if self.orch.llm else 2)
        self._last_tick = time.monotonic()

    def control(self, action: str, value: float | None = None) -> None:
        if action == "play":
            self.playing = True
            self._last_tick = time.monotonic()
        elif action == "pause":
            self.playing = False
        elif action == "speed" and value is not None:
            self.speed = float(value)
        elif action == "autopilot":
            self.orch.autopilot = bool(value)
        elif action == "fault":
            self.orch.fault_injection = bool(value)

    # ------------------------------------------------------------------ views
    def _player(self, pid: str | None) -> dict | None:
        if not pid:
            return None
        p = self.world.player(pid)
        return {"id": p.id, "name": p.name, "short": short_name(p.name), "last": p.name.split()[-1], "initials": p.initials, "team": p.team_id, "number": p.number, "position": p.position}

    def _ball(self) -> dict:
        for e in reversed(self.events[: self.cursor]):
            if e.get("x") is not None and e.get("team"):
                x, y = e.get("endX", e["x"]) if e["type"] == "pass" else e["x"], e.get("endY", e["y"]) if e["type"] == "pass" else e["y"]
                if e["team"] == self.away:
                    x, y = 100 - x, 100 - y
                return {"x": round(x, 1), "y": round(y, 1), "team": e["team"], "type": e["type"]}
        return {"x": 50, "y": 50, "team": None, "type": None}

    def lineups(self) -> dict:
        out = {}
        for tid in (self.home, self.away):
            on = self.stats.on_pitch[tid]
            players = []
            for pid in on + self.stats.bench[tid]:
                d = self._player(pid)
                p = self.world.player(pid)
                d.update({"onPitch": pid in on, "role": p.role, "baseX": p.base_x if p.starter else {"DEF": 25, "MID": 45, "FWD": 72, "GK": 5}[p.role], "baseY": p.base_y if p.starter else 50})
                d["stats"] = self.stats.player_stats(pid)
                players.append(d)
            out[tid] = players
        return out

    def snapshot(self) -> dict:
        st, r, o = self.stats, self.radar, self.orch
        now = st.t
        storylines = [s.public(now) for s in r.lines.values()]
        for s in self.extra_lines.values():
            storylines.append(s.public(now))
        ranked = [s.id for s in r.ranked()]
        tags = [
            {"player": self._player(i.player), "text": i.text, "minute": i.minute, "data": i.data}
            for i in st.insights
            if i.kind == "player_tag" and now - i.t <= 150 and "speedKmh" in i.data
        ]
        cc = st.control_chaos()
        teams = {tid: {**self.world.teams[tid].public(), "form": self.memory.form(tid)} for tid in (self.home, self.away)}
        return {
            "room": self.room,
            "seed": self.seed,
            "scenario": self.scenario,
            "version": self.version,
            "backend": o.backend,
            "match": {
                "id": self.cfg.match_id,
                "matchweek": self.matchweek,
                "home": teams[self.home],
                "away": teams[self.away],
                "score": {"home": st.score[self.home], "away": st.score[self.away]},
                "clock": clock(self.clock),
                "t": self.clock,
                "minute": st.minute_now(),
                "period": 1 if self.clock < 45 * 60 else 2,
                "finished": st.finished,
                "venue": st.metadata.get("venue"),
                "goals": [{**g, "playerInfo": self._player(g["player"])} for g in st.goals],
            },
            "control": {"playing": self.playing, "speed": self.speed, "speeds": SPEEDS, "autopilot": o.autopilot, "faultInjection": o.fault_injection},
            "feed": list(reversed(st.timeline[-40:])),
            "momentum": st.momentum(),
            "controlChaos": cc,
            "teamStats": st.team_stats(),
            "ball": self._ball(),
            "tags": tags[-3:],
            "storylines": storylines,
            "ranked": ranked,
            "evidence": {s.id: r.evidence(s) for s in r.lines.values() if not s.resolved},
            "content": {k: c.public() for k, c in o.content.items()},
            "traces": o.traces,
            "audit": o.audit[-80:],
            "moments": list(reversed(o.moments)),
            "overlays": o.overlays,
            "agents": o.agent_state,
            "recap": o.recap,
            "lifecycle": r.log[-60:],
        }


class Rooms:
    """Bounded set of live matches (LRU)."""

    def __init__(self, agents=None, max_rooms: int = 8):
        self.rooms: OrderedDict[str, MatchRuntime] = OrderedDict()
        self.agents = agents
        self.max_rooms = max_rooms

    def get(self, room: str) -> MatchRuntime:
        rt = self.rooms.get(room)
        if rt is None:
            rt = self.new(room)
        self.rooms.move_to_end(room)
        rt.touched = time.time()
        return rt

    def new(self, room: str, seed: int = SCENARIO_SEED) -> MatchRuntime:
        old = self.rooms.pop(room, None)
        if old:
            for t in list(old.orch.tasks):
                t.cancel()
        rt = MatchRuntime(room, seed, self.agents)
        rt.ingest_until(0.5)  # metadata + kickoff
        self.rooms[room] = rt
        while len(self.rooms) > self.max_rooms:
            self.rooms.popitem(last=False)
        return rt

    async def run(self) -> None:
        while True:
            for rt in list(self.rooms.values()):
                try:
                    rt.tick()
                except Exception:
                    log.exception("tick failed in room %s", rt.room)
            await asyncio.sleep(0.25)
