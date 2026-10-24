"""The demo scenario: Harbour City FC vs Northvale United, Matchweek 12.

Only a handful of moments are pinned (the goals, the post, one card, one sub) so the
demo is repeatable. Every other event is simulated, and Story Radar computes every
probability live from events; nothing about the forecast is scripted. Any other seed
runs the fully random version of the same world.
"""

from __future__ import annotations

import random

from ..stats.metrics import xg as stats_xg
from ..util import make_rng
from .match import MatchConfig, Pin
from .season import SEASON, Goal, Result, SeasonHistory, build_history
from .world import World, build_world

SCENARIO_SEED = 2026
HOME, AWAY = "HFC", "NLU"
MATCHWEEK = 12

# index in the team's player list -> (name, overrides)
HFC_PLAYERS = {
    0: ("Tomas Silva", {}),
    5: ("Alex Reyes", {"passing": 1.22}),
    8: ("Rafael Costa", {"stamina": 0.88}),
    9: ("Kai Mendes", {"finishing": 1.08, "shot_weight": 3.4, "pace_kmh": 34.6}),
    14: ("Jae Park", {"finishing": 1.05, "shot_weight": 2.6, "signed_this_week": True, "club_goals_before_season": 0}),
}
NLU_PLAYERS = {
    9: ("Daniel Okafor", {"finishing": 1.12, "shot_weight": 3.5}),
}

# Authored season lines for the two clubs (MW1..11). For each matchweek:
# (goals for: [(minute, scorer, assist)], minutes conceded). Scorer keys map below.
HFC_SEASON = {
    1: ([(23, "KM", "AR"), (67, "RC", None)], [50]),
    2: ([(40, "AR", "KM")], [72]),
    3: ([(12, "KM", "RC"), (34, "RC", "AR"), (58, "AR", None), (77, "KM", "AR")], []),
    4: ([(30, "RC", "KM"), (86, "AR", "RC")], [55]),
    5: ([(44, "KM", None)], [20, 61]),
    6: ([], [70]),
    7: ([(15, "RC", "AR"), (80, "AR", None)], [33, 66]),
    8: ([(52, "RC", "AR")], []),
    9: ([(83, "AR", "RC")], []),
    10: ([], []),
    11: ([(25, "RC", "AR"), (70, "RC", None)], []),
}
NLU_SEASON = {
    1: ([(10, "DO", None), (55, "DO", None)], []),
    2: ([(70, "DO", None)], [12, 40, 81]),
    3: ([], [12, 34, 58, 77]),
    4: ([(5, "DO", None), (49, "DO", None), (80, "*", None)], [66]),
    5: ([(61, "DO", None)], [30]),
    6: ([(30, "*", None), (88, "DO", None)], [15]),
    7: ([], [22, 75]),
    8: ([(74, "DO", None)], []),
    9: ([(15, "DO", None), (60, "*", None)], [35, 70]),
    10: ([], [58]),
    11: ([(44, "*", None)], []),
}


def _keymap(world: World) -> dict[str, str]:
    h, n = world.teams[HOME].players, world.teams[AWAY].players
    return {"KM": h[9].id, "AR": h[5].id, "RC": h[8].id, "TS": h[0].id, "JP": h[14].id, "DO": n[9].id}


def build_scenario_world() -> World:
    world = build_world(SCENARIO_SEED)
    for team, table in ((HOME, HFC_PLAYERS), (AWAY, NLU_PLAYERS)):
        for idx, (name, overrides) in table.items():
            p = world.teams[team].players[idx]
            p.name = name
            for k, v in overrides.items():
                setattr(p, k, v)
    # Harbour City slightly stronger on paper; Northvale solid away.
    world.teams[HOME].attack, world.teams[HOME].defense = 1.62, 1.18
    world.teams[AWAY].attack, world.teams[AWAY].defense = 1.38, 1.3
    return world


def _apply_line(rng: random.Random, world: World, r: Result, team: str, line, keys: dict[str, str]) -> None:
    """Overwrite one side of a result with an authored line."""
    scored, conceded = line
    opp = r.opponent(team)
    goals = [g for g in r.goals if g.team not in (team, opp)]
    for minute, scorer, assist in scored:
        sid = keys[scorer] if scorer in keys else rng.choice([p.id for p in world.teams[team].starters if p.role in ("FWD", "MID") and p.id not in keys.values()])
        goals.append(Goal(minute, team, sid, keys.get(assist) if assist else None))
    for minute in conceded:
        opp_scorers = [p.id for p in world.teams[opp].starters if p.role in ("FWD", "MID")]
        goals.append(Goal(minute, opp, rng.choice(opp_scorers), None))
    r.goals = sorted(goals, key=lambda g: g.minute)
    gf, ga = len(scored), len(conceded)
    if team == r.home:
        r.hg, r.ag = gf, ga
    else:
        r.hg, r.ag = ga, gf


