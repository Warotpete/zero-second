"""Season history: last season's results plus this season up to the current matchweek.

Results are generated with a simple team-strength Poisson model; goal minutes and
scorers are sampled from player traits. Season Memory is built from this.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import random

from ..util import make_rng
from .world import World

SEASON = "2026/27"
LAST_SEASON = "2025/26"


@dataclass
class Goal:
    minute: int
    team: str
    scorer: str
    assist: str | None = None


@dataclass
class Result:
    season: str
    mw: int
    home: str
    away: str
    hg: int
    ag: int
    goals: list[Goal] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)  # starters left out this match

    @property
    def id(self) -> str:
        tag = "ls" if self.season == LAST_SEASON else "mw"
        return f"{tag}{self.mw}-{self.home}-{self.away}"

    def score_for(self, team: str) -> tuple[int, int]:
        return (self.hg, self.ag) if team == self.home else (self.ag, self.hg)

    def opponent(self, team: str) -> str:
        return self.away if team == self.home else self.home

    def public(self) -> dict:
        return {
            "id": self.id,
            "season": self.season,
            "mw": self.mw,
            "home": self.home,
            "away": self.away,
            "hg": self.hg,
            "ag": self.ag,
            "goals": [g.__dict__ for g in self.goals],
        }


@dataclass
class Arc:
    player: str
    mw: int
    kind: str  # dropped | returned | signed | injury
    note: str


@dataclass
class SeasonHistory:
    current_mw: int
    results: list[Result]  # this season, MW1..current_mw-1
    last_season: list[Result]
    fixtures: list[tuple[str, str]]  # current matchweek
    arcs: list[Arc] = field(default_factory=list)


def round_robin(team_ids: list[str]) -> list[list[tuple[str, str]]]:
    """Circle-method double round robin. Returns 2*(n-1) rounds of (home, away)."""
    n = len(team_ids)
    fixed, rot = team_ids[-1], team_ids[:-1]
    rounds = []
    for r in range(n - 1):
        pairs = []
        for i in range(n - 1):
            j = (r - i) % (n - 1)
            if i < j:
                a, b = rot[i], rot[j]
                pairs.append((a, b) if (i + r) % 2 == 0 else (b, a))
            elif i == j:
                pairs.append((rot[i], fixed) if r % 2 == 0 else (fixed, rot[i]))
        rounds.append(pairs)
    second = [[(b, a) for a, b in rnd] for rnd in rounds]
    return rounds + second


def force_fixture(rnd: list[tuple[str, str]], home: str, away: str) -> list[tuple[str, str]]:
    """Make home-vs-away happen in this round by swapping opponents."""
    if (home, away) in rnd:
        return rnd
    rest, freed = [], []
    for h, a in rnd:
        if {h, a} & {home, away}:
            freed += [t for t in (h, a) if t not in (home, away)]
        else:
            rest.append((h, a))
    out = rest + [(home, away)]
    if len(freed) == 2:
        out.append((freed[0], freed[1]))
    return out


def _pick_scorer(rng: random.Random, world: World, team: str, exclude: set[str]) -> str:
    cands = [p for p in world.teams[team].starters if p.role != "GK" and p.id not in exclude]
    weights = [p.shot_weight * p.finishing for p in cands]
    return rng.choices(cands, weights)[0].id


def _pick_assist(rng: random.Random, world: World, team: str, scorer: str) -> str | None:
    if rng.random() < 0.25:
        return None
    cands = [p for p in world.teams[team].starters if p.role != "GK" and p.id != scorer]
    weights = [1.6 if p.role == "MID" else 1.0 for p in cands]
    return rng.choices(cands, weights)[0].id


def sample_result(
    rng: random.Random, world: World, season: str, mw: int, home: str, away: str, dropped: set[str] | None = None
) -> Result:
    th, ta = world.teams[home], world.teams[away]
    mu_h = th.attack * ta.defense / 1.4 * 1.08
    mu_a = ta.attack * th.defense / 1.4 * 0.92
    hg, ag = _poisson(rng, mu_h), _poisson(rng, mu_a)
    goals = []
    for team, n in ((home, hg), (away, ag)):
        for _ in range(n):
            scorer = _pick_scorer(rng, world, team, dropped or set())
            goals.append(Goal(rng.randint(1, 90), team, scorer, _pick_assist(rng, world, team, scorer)))
    goals.sort(key=lambda g: g.minute)
    return Result(season, mw, home, away, hg, ag, goals, sorted(dropped or []))


def _poisson(rng: random.Random, mu: float) -> int:
    limit, k, p = math.exp(-mu), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def break_fixture(rnd: list[tuple[str, str]], a: str, b: str) -> list[tuple[str, str]]:
    """Remove a meeting of a and b from this round by swapping with another pair."""
    idx = next((i for i, (h, w) in enumerate(rnd) if {h, w} == {a, b}), None)
    if idx is None:
        return rnd
    other = 0 if idx != 0 else 1
    (x, y), (c, d) = rnd[idx], rnd[other]
    out = [p for i, p in enumerate(rnd) if i not in (idx, other)]
    return out + [(x, c), (d, y)]


def build_history(
    world: World, current_mw: int = 12, forced: dict[int, tuple[str, str]] | None = None
) -> SeasonHistory:
    rng = make_rng(world.seed, "season")
    ids = list(world.teams)
    order = ids[:]
    rng.shuffle(order)
    rounds = round_robin(order)
    for mw, (h, a) in (forced or {}).items():
        for r in range(current_mw):
            if r + 1 != mw and r + 1 not in (forced or {}):
                rounds[r] = break_fixture(rounds[r], h, a)
        rounds[mw - 1] = force_fixture(rounds[mw - 1], h, a)

    last = []
    rounds_ls = round_robin(sorted(ids))
    for mw, rnd in enumerate(rounds_ls, start=1):
        for h, a in rnd:
            last.append(sample_result(rng, world, LAST_SEASON, mw, h, a))

    arcs: list[Arc] = []
    dropped_at: dict[str, int] = {}
    for team in world.teams.values():
        fwds = [p for p in team.starters if p.role == "FWD"]
        if fwds and rng.random() < 0.35:
            p = rng.choice(fwds)
            mw = rng.randint(3, current_mw - 2)
            dropped_at[p.id] = mw
            arcs.append(Arc(p.id, mw, "dropped", f"Dropped for Matchweek {mw}"))
            arcs.append(Arc(p.id, mw + 1, "returned", f"Back in the starting XI in Matchweek {mw + 1}"))

    results = []
    for mw in range(1, current_mw):
        for h, a in rounds[mw - 1]:
            dropped = {pid for pid, d in dropped_at.items() if d == mw and pid.split("-")[0] in (h, a)}
            results.append(sample_result(rng, world, SEASON, mw, h, a, dropped))
    return SeasonHistory(current_mw, results, last, rounds[current_mw - 1], arcs)
