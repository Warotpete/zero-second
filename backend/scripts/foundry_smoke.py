"""One real Writer + Verifier call against Foundry, to check credentials and output format."""
import asyncio, json, pathlib, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from zerosecond.api import _load_dotenv
_load_dotenv(pathlib.Path(__file__).resolve().parents[1] / ".env")
from zerosecond.agents.foundry import FoundryAgents
from zerosecond.agents.verifier import verify

FACTS = {
    "storyline": {"id": "HFC-09-ms50", "kind": "milestone", "title": "Mendes – 50th club goal"},
    "team": {"id": "HFC", "name": "Harbour City FC", "short": "Harbour City"},
    "opponent": {"id": "NLU", "name": "Northvale United", "short": "Northvale"},
    "players": {"subject": "HFC-09"}, "names": {"HFC-09": "Kai Mendes"},
    "values": {"club_goals_before": 49, "club_goals_after": 50, "target": 50, "dropped_mw": 6, "season_goals_before": 4, "season_goals_after": 5, "probability_pct": 13, "matchweek": 12},
    "memory": [{"id": "mem-player-HFC-09", "text": "49 goals · first since dropped MW6"}],
    "slots": ["minute", "minute_ord", "score", "shot_xg", "shot_speed", "assist"],
}

async def main():
    a = FoundryAgents(None)
    await a.start()
    t = time.perf_counter()
    draft = await a.write(FACTS, "Milestone plus personal comeback arc")
    print(f"writer {time.perf_counter() - t:.1f}s")
    print(json.dumps(draft, ensure_ascii=False, indent=1))
    for v in draft["versions"]:
        for f in ("text", "sub"):
            if v.get(f):
                chk = verify(v[f], FACTS, {"Mendes": "HFC-09", "Okafor": "NLU-09"}, set(FACTS["slots"]))
                print(v["key"], f, "OK" if chk.ok else chk.issues)
    t = time.perf_counter()
    print("semantic check", await a.check(FACTS, draft), f"{time.perf_counter() - t:.1f}s")
    await a.stop()

asyncio.run(main())
