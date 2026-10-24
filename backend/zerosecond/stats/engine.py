"""Incremental Stats Engine.

`ingest(event)` updates running totals; `snapshot()` returns everything the UI,
Story Radar and agents need. Every number shown to a user comes from here or from
Season Memory, never from a language model.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from ..util import clamp
from .metrics import BIG_CHANCE_XG, in_box, pass_difficulty, xg

SPRINT_TAG_KMH = 33.0
DISTANCE_TAG_KM = 11.0
PRESSURE_SPIKE = 4  # final-third pressures in 3 minutes


@dataclass
class PlayerLine:
    passes: int = 0
    completed: int = 0
    difficulty_sum: float = 0.0
    shots: int = 0
    on_target: int = 0
    xg: float = 0.0
    goals: int = 0
    assists: int = 0
    big_chances: int = 0
    box_touches: int = 0
    tackles: int = 0
    interceptions: int = 0
    pressures: int = 0
    distance_km: float = 0.0
    top_speed: float = 0.0
    yellow: int = 0
    red: int = 0

    def rating(self) -> float:
        r = 6.3 + 1.1 * self.goals + 0.7 * self.assists + 0.5 * self.xg + 0.05 * self.completed / 4
        r += 0.15 * (self.tackles + self.interceptions) + 0.02 * self.pressures - 0.4 * self.yellow - 1.5 * self.red
        if self.passes >= 10:
            r += (self.completed / self.passes - 0.82) * 2
        return round(clamp(r, 3.0, 10.0), 1)

    def public(self) -> dict:
        d = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in self.__dict__.items()}
        d["passAccuracy"] = round(100 * self.completed / self.passes) if self.passes else None
        d["avgPassDifficulty"] = round(self.difficulty_sum / self.passes, 1) if self.passes else None
        d["rating"] = self.rating()
        return d


@dataclass
class TeamLine:
    passes: int = 0
    completed: int = 0
    shots: int = 0
    on_target: int = 0
    xg: float = 0.0
    big_chances: int = 0
    tackles: int = 0
    interceptions: int = 0
    pressures: int = 0
    fouls: int = 0
    yellow: int = 0
    red: int = 0
    top_ball_speed: float = 0.0
    top_shot_speed: float = 0.0
    box_touches: int = 0


@dataclass
class Insight:
    """A deterministic observation (pressure spike, sprint tag ...) that may become evidence."""

    id: str
    t: float
    minute: int
    kind: str
    team: str | None
    player: str | None
    text: str
    data: dict = field(default_factory=dict)


class StatsEngine:
    def __init__(self, home: str, away: str):
        self.home, self.away = home, away
        self.t = 0.0
        self.score = {home: 0, away: 0}
        self.team = {home: TeamLine(), away: TeamLine()}
        self.players: dict[str, PlayerLine] = defaultdict(PlayerLine)
        self.player_team: dict[str, str] = {}
        self.on_pitch: dict[str, list[str]] = {home: [], away: []}
        self.bench: dict[str, list[str]] = {home: [], away: []}
        self.debut: set[str] = set()
        self.goals: list[dict] = []
        self.cards: list[dict] = []
        self.subs: list[dict] = []
        self.shots: list[dict] = []
        self.events_by_id: dict[str, dict] = {}
        self.timeline: list[dict] = []  # notable events for the feed
        self.insights: list[Insight] = []
        # per-minute series
        self.threat = {home: defaultdict(float), away: defaultdict(float)}
        self.turnovers = defaultdict(int)
        self.passes_min = defaultdict(int)
        self.xg_min = {home: defaultdict(float), away: defaultdict(float)}
        self.shots_min = {home: defaultdict(int), away: defaultdict(int)}
        self.final_third_press = {home: deque(), away: deque()}
        self._last_spike = {home: -999.0, away: -999.0}
        self._tagged: set[tuple[str, str]] = set()
        self.metadata: dict = {}
        self.finished = False
        self.names: dict[str, str] = {}  # player id -> display name, set by the runtime
        self.team_names: dict[str, str] = {}

    def opp(self, team: str) -> str:
        return self.away if team == self.home else self.home

    # --------------------------------------------------------------- ingest
    def ingest(self, e: dict) -> list[Insight]:
        self.t = max(self.t, e["t"])
        self.events_by_id[e["id"]] = e
        typ, team, pid, q = e["type"], e.get("team"), e.get("player"), e.get("qualifiers", {})
        minute = e["minute"]
        new: list[Insight] = []
        if pid and team:
            self.player_team[pid] = team
        if typ == "match_metadata":
            self.metadata = q
            for tid in (self.home, self.away):
                self.on_pitch[tid] = [p["id"] for p in q["lineups"][tid]["starters"]]
                self.bench[tid] = [p["id"] for p in q["lineups"][tid]["bench"]]
                for p in q["lineups"][tid]["starters"] + q["lineups"][tid]["bench"]:
                    self.player_team[p["id"]] = tid
        elif typ == "pass":
            tl, pl = self.team[team], self.players[pid]
            ok = e["outcome"] == "complete"
            diff = pass_difficulty(q.get("lengthM", 15), q.get("pressured", False), e["x"], e["endX"])
            e["_difficulty"] = diff
            tl.passes += 1
            pl.passes += 1
            pl.difficulty_sum += diff
            self.passes_min[minute] += 1
            if ok:
                tl.completed += 1
                pl.completed += 1
                if e["endX"] > 66:
                    self.threat[team][minute] += 0.25 + (0.35 if e["endX"] > 83 else 0)
                if in_box(e["endX"], e["endY"]) and q.get("receiver"):
                    self.players[q["receiver"]].box_touches += 1
                    tl.box_touches += 1
            else:
                self.turnovers[minute] += 1
            tl.top_ball_speed = max(tl.top_ball_speed, q.get("speedKmh", 0))
        elif typ == "shot":
            body = "head" if q.get("bodyPart") == "head" else "foot"
            val = xg(e["x"], e["y"], body)
            e["_xg"] = val
            tl, pl = self.team[team], self.players[pid]
            tl.shots += 1
            pl.shots += 1
            tl.xg += val
            pl.xg += val
            self.xg_min[team][minute] += val
            self.shots_min[team][minute] += 1
            self.threat[team][minute] += 1.0 + 8 * val
            if in_box(e["x"], e["y"]):
                pl.box_touches += 1
            if val >= BIG_CHANCE_XG:
                tl.big_chances += 1
                pl.big_chances += 1
            if e["outcome"] in ("goal", "saved", "post"):
                tl.on_target += e["outcome"] != "post"
                pl.on_target += e["outcome"] != "post"
            tl.top_shot_speed = max(tl.top_shot_speed, q.get("speedKmh", 0))
            tl.top_ball_speed = max(tl.top_ball_speed, q.get("speedKmh", 0))
            shot = {
                "id": e["id"], "t": e["t"], "minute": minute, "team": team, "player": pid,
                "x": e["x"], "y": e["y"], "xg": val, "outcome": e["outcome"],
                "speedKmh": q.get("speedKmh"), "assist": q.get("assist"), "bodyPart": q.get("bodyPart"),
            }
            self.shots.append(shot)
            if e["outcome"] == "goal":
                self.score[team] += 1
                pl.goals += 1
                if q.get("assist"):
                    self.players[q["assist"]].assists += 1
                g = dict(shot, score=dict(self.score))
                self.goals.append(g)
                self._feed(e, "goal", f"GOAL {self._name(pid)}", g)
            elif e["outcome"] == "post" or val >= BIG_CHANCE_XG:
                label = "hits the post" if e["outcome"] == "post" else f"big chance ({e['outcome'].replace('_', ' ')})"
                self._feed(e, "chance", f"{self._name(pid)} {label}", shot)
            elif e["outcome"] in ("saved", "blocked"):
                self._feed(e, "shot", f"{self._name(pid)} shot {e['outcome']}", shot)
        elif typ in ("tackle", "interception"):
            setattr(self.team[team], typ + "s", getattr(self.team[team], typ + "s") + 1)
            setattr(self.players[pid], typ + "s", getattr(self.players[pid], typ + "s") + 1)
            self.turnovers[minute] += 0  # turnovers already counted on the failed pass
        elif typ == "pressure":
            self.team[team].pressures += 1
            self.players[pid].pressures += 1
            if e["x"] > 66:
                dq = self.final_third_press[team]
                dq.append(e["t"])
                while dq and dq[0] < e["t"] - 180:
                    dq.popleft()
                if len(dq) >= PRESSURE_SPIKE and e["t"] - self._last_spike[team] > 300:
                    self._last_spike[team] = e["t"]
                    ins = self._insight(e, "pressure_spike", team, None, f"{self._tname(team)} pressure spike in the final third", {"pressures3min": len(dq)})
                    new.append(ins)
                    self._feed(e, "pressure", ins.text, ins.data)
        elif typ == "foul":
            self.team[team].fouls += 1
        elif typ == "card":
            color = e["outcome"]
            setattr(self.team[team], color, getattr(self.team[team], color) + 1)
            setattr(self.players[pid], color, getattr(self.players[pid], color) + 1)
            c = {"id": e["id"], "t": e["t"], "minute": minute, "team": team, "player": pid, "color": color}
            self.cards.append(c)
            self._feed(e, "card", f"{color.title()} card {self._name(pid)}", c)
            if color == "red" and pid in self.on_pitch[team]:
                self.on_pitch[team].remove(pid)
        elif typ == "substitution":
            off, on = q["playerOff"], q["playerOn"]
            if off in self.on_pitch[team]:
                self.on_pitch[team][self.on_pitch[team].index(off)] = on
            if on in self.bench[team]:
                self.bench[team].remove(on)
            s = {"id": e["id"], "t": e["t"], "minute": minute, "team": team, "on": on, "off": off}
            self.subs.append(s)
            self._feed(e, "sub", f"{self._name(on)} on for {self._name(off)}", s)
        elif typ == "sprint":
            pl = self.players[pid]
            pl.top_speed = max(pl.top_speed, q["speedKmh"])
            if q["speedKmh"] >= SPRINT_TAG_KMH and (pid, "sprint") not in self._tagged:
                self._tagged.add((pid, "sprint"))
                new.append(self._insight(e, "player_tag", team, pid, f"{self._name(pid)} · {q['speedKmh']} km/h", {"speedKmh": q["speedKmh"]}))
        elif typ == "physical":
            for p, km in q["distanceKm"].items():
                pl = self.players[p]
                pl.distance_km += km
                if pl.distance_km >= DISTANCE_TAG_KM and (p, "distance") not in self._tagged:
                    self._tagged.add((p, "distance"))
                    new.append(self._insight(e, "player_tag", self.player_team.get(p), p, f"{self._name(p)} passes 11 km covered", {"distanceKm": round(pl.distance_km, 1)}))
        elif typ == "full_time":
            self.finished = True
            self._feed(e, "ft", "Full time", {"score": dict(self.score)})
        elif typ == "period_end" and q.get("period") == 1:
            self._feed(e, "ht", "Half time", {"score": dict(self.score)})
        return new

    # --------------------------------------------------------------- helpers
    def _name(self, pid: str | None) -> str:
        return self.names.get(pid or "", pid or "")

    def _tname(self, tid: str) -> str:
        return self.team_names.get(tid, tid)

    def _feed(self, e: dict, kind: str, text: str, data: dict) -> None:
        self.timeline.append({"id": e["id"], "t": e["t"], "minute": e["minute"], "kind": kind, "team": e.get("team"), "player": e.get("player"), "text": text, "data": data})

    def _insight(self, e: dict, kind: str, team: str | None, pid: str | None, text: str, data: dict) -> Insight:
        ins = Insight(f"ins-{e['id']}", e["t"], e["minute"], kind, team, pid, text, data)
        self.insights.append(ins)
        return ins

    # --------------------------------------------------------------- queries
    def minute_now(self) -> int:
        return int(self.t // 60) + 1

    def xg_window(self, team: str, minutes: int, end_minute: int | None = None) -> float:
        end = end_minute if end_minute is not None else self.minute_now()
        return round(sum(v for m, v in self.xg_min[team].items() if end - minutes < m <= end), 3)

    def shots_window(self, team: str, minutes: int) -> int:
        end = self.minute_now()
        return sum(v for m, v in self.shots_min[team].items() if end - minutes < m <= end)

    def momentum(self) -> list[dict]:
        """Per-minute momentum: smoothed threat difference, positive = home on top."""
        out, ema = [], 0.0
        for m in range(1, min(self.minute_now(), 90) + 1):
            raw = self.threat[self.home][m] - self.threat[self.away][m]
            ema = 0.55 * ema + 0.45 * raw
            out.append({"minute": m, "value": round(clamp(ema, -3, 3), 2)})
        return out

    def control_chaos(self, window: int = 10) -> dict:
        """0 = controlled (long sequences, few turnovers), 1 = chaotic (end-to-end)."""
        end = self.minute_now()
        mins = range(max(1, end - window + 1), end + 1)
        passes = sum(self.passes_min[m] for m in mins)
        turnovers = sum(self.turnovers[m] for m in mins)
        shots = sum(self.shots_min[t][m] for t in (self.home, self.away) for m in mins)
        if passes == 0:
            return {"index": 0.5, "label": "settling"}
        rate = turnovers / passes  # ~0.12 controlled .. ~0.22 chaotic
        idx = clamp((rate - 0.1) / 0.13 + 0.04 * (shots - 2), 0, 1)
        label = "chaotic" if idx > 0.66 else ("controlled" if idx < 0.33 else "balanced")
        return {"index": round(idx, 2), "label": label, "turnoverRate": round(rate, 3)}

    def possession(self) -> dict:
        h, a = self.team[self.home].passes, self.team[self.away].passes
        tot = h + a or 1
        return {self.home: round(100 * h / tot), self.away: 100 - round(100 * h / tot)}

    def team_stats(self) -> dict:
        poss = self.possession()
        out = {}
        for tid, tl in self.team.items():
            out[tid] = {
                "possession": poss[tid],
                "xg": round(tl.xg, 2),
                "shots": tl.shots,
                "onTarget": tl.on_target,
                "bigChances": tl.big_chances,
                "passes": tl.passes,
                "passAccuracy": round(100 * tl.completed / tl.passes) if tl.passes else 0,
                "tackles": tl.tackles,
                "interceptions": tl.interceptions,
                "pressures": tl.pressures,
                "fouls": tl.fouls,
                "yellow": tl.yellow,
                "red": tl.red,
                "topBallSpeed": round(tl.top_ball_speed),
                "topShotSpeed": round(tl.top_shot_speed),
                "boxTouches": tl.box_touches,
            }
        return out

    def player_stats(self, pid: str) -> dict:
        d = self.players[pid].public()
        d["onPitch"] = pid in self.on_pitch.get(self.player_team.get(pid, ""), [])
        return d
