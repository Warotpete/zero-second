"""Deterministic Writer used when no Foundry endpoint is configured.

Produces the same four versions the Foundry Writer does (EN analyst, EN casual,
TH casual with an English gloss, broadcast overlay), using only facts-pack values
and live slots.
"""

from __future__ import annotations

from ..util import ordinal

NUM_WORD = {10: "TEN", 25: "TWENTY-FIVE", 50: "FIFTY", 75: "SEVENTY-FIVE", 100: "A HUNDRED"}


def _last(full: str) -> str:
    return full.split()[-1]


def write_versions(f: dict) -> dict:
    kind = f["storyline"]["kind"]
    v = f["values"]
    team, opp = f["team"], f["opponent"]
    subj = f["players"].get("subject")
    name = f["names"].get(subj, "") if subj else ""
    last = _last(name) if name else ""
    up = last.upper()
    target = v.get("target")
    dropped = v.get("dropped_mw")

    if kind == "milestone":
        word = NUM_WORD.get(target, str(target))
        if dropped:
            analyst = f"{target} club goals for {name}, and his first since being dropped for Matchweek {dropped}: a {{shot_xg}} xG chance finished at {{shot_speed}} km/h in the {{minute_ord}} minute."
            casual = f"{word.title()}! {last} answers his doubters in style."
            th = f"{last} ยิงครบ {target} ประตูให้สโมสรแล้ว! ประตูแรกหลังถูกดร็อปในนัดที่ {dropped}"
            gloss = f"{last} reaches {target} club goals! His first since being dropped in Matchweek {dropped}."
            sub = f"FIRST SINCE MW{dropped}"
        else:
            analyst = f"{target} club goals for {name}. Number {target} arrives from a {{shot_xg}} xG chance, struck at {{shot_speed}} km/h in the {{minute_ord}} minute."
            casual = f"{word.title()} for the club! {last} brings up the milestone."
            th = f"{last} ยิงครบ {target} ประตูให้สโมสรแล้ว!"
            gloss = f"{last} reaches {target} club goals!"
            sub = f"{{minute}}' · {{shot_xg}} XG"
        overlay = {"headline": f"{up} · {target} CLUB GOALS", "sub": sub}
    elif kind == "redemption":
        analyst = f"{name} scores for the first time since being dropped for Matchweek {dropped}, from a {{shot_xg}} xG chance in the {{minute_ord}} minute."
        casual = f"{last} is back! First goal since being dropped, and what a moment."
        th = f"{last} กลับมาซัดประตูแรกหลังถูกดร็อปในนัดที่ {dropped}!"
        gloss = f"{last} scores his first goal since being dropped in Matchweek {dropped}!"
        overlay = {"headline": f"{up} · FIRST SINCE BEING DROPPED", "sub": f"{{minute}}' · {{shot_xg}} XG"}
    elif kind == "tally":
        analyst = f"{name} reaches {target} goals for the season with a {{shot_xg}} xG finish in the {{minute_ord}} minute."
        casual = f"That's {target} this season for {last}!"
        th = f"{last} ซัดประตูที่ {target} ของฤดูกาล!"
        gloss = f"{last} scores his {ordinal(target)} goal of the season!"
        overlay = {"headline": f"{up} · {target} THIS SEASON", "sub": f"{{minute}}' · {{shot_xg}} XG"}
    elif kind == "debut":
        analyst = f"{name}, signed this week, scores on his debut: a {{shot_xg}} xG chance taken in the {{minute_ord}} minute."
        casual = f"What a start! {last} scores on his debut."
        th = f"{last} ประเดิมสนามนัดแรกก็ยิงประตูได้ทันที!"
        gloss = f"{last} scores on his debut!"
        overlay = {"headline": f"{up} · GOAL ON DEBUT", "sub": "SIGNED THIS WEEK"}
    elif kind in ("brace", "hattrick"):
        label = "brace" if kind == "brace" else "hat-trick"
        analyst = f"{name} adds another, his {label} today from a {{shot_xg}} xG chance in the {{minute_ord}} minute."
        casual = f"{last} again! That's a {label}."
        th = f"{last} ซัด{'เบิ้ล' if kind == 'brace' else 'แฮตทริก'}!"
        gloss = f"{last} scores a {label}!"
        overlay = {"headline": f"{up} · {label.upper()}", "sub": f"{{minute}}' · {{shot_xg}} XG"}
    elif kind == "clean_sheet":
        n = v["target"]
        analyst = f"{name} keeps a {ordinal(n)} consecutive clean sheet for {team['short']}."
        casual = f"Another shutout! {last} makes it {n} clean sheets in a row."
        th = f"{last} เก็บคลีนชีตได้ {n} นัดติดต่อกัน!"
        gloss = f"{last} keeps a clean sheet for the {ordinal(n)} match in a row!"
        overlay = {"headline": f"{up} · {n} CLEAN SHEETS IN A ROW", "sub": f"{team['short'].upper()} · FULL TIME"}
    elif kind == "revenge":
        then = f"{v['then_against']}–{v['then_for']}"
        when = "in August" if v.get("then_season") == "2026/27" and v.get("then_mw", 99) <= 3 else ("this season" if v.get("then_season") == "2026/27" else "last season")
        analyst = f"{team['name']} beat {opp['short']}, avenging the {then} defeat {when}. Final score {{score}}."
        casual = f"Revenge is sweet! {team['short']} get one back for the {then}."
        th = f"{team['short']} แก้แค้นสำเร็จ! ล้างความพ่าย {then} ได้แล้ว"
        gloss = f"{team['short']} get their revenge for the {then} defeat!"
        overlay = {"headline": f"{team['short'].upper()} · REVENGE FOR THE {then}", "sub": "FULL TIME · {score}"}
    elif kind == "late_winner":
        n = v["late_winner_n"]
        analyst = f"{team['name']} win it late: the decisive goal came after the 80th minute, their {ordinal(n)} late winner this season. Final score {{score}}."
        casual = f"Late, late drama! {team['short']} snatch it at the death."
        th = f"{team['short']} ยิงประตูชัยช่วงท้ายเกม! เป็นครั้งที่ {n} ของฤดูกาล"
        gloss = f"{team['short']} score a late winner, their {ordinal(n)} of the season!"
        overlay = {"headline": f"{team['short'].upper()} · LATE WINNER", "sub": f"{ordinal(n).upper()} THIS SEASON"}
    else:  # reactive goal with no storyline
        analyst = f"Goal for {team['short']}: {name} scores in the {{minute_ord}} minute from a {{shot_xg}} xG chance. It's {{score}}."
        casual = f"GOAL! {last} scores for {team['short']}!"
        th = f"ประตู! {last} ทำประตูให้ {team['short']} ในนาทีที่ {{minute}}"
        gloss = f"Goal! {last} scores for {team['short']} in minute {{minute}}."
        overlay = {"headline": f"GOAL · {up}", "sub": "{minute}' · {score}"}

    return {
        "versions": [
            {"key": "en_analyst", "lang": "en", "audience": "analyst", "text": analyst},
            {"key": "en_casual", "lang": "en", "audience": "casual", "text": casual},
            {"key": "th_casual", "lang": "th", "audience": "casual", "text": th, "gloss": gloss},
            {"key": "overlay", "lang": "en", "audience": "overlay", "text": overlay["headline"], "sub": overlay["sub"]},
        ],
        "angle": _angle(kind, f),
    }


