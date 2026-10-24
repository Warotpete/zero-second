"""Story Radar.

Storyline templates are predefined (as in broadcast data teams). Which storylines
activate, how likely they are, and how they resolve is computed live from Season
Memory and the Stats Engine.

Lifecycle: Watching/Rising -> (agents) Writing -> Ready -> Pre-approved
           -> Happened | Near miss | Ruled out | Unresolved
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..memory.store import ROLE_SHARE_PRIOR, SeasonMemory
from ..pitchforge.world import World
from ..stats.engine import StatsEngine
from ..stats.metrics import BIG_CHANCE_XG
from ..util import ordinal, short_name
from . import model

IMPACT_WEIGHT = {"HIGH": 3.0, "MED": 2.0, "LOW": 1.0}
PLAYER_KINDS = {"milestone", "tally", "debut", "redemption", "brace", "hattrick"}
SAMPLE_EVERY_S = 30.0


@dataclass
class Storyline:
    id: str
    kind: str
    team: str
    opp: str
    title: str
    question: str
    impact: str
    memory_line: str
    memory_fact: str | None
    trigger: str
    activated_t: float
    player: str | None = None
    target: int | None = None  # e.g. milestone number
    p: float = 0.0
    history: list[tuple[float, float]] = field(default_factory=list)
    peak_p: float = 0.0
    peak_t: float = 0.0
    why: str = ""
    drivers: list[str] = field(default_factory=list)
    resolution: str | None = None  # happened | near_miss | ruled_out | unresolved
    resolved_t: float | None = None
    resolution_note: str = ""
    resolution_event: str | None = None
    prep: str = "none"  # none | writing | ready | pre_approved
    called_t: float | None = None  # when content became Ready (the forecast "call")
    called_p: float | None = None
    versions_ready: int = 0
    approved_by: str | None = None
    approved_t: float | None = None
    initials: str = ""

    @property
    def weight(self) -> float:
        return IMPACT_WEIGHT[self.impact]

    @property
    def score(self) -> float:
        return self.p * self.weight

    @property
    def resolved(self) -> bool:
        return self.resolution is not None

    def status(self) -> str:
        if self.resolution:
            return {"happened": "Happened", "near_miss": "Near miss", "ruled_out": "Ruled out", "unresolved": "Unresolved"}[self.resolution]
        if self.prep == "pre_approved":
            return "Pre-approved"
        if self.prep == "ready":
            return "Ready"
        if self.prep == "writing":
            return "Writing"
        return "Rising" if self.rising() else "Watching"

    def p_at(self, t: float) -> float | None:
        prev = [p for (ht, p) in self.history if ht <= t]
        return prev[-1] if prev else None

    def delta15(self, now: float) -> float | None:
        if now - self.activated_t < 5 * 60:
            return None
        base = self.p_at(max(self.activated_t, now - 15 * 60))
        return None if base is None else self.p - base

    def rising(self) -> bool:
        if not self.history:
            return False
        now = self.history[-1][0]
        base = self.p_at(now - 5 * 60)
        if base is None:
            return now - self.activated_t < 5 * 60 and self.p >= 0.05
        return self.p - base >= 0.03

    def public(self, now: float) -> dict:
        d15 = self.delta15(now)
        return {
            "id": self.id,
            "kind": self.kind,
            "team": self.team,
            "opp": self.opp,
            "player": self.player,
            "initials": self.initials,
            "title": self.title,
            "question": self.question,
            "impact": self.impact,
            "memoryLine": self.memory_line,
            "memoryFact": self.memory_fact,
            "trigger": self.trigger,
            "p": round(self.p, 4),
            "pct": round(100 * self.p),
            "delta15": None if d15 is None else round(100 * d15),
            "isNew": now - self.activated_t < 5 * 60,
            "score": round(self.score, 4),
            "peakPct": round(100 * self.peak_p),
            "peakMinute": int(self.peak_t // 60) + 1,
            "why": self.why,
            "drivers": self.drivers,
            "status": self.status(),
            "prep": self.prep,
            "resolution": self.resolution,
            "resolvedMinute": None if self.resolved_t is None else int(self.resolved_t // 60) + 1,
            "resolutionNote": self.resolution_note,
            "resolutionEvent": self.resolution_event,
            "calledMinute": None if self.called_t is None else int(self.called_t // 60) + 1,
            "calledPct": None if self.called_p is None else round(100 * self.called_p),
            "versionsReady": self.versions_ready,
            "approvedBy": self.approved_by,
            "approvedClock": self.approved_t,
            "spark": [round(100 * p) for _, p in self.history[-20:]],
            "activatedMinute": int(self.activated_t // 60) + 1,
        }


class StoryRadar:
    def __init__(self, world: World, memory: SeasonMemory, stats: StatsEngine, home: str, away: str):
        self.w, self.mem, self.stats = world, memory, stats
        self.home, self.away = home, away
        self.lines: dict[str, Storyline] = {}
        self.rates: dict[str, model.Rate] = {}
        self._xg_hist: dict[str, list[tuple[int, float]]] = {home: [], away: []}
        self._last_sample = -1e9
        self._activated_kickoff = False
        self._passed_80 = False
        self.log: list[dict] = []  # lifecycle log (feeds the recap)

    # ------------------------------------------------------------------ names
    def short(self, pid: str) -> str:
        return short_name(self.w.player(pid).name)

    def last(self, pid: str) -> str:
        return self.w.player(pid).name.split()[-1]

    def tshort(self, tid: str) -> str:
        return self.w.teams[tid].short

    def opp(self, team: str) -> str:
        return self.away if team == self.home else self.home

    # ------------------------------------------------------------------ activation
    def _add(self, s: Storyline) -> None:
        if s.id in self.lines:
            return
        s.initials = self.w.player(s.player).initials if s.player else s.team[:2]
        self.lines[s.id] = s
        self._log(s, "activated", s.title)

    def _log(self, s: Storyline, action: str, detail: str) -> None:
        self.log.append({"t": self.stats.t, "minute": self.stats.minute_now(), "storyline": s.id, "action": action, "detail": detail})

    def activate_player(self, pid: str) -> None:
        p = self.w.player(pid)
        if p.role == "GK":
            return
        team, opp = p.team_id, self.opp(p.team_id)
        arc = self.mem.player_arc(pid)
        t = self.stats.t
        ms = self.mem.milestone(pid)
        redemption = arc["noGoalSinceDropped"]
        if ms:
            mem = f"{arc['clubGoals']} goals"
            if redemption:
                mem += f" · first since dropped MW{arc['droppedMw']}"
            impact = "HIGH" if ms["milestone"] >= 50 or redemption else "MED"
            self._add(Storyline(
                f"{pid}-ms{ms['milestone']}", "milestone", team, opp,
                f"{self.last(pid)} – {ordinal(ms['milestone'])} club goal",
                f"{self.last(pid)} to reach {ms['milestone']} club goals?",
                impact, mem, arc["factId"], f"GOAL · {p.initials}", t, player=pid, target=ms["milestone"],
            ))
        elif redemption:
            self._add(Storyline(
                f"{pid}-redemption", "redemption", team, opp,
                f"{self.last(pid)} – first goal since being dropped",
                f"{self.last(pid)} answers his critics?",
                "MED", f"Dropped MW{arc['droppedMw']} · no goal since", arc["factId"], f"GOAL · {p.initials}", t, player=pid,
            ))
        tally = self.mem.season_tally_target(pid)
        if tally:
            self._add(Storyline(
                f"{pid}-tally{tally}", "tally", team, opp,
                f"{self.last(pid)} – {ordinal(tally)} of the season",
                f"{self.last(pid)} to hit {tally} for the season?",
                "MED" if tally >= 10 else "LOW", f"{tally - 1} goals this season", arc["factId"], f"GOAL · {p.initials}", t, player=pid, target=tally,
            ))
        if arc["signedThisWeek"]:
            self._add(Storyline(
                f"{pid}-debut", "debut", team, opp,
                f"{self.last(pid)} scores on debut",
                f"{self.last(pid)} scores on debut?",
                "LOW", "Signed this week", arc["factId"], f"GOAL · {p.initials}", t, player=pid,
            ))

    def activate_kickoff(self) -> None:
        self._activated_kickoff = True
        for team in (self.home, self.away):
            for pid in self.stats.on_pitch[team]:
                self.activate_player(pid)
            opp = self.opp(team)
            worst = self.mem.worst_defeat_to(team, opp)
            if worst:
                score = f"{worst['against']}–{worst['for']}"
                when = "August" if worst["season"] == "2026/27" and worst["mw"] <= 3 else (f"MW{worst['mw']}" if worst["season"] == "2026/27" else "last season")
                venue = "at home" if worst["home"] == team else "away"
                margin = worst["against"] - worst["for"]
                self._add(Storyline(
                    f"{team}-revenge", "revenge", team, opp,
                    f"{self.tshort(team)} revenge for last season's {score}" if when == "last season" else f"{self.tshort(team)} revenge for the {when} {score}",
                    f"{self.tshort(team)} revenge for the {score}?",
                    "HIGH" if margin >= 3 else "MED",
                    f"Lost {score} {venue}, {'MW' + str(worst['mw']) if worst['season'] == '2026/27' else 'last season'}",
                    worst["factId"], f"FT · {team} win", self.stats.t,
                ))
            cs = self.mem.clean_sheet_streak(team)
            if cs["streak"] >= 3:
                kp = cs["keeper"]
                self._add(Storyline(
                    f"{team}-cs{cs['streak'] + 1}", "clean_sheet", team, opp,
                    f"{self.last(kp)} – {ordinal(cs['streak'] + 1)} clean sheet in a row",
                    f"{self.last(kp)} keeps a {ordinal(cs['streak'] + 1)} straight clean sheet?",
                    "HIGH" if cs["streak"] >= 4 else "MED", f"{cs['streak']} clean sheets in a row", cs["factId"], f"FT · {team} 0 conceded", self.stats.t,
                    player=kp, target=cs["streak"] + 1,
                ))

    def _activate_late_winner(self) -> None:
        for team in (self.home, self.away):
            gf, ga = self.stats.score[team], self.stats.score[self.opp(team)]
            if gf > ga or ga - gf > 1:
                continue
            lw = self.mem.late_winners(team)
            mem = f"Would be their {ordinal(lw['count'] + 1)} late winner this season" if lw["count"] else "No late winner yet this season"
            self._add(Storyline(
                f"{team}-latewinner", "late_winner", team, self.opp(team),
                f"{self.tshort(team)} late winner",
                f"{self.tshort(team)} late winner?",
                "HIGH" if lw["count"] >= 2 else "MED", mem, lw["factId"], f"GOAL 81'+ · {team}", self.stats.t,
            ))

    # ------------------------------------------------------------------ rates
    def _elapsed(self) -> float:
        return self.stats.t / 60

    def _left(self) -> float:
        return max(0.0, 90 - self._elapsed())

    def compute_rates(self) -> None:
        el = self._elapsed()
        for team in (self.home, self.away):
            opp = self.opp(team)
            k = model.PARAMS["prior_games"]
            prior = 0.5 * (self.mem.scoring_rate(team, k) + self.mem.conceding_rate(opp, k))
            diff = self.stats.score[team] - self.stats.score[opp]
            r = model.team_rate(prior, self.stats.xg_window(team, model.WINDOW), el, self.stats.team[team].red, diff)
            r.team = team
            self.rates[team] = r
            m = self.stats.minute_now()
            hist = self._xg_hist[team]
            if not hist or hist[-1][0] != m:
                hist.append((m, self.stats.xg_window(team, model.WINDOW)))

    def _xg15_before(self, team: str, minutes_ago: int = 15) -> float | None:
        m = self.stats.minute_now() - minutes_ago
        if m < 15:
            return None
        return self.stats.xg_window(team, model.WINDOW, end_minute=m)

    def shares(self, team: str) -> dict[str, float]:
        raw = {}
        for pid in self.stats.on_pitch[team]:
            p = self.w.player(pid)
            if p.role == "GK":
                continue
            arc_apps = self.mem.apps(pid)
            raw[pid] = self.mem.goal_share(pid) if arc_apps > 0 else ROLE_SHARE_PRIOR[p.role] * 0.8
        tot = sum(raw.values()) or 1.0
        prior = {k: v / tot for k, v in raw.items()}
        team_xg = self.stats.team[team].xg
        if team_xg < 0.2:
            return prior
        w = 0.35 * min(1.0, team_xg / 1.2)
        return {pid: (1 - w) * prior[pid] + w * (self.stats.players[pid].xg / team_xg) for pid in prior}

    # ------------------------------------------------------------------ update
    def update(self) -> None:
        if not self._activated_kickoff:
            return
        self.compute_rates()
        if self._elapsed() >= 69.0:
            self._activate_late_winner()
        if self._elapsed() >= 80.0 and not self._passed_80:
            self._passed_80 = True
            for s in self.lines.values():
                if s.kind == "late_winner" and not s.resolved and self.stats.score[s.team] > self.stats.score[s.opp]:
                    self._resolve(s, "ruled_out", "Ahead before the 80th minute", None)
        left = self._left()
        shares = {t: self.shares(t) for t in (self.home, self.away)}
        sample = self.stats.t - self._last_sample >= SAMPLE_EVERY_S
        for s in self.lines.values():
            if s.resolved:
                continue
            s.p, s.why, s.drivers = self._prob(s, left, shares)
            if s.p > s.peak_p:
                s.peak_p, s.peak_t = s.p, self.stats.t
            if sample or not s.history:
                s.history.append((self.stats.t, s.p))
        if sample:
            self._last_sample = self.stats.t

    def _xg_why(self, team: str) -> tuple[str, list[str]]:
        now = self.stats.xg_window(team, model.WINDOW)
        before = self._xg15_before(team)
        tid = team
        drivers = []
        if before is not None:
            why = f"{tid} xG last 15': {before:.2f} → {now:.2f}"
            if now >= 0.3 and now >= 1.8 * max(before, 0.05):
                why += " (doubled)" if now < 3 * max(before, 0.05) else " (surging)"
        else:
            why = f"{tid} xG so far: {self.stats.team[team].xg:.2f}"
        shots10 = self.stats.shots_window(team, 10)
        if shots10:
            drivers.append(f"{shots10} shot{'s' if shots10 != 1 else ''} in the last 10 minutes")
        cc = self.stats.control_chaos()
        if cc["label"] == "chaotic":
            drivers.append(f"Control ↔ Chaos {cc['index']:.2f} (open, end-to-end)")
        return why, drivers

    def _prob(self, s: Storyline, left: float, shares: dict[str, dict[str, float]]) -> tuple[float, str, list[str]]:
        team, opp = s.team, s.opp
        lam, lam_o = self.rates[team].lam, self.rates[opp].lam
        gf, ga = self.stats.score[team], self.stats.score[opp]
        if s.kind in PLAYER_KINDS:
            share = shares[team].get(s.player or "", 0.0)
            if share == 0.0:
                return 0.0, "Not on the pitch", []
            k = 1
            p = model.p_player_scores(lam, share, left, k)
            why, drivers = self._xg_why(team)
            pl = self.stats.players[s.player]
            drivers = [f"{round(100 * share)}% of {self.tshort(team)}'s expected goals"] + drivers
            if pl.shots:
                drivers.append(f"{pl.shots} shot{'s' if pl.shots != 1 else ''}, {pl.xg:.2f} xG today")
            return p, why, drivers
        if s.kind == "clean_sheet":
            if ga > 0:
                return 0.0, "Conceded", []
            p = model.p_clean_sheet(lam_o, left)
            why, drivers = self._xg_why(opp)
            return p, f"{round(left)} min to hold · " + why, drivers
        if s.kind == "revenge":
            p = model.outcome_probs(gf, ga, lam, lam_o, left)["win"]
            state = "Leading" if gf > ga else ("Level" if gf == ga else "Trailing")
            why, drivers = self._xg_why(team)
            return p, f"{state} with {round(left)} min left", [why] + drivers
        if s.kind == "late_winner":
            p = model.p_late_winner(gf, ga, lam, lam_o, self._elapsed())
            why, drivers = self._xg_why(team)
            shots10 = self.stats.shots_window(team, 10)
            head = f"{shots10} shot{'s' if shots10 != 1 else ''} in 10 minutes" if shots10 else why
            return p, head, [why] + drivers
        return 0.0, "", []

    # ------------------------------------------------------------------ triggers
    def on_event(self, e: dict) -> list[Storyline]:
        """Check triggers. Returns storylines that just resolved as 'happened'."""
        typ, team, pid, q = e["type"], e.get("team"), e.get("player"), e.get("qualifiers", {})
        fired: list[Storyline] = []
        if typ == "match_metadata":
            return fired
        if not self._activated_kickoff and typ == "period_start":
            self.activate_kickoff()
            return fired
        if typ == "shot" and e["outcome"] == "goal":
            for s in list(self.lines.values()):
                if s.resolved:
                    continue
                if s.kind in PLAYER_KINDS and s.player == pid:
                    self._resolve(s, "happened", f"Scored {e['minute']}'", e["id"])
                    fired.append(s)
                if s.kind == "clean_sheet" and s.opp == team:
                    self._resolve(s, "ruled_out", f"Conceded {e['minute']}'", e["id"])
            # follow-up storyline for the scorer
            goals_today = self.stats.players[pid].goals
            if goals_today in (1, 2) and self.w.player(pid).role != "GK":
                kind = "brace" if goals_today == 1 else "hattrick"
                club = self.mem.club_goals(pid) + goals_today
                ms_line = any(x.kind == "milestone" and x.player == pid for x in self.lines.values())
                title = f"{self.last(pid)} makes it {club + 1}" if ms_line else f"{self.last(pid)} – {'brace' if kind == 'brace' else 'hat-trick'}"
                self._add(Storyline(
                    f"{pid}-{kind}", kind, team, self.opp(team), title, f"{self.last(pid)} makes it {club + 1}?" if ms_line else f"{self.last(pid)} {'brace' if kind == 'brace' else 'hat-trick'}?",
                    "HIGH" if kind == "hattrick" else "MED", f"{club} club goals", f"mem-player-{pid}", f"GOAL · {self.w.player(pid).initials}", e["t"], player=pid,
                ))
        elif typ == "substitution":
            off, on = q["playerOff"], q["playerOn"]
            for s in self.lines.values():
                if not s.resolved and s.kind in PLAYER_KINDS and s.player == off:
                    self._resolve(s, "ruled_out", f"Subbed off {e['minute']}'", e["id"])
            self.activate_player(on)
        elif typ == "card" and e["outcome"] == "red":
            for s in self.lines.values():
                if not s.resolved and s.player == pid and s.kind in PLAYER_KINDS:
                    self._resolve(s, "ruled_out", f"Sent off {e['minute']}'", e["id"])
        elif typ == "full_time":
            fired += self._resolve_ft(e)
        return fired

    def _resolve(self, s: Storyline, res: str, note: str, event_id: str | None) -> None:
        s.resolution, s.resolved_t, s.resolution_note, s.resolution_event = res, self.stats.t, note, event_id
        if res == "happened":
            s.p = 1.0
        elif res == "ruled_out":
            s.p = 0.0
        s.history.append((self.stats.t, s.p))
        self._log(s, res, note)

    def _near_miss_evidence(self, s: Storyline) -> dict | None:
        since = s.activated_t
        if s.kind in PLAYER_KINDS:
            shots = [x for x in self.stats.shots if x["player"] == s.player and x["t"] >= since and x["outcome"] != "goal"]
        else:
            shots = [x for x in self.stats.shots if x["team"] == s.team and x["t"] >= max(since, 75 * 60) and x["outcome"] != "goal"]
        good = [x for x in shots if x["outcome"] == "post" or x["xg"] >= BIG_CHANCE_XG]
        return max(good, key=lambda x: (x["outcome"] == "post", x["xg"])) if good else None

    def _resolve_ft(self, e: dict) -> list[Storyline]:
        fired = []
        goals = self.stats.goals
        for s in self.lines.values():
            if s.resolved:
                continue
            gf, ga = self.stats.score[s.team], self.stats.score[s.opp]
            happened = False
            if s.kind == "clean_sheet":
                happened = ga == 0
            elif s.kind == "revenge":
                happened = gf > ga
            elif s.kind == "late_winner":
                f = a = 0
                decisive = None
                for g in goals:
                    was_ahead = f > a
                    if g["team"] == s.team:
                        f += 1
                    else:
                        a += 1
                    if g["team"] == s.team and not was_ahead and f > a:
                        decisive = g["minute"]
                happened = gf > ga and decisive is not None and decisive > 80
            if happened:
                self._resolve(s, "happened", "Full time", e["id"])
                fired.append(s)
                continue
            ev = self._near_miss_evidence(s)
            if ev:
                label = "hit the post" if ev["outcome"] == "post" else f"{ev['xg']:.2f} xG chance {ev['outcome'].replace('_', ' ')}"
                self._resolve(s, "near_miss", f"{ev['minute']}' {label}", ev["id"])
            else:
                self._resolve(s, "unresolved", "Draw" if gf == ga and s.kind in ("revenge", "late_winner") else "Full time", e["id"])
        return fired

    # ------------------------------------------------------------------ views
    def ranked(self) -> list[Storyline]:
        active = [s for s in self.lines.values() if not s.resolved and s.p > 0.005]
        return sorted(active, key=lambda s: -s.score)

    def resolved_lines(self) -> list[Storyline]:
        return sorted([s for s in self.lines.values() if s.resolved], key=lambda s: s.resolved_t or 0)

    def evidence(self, s: Storyline) -> list[dict]:
        now = self.stats.t
        team = s.opp if s.kind == "clean_sheet" else s.team
        ev = []
        for x in self.stats.shots:
            if x["team"] == team and now - x["t"] <= 15 * 60 and x["xg"] >= 0.15:
                ev.append({"id": x["id"], "minute": x["minute"], "text": f"{x['minute']}' chance {x['xg']:.2f} xG ({x['outcome'].replace('_', ' ')})"})
        for ins in self.stats.insights:
            if ins.kind == "pressure_spike" and ins.team == team and now - ins.t <= 15 * 60:
                ev.append({"id": ins.id, "minute": ins.minute, "text": f"{ins.minute}' pressure spike"})
        ev.sort(key=lambda d: -d["minute"])
        ev = ev[:3]
        if s.memory_fact:
            ev.append({"id": s.memory_fact, "minute": None, "text": f"{s.memory_line} (Season Memory)"})
        return ev
