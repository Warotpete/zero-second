"""Facts packs: the only material a Writer may use, and what the Verifier checks against.

Pre-moment content may also use *live slots* ({minute}, {score}, {shot_xg} ...). Slots
are filled by code from the Stats Engine at the moment the storyline triggers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..util import ordinal, short_name

if TYPE_CHECKING:
    from ..radar.radar import Storyline
    from ..runtime import MatchRuntime

PLAYER_SLOTS = {"minute", "minute_ord", "score", "shot_xg", "shot_speed", "assist"}
TEAM_SLOTS = {"score", "minute", "minute_ord"}


def build_facts(rt: "MatchRuntime", s: "Storyline") -> dict:
    mem, stats, w = rt.memory, rt.stats, rt.world
    team, opp = w.teams[s.team], w.teams[s.opp]
    vals: dict[str, object] = {"probability_pct": round(100 * s.p), "matchweek": rt.matchweek}
    players: dict[str, str] = {}
    names: dict[str, str] = {}
    memory: list[dict] = []
    if s.player:
        p = w.player(s.player)
        arc = mem.player_arc(s.player)
        players["subject"] = p.id
        names[p.id] = p.name
        vals.update({"club_goals_now": arc["clubGoals"], "season_goals": arc["seasonGoals"]})
        if arc["droppedMw"]:
            vals["dropped_mw"] = arc["droppedMw"]
        if s.target:
            vals["target"] = s.target
        if s.kind == "brace":
            vals["goals_today"] = 1
            vals["club_goals_after"] = arc["clubGoals"] + 2
        if s.kind == "hattrick":
            vals["goals_today"] = 2
        memory.append({"id": arc["factId"], "text": s.memory_line})
    if s.kind == "clean_sheet":
        cs = mem.clean_sheet_streak(s.team)
        vals.update({"streak_before": cs["streak"], "target": cs["streak"] + 1})
        memory.append({"id": cs["factId"], "text": s.memory_line})
    if s.kind == "revenge":
        worst = mem.worst_defeat_to(s.team, s.opp)
        vals.update({"then_for": worst["for"], "then_against": worst["against"], "then_mw": worst["mw"], "then_season": worst["season"]})
        memory.append({"id": worst["factId"], "text": s.memory_line})
    if s.kind == "late_winner":
        lw = mem.late_winners(s.team)
        vals.update({"late_winners_before": lw["count"], "late_winner_n": lw["count"] + 1, "after_minute": 80})
        memory.append({"id": lw["factId"], "text": s.memory_line})
    slots = PLAYER_SLOTS if s.player and s.kind != "clean_sheet" else TEAM_SLOTS
    return {
        "storyline": {"id": s.id, "kind": s.kind, "title": s.title, "question": s.question, "impact": s.impact},
        "team": {"id": team.id, "name": team.name, "short": team.short},
        "opponent": {"id": opp.id, "name": opp.name, "short": opp.short},
        "players": players,
        "names": names,
        "values": vals,
        "memory": memory,
        "why_now": s.why,
        "score_now": f"{stats.score[rt.home]}–{stats.score[rt.away]}",
        "slots": sorted(slots),
    }


def trigger_slots(rt: "MatchRuntime", s: "Storyline", event: dict | None) -> tuple[dict, dict]:
    """Values for live slots at the trigger moment, plus extra facts they introduce."""
    stats = rt.stats
    minute = event["minute"] if event else stats.minute_now()
    slots: dict[str, object] = {
        "minute": minute,
        "minute_ord": ordinal(minute),
        "score": f"{stats.score[rt.home]}–{stats.score[rt.away]}",
    }
    extra: dict = {"values": {"minute": minute, "home_goals": stats.score[rt.home], "away_goals": stats.score[rt.away]}, "players": {}}
    if event and event.get("type") == "shot":
        shot = next((x for x in stats.shots if x["id"] == event["id"]), None)
        if shot:
            slots["shot_xg"] = f"{shot['xg']:.2f}"
            slots["shot_speed"] = shot["speedKmh"]
            extra["values"].update({"shot_xg": round(shot["xg"], 2), "shot_speed": shot["speedKmh"]})
            if shot.get("assist"):
                slots["assist"] = short_name(rt.world.player(shot["assist"]).name)
                extra["players"]["assist"] = shot["assist"]
    slots.setdefault("assist", "")
    slots.setdefault("shot_xg", "")
    slots.setdefault("shot_speed", "")
    return slots, extra


def merge_facts(facts: dict, extra: dict) -> dict:
    out = {**facts, "values": {**facts["values"], **extra.get("values", {})}, "players": {**facts["players"], **extra.get("players", {})}}
    return out
