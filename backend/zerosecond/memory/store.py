"""Season Memory store.

Every fact has a stable id (e.g. ``mem-mw3-NLU-HFC``) so agents can cite it and the
Verifier can check it. All values are computed from the generated season, never
written by a model.
"""

from __future__ import annotations

from collections import defaultdict

from ..pitchforge.season import LAST_SEASON, SEASON, Result, SeasonHistory
from ..pitchforge.world import World
from ..util import short_name

MILESTONES = [10, 25, 50, 75, 100, 150, 200, 250, 300]
ROLE_SHARE_PRIOR = {"FWD": 0.2, "MID": 0.07, "DEF": 0.025, "GK": 0.0}


class SeasonMemory:
    def __init__(self, world: World, history: SeasonHistory):
        self.w = world
        self.h = history
        self.season = [r for r in history.results if r.season == SEASON]
        self.last = history.last_season
        self._season_goals: dict[str, list[tuple[int, int]]] = defaultdict(list)  # pid -> [(mw, minute)]
        for r in self.season:
            for g in r.goals:
                self._season_goals[g.scorer].append((r.mw, g.minute))

    # ------------------------------------------------------------- players
    def name(self, pid: str) -> str:
        return self.w.player(pid).name

    def season_goals(self, pid: str) -> int:
        return len(self._season_goals[pid])

    def club_goals(self, pid: str) -> int:
        return self.w.player(pid).club_goals_before_season + self.season_goals(pid)

    def last_goal(self, pid: str) -> tuple[int, int] | None:
        goals = self._season_goals[pid]
        return max(goals) if goals else None

    def arcs(self, pid: str) -> list[dict]:
        return [a.__dict__ for a in self.h.arcs if a.player == pid]

    def apps(self, pid: str) -> int:
        team = pid.split("-")[0]
        p = self.w.player(pid)
        if not p.starter:
            return 0
        return sum(1 for r in self.season if team in (r.home, r.away) and pid not in r.dropped)

    def player_arc(self, pid: str) -> dict:
        p = self.w.player(pid)
        lg = self.last_goal(pid)
        dropped = [a for a in self.arcs(pid) if a["kind"] == "dropped"]
        dropped_mw = dropped[-1]["mw"] if dropped else None
        out = {
            "player": pid,
            "name": p.name,
            "short": short_name(p.name),
            "team": p.team_id,
            "role": p.role,
            "clubGoals": self.club_goals(pid),
            "seasonGoals": self.season_goals(pid),
            "apps": self.apps(pid),
            "lastGoalMw": lg[0] if lg else None,
            "droppedMw": dropped_mw,
            "noGoalSinceDropped": bool(dropped_mw and (not lg or lg[0] < dropped_mw)),
            "signedThisWeek": p.signed_this_week,
            "factId": f"mem-player-{pid}",
        }
        return out

    def milestone(self, pid: str) -> dict | None:
        """Next club-goal milestone if it is one goal away."""
        g = self.club_goals(pid)
        for m in MILESTONES:
            if g < m:
                if m - g == 1:
                    return {"milestone": m, "current": g, "factId": f"mem-player-{pid}"}
                return None
        return None

    def season_tally_target(self, pid: str) -> int | None:
        """Round season number (10, 15, 20 ...) reachable with the next goal."""
        g = self.season_goals(pid)
        return g + 1 if g >= 9 and (g + 1) % 5 == 0 else None

    def goal_share(self, pid: str) -> float:
        """Share of the team's goals this player is expected to take (shrunk to a role prior)."""
        p = self.w.player(pid)
        team = p.team_id
        team_goals = sum(len(v) for k, v in self._season_goals.items() if k.startswith(team + "-"))
        prior = ROLE_SHARE_PRIOR[p.role]
        k = 8.0
        return (self.season_goals(pid) + k * prior) / (team_goals + k)

    # ------------------------------------------------------------- teams
    def team_results(self, team: str, season: str = SEASON) -> list[Result]:
        rs = self.season if season == SEASON else self.last
        return sorted([r for r in rs if team in (r.home, r.away)], key=lambda r: r.mw)

    def scoring_rate(self, team: str, prior_games: float = 4.0) -> float:
        """Goals per minute, blending this season with last season, shrunk to the league mean."""
        cur = self.team_results(team)
        prev = self.team_results(team, LAST_SEASON)
        g_cur = sum(r.score_for(team)[0] for r in cur)
        g_prev = sum(r.score_for(team)[0] for r in prev)
        n_cur, n_prev = len(cur), len(prev)
        per90 = (g_cur + 0.3 * g_prev + 1.35 * prior_games) / (n_cur + 0.3 * n_prev + prior_games)
        return per90 / 90

    def conceding_rate(self, team: str, prior_games: float = 4.0) -> float:
        cur = self.team_results(team)
        prev = self.team_results(team, LAST_SEASON)
        c_cur = sum(r.score_for(team)[1] for r in cur)
        c_prev = sum(r.score_for(team)[1] for r in prev)
        per90 = (c_cur + 0.3 * c_prev + 1.35 * prior_games) / (len(cur) + 0.3 * len(prev) + prior_games)
        return per90 / 90

    def clean_sheet_streak(self, team: str) -> dict:
        streak = 0
        for r in reversed(self.team_results(team)):
            if r.score_for(team)[1] == 0:
                streak += 1
            else:
                break
        gk = next(p for p in self.w.teams[team].starters if p.role == "GK")
        return {"team": team, "keeper": gk.id, "keeperName": gk.name, "streak": streak, "factId": f"mem-cs-{team}"}

    def late_winners(self, team: str) -> dict:
        """Wins where the decisive go-ahead goal came after the 80th minute."""
        mws = []
        for r in self.team_results(team):
            gf, ga = r.score_for(team)
            if gf <= ga:
                continue
            f = a = 0
            decisive = None
            for g in r.goals:
                was_ahead = f > a
                if g.team == team:
                    f += 1
                else:
                    a += 1
                if g.team == team and not was_ahead and f > a:
                    decisive = g.minute
            if decisive and decisive > 80:
                mws.append(r.mw)
        return {"team": team, "count": len(mws), "matchweeks": mws, "factId": f"mem-late-{team}"}

    def h2h(self, team: str, opp: str) -> list[dict]:
        out = []
        for r in self.season + self.last:
            if {r.home, r.away} == {team, opp}:
                gf, ga = r.score_for(team)
                out.append({**r.public(), "for": gf, "against": ga, "factId": f"mem-{r.id}"})
        return sorted(out, key=lambda d: (d["season"], d["mw"]), reverse=True)

    def worst_defeat_to(self, team: str, opp: str) -> dict | None:
        """Biggest loss of `team` against `opp` in the last two seasons (margin >= 2)."""
        losses = [d for d in self.h2h(team, opp) if d["against"] - d["for"] >= 2]
        if not losses:
            return None
        return max(losses, key=lambda d: (d["against"] - d["for"], d["season"] == SEASON))

    def form(self, team: str, n: int = 5) -> str:
        out = []
        for r in self.team_results(team)[-n:]:
            gf, ga = r.score_for(team)
            out.append("W" if gf > ga else ("D" if gf == ga else "L"))
        return "".join(out)

    def table(self) -> list[dict]:
        rows = {t: {"team": t, "name": self.w.teams[t].name, "p": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "pts": 0} for t in self.w.teams}
        for r in self.season:
            for t in (r.home, r.away):
                gf, ga = r.score_for(t)
                row = rows[t]
                row["p"] += 1
                row["gf"] += gf
                row["ga"] += ga
                if gf > ga:
                    row["w"] += 1
                    row["pts"] += 3
                elif gf == ga:
                    row["d"] += 1
                    row["pts"] += 1
                else:
                    row["l"] += 1
        out = sorted(rows.values(), key=lambda r: (-r["pts"], -(r["gf"] - r["ga"]), -r["gf"], r["name"]))
        for i, r in enumerate(out, 1):
            r["pos"] = i
            r["gd"] = r["gf"] - r["ga"]
        return out

    def top_scorers(self, n: int = 10) -> list[dict]:
        rows = [(pid, len(g)) for pid, g in self._season_goals.items()]
        rows.sort(key=lambda r: -r[1])
        return [{"player": pid, "name": self.name(pid), "team": pid.split("-")[0], "goals": g} for pid, g in rows[:n]]

    def summary(self, home: str, away: str) -> dict:
        """Everything the Media Desk 'Season Memory' page shows for the current fixture."""
        players = [p.id for t in (home, away) for p in self.w.teams[t].players]
        return {
            "matchweek": self.h.current_mw,
            "table": self.table(),
            "form": {home: self.form(home), away: self.form(away)},
            "h2h": self.h2h(home, away),
            "cleanSheets": {home: self.clean_sheet_streak(home), away: self.clean_sheet_streak(away)},
            "lateWinners": {home: self.late_winners(home), away: self.late_winners(away)},
            "players": [self.player_arc(pid) for pid in players],
            "topScorers": self.top_scorers(),
            "results": [r.public() for r in self.season if home in (r.home, r.away) or away in (r.home, r.away)],
        }