def _angle(kind: str, f: dict) -> str:
    return {
        "milestone": "Milestone plus personal comeback arc" if f["values"].get("dropped_mw") else "Club milestone",
        "redemption": "Comeback arc after being dropped",
        "tally": "Season scoring landmark",
        "debut": "New signing, instant impact",
        "brace": "Hot hand: second of the day",
        "hattrick": "Hat-trick watch",
        "clean_sheet": "Streak defence",
        "revenge": "Rivalry: unfinished business",
        "late_winner": "Late drama with season context",
    }.get(kind, "Live moment")


def write_recap(r: dict) -> dict:
    """Recap from the lifecycle log. `r` is built by the orchestrator (all facts verified)."""
    home, away, hs, as_ = r["home"], r["away"], r["home_goals"], r["away_goals"]
    score = f"{hs}–{as_}"
    if hs > as_:
        result = f"{home} beat {away} {score}"
    elif hs < as_:
        result = f"{away} won {as_}–{hs} at {home}"
    else:
        result = f"{home} and {away} drew {score}"
    goals = r["goals"]
    goal_bits = [f"{g['scorer']} ({g['minute']}') [{g['ref']}]" for g in goals]
    happened = [s for s in r["storylines"] if s["resolution"] == "happened"]
    near = [s for s in r["storylines"] if s["resolution"] == "near_miss"]
    rank = {"HIGH": 0, "MED": 1, "LOW": 2}
    called = sorted([s for s in happened if s.get("calledMinute")], key=lambda s: rank.get(s.get("impact", "LOW"), 3))

    b = [f"{result}." + (f" Goals: {', '.join(goal_bits)}." if goal_bits else " No goals.")]
    for s in happened[:3]:
        b.append(f"{s['title']}: it happened in the {ordinal(s['resolvedMinute'])} minute [{s['ref']}].")
    for s in near[:2]:
        b.append(f"{s['title']} came close: {s['resolutionNote']} [{s['ref']}].")
    broadcaster = " ".join(b)

    c = [f"Full time: {result}!"]
    if called:
        s = called[0]
        when = "before kickoff" if s["calledMinute"] <= 1 else f"in the {ordinal(s['calledMinute'])} minute"
        c.append(f"We had \"{s['title']}\" ready {when}, and it came true.")
    if near:
        c.append(f"So close: {near[0]['title']} ({near[0]['resolutionNote']}).")
    casual = " ".join(c)

    a = [f"{result}. xG {r['home_xg']:.2f}–{r['away_xg']:.2f}, shots {r['home_shots']}–{r['away_shots']}, possession {r['home_poss']}%–{r['away_poss']}%."]
    for s in happened[:3]:
        a.append(f"{s['title']}: forecast peaked at {s['peakPct']}% ({s['peakMinute']}') before it happened at {s['resolvedMinute']}'.")
    for s in near[:2]:
        a.append(f"Near miss: {s['title']} ({s['resolutionNote']}).")
    analyst = " ".join(a)
    return {"broadcaster": broadcaster, "casual": casual, "analyst": analyst}
