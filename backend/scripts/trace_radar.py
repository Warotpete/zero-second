import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import sys
from zerosecond.pitchforge.scenario import build_scenario_world, build_scenario_history, scenario_config
from zerosecond.pitchforge.match import simulate
from zerosecond.memory.store import SeasonMemory
from zerosecond.stats.engine import StatsEngine
from zerosecond.radar.radar import StoryRadar
w=build_scenario_world(); h=build_scenario_history(w); m=SeasonMemory(w,h); cfg=scenario_config(int(sys.argv[1]) if len(sys.argv)>1 else 2026)
ev=simulate(w,cfg)
st=StatsEngine("HFC","NLU"); st.names={p.id:p.name for p in w.all_players()}; st.team_names={t:w.teams[t].short for t in w.teams}
r=StoryRadar(w,m,st,"HFC","NLU")
checkpoints=[1,30,55,60,63,65,68,72,76,78,80,85,89,91]
ci=0
for e in ev:
    st.ingest(e); r.on_event(e); r.update()
    while ci<len(checkpoints) and e['t']>=checkpoints[ci]*60-1:
        print(f"--- {checkpoints[ci]}' score {st.score} xg H {st.team['HFC'].xg:.2f} N {st.team['NLU'].xg:.2f} lamH {r.rates['HFC'].lam*90:.2f} lamN {r.rates['NLU'].lam*90:.2f}")
        for s in sorted(r.lines.values(), key=lambda s:-s.score)[:8]:
            print(f"   {s.title:45s} {100*s.p:5.1f}% {s.impact:4s} {s.status():11s} | {s.why} | {s.memory_line}")
        ci+=1
print("goals", [(g['minute'],g['player'],g['xg']) for g in st.goals])
print("shots HFC/NLU", st.team['HFC'].shots, st.team['NLU'].shots, "insights", [(i.minute,i.kind,i.text) for i in st.insights][:12])
for s in r.resolved_lines(): print("RES", s.title, s.resolution, s.resolution_note, "peak", round(100*s.peak_p), int(s.peak_t//60)+1)
