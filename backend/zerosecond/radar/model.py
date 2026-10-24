"""The documented probability model. Explainable, not LLM-guessed.

Team scoring rate (goals per minute):
    lambda = scale * ((1 - w) * prior + w * recent), x0.75 per red card
    prior  = mean(team scoring rate, opponent conceding rate)   from Season Memory,
             shrunk towards the league average by `prior_games` matches
    recent = team xG over the last 15 minutes / 15                from the Stats Engine
    w      = recent_weight * min(elapsed, 15) / 15
    score effects: after 55', a trailing team's rate x(1 + state_boost),
                   a leading team's rate x(1 - state_boost / 2)

`scale`, `recent_weight`, `prior_games` and `state_boost` are fitted on training matches by
`python -m zerosecond.calibration --fit` (data/model_params.json) and evaluated on
held-out matches.

Player scores before full time:   P = 1 - exp(-lambda_team * share * minutes_left)
Clean sheet holds:                P = exp(-lambda_opp * minutes_left)
Win / late winner:                exact Poisson enumeration of the remaining goals.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path

from ..util import poisson_pmf

WINDOW = 15
MAX_GOALS = 8
PARAMS_FILE = Path(__file__).resolve().parents[2] / "data" / "model_params.json"
PARAMS = {"scale": 1.0, "recent_weight": 0.5, "prior_games": 4.0, "state_boost": 0.0}
if PARAMS_FILE.exists():
    PARAMS.update({k: float(v) for k, v in json.loads(PARAMS_FILE.read_text(encoding="utf-8")).get("params", {}).items()})


@dataclass
class Rate:
    team: str
    lam: float  # goals per minute
    prior: float
    recent: float
    xg_window: float
    weight: float

    def per90(self) -> float:
        return self.lam * 90


def team_rate(prior: float, xg_window: float, elapsed_min: float, reds: int = 0, goal_diff: int = 0) -> Rate:
    span = min(max(elapsed_min, 1.0), WINDOW)
    recent = xg_window / span
    w = PARAMS["recent_weight"] * min(elapsed_min, WINDOW) / WINDOW
    lam = PARAMS["scale"] * ((1 - w) * prior + w * recent)
    lam *= 0.75**reds
    if elapsed_min > 55 and goal_diff != 0:
        lam *= (1 + PARAMS["state_boost"]) if goal_diff < 0 else (1 - PARAMS["state_boost"] / 2)
    return Rate("", lam, prior, recent, xg_window, w)


def p_player_scores(lam_team: float, share: float, minutes_left: float, k: int = 1) -> float:
    """Probability the player scores at least k more goals."""
    mu = max(0.0, lam_team * share * minutes_left)
    return 1 - sum(poisson_pmf(j, mu) for j in range(k))


def p_clean_sheet(lam_opp: float, minutes_left: float) -> float:
    return math.exp(-max(0.0, lam_opp * minutes_left))


def outcome_probs(gf: int, ga: int, lam_f: float, lam_a: float, minutes_left: float) -> dict[str, float]:
    """Final result distribution for the team from the current score."""
    mf, ma = lam_f * minutes_left, lam_a * minutes_left
    win = draw = loss = 0.0
    for x in range(MAX_GOALS):
        px = poisson_pmf(x, mf)
        for y in range(MAX_GOALS):
            p = px * poisson_pmf(y, ma)
            d = (gf + x) - (ga + y)
            if d > 0:
                win += p
            elif d == 0:
                draw += p
            else:
                loss += p
    tot = win + draw + loss
    return {"win": win / tot, "draw": draw / tot, "loss": loss / tot}


def p_late_winner(gf: int, ga: int, lam_f: float, lam_a: float, minute_now: float, cutoff: float = 80.0) -> float:
    """P(team is not ahead at `cutoff` and wins) = the decisive goal comes after the cutoff."""
    if minute_now >= cutoff:
        if gf > ga:
            return 0.0
        return outcome_probs(gf, ga, lam_f, lam_a, 90 - minute_now)["win"]
    t1 = cutoff - minute_now
    total = 0.0
    for x in range(MAX_GOALS):
        px = poisson_pmf(x, lam_f * t1)
        for y in range(MAX_GOALS):
            p = px * poisson_pmf(y, lam_a * t1)
            f, a = gf + x, ga + y
            if f > a or p < 1e-9:
                continue
            total += p * outcome_probs(f, a, lam_f, lam_a, 90 - cutoff)["win"]
    return total