def build_scenario_history(world: World) -> SeasonHistory:
    hist = build_history(world, MATCHWEEK, forced={3: (AWAY, HOME), MATCHWEEK: (HOME, AWAY)})
    rng = make_rng(SCENARIO_SEED, "scenario-season")
    keys = _keymap(world)
    for r in hist.results:
        if r.season != SEASON:
            continue
        if r.mw == 3 and {r.home, r.away} == {HOME, AWAY}:
            _apply_line(rng, world, r, HOME, HFC_SEASON[3], keys)
            continue
        if HOME in (r.home, r.away):
            _apply_line(rng, world, r, HOME, HFC_SEASON[r.mw], keys)
        if AWAY in (r.home, r.away):
            _apply_line(rng, world, r, AWAY, NLU_SEASON[r.mw], keys)
        if r.mw == 6 and HOME in (r.home, r.away):
            r.dropped = [keys["KM"]]
    # Story arcs for the scenario clubs are authored; others stay random.
    hist.arcs = [a for a in hist.arcs if a.player.split("-")[0] not in (HOME, AWAY)]
    from .season import Arc

    hist.arcs += [
        Arc(keys["KM"], 6, "dropped", "Dropped for Matchweek 6"),
        Arc(keys["KM"], 7, "returned", "Back in the starting XI in Matchweek 7"),
        Arc(keys["JP"], 12, "signed", "Signed this week"),
    ]
    # Mendes: 49 club goals before today.
    km = world.player(keys["KM"])
    season_goals = sum(1 for r in hist.results for g in r.goals if g.scorer == km.id)
    km.club_goals_before_season = 49 - season_goals
    return hist


def _spot_for_xg(target: float, y: float, body: str = "foot") -> tuple[float, float]:
    """Find a shot x (on line y) whose Stats Engine xG is closest to target."""
    best = min((abs(stats_xg(x / 10, y, body) - target), x / 10) for x in range(700, 995))
    return best[1], y


def scenario_config(seed: int = SCENARIO_SEED) -> MatchConfig:
    world = build_scenario_world()
    keys = _keymap(world)
    mx, my = _spot_for_xg(0.12, 36.0)
    cx, cy = _spot_for_xg(0.31, 45.0)
    px, py = _spot_for_xg(0.41, 53.0)
    ox, oy = _spot_for_xg(0.22, 58.0)
    b1x, b1y = _spot_for_xg(0.18, 62.0)
    b2x, b2y = _spot_for_xg(0.24, 47.0)
    b3x, b3y = _spot_for_xg(0.16, 40.0)
    nlu_mid = world.teams[AWAY].players[5].id
    pins = [
        Pin(58 * 60 + 20, "card", HOME, keys["AR"], outcome="yellow"),
        Pin(62 * 60 + 40, "goal", AWAY, keys["DO"], ox, oy, q={"assist": nlu_mid, "speedKmh": 91}),
        Pin(63 * 60 + 50, "shot", HOME, keys["KM"], cx, cy, outcome="saved", q={"speedKmh": 102}),
        Pin(66 * 60 + 35, "shot", HOME, keys["KM"], b1x, b1y, outcome="blocked", q={"speedKmh": 94}),
        Pin(69 * 60 + 50, "shot", HOME, keys["KM"], b2x, b2y, outcome="saved", q={"speedKmh": 104}),
        Pin(70 * 60 + 30, "sub", HOME, keys["JP"], q={"playerOff": keys["RC"]}),
        Pin(73 * 60 + 55, "shot", HOME, keys["KM"], b3x, b3y, outcome="off_target", q={"speedKmh": 99}),
        Pin(77 * 60 + 40, "goal", HOME, keys["KM"], mx, my, q={"assist": keys["AR"], "speedKmh": 98}),
        Pin(88 * 60 + 25, "shot", HOME, keys["JP"], px, py, outcome="post", q={"speedKmh": 87}),
    ]
    return MatchConfig(
        seed=seed,
        home=HOME,
        away=AWAY,
        match_id=f"mw{MATCHWEEK}-{HOME}-{AWAY}",
        matchweek=MATCHWEEK,
        pins=pins,
        suppress_random_goals=True,
        spell_overrides=[(HOME, 55 * 60, 78 * 60, 1.7), (AWAY, 64 * 60, 90 * 60, 0.75)],
        protected={keys["KM"], keys["AR"], keys["TS"], keys["DO"], keys["RC"], keys["JP"]},
    )
