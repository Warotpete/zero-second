# Model card: Story Radar probability model

## Purpose
Estimate, live, the probability that each active storyline happens before full time, so the system can decide what to prepare and so fans see an honest "how likely".

## Inputs (all deterministic)
- **Season Memory**: each team's scoring and conceding rate this season and last season.
- **Stats Engine**: team xG in the last 15 minutes, player xG share today, score, minute, red cards.

The model never sees the simulator's hidden traits (finishing skill, spells of pressure, fatigue).

## Equations
```
prior(team)   = ½ · (scoring_rate(team) + conceding_rate(opponent))
                each rate = (goals_this_season + 0.3·goals_last_season + 1.35·k) / (games + 0.3·games_last + k),  k = prior_games
recent(team)  = xG in the last 15 minutes / 15
w             = recent_weight · min(elapsed, 15) / 15
λ(team)       = scale · ((1 − w)·prior + w·recent) · 0.75^reds
score effect  : after 55', trailing team λ·(1 + state_boost), leading team λ·(1 − state_boost/2)

player share  = season goal share shrunk to a role prior, renormalised over players on the pitch,
                blended with today's xG share as the team's xG grows
P(player scores ≥ 1)   = 1 − exp(−λ · share · minutes_left)
P(clean sheet holds)   = exp(−λ_opp · minutes_left)
P(team wins)           = Σ over remaining goals x, y ~ Poisson(λ·t) with final margin > 0
P(late winner)         = P(not ahead at 80' and wins) via two-phase Poisson enumeration
```
Ranking score = probability × impact weight (HIGH 3, MED 2, LOW 1). "Why rising" is generated from the change in the inputs (e.g. *HFC xG last 15': 0.13 → 1.02*), not by a language model.

## Fitting and evaluation
`python -m zerosecond.calibration --fit 60 --matches 200`
- Grid search over `scale`, `recent_weight`, `prior_games`, `state_boost` on **60 training matches** (seeds 50000+), minimising the Brier score.
- Evaluation on **200 held-out matches** (seeds 10000+), sampling every live storyline at 10', 25', 40', 55', 70', 80'.

Fitted parameters (`backend/data/model_params.json`): scale 0.65, recent_weight 0.10, prior_games 4, state_boost 1.0.

| Predicted bin | n | Predicted | Actual |
|---|---|---|---|
| 0–5% | 2226 | 1.7% | 2.2% |
| 5–10% | 943 | 7.3% | 6.5% |
| 10–20% | 564 | 13.8% | 14.5% |
| 20–30% | 288 | 25.0% | 18.1% |
| 30–40% | 83 | 33.2% | 27.7% |
| 60–70% | 30 | 65.8% | 40.0% |
| 70–80% | 74 | 74.7% | 62.2% |
| 80–100% | 84 | 92.9% | 92.9% |

Brier 0.0628 vs 0.0852 for a constant base-rate forecast (skill 26%).

## Known limitations
- Team-result storylines above 60% (mostly "revenge" wins while leading) are over-confident: leading teams concede more often than the model expects. Samples are small (n = 30, 74).
- Clean-sheet streak storylines are over-confident (n = 27): streaks partly reflect luck, and the prior shrinks conceding rates only lightly.
- Rare "redemption" storylines are under-confident.
- Calibrated on PitchForge matches. On a real feed the same fitting script would be re-run on historical data.

Next steps: per-kind calibration (isotonic regression on top of the model), separate shrinkage for conceding, more training matches.
