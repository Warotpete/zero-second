"""Live match simulator.

Produces an Opta-style event stream (passes, pressures, tackles, interceptions,
shots, fouls, cards, substitutions, sprints, physical summaries, match metadata).
Coordinates are 0-100 in the acting team's attacking direction, like Opta.

The simulator decides outcomes from *hidden* player traits and a hidden momentum
"spell" process. Nothing downstream can read those; it only sees events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import random
from typing import Any

from ..util import clamp, make_rng
from .world import Player, World

HALF = 45 * 60
FULL = 90 * 60
PITCH_X_M = 105 / 100  # metres per x unit
PITCH_Y_M = 68 / 100  # metres per y unit


def true_xg(x: float, y: float, header: bool = False) -> float:
    """Hidden 'true' chance quality used by the simulator (differs from the Stats Engine's model)."""
    dx = (100 - x) * PITCH_X_M
    dy = (y - 50) * PITCH_Y_M
    dist = math.hypot(dx, dy)
    # angle subtended by the goal mouth (7.32 m)
    a = math.atan2(7.32 * dx, dx * dx + dy * dy - (7.32 / 2) ** 2)
    if a < 0:
        a += math.pi
    z = -0.95 - 0.105 * dist + 1.55 * a - (0.75 if header else 0.0)
    return clamp(1 / (1 + math.exp(-z)), 0.01, 0.92)


@dataclass
class Pin:
    """A scripted moment (used only by the demo scenario)."""

    t: float
    kind: str  # goal | shot | card | sub
    team: str
    player: str
    x: float = 0.0
    y: float = 0.0
    outcome: str = ""
    q: dict[str, Any] = field(default_factory=dict)


@dataclass
class MatchConfig:
    seed: int
    home: str
    away: str
    match_id: str
    matchweek: int
    pins: list[Pin] = field(default_factory=list)
    suppress_random_goals: bool = False
    # (team, from_s, to_s, multiplier) applied to the hidden attacking spell
    spell_overrides: list[tuple[str, float, float, float]] = field(default_factory=list)
    planned_subs: bool = True
    protected: set[str] = field(default_factory=set)  # never subbed off by the random plan


class MatchSimulator:
    def __init__(self, world: World, cfg: MatchConfig):
        self.w = world
        self.cfg = cfg
        self.rng: random.Random = make_rng(cfg.seed, "match", cfg.match_id)
        self.events: list[dict] = []
        self.t = 0.0
        self.score = {cfg.home: 0, cfg.away: 0}
        self.on_pitch = {
            tid: [p.id for p in self.w.teams[tid].starters] for tid in (cfg.home, cfg.away)
        }
        self.bench = {tid: [p.id for p in self.w.teams[tid].bench] for tid in (cfg.home, cfg.away)}
        self.subs_used = {cfg.home: 0, cfg.away: 0}
        self.yellows: set[str] = set()
        self.spell = {cfg.home: 0.0, cfg.away: 0.0}
        self._spell_minute = -1
        self._pins = sorted(cfg.pins, key=lambda p: p.t)
        self._next_phys = 300.0
        self._seq = 0
        self._planned_subs = self._plan_subs() if cfg.planned_subs else []

    # ------------------------------------------------------------------ helpers
    def opp(self, team: str) -> str:
        return self.cfg.away if team == self.cfg.home else self.cfg.home

    def P(self, pid: str) -> Player:
        return self.w.player(pid)

    def emit(self, type_: str, team: str | None = None, player: str | None = None, **kw: Any) -> dict:
        self._seq += 1
        t = round(self.t, 1)
        ev = {
            "id": f"{self.cfg.match_id}-e{self._seq:05d}",
            "matchId": self.cfg.match_id,
            "seq": self._seq,
            "period": 1 if t < HALF else 2,
            "t": t,
            "minute": int(t // 60) + 1,
            "second": int(t % 60),
            "type": type_,
            "team": team,
            "player": player,
        }
        q = kw.pop("q", None)
        ev.update({k: (round(v, 1) if isinstance(v, float) else v) for k, v in kw.items()})
        ev["qualifiers"] = q or {}
        self.events.append(ev)
        return ev

    def _pick(self, team: str, x: float, exclude: str | None = None) -> str:
        """Pick an on-pitch player of `team` likely to be near ball position x."""
        cands, weights = [], []
        for pid in self.on_pitch[team]:
            if pid == exclude:
                continue
            p = self.P(pid)
            if p.role == "GK" and x > 25:
                continue
            target = p.base_x if p.starter else {"DEF": 25, "MID": 45, "FWD": 72, "GK": 5}[p.role]
            w = math.exp(-((x - target) ** 2) / (2 * 22**2)) + 0.05
            cands.append(pid)
            weights.append(w)
        return self.rng.choices(cands, weights)[0]

    def _shooter(self, team: str) -> str:
        cands = [pid for pid in self.on_pitch[team] if self.P(pid).role != "GK"]
        weights = [self.P(pid).shot_weight for pid in cands]
        return self.rng.choices(cands, weights)[0]

    def _y_near(self, pid: str) -> float:
        p = self.P(pid)
        base = p.base_y if p.starter else 50
        return clamp(self.rng.gauss(base, 14), 2, 98)

    def _update_spell(self) -> None:
        minute = int(self.t // 60)
        if minute == self._spell_minute:
            return
        self._spell_minute = minute
        for team in self.spell:
            self.spell[team] = 0.82 * self.spell[team] + self.rng.gauss(0, 0.22)

    def _attack_mult(self, team: str) -> float:
        o = self.opp(team)
        ta, to = self.w.teams[team], self.w.teams[o]
        base = (ta.attack * to.defense / 1.4) / 1.4
        home = 1.06 if team == self.cfg.home else 0.94
        diff = self.score[team] - self.score[o]
        state = 1.0
        if self.t > 55 * 60:
            state = 1.18 if diff < 0 else (0.9 if diff > 0 else 1.0)
        mult = base * home * state * math.exp(self.spell[team])
        for tm, a, b, m in self.cfg.spell_overrides:
            if tm == team and a <= self.t < b:
                mult *= m
        return mult

    # ------------------------------------------------------------------ main
    def run(self) -> list[dict]:
        cfg = self.cfg
        lineups = {
            tid: {
                "starters": [self.P(pid).public() for pid in self.on_pitch[tid]],
                "bench": [self.P(pid).public() for pid in self.bench[tid]],
            }
            for tid in (cfg.home, cfg.away)
        }
        self.emit(
            "match_metadata",
            q={
                "home": cfg.home,
                "away": cfg.away,
                "matchweek": cfg.matchweek,
                "venue": f"{self.w.teams[cfg.home].short} Stadium",
                "referee": "M. Ellison",
                "weather": self.rng.choice(["Clear, 14°C", "Light rain, 11°C", "Overcast, 12°C"]),
                "lineups": lineups,
                "formation": {cfg.home: "4-3-3", cfg.away: "4-3-3"},
            },
        )
        self.emit("period_start", q={"period": 1})
        team = cfg.home
        half_done = False
        while self.t < FULL:
            if self.t >= HALF and not half_done:
                half_done = True
                self.t = HALF
                self.emit("period_end", q={"period": 1})
                self.emit("period_start", q={"period": 2})
                team = cfg.away
            team = self._possession(team, start_x=50 if self.t in (0, HALF) else None)
        self.t = FULL
        self._flush_pins(FULL + 1)
        self.emit("period_end", q={"period": 2})
        self.emit("full_time", q={"score": dict(self.score)})
        # a possession can run a few seconds past 90:00; keep the feed monotonic and inside the match
        for e in self.events:
            if e["t"] > FULL:
                e["t"], e["minute"], e["second"] = float(FULL), 90, 0
        self.events.sort(key=lambda e: (e["t"], e["type"] in ("period_end", "full_time"), e["seq"]))
        return self.events

    def _advance(self, dt: float) -> None:
        self.t += dt
        self._update_spell()
        while self.t >= self._next_phys and self._next_phys <= FULL:
            self._physical(self._next_phys)
            self._next_phys += 300
        self._maybe_sub()

    def _possession(self, team: str, start_x: float | None = None) -> str:
        """Simulate one possession. Returns the team that has the ball next."""
        if self._pins and self._pins[0].t <= self.t:
            return self._flush_pins(self.t, team)
        o = self.opp(team)
        rng = self.rng
        x = start_x if start_x is not None else clamp(rng.gauss(30, 14), 3, 75)
        holder = self._pick(team, x)
        y = self._y_near(holder)
        mult = self._attack_mult(team)
        passing = sum(self.P(pid).passing for pid in self.on_pitch[team]) / len(self.on_pitch[team])
        first_half = self.t < HALF
        for _ in range(40):
            if self.t >= FULL or (first_half and self.t >= HALF):
                return o
            if self._pins and self._pins[0].t <= self.t:
                return self._flush_pins(self.t, team)
            # shot decision in the final third
            if x > 72:
                p_shot = clamp(0.042 * mult * (1 + (x - 72) / 25), 0.005, 0.4)
                if rng.random() < p_shot:
                    self._shot(team, x, y)
                    return o
            # pressure from the opponent (more in the attacking half = high press)
            press_p = 0.18 + 0.22 * (x / 100) + 0.05 * self.spell[o]
            pressured = rng.random() < clamp(press_p, 0.05, 0.6)
            if pressured:
                presser = self._pick(o, 100 - x)
                self.emit("pressure", o, presser, x=100 - x, y=100 - y, q={"on": holder})
            receiver = self._pick(team, min(98, x + 8), exclude=holder)
            dist = clamp(abs(rng.gauss(17, 9)), 4, 55)
            angle = rng.gauss(0.35 if x < 80 else 0.1, 0.9)
            ex = clamp(x + dist / PITCH_X_M * math.cos(angle), 1, 99)
            ey = clamp(y + dist / PITCH_Y_M * math.sin(angle) * 0.6, 1, 99)
            p_ok = 0.95 - 0.006 * max(0, dist - 12) - (0.13 if pressured else 0) - (0.1 if ex > 80 else 0)
            p_ok = clamp(p_ok * (0.85 + 0.15 * passing) * (1 + 0.04 * math.tanh(mult - 1)), 0.25, 0.98)
            ok = rng.random() < p_ok
            speed = clamp(rng.gauss(28 + dist * 1.15, 6), 18, 105)
            self._advance(clamp(rng.gauss(3.2 + dist / 12, 1.2), 1.5, 9))
            self.emit(
                "pass",
                team,
                holder,
                x=x,
                y=y,
                endX=ex,
                endY=ey,
                outcome="complete" if ok else "incomplete",
                q={"receiver": receiver if ok else None, "lengthM": round(dist, 1), "speedKmh": round(speed), "pressured": pressured},
            )
            if self.rng.random() < 0.02 * (1 + abs(self.spell[team])):
                self._sprint(team)
            if not ok:
                winner = self._pick(o, 100 - ex)
                kind = "tackle" if pressured and rng.random() < 0.6 else "interception"
                self.emit(kind, o, winner, x=100 - ex, y=100 - ey, outcome="won")
                if kind == "tackle" and rng.random() < 0.09:
                    self.emit("foul", o, winner, x=100 - ex, y=100 - ey, q={"on": receiver})
                    if rng.random() < 0.22:
                        self._card(o, winner)
                    self._advance(rng.uniform(10, 25))
                    return team  # free kick, team keeps the ball
                self._advance(rng.uniform(1, 3))
                return o
            holder, x, y = receiver, ex, ey
        return o

    def _shot(self, team: str, ball_x: float, ball_y: float, shooter: str | None = None, **forced: Any) -> dict:
        rng = self.rng
        o = self.opp(team)
        shooter = shooter or self._shooter(team)
        sx = forced.get("x", clamp(rng.gauss(83.5, 6.5), 66, 98.5))
        sy = forced.get("y", clamp(rng.gauss(50, 15), 12, 88))
        header = forced.get("header", rng.random() < 0.14 and sx > 88)
        xg = true_xg(sx, sy, header)
        keeper = next((self.P(pid) for pid in self.on_pitch[o] if self.P(pid).role == "GK"), None)
        ks = keeper.keeper_skill if keeper else 1.0
        p_goal = clamp(xg * self.P(shooter).finishing * (2 - ks), 0.005, 0.95)
        outcome = forced.get("outcome")
        if outcome is None:
            u = rng.random()
            if u < p_goal and not self.cfg.suppress_random_goals:
                outcome = "goal"
            else:
                outcome = rng.choices(["post", "blocked", "saved", "off_target"], [0.04, 0.26, 0.33, 0.37])[0]
        assist = forced.get("assist")
        if assist is None and outcome == "goal" and rng.random() < 0.75:
            assist = self._pick(team, sx - 10, exclude=shooter)
        speed = forced.get("speedKmh", round(clamp(rng.gauss(88 if not header else 55, 13), 40, 125)))
        self._advance(rng.uniform(1, 3))
        ev = self.emit(
            "shot",
            team,
            shooter,
            x=sx,
            y=sy,
            outcome=outcome,
            q={"bodyPart": "head" if header else rng.choice(["right_foot", "left_foot"]), "speedKmh": speed, "assist": assist},
        )
        if outcome == "goal":
            self.score[team] += 1
            self._advance(rng.uniform(45, 70))
            self.emit("kickoff", o, None, x=50, y=50)
        else:
            self._advance(rng.uniform(8, 20))
        return ev

    def _card(self, team: str, pid: str, color: str | None = None) -> None:
        color = color or ("red" if pid in self.yellows else "yellow")
        self.yellows.add(pid)
        self.emit("card", team, pid, outcome=color)
        if color == "red" and pid in self.on_pitch[team]:
            self.on_pitch[team].remove(pid)

    def _sprint(self, team: str) -> None:
        pid = self.rng.choice([p for p in self.on_pitch[team] if self.P(p).role != "GK"])
        fatigue = 1 - 0.04 * (self.t / FULL) / self.P(pid).stamina
        speed = clamp(self.rng.gauss(self.P(pid).pace_kmh - 1.2, 1.1) * fatigue, 24, 36.5)
        self.emit("sprint", team, pid, q={"speedKmh": round(speed, 1)})

    def _physical(self, at: float) -> None:
        dist = {}
        for team in (self.cfg.home, self.cfg.away):
            for pid in self.on_pitch[team]:
                p = self.P(pid)
                tired = 1 - 0.06 * (at / FULL) / p.stamina
                dist[pid] = round(p.work_rate_km / 18 * tired * self.rng.uniform(0.92, 1.08), 3)
        saved_t = self.t
        self.t = at
        self.emit("physical", q={"windowS": 300, "distanceKm": dist})
        self.t = saved_t

    def _plan_subs(self) -> list[tuple[float, str, str, str]]:
        plan = []
        for team in (self.cfg.home, self.cfg.away):
            bench = [pid for pid in self.bench[team] if self.P(pid).role != "GK" and pid not in self.cfg.protected]
            self.rng.shuffle(bench)
            for pid_on in bench[:3]:
                role = self.P(pid_on).role
                plan.append((self.rng.uniform(58, 84) * 60, team, role, pid_on))
        return sorted(plan)

    def _maybe_sub(self) -> None:
        while self._planned_subs and self._planned_subs[0][0] <= self.t:
            _, team, role, pid_on = self._planned_subs.pop(0)
            if pid_on not in self.bench[team]:
                continue
            free = [pid for pid in self.on_pitch[team] if pid not in self.cfg.protected]
            outs = [pid for pid in free if self.P(pid).role == role and self.P(pid).starter]
            if not outs:
                outs = [pid for pid in free if self.P(pid).role != "GK"]
            if not outs:
                continue
            pid_off = min(outs, key=lambda pid: self.P(pid).stamina)
            self.substitute(team, pid_off, pid_on)

    def substitute(self, team: str, pid_off: str, pid_on: str) -> None:
        if pid_off not in self.on_pitch[team] or pid_on not in self.bench[team]:
            return
        self.on_pitch[team][self.on_pitch[team].index(pid_off)] = pid_on
        self.bench[team].remove(pid_on)
        self.subs_used[team] += 1
        self.emit("substitution", team, pid_on, q={"playerOff": pid_off, "playerOn": pid_on})

    def _flush_pins(self, until: float, team_with_ball: str | None = None) -> str:
        nxt = team_with_ball or self.cfg.home
        while self._pins and self._pins[0].t <= until:
            pin = self._pins.pop(0)
            self.t = max(self.t, pin.t)
            if pin.kind in ("goal", "shot"):
                self._shot(
                    pin.team,
                    pin.x,
                    pin.y,
                    shooter=pin.player,
                    x=pin.x,
                    y=pin.y,
                    outcome="goal" if pin.kind == "goal" else pin.outcome,
                    assist=pin.q.get("assist"),
                    speedKmh=pin.q.get("speedKmh"),
                    header=pin.q.get("header", False),
                )
                nxt = self.opp(pin.team)
            elif pin.kind == "card":
                self._card(pin.team, pin.player, pin.outcome or "yellow")
            elif pin.kind == "sub":
                self.substitute(pin.team, pin.q["playerOff"], pin.player)
                self._planned_subs = [s for s in self._planned_subs if s[3] != pin.player]
        return nxt


def simulate(world: World, cfg: MatchConfig) -> list[dict]:
    return MatchSimulator(world, cfg).run()
