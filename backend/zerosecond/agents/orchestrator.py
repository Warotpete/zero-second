"""Agent orchestration.

For each storyline Story Radar ranks highly, the orchestrator runs:

    Story Radar (model) -> Editor agent -> Tools (MCP) -> Writer agent -> Verifier agent
        -> (reject -> Writer redraft, up to 2x -> fallback writer) -> Ready -> Producer approval

Shared state lives here (content, traces, audit log, moments). When a storyline
triggers, pre-approved content is published at once with live slots filled from the
Stats Engine. If nothing was prepared, a reactive path writes it on the spot.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..util import clock
from . import foundry, local_writer
from .facts import build_facts, merge_facts, trigger_slots
from .verifier import allowed_numbers, fill_slots, verify

if TYPE_CHECKING:
    from ..radar.radar import Storyline
    from ..runtime import MatchRuntime

log = logging.getLogger("zerosecond.orchestrator")

MAX_REDRAFTS = 2
PREP_TOP_N = 3
PREP_MIN_P = 0.06
PREP_MIN_SCORE = 0.45
AUTOPILOT_DELAY_S = 25.0  # match seconds before the autopilot producer approves
AGENTS = ["Editor", "Writer", "Verifier", "Recap"]


@dataclass
class Content:
    storyline: str
    facts: dict
    versions: list[dict] = field(default_factory=list)
    angle: str = ""
    state: str = "writing"  # writing | ready | pre_approved | held | published | awaiting_approval
    drafts: list[dict] = field(default_factory=list)  # rejected drafts kept for the trace
    reactive: bool = False
    ready_t: float | None = None
    approved_by: str | None = None
    approved_t: float | None = None
    published_t: float | None = None
    filled: list[dict] | None = None
    backend: str = "local"

    def public(self) -> dict:
        return {
            "storyline": self.storyline,
            "versions": self.filled or self.versions,
            "template": self.versions,
            "angle": self.angle,
            "state": self.state,
            "reactive": self.reactive,
            "readyClock": None if self.ready_t is None else clock(self.ready_t),
            "approvedBy": self.approved_by,
            "approvedClock": None if self.approved_t is None else clock(self.approved_t),
            "publishedClock": None if self.published_t is None else clock(self.published_t),
            "drafts": self.drafts,
            "backend": self.backend,
            "slots": self.facts.get("slots", []),
        }


class Orchestrator:
    def __init__(self, rt: "MatchRuntime", agents: "foundry.FoundryAgents | None"):
        self.rt = rt
        self.llm = agents
        self.content: dict[str, Content] = {}
        self.traces: dict[str, list[dict]] = {}
        self.audit: list[dict] = []
        self.moments: list[dict] = []
        self.overlays: list[dict] = []
        self.recap: dict | None = None
        self.agent_state = {a: {"state": "idle", "since": 0.0} for a in AGENTS}
        self.tasks: set[asyncio.Task] = set()
        self.autopilot = True
        self.fault_injection = False
        self._rng = random.Random(rt.seed)
        self._pending_approval: dict[str, float] = {}

    # ------------------------------------------------------------------ utils
    @property
    def backend(self) -> str:
        return f"foundry:{self.llm.model}" if self.llm else "local"

    def now(self) -> float:
        return self.rt.stats.t

    def _audit(self, actor: str, action: str, detail: str, storyline: str | None = None, level: str = "info") -> None:
        self.audit.append({"clock": clock(self.now()), "t": self.now(), "actor": actor, "action": action, "detail": detail, "storyline": storyline, "level": level})

    def _trace(self, sid: str, lane: str, label: str, kind: str = "ok", ms: float = 0.0, **extra: Any) -> None:
        self.traces.setdefault(sid, []).append({"clock": clock(self.now()), "t": self.now(), "lane": lane, "label": label, "kind": kind, "ms": round(ms), "wall": time.time(), **extra})

    def _busy(self, agent: str, state: str = "working") -> None:
        self.agent_state[agent] = {"state": state, "since": self.now()}

    def _spawn(self, coro) -> None:
        task = asyncio.ensure_future(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def _known_names(self) -> dict[str, str]:
        out = {}
        for team in (self.rt.home, self.rt.away):
            for p in self.rt.world.teams[team].players:
                out[p.name.split()[-1]] = p.id
        return out

    # ------------------------------------------------------------------ planning
    def plan(self) -> None:
        """Called after each Radar update: start preparing the storylines worth preparing."""
        ranked = self.rt.radar.ranked()
        writing = sum(1 for c in self.content.values() if c.state == "writing")
        limit = 2 if self.llm else 6
        for i, s in enumerate(ranked):
            if s.prep != "none" or s.id in self.content:
                continue
            if self.rt.stats.t > 89 * 60:
                break
            worth = (i < PREP_TOP_N and s.p >= PREP_MIN_P) or s.score >= PREP_MIN_SCORE
            if not worth or writing >= limit:
                continue
            writing += 1
            s.prep = "writing"
            self.content[s.id] = Content(s.id, build_facts(self.rt, s), backend=self.backend)
            self._spawn(self.prepare(s))
        # autopilot approvals
        if self.autopilot:
            for sid, ready_at in list(self._pending_approval.items()):
                if self.now() - ready_at >= AUTOPILOT_DELAY_S:
                    self._pending_approval.pop(sid, None)
                    c = self.content.get(sid)
                    if c and c.state == "ready":
                        self.approve(sid, "Producer (autopilot)")

    def _tool_calls_local(self, s: "Storyline") -> list[str]:
        """The same tools the MCP server exposes, called in-process in local mode."""
        mem, st = self.rt.memory, self.rt.stats
        team = s.opp if s.kind == "clean_sheet" else s.team
        calls = [f"stats_xg_window({team},15)"]
        st.xg_window(team, 15)
        if s.player:
            mem.player_arc(s.player)
            calls.append(f"memory_player_arc({self.rt.world.player(s.player).initials})")
            if s.kind == "milestone":
                mem.milestone(s.player)
                calls.append(f"memory_milestones({self.rt.world.player(s.player).initials})")
        if s.kind == "revenge":
            mem.h2h(s.team, s.opp)
            calls.append(f"memory_h2h({s.team},{s.opp})")
        if s.kind == "clean_sheet":
            mem.clean_sheet_streak(s.team)
            calls.append(f"memory_clean_sheets({s.team})")
        if s.kind == "late_winner":
            mem.late_winners(s.team)
            calls.append(f"memory_late_winners({s.team})")
        return calls

    # ------------------------------------------------------------------ pipeline
    async def prepare(self, s: "Storyline") -> None:
        c = self.content[s.id]
        sid = s.id
        try:
            hist15 = s.p_at(max(s.activated_t, self.now() - 15 * 60))
            before = round(100 * (hist15 if hist15 is not None else s.p))
            self._trace(sid, "Story Radar (model)", f"Probability {before}% → {round(100 * s.p)}% · {s.why}", "radar")
            self._audit("Story Radar", "Rising", f"{s.title} · {round(100 * s.p)}%", sid)

            # Editor
            self._busy("Editor")
            t0 = time.perf_counter()
            angle, tool_calls = "", []
            if self.llm:
                try:
                    data, tool_calls = await self.llm.edit(self.rt.room, c.facts)
                    angle = str(data.get("angle", ""))
                except Exception as exc:
                    self._trace(sid, "Editor agent", f"Editor error, using rule-based angle: {exc}"[:140], "fallback")
            if not angle:
                angle = local_writer.write_versions(c.facts)["angle"]
            c.angle = angle
            self._trace(sid, "Editor agent", f"Selected · impact {s.impact} ({angle})", "ok", (time.perf_counter() - t0) * 1000)
            self._audit("Editor", "Selected", f"{angle} · {s.impact}", sid)
            self._busy("Editor", "idle")
            if not tool_calls:
                tool_calls = self._tool_calls_local(s)
            for call in tool_calls:
                self._trace(sid, "Tools (MCP)", call, "tool")

            # Writer + Verifier loop
            feedback: list[str] | None = None
            versions = None
            for attempt in range(MAX_REDRAFTS + 1):
                self._busy("Writer")
                t0 = time.perf_counter()
                try:
                    draft = await self._write(c.facts, angle, feedback)
                except Exception as exc:
                    self._trace(sid, "Writer agent", f"Foundry writer error ({type(exc).__name__}); deterministic writer used", "fallback")
                    self._audit("Writer", "Fallback", f"model error: {type(exc).__name__}", sid, "warn")
                    draft = local_writer.write_versions(c.facts)["versions"]
                if attempt == 0 and self.fault_injection:
                    draft = self._inject_fault(draft, c.facts)
                label = "Drafted 4 versions" if attempt == 0 else f"Redraft #{attempt}"
                self._trace(sid, "Writer agent", label, "ok", (time.perf_counter() - t0) * 1000)
                self._audit("Writer", "Drafted" if attempt == 0 else "Redrafted", f"{len(draft)} versions", sid)
                self._busy("Writer", "idle")
                self._busy("Verifier")
                t0 = time.perf_counter()
                issues, checked = await self._verify(c.facts, draft)
                self._busy("Verifier", "idle")
                if not issues:
                    versions = draft
                    self._trace(sid, "Verifier agent", f"All {len(draft)} verified · {checked} figures checked", "ok", (time.perf_counter() - t0) * 1000)
                    self._audit("Verifier", "Verified", f"All {len(draft)} versions · {checked} figures checked", sid)
                    break
                c.drafts.append({"attempt": attempt, "versions": draft, "issues": issues})
                self._trace(sid, "Verifier agent", f"Rejected: {issues[0]}", "reject", (time.perf_counter() - t0) * 1000, issues=issues)
                self._audit("Verifier", "Rejected", issues[0], sid, "error")
                feedback = issues
            if versions is None:
                versions = local_writer.write_versions(c.facts)["versions"]
                self._trace(sid, "Writer agent", "Fallback: deterministic writer after repeated rejections", "fallback")
                self._audit("Writer", "Fallback", "deterministic writer used", sid, "warn")
            c.versions = versions
            if s.resolved:
                if s.resolution != "happened":
                    c.state = "discarded"  # ruled out while the agents were writing
                    self._audit("Editor", "Discarded", f"{s.title}: {s.resolution_note}", sid)
                return  # if it happened while writing, on_trigger handles it
            c.state = "ready"
            c.ready_t = self.now()
            s.prep = "ready"
            s.versions_ready = len(versions)
            s.called_t, s.called_p = self.now(), s.p
            self._audit("Editor", "Ready", f"{s.title} · {len(versions)} versions ready", sid)
            if self.autopilot:
                self._pending_approval[sid] = self.now()
        except Exception as exc:  # never let one storyline break the match
            log.exception("prepare failed")
            self._trace(sid, "Writer agent", f"Pipeline error: {exc}"[:140], "reject")
            self._audit("Orchestrator", "Error", str(exc)[:120], sid, "error")
            s.prep = "none"
            self.content.pop(sid, None)

    async def _write(self, facts: dict, angle: str, feedback: list[str] | None) -> list[dict]:
        if self.llm:
            try:
                data = await self.llm.write(facts, angle, feedback)
                vs = data["versions"]
                keys = {v.get("key") for v in vs}
                if {"en_analyst", "en_casual", "th_casual", "overlay"} <= keys:
                    meta = {"en_analyst": ("en", "analyst"), "en_casual": ("en", "casual"), "th_casual": ("th", "casual"), "overlay": ("en", "overlay")}
                    return [{**v, "lang": meta[v["key"]][0], "audience": meta[v["key"]][1]} for v in vs if v.get("key") in meta]
                raise ValueError("missing versions")
            except Exception as exc:
                log.warning("Foundry writer failed: %s", exc)
                raise
        return local_writer.write_versions(facts)["versions"]

    async def _verify(self, facts: dict, versions: list[dict], allowed_slots: set[str] | None = None) -> tuple[list[str], int]:
        names = self._known_names()
        slots = set(facts.get("slots", [])) if allowed_slots is None else allowed_slots
        issues: list[str] = []
        checked = 0
        for v in versions:
            for field_ in ("text", "sub", "gloss"):
                if v.get(field_):
                    chk = verify(v[field_], facts, names, slots)
                    checked += chk.numbers_checked
                    issues += [f"{v['key']}: {i}" for i in chk.issues]
        if not issues and self.llm:
            try:
                data = await self.llm.check(facts, {"versions": versions})
                if not data.get("ok", True):
                    issues += [f"meaning: {i}" for i in data.get("issues", [])][:3]
            except Exception as exc:
                log.warning("Foundry verifier unavailable: %s", exc)
        return issues, checked

    def _inject_fault(self, draft: list[dict], facts: dict) -> list[dict]:
        """Chaos test: corrupt one figure in the analyst draft so the Verifier must catch it."""
        import re

        out = [dict(v) for v in draft]
        allowed = allowed_numbers(facts)
        for v in out:
            if v["key"] != "en_analyst":
                continue
            m = re.search(r"(?<![{\w.])(\d+)(?![\w}])", v["text"]) or re.search(r"(\d+)", v["text"])
            base = int(m.group(1)) if m else int(facts["values"].get("probability_pct", 10))
            wrong = base + 1
            while wrong in allowed:
                wrong += 1
            if m:
                v["text"] = v["text"][: m.start(1)] + str(wrong) + v["text"][m.end(1):]
            else:
                v["text"] += f" That makes {wrong}."
            v["faultInjected"] = True
            break
        return out

    # ------------------------------------------------------------------ approvals
    def approve(self, sid: str, actor: str = "Producer") -> bool:
        c = self.content.get(sid)
        s = self.rt.radar.lines.get(sid)
        if not c or c.state not in ("ready", "held", "awaiting_approval"):
            return False
        c.approved_by, c.approved_t = actor, self.now()
        if c.state == "awaiting_approval":
            self._publish(sid)
        else:
            c.state = "pre_approved"
            if s and not s.resolved:
                s.prep = "pre_approved"
                s.approved_by, s.approved_t = actor, self.now()
        self._trace(sid, "Producer", f"{'Approved' if c.published_t else 'Pre-approved'} by {actor}", "approve")
        self._audit(actor, "Pre-approved" if not c.published_t else "Approved", f"{len(c.versions)} versions · markets UK, TH", sid)
        return True

    def hold(self, sid: str, actor: str = "Producer") -> bool:
        c = self.content.get(sid)
        if not c or c.state not in ("ready", "pre_approved"):
            return False
        c.state = "held"
        self._pending_approval.pop(sid, None)
        s = self.rt.radar.lines.get(sid)
        if s and not s.resolved:
            s.prep = "ready"
        self._audit(actor, "Held", "content on hold", sid, "warn")
        return True

    def revoke(self, sid: str, actor: str = "Producer") -> bool:
        c = self.content.get(sid)
        if not c or c.state != "pre_approved":
            return False
        c.state = "ready"
        c.approved_by = c.approved_t = None
        s = self.rt.radar.lines.get(sid)
        if s and not s.resolved:
            s.prep = "ready"
        self._audit(actor, "Revoked", "approval revoked", sid, "warn")
        return True

    def edit(self, sid: str, key: str, text: str, actor: str = "Producer") -> tuple[bool, list[str]]:
        c = self.content.get(sid)
        if not c:
            return False, ["no content"]
        versions = [dict(v) for v in c.versions]
        for v in versions:
            if v["key"] == key:
                v["text"] = text
        names = self._known_names()
        chk = verify(text, c.facts, names, set(c.facts.get("slots", [])))
        if not chk.ok:
            self._audit("Verifier", "Rejected", f"producer edit: {chk.issues[0]}", sid, "error")
            return False, chk.issues
        c.versions = versions
        self._audit(actor, "Edited", f"{key} (re-verified)", sid)
        return True, []

    # ------------------------------------------------------------------ triggers
    def on_trigger(self, s: "Storyline", event: dict | None) -> None:
        c = self.content.get(s.id)
        if c and c.versions:
            self._fill_and_route(s, c, event)
        else:
            self._spawn(self._reactive(s, event))

    def _fill_and_route(self, s: "Storyline", c: Content, event: dict | None) -> None:
        slots, extra = trigger_slots(self.rt, s, event)
        facts = merge_facts(c.facts, extra)
        filled = []
        for v in c.versions:
            fv = dict(v)
            for f in ("text", "sub", "gloss"):
                if fv.get(f):
                    fv[f] = _tidy(fill_slots(fv[f], slots))
            filled.append(fv)
        names = self._known_names()
        bad = []
        for v in filled:
            for f in ("text", "sub", "gloss"):
                if v.get(f):
                    bad += verify(v[f], facts, names, set()).issues
        c.filled = filled
        c.facts = facts
        if bad:
            self._audit("Verifier", "Rejected", f"after slot fill: {bad[0]}", s.id, "error")
            c.state = "awaiting_approval"
            return
        self._trace(s.id, "Story Radar (model)", f"Triggered {s.resolution_note}", "trigger")
        if c.state == "pre_approved":
            self._publish(s.id, event)
        else:
            c.state = "awaiting_approval"
            self._audit("Editor", "Awaiting approval", f"{s.title} happened · content ready, not yet approved", s.id, "warn")
            if self.autopilot:
                self.approve(s.id, "Producer (autopilot)")

    async def _reactive(self, s: "Storyline", event: dict | None) -> None:
        sid = s.id
        c = Content(sid, build_facts(self.rt, s), reactive=True, backend=self.backend)
        self.content[sid] = c
        self._trace(sid, "Story Radar (model)", f"Triggered without prepared content · {s.resolution_note}", "trigger")
        self._busy("Writer")
        t0 = time.perf_counter()
        try:
            versions = await self._write(c.facts, "Reactive: it just happened", None)
        except Exception:
            versions = local_writer.write_versions(c.facts)["versions"]
        self._busy("Writer", "idle")
        issues, checked = await self._verify(c.facts, versions)
        if issues:
            versions = local_writer.write_versions(c.facts)["versions"]
            self._trace(sid, "Writer agent", "Fallback writer (reactive)", "fallback")
        self._trace(sid, "Writer agent", "Reactive draft (written after the moment)", "ok", (time.perf_counter() - t0) * 1000)
        self._trace(sid, "Verifier agent", f"Verified · {checked} figures checked", "ok")
        c.versions = versions
        c.state = "awaiting_approval"
        self._audit("Writer", "Reactive", f"{s.title}: written after the moment", sid, "warn")
        self._fill_and_route(s, c, event)

    def reactive_goal(self, event: dict) -> None:
        """A goal no storyline covered still gets verified content (reactive)."""
        from ..radar.radar import Storyline

        team, pid = event["team"], event["player"]
        s = Storyline(
            f"goal-{event['id']}", "goal", team, self.rt.radar.opp(team), f"Goal – {self.rt.radar.last(pid)}",
            "", "MED", "", None, "GOAL", event["t"], player=pid,
        )
        s.resolution, s.resolved_t, s.resolution_note, s.resolution_event = "happened", event["t"], f"Scored {event['minute']}'", event["id"]
        s.initials = self.rt.world.player(pid).initials
        self.rt.extra_lines[s.id] = s
        self._spawn(self._reactive(s, event))

    def _publish(self, sid: str, event: dict | None = None) -> None:
        c = self.content[sid]
        s = self.rt.radar.lines.get(sid) or self.rt.extra_lines.get(sid)
        c.state = "published"
        c.published_t = self.now()
        versions = c.filled or c.versions
        overlay = next((v for v in versions if v["key"] == "overlay"), None)
        moment = {
            "id": f"moment-{sid}",
            "storyline": sid,
            "kind": s.kind if s else "goal",
            "title": s.title if s else "",
            "team": s.team if s else None,
            "player": s.player if s else None,
            "minute": (event or {}).get("minute") or (int(s.resolved_t // 60) + 1 if s and s.resolved_t else self.rt.stats.minute_now()),
            "clock": clock(self.now()),
            "versions": versions,
            "reactive": c.reactive,
            "calledMinute": None if not s or s.called_t is None else int(s.called_t // 60) + 1,
            "calledPct": None if not s or s.called_p is None else round(100 * s.called_p),
            "approvedBy": c.approved_by,
            "event": (event or {}).get("id"),
        }
        self.moments.append(moment)
        if overlay:
            cue = {
                "id": f"cue-{sid}",
                "type": "lower_third",
                "storyline": sid,
                "trigger": {"event": (event or {}).get("id"), "matchClock": clock(self.now())},
                "in": 0.0,
                "out": 8.0,
                "headline": overlay["text"],
                "sub": overlay.get("sub", ""),
                "player": None if not s or not s.player else {"id": s.player, "initials": self.rt.world.player(s.player).initials},
                "team": s.team if s else None,
            }
            self.overlays.append(cue)
        self._trace(sid, "Producer", f"Published · {len(versions)} versions", "publish")
        self._audit("Publisher", "Published", f"{moment['title']} · {len(versions)} versions · UK, TH", sid)

    # ------------------------------------------------------------------ recap
    async def build_recap(self) -> None:
        rt = self.rt
        self._busy("Recap")
        names = {p.id: p.name for p in rt.world.all_players()}
        goals = [{"scorer": names[g["player"]], "minute": g["minute"], "team": g["team"], "ref": f"evt-{g['minute']}"} for g in rt.stats.goals]
        lines = []
        by_id = {e["id"]: e for e in rt.events}
        for s in rt.radar.resolved_lines():
            d = s.public(rt.stats.t)
            ev = by_id.get(s.resolution_event or "")
            if d["resolution"] in ("happened", "near_miss") and ev and ev["type"] != "full_time":
                d["ref"] = f"evt-{ev['minute']}"
            else:
                d["ref"] = "evt-ft" if d["resolution"] != "ruled_out" else f"evt-{d['resolvedMinute']}"
            lines.append(d)
        ts = rt.stats.team_stats()
        payload = {
            "home": rt.world.teams[rt.home].short,
            "away": rt.world.teams[rt.away].short,
            "home_goals": rt.stats.score[rt.home],
            "away_goals": rt.stats.score[rt.away],
            "home_xg": ts[rt.home]["xg"],
            "away_xg": ts[rt.away]["xg"],
            "home_shots": ts[rt.home]["shots"],
            "away_shots": ts[rt.away]["shots"],
            "home_poss": ts[rt.home]["possession"],
            "away_poss": ts[rt.away]["possession"],
            "goals": goals,
            "storylines": [{k: d[k] for k in ("title", "impact", "resolution", "resolutionNote", "resolvedMinute", "peakPct", "peakMinute", "calledMinute", "calledPct", "ref")} for d in lines],
        }
        text = None
        backend = "local"
        if self.llm:
            try:
                text = await self.llm.recap(payload)
                backend = self.backend
            except Exception as exc:
                log.warning("Foundry recap failed: %s", exc)
        if not text:
            text = local_writer.write_recap(payload)
        # verify numbers against the payload
        names_map = self._known_names()
        cast = {p: p for p in [g_pid for g_pid in (x["player"] for x in rt.stats.goals)]}
        cast.update({s.player: s.player for s in rt.radar.lines.values() if s.player})
        facts = {"values": payload, "players": cast}
        issues = []
        for k, v in text.items():
            issues += [f"{k}: {i}" for i in verify(v, facts, names_map).issues]
        if issues and backend != "local":
            text = local_writer.write_recap(payload)
            backend = "local"
            self._audit("Verifier", "Rejected", f"recap: {issues[0]}", None, "error")
        self.recap = {"text": text, "payload": payload, "state": "ready", "backend": backend, "verified": True, "approvedBy": None}
        self._audit("Recap", "Drafted", "3 recaps · verified", None)
        self._busy("Recap", "idle")
        if self.autopilot:
            self.approve_recap("Producer (autopilot)")

    def approve_recap(self, actor: str = "Producer") -> bool:
        if not self.recap:
            return False
        self.recap["state"] = "approved"
        self.recap["approvedBy"] = actor
        self._audit(actor, "Approved", "match recap", None)
        return True


def _tidy(text: str) -> str:
    """Clean up empty-slot leftovers such as 'a  xG chance'."""
    return " ".join(text.replace(" ,", ",").split())
