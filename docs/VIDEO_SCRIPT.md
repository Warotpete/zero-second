# Demo video script (1:55)

**Setup before recording**
- Deployed URL (or localhost) in a clean browser window at 1600×900, zoom 100%. Second window for the phone view: browser dev tools device mode, iPhone 14 Pro (430 wide), on `/fan`.
- Room: `?room=video`. Before recording: **New match → Demo**, turn **Autopilot producer OFF**, speed **20×**.
- Second room for the fault shot: open `?room=videofault`, **New match → Demo**, turn **Fault injection ON** first, then **Jump → 80'**. Its Agent Trace will show the rejection and redraft for the late-winner storyline.
- Only say "agents on Microsoft Foundry" if the status bar shows **Foundry · <model>**. With the local writer, say "agents" instead.
- Screen recorder: Clipchamp (free on Windows) or OBS. Record each shot separately and cut them together. Voiceover recorded separately for a clean sound.
- Music: none, or a royalty-free track from the Clipchamp/YouTube Audio Library with a clear licence. No league logos or real footage anywhere.
- Captions on (judges often watch muted).

Target about 250 spoken words. Timings are the cut points.

| Time | Screen | Voiceover |
|---|---|---|
| **0:00–0:08** | Black → logo "0″ Zero Second · Ready before it happens" | "Every football app tells you what just happened. Zero Second gets ready for what's *about* to happen." |
| **0:08–0:20** | Media Desk at **60'**, slow pan across the Rundown | "It's a newsroom engine for clubs and broadcasters. Story Radar ranks the storylines that could happen next, by probability times impact, using a calibrated statistical model, not a guess from a chatbot." |
| **0:20–0:38** | Jump to **66'**. Zoom on *Mendes – 50th club goal*: status **Ready**, Δ15' ▲, "Why rising: HFC xG last 15' … (surging)". Click it; preview shows four versions with live slots | "Harbour City are surging. Mendes is one away from fifty club goals, his first since being dropped. The Editor, Writer and Verifier agents on Microsoft Foundry have already written it: analyst, casual, Thai, and a broadcast graphic, with live slots for the minute and the xG." |
| **0:38–0:45** | Press **A** → tag turns *Pre-approved* | "The producer approves it now, before it happens." |
| **0:45–1:00** | Play to **78'**. Goal. Rundown row turns *Happened*; cut to phone: lower-third + "Fifty! Mendes answers his doubters", badge "Called…"; toggle **ไทย**, then **Analyst** with shot map | "Seventy-eight minutes. He scores, and it's out instantly, with the real numbers filled in from the Stats Engine. Every fan gets their own version: casual, analyst, English or Thai, following their player." |
| **1:00–1:15** | **Watch for** tab: "Harbour City late winner? 31% ▲", bell on. Then Rundown shows *Silva clean sheet – Ruled out 63'* | "Fans get the forecast too: what to watch for, how likely, and why. Storylines that die are tracked honestly, ruled out or near miss." |
| **1:15–1:30** | Switch to room `videofault`, open **Agent Trace** (storyline marked "(rejection)"): magenta "Rejected: number 81 is not in the facts pack" → "Redraft" → green "All verified". Audit log | "For enterprise use, nothing ships unchecked. Here we inject a wrong number; the Verifier catches it and the Writer redrafts. Every step is traced and audited." |
| **1:30–1:42** | **Recap** at FT: outcomes table, near miss 89' post, calibration chart | "At full time the Recap agent writes cited recaps from the storyline log, and we publish how accurate our forecasts are on two hundred held-out matches." |
| **1:42–1:52** | Live page: **New match → seed 4821**, different clubs and storylines appear. Then architecture diagram from the README | "Nothing is scripted: any seed is a new synthetic match. Built with Microsoft Agent Framework, Foundry, an MCP server for stats and memory, on Azure Container Apps." |
| **1:52–1:58** | Logo + URL + GitHub | "Zero Second. Ready before it happens." |

**Checks before uploading**
- Under 2:00 (aim for 1:55).
- Upload to YouTube as **Public** or **Unlisted** (the rules ask for a public URL; Public is safest). Title: "Zero Second – the anticipation layer for football (Inside the Game hackathon)".
- No copyrighted music, no real club or league marks.
