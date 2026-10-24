"""Run a full match headless and print what the Media Desk would show."""
import asyncio, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from zerosecond.runtime import MatchRuntime

async def main(seed: int, fault: bool):
    rt = MatchRuntime("t", seed)
    rt.orch.fault_injection = fault
    for m in (66, 72, 78, 91):
        await rt.jump(m)
        if rt.orch.tasks: await asyncio.wait(list(rt.orch.tasks), timeout=5)
        snap = rt.snapshot()
        print(f"=== {snap['match']['clock']} {snap['match']['home']['short']} {snap['match']['score']['home']}-{snap['match']['score']['away']} {snap['match']['away']['short']}")
        for s in sorted(snap['storylines'], key=lambda d: -d['score'])[:7]:
            print(f"  {s['title']:42s} {s['pct']:3d}% {s['impact']:4s} {s['status']:12s} d15={s['delta15']} called={s['calledMinute']} {s['resolutionNote']}")
    await asyncio.sleep(0.1)
    if rt.orch.tasks: await asyncio.wait(list(rt.orch.tasks), timeout=5)
    print("--- audit"); [print("  ", a['clock'], a['actor'], a['action'], a['detail']) for a in rt.orch.audit[:40]]
    print("--- moments"); [print("  ", m['minute'], m['title'], "| called", m['calledMinute'], m['calledPct'], "|", m['versions'][0]['text'], "|", m['versions'][2]['text'], "|", m['versions'][3]['text'], m['versions'][3].get('sub')) for m in rt.orch.moments]
    print("--- recap"); print(rt.orch.recap and rt.orch.recap['text'])
    sid = next(iter(rt.orch.traces)); print("--- trace", sid); [print("  ", x['clock'], x['lane'], x['kind'], x['label']) for x in rt.orch.traces[sid]]

asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 2026, "--fault" in sys.argv))
