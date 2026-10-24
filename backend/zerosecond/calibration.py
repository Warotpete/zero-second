"""Forecast calibration: do storylines rated X% happen X% of the time?

Runs N random-seed matches (no scripted moments), samples every live storyline's
probability at fixed minutes, and compares with the outcome. The simulator decides
outcomes from hidden traits; Story Radar only sees events, so this is a fair test.

    python -m zerosecond.calibration --matches 200
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .memory.store import SeasonMemory
from .pitchforge.match import MatchConfig, simulate
from .pitchforge.season import build_history
from .pitchforge.world import build_world
from .radar import model
from .radar.radar import StoryRadar
from .stats.engine import StatsEngine
from .util import make_rng

CHECK_MINUTES = [10, 25, 40, 55, 70, 80]
BINS = [0, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.01]


def run_match(seed: int) -> list[tuple[float, int, str]]:
    world = build_world(seed)
    hist = build_history(world)
    home, away = make_rng(seed, "fixture").choice(hist.fixtures)
    mem = SeasonMemory(world, hist)
    events = simulate(world, MatchConfig(seed, home, away, f"cal-{seed}", hist.current_mw))
    stats = StatsEngine(home, away)
    radar = StoryRadar(world, mem, stats, home, away)
    samples: dict[str, list[float]] = {}
    checks = iter(CHECK_MINUTES)
    nxt = next(checks)
    for e in events:
        stats.ingest(e)
        radar.on_event(e)
        if nxt is not None and e["t"] >= nxt * 60:
            radar.update()
            for s in radar.lines.values():
                if not s.resolved and s.p > 0.0:
                    samples.setdefault(s.id, []).append(s.p)
            nxt = next(checks, None)
    out = []
    for sid, ps in samples.items():
        s = radar.lines[sid]
        hit = 1 if s.resolution == "happened" else 0
        out += [(p, hit, s.kind) for p in ps]
    return out


TEST_SEED = 10_000
TRAIN_SEED = 50_000


def _brier(rows: list[tuple[float, int, str]]) -> float:
    return sum((p - h) ** 2 for p, h, _ in rows) / len(rows)


def fit(matches: int) -> dict:
    """Grid search on training seeds (disjoint from the test seeds)."""
    best = None
    for scale in (0.45, 0.55, 0.65):
        for rw in (0.1, 0.15, 0.25):
            for pg in (4.0, 10.0):
                for sb in (0.4, 0.7, 1.0):
                    model.PARAMS.update({"scale": scale, "recent_weight": rw, "prior_games": pg, "state_boost": sb})
                    rows = [r for i in range(matches) for r in run_match(TRAIN_SEED + i)]
                    b = _brier(rows)
                    if best is None or b < best[0]:
                        best = (b, dict(model.PARAMS))
    model.PARAMS.update(best[1])
    return {"params": best[1], "trainBrier": round(best[0], 4), "trainMatches": matches, "trainSeeds": f"{TRAIN_SEED}+"}


def calibrate(matches: int, start_seed: int = TEST_SEED) -> dict:
    rows: list[tuple[float, int, str]] = []
    for i in range(matches):
        rows += run_match(start_seed + i)
    bins = []
    for lo, hi in zip(BINS, BINS[1:]):
        sel = [(p, h) for p, h, _ in rows if lo <= p < hi]
        if len(sel) < 15:
            continue
        bins.append({
            "lo": lo, "hi": min(hi, 1.0), "n": len(sel),
            "predicted": round(sum(p for p, _ in sel) / len(sel), 3),
            "actual": round(sum(h for _, h in sel) / len(sel), 3),
        })
    brier = sum((p - h) ** 2 for p, h, _ in rows) / len(rows)
    base = sum(h for _, h, _ in rows) / len(rows)
    brier_ref = sum((base - h) ** 2 for _, h, _ in rows) / len(rows)
    by_kind = {}
    for kind in sorted({k for _, _, k in rows}):
        sel = [(p, h) for p, h, k in rows if k == kind]
        by_kind[kind] = {"n": len(sel), "predicted": round(sum(p for p, _ in sel) / len(sel), 3), "actual": round(sum(h for _, h in sel) / len(sel), 3)}
    return {
        "available": True,
        "matches": matches,
        "samples": len(rows),
        "checkMinutes": CHECK_MINUTES,
        "bins": bins,
        "brier": round(brier, 4),
        "brierBaseline": round(brier_ref, 4),
        "skill": round(1 - brier / brier_ref, 3),
        "byKind": by_kind,
        "params": dict(model.PARAMS),
        "testSeeds": f"{start_seed}+",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--matches", type=int, default=200)
    ap.add_argument("--fit", type=int, default=0, help="fit model parameters on N training matches first")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "data" / "calibration.json"))
    args = ap.parse_args()
    if args.fit:
        fitted = fit(args.fit)
        model.PARAMS_FILE.parent.mkdir(parents=True, exist_ok=True)
        model.PARAMS_FILE.write_text(json.dumps(fitted, indent=2), encoding="utf-8")
        print("fitted", fitted)
    res = calibrate(args.matches)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("matches", "samples", "brier", "brierBaseline", "skill")}, indent=2))
    for b in res["bins"]:
        print(f"  {b['lo']:.2f}-{b['hi']:.2f}  n={b['n']:5d}  predicted {b['predicted']:.3f}  actual {b['actual']:.3f}")
    for k, v in res["byKind"].items():
        print(f"  {k:12s} n={v['n']:5d} predicted {v['predicted']:.3f} actual {v['actual']:.3f}")


if __name__ == "__main__":
    main()
