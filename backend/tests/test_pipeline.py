"""Core behaviour of the Zero Second pipeline."""

from __future__ import annotations

import asyncio
import math

from zerosecond.agents.orchestrator import Orchestrator
from zerosecond.agents.verifier import fill_slots, numbers_in, verify
from zerosecond.memory.store import SeasonMemory
from zerosecond.pitchforge.match import MatchConfig, simulate
from zerosecond.pitchforge.scenario import _keymap, build_scenario_history, build_scenario_world
from zerosecond.pitchforge.season import build_history
from zerosecond.pitchforge.world import build_world
from zerosecond.radar import model
from zerosecond.runtime import MatchRuntime
from zerosecond.stats.metrics import pass_difficulty, xg


# ---------------------------------------------------------------- PitchForge
def test_simulation_is_reproducible_and_monotonic():
    w = build_world(7)
    h = build_history(w)
    home, away = h.fixtures[0]
    a = simulate(w, MatchConfig(1, home, away, "m", 12))
    b = simulate(build_world(7), MatchConfig(1, home, away, "m", 12))
    assert [e["id"] for e in a] == [e["id"] for e in b]
    ts = [e["t"] for e in a]
    assert all(x <= y for x, y in zip(ts, ts[1:]))
    assert a[0]["type"] == "match_metadata" and a[-1]["type"] == "full_time"
    assert max(ts) <= 90 * 60


def test_scenario_season_memory_facts():
    w = build_scenario_world()
    m = SeasonMemory(w, build_scenario_history(w))
    k = _keymap(w)
    assert m.club_goals(k["KM"]) == 49
    assert m.milestone(k["KM"])["milestone"] == 50
    assert m.player_arc(k["KM"])["droppedMw"] == 6
    assert m.season_goals(k["DO"]) == 9
    assert m.clean_sheet_streak("HFC")["streak"] == 4
    assert m.late_winners("HFC")["count"] == 2
    worst = m.worst_defeat_to("NLU", "HFC")
    assert (worst["for"], worst["against"], worst["mw"]) == (0, 4, 3)


# ---------------------------------------------------------------- Stats Engine
def test_xg_model_behaves():
    assert xg(95, 50) > xg(85, 50) > xg(75, 50)  # closer is better
    assert xg(88, 50) > xg(88, 15)  # central is better than wide
    assert xg(90, 50, "head") < xg(90, 50)  # headers are harder
    assert 0 < xg(70, 50) < 0.1


def test_pass_difficulty_bounds():
    assert pass_difficulty(40, True, 50, 90) > pass_difficulty(8, False, 30, 35)
    assert 0 <= pass_difficulty(80, True, 10, 99) <= 10


# ---------------------------------------------------------------- Probability model
def test_probability_model():
    assert math.isclose(model.p_clean_sheet(0.0, 30), 1.0)
    assert model.p_player_scores(0.02, 0.3, 30) < model.p_player_scores(0.02, 0.3, 60)
    probs = model.outcome_probs(1, 0, 0.015, 0.015, 10)
    assert math.isclose(sum(probs.values()), 1.0, rel_tol=1e-6)
    assert probs["win"] > probs["loss"]
    assert model.p_late_winner(1, 0, 0.02, 0.02, 85) == 0.0  # already ahead after 80'


# ---------------------------------------------------------------- Verifier
def test_verifier_catches_wrong_number_and_player():
    facts = {"values": {"target": 50, "dropped_mw": 6}, "players": {"subject": "HFC-09"}}
    names = {"Mendes": "HFC-09", "Okafor": "NLU-09"}
    assert verify("50 club goals for Mendes, first since MW6.", facts, names).ok
    bad = verify("51 club goals for Mendes.", facts, names)
    assert not bad.ok and "51" in bad.issues[0]
    assert not verify("Fifty-one? No: Okafor scored 50.", facts, names).ok  # Okafor is not in this story
    assert 50 in numbers_in("FIFTY! What a moment.")
    live = {**facts, "why_now": "HFC xG so far: 0.00", "memory": [{"id": "mem-player-HFC-09", "text": "49 goals"}]}
    assert not verify("Harbour City on 0.00 xG.", live, names).ok  # live context is not a publishable fact
    assert not verify("He wore number 9.", live, names).ok  # digits inside ids don't count


def test_slots_fill():
    assert fill_slots("in the {minute_ord} minute", {"minute_ord": "78th"}) == "in the 78th minute"


# ---------------------------------------------------------------- end to end
def _run(rt: MatchRuntime, minute: float) -> None:
    async def go():
        await rt.jump(minute)
        if rt.orch.tasks:
            await asyncio.wait(list(rt.orch.tasks), timeout=5)

    asyncio.get_event_loop().run_until_complete(go())


def test_scenario_end_to_end():
    asyncio.set_event_loop(asyncio.new_event_loop())
    rt = MatchRuntime("t")
    _run(rt, 91)
    lines = {s.id: s for s in rt.radar.lines.values()}
    assert lines["HFC-09-ms50"].resolution == "happened"
    assert lines["HFC-09-ms50"].called_t is not None  # prepared before it happened
    assert lines["HFC-cs5"].resolution == "ruled_out"
    assert lines["HFC-latewinner"].resolution == "near_miss"
    published = {m["storyline"] for m in rt.orch.moments}
    assert "HFC-09-ms50" in published
    mendes = next(m for m in rt.orch.moments if m["storyline"] == "HFC-09-ms50")
    analyst = next(v for v in mendes["versions"] if v["key"] == "en_analyst")["text"]
    assert "{" not in analyst and "0.12" in analyst  # live slots filled from the Stats Engine
    assert rt.orch.recap and "1–1" in rt.orch.recap["text"]["broadcaster"]


def test_fault_injection_is_caught_and_redrafted():
    asyncio.set_event_loop(asyncio.new_event_loop())
    rt = MatchRuntime("f")
    rt.orch.fault_injection = True
    rt.orch.autopilot = False
    _run(rt, 80)
    rejects = [t for steps in rt.orch.traces.values() for t in steps if t["kind"] == "reject"]
    assert rejects, "the Verifier should reject the corrupted draft"
    for c in rt.orch.content.values():
        for v in c.versions:
            assert not v.get("faultInjected")


class FakeFoundry:
    """Stands in for FoundryAgents: first draft has a wrong number, redraft is correct."""

    model = "fake-model"

    def __init__(self):
        self.calls = 0

    async def edit(self, room, facts):
        return {"prepare": True, "angle": "Test angle"}, ["memory_player_arc(KM)"]

    async def write(self, facts, angle, feedback=None):
        self.calls += 1
        target = facts["values"].get("target", 3)
        n = target + 7 if feedback is None else target
        return {"versions": [
            {"key": "en_analyst", "text": f"Number {n} arrives in the {{minute_ord}} minute."},
            {"key": "en_casual", "text": "What a moment!"},
            {"key": "overlay", "text": "HEADLINE", "sub": "SUB"},
        ]}

    async def check(self, facts, draft):
        return {"ok": True, "issues": []}

    async def check_recap(self, payload, recap):
        return {"ok": True, "issues": []}

    async def recap(self, payload):
        return {"broadcaster": "A draw.", "casual": "A draw!", "analyst": "A draw."}


def test_foundry_code_path_with_fake_agents():
    asyncio.set_event_loop(asyncio.new_event_loop())
    rt = MatchRuntime("x")
    rt.orch = Orchestrator(rt, FakeFoundry())  # type: ignore[arg-type]
    _run(rt, 30)
    traces = [t for steps in rt.orch.traces.values() for t in steps]
    assert any(t["kind"] == "reject" for t in traces)
    assert any(t["lane"] == "Tools (MCP)" and "memory_player_arc" in t["label"] for t in traces)
    assert rt.orch.backend == "foundry:fake-model"
