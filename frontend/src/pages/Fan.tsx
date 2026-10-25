import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, usePoll } from "../api";
import { Avatar, Badge, Logo, Momentum, ProbBar, sideOf, initialsOf } from "../components/ui";
import type { LineupPlayer, Moment, Snapshot, Storyline } from "../types";

type Mode = "casual" | "analyst";
type Tab = "moments" | "watch" | "timeline" | "stats" | "lineups";

function useLocal<T>(key: string, init: T): [T, (v: T) => void] {
  const [v, setV] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw ? (JSON.parse(raw) as T) : init;
    } catch {
      return init;
    }
  });
  const set = (x: T) => {
    setV(x);
    try { localStorage.setItem(key, JSON.stringify(x)); } catch { /* private mode */ }
  };
  return [v, set];
}

function Pitch({ snap, lineups, moment, follow }: { snap: Snapshot; lineups: Record<string, LineupPlayer[]> | null; moment: Moment | null; follow: string }) {
  const home = snap.match.home.id;
  const ball = snap.ball;
  const shift = (ball.x - 50) * 0.22;
  const dots: { x: number; y: number; side: "home" | "away"; id: string; ini: string }[] = [];
  if (lineups) {
    for (const [tid, players] of Object.entries(lineups)) {
      for (const p of players.filter((q) => q.onPitch)) {
        const isHome = tid === home;
        const bx = 8 + p.baseX * 0.52;
        dots.push({ x: (isHome ? bx : 100 - bx) + shift, y: isHome ? p.baseY : 100 - p.baseY, side: isHome ? "home" : "away", id: p.id, ini: p.initials });
      }
    }
  }
  const tag = snap.tags.find((t) => t.player.id === follow) ?? snap.tags[snap.tags.length - 1];
  const tagDot = tag ? dots.find((d) => d.id === tag.player.id) : undefined;
  const overlay = moment?.versions.find((v) => v.key === "overlay");
  const fresh = moment && snap.match.minute - moment.minute <= 4;
  return (
    <div style={{ position: "relative", borderRadius: 10, overflow: "hidden", margin: "12px 0" }}>
      <svg viewBox="0 0 100 64" width="100%" style={{ display: "block", background: "repeating-linear-gradient(90deg,#1f6b34 0 10%,#237a3b 10% 20%)" }}>
        <g stroke="#ffffffcc" strokeWidth="0.35" fill="none">
          <rect x="1" y="1" width="98" height="62" />
          <line x1="50" y1="1" x2="50" y2="63" />
          <circle cx="50" cy="32" r="8" />
          <rect x="1" y="17" width="15" height="30" /><rect x="84" y="17" width="15" height="30" />
          <rect x="1" y="25" width="5" height="14" /><rect x="94" y="25" width="5" height="14" />
        </g>
        {dots.map((d) => (
          <circle key={d.id} cx={Math.max(2, Math.min(98, d.x))} cy={1 + d.y * 0.62} r={d.id === follow ? 1.9 : 1.45}
            fill={d.side === "home" ? "var(--cyan)" : "var(--magenta)"} stroke={d.id === follow ? "#fff" : "none"} strokeWidth="0.5" style={{ transition: "all .8s" }} />
        ))}
        <circle cx={Math.max(2, Math.min(98, ball.x))} cy={1 + ball.y * 0.62} r="1.1" fill="#fff" stroke="#000" strokeWidth="0.2" style={{ transition: "all .6s" }} />
        {tag && tagDot && (
          <g>
            <rect x={Math.min(78, tagDot.x - 10)} y={Math.max(1, 1 + tagDot.y * 0.62 - 8)} width="21" height="5" rx="1" fill="#2a0030" stroke="#fff" strokeWidth="0.2" />
            <text x={Math.min(78, tagDot.x - 10) + 10.5} y={Math.max(1, 1 + tagDot.y * 0.62 - 8) + 3.5} fontSize="2.8" fill="#fff" textAnchor="middle" fontFamily="Outfit" fontWeight="700">
              {tag.player.initials} · {tag.data.speedKmh} km/h
            </text>
          </g>
        )}
      </svg>
      {overlay && fresh && (
        <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, background: "#2a0030", borderTop: "3px solid transparent", borderImage: "linear-gradient(90deg,var(--cyan),var(--violet),var(--magenta)) 1", padding: "7px 10px" }}>
          <div style={{ fontWeight: 900, fontSize: 14, letterSpacing: "0.01em" }}>{overlay.text}</div>
          <div style={{ fontWeight: 800, fontSize: 11, color: "var(--green)" }}>{overlay.sub}</div>
        </div>
      )}
    </div>
  );
}

function versionFor(m: Moment, mode: Mode) {
  return m.versions.find((v) => v.key === (mode === "analyst" ? "en_analyst" : "en_casual"));
}

function MomentCard({ m, mode, snap }: { m: Moment; mode: Mode; snap: Snapshot }) {
  const v = versionFor(m, mode);
  const s = snap.storylines.find((x) => x.id === m.storyline);
  const goal = snap.match.goals.find((g) => g.minute === m.minute && g.player === m.player);
  return (
    <div className="panel" style={{ marginBottom: 10 }}>
      <div className="row">
        <span className="muted" style={{ fontWeight: 700, fontSize: 13 }}>{m.minute}' · {m.kind === "goal" || goal ? "GOAL" : "MOMENT"}</span>
        <span className="spacer" />
        {m.calledMinute ? (
          <span className="pill small grad">{m.calledMinute <= 1 ? "Called pre-match" : `Called at ${m.calledMinute}'`} · {m.calledPct}%</span>
        ) : m.reactive ? <span className="pill small">Live</span> : null}
      </div>
      <div style={{ fontSize: mode === "casual" ? 26 : 18, fontWeight: 800, lineHeight: 1.15, margin: "8px 0", letterSpacing: "-0.01em" }}>
        {v?.text}
      </div>
      {mode === "casual" && s?.memoryLine && <div className="muted" style={{ fontSize: 15 }}>Why it matters: {s.memoryLine}</div>}
      {mode === "analyst" && goal && (
        <div style={{ marginTop: 8 }}>
          <ShotMap snap={snap} highlight={goal.id} />
          <div className="small" style={{ marginTop: 6 }}>xG {goal.xg.toFixed(2)} · shot {goal.speedKmh} km/h{goal.assist ? " · assisted" : ""}</div>
        </div>
      )}
    </div>
  );
}

function ShotMap({ snap, highlight }: { snap: Snapshot; highlight?: string }) {
  // shots arrive in attacking coordinates (0-100); draw the attacking half
  const g = snap.match.goals.find((x) => x.id === highlight);
  const px = (x: number) => 1 + ((x - 50) / 50) * 58;
  const py = (y: number) => 1 + (y / 100) * 38;
  return (
    <svg viewBox="0 0 60 40" width="100%" style={{ background: "#2e0a36", borderRadius: 8 }}>
      <g stroke="#ffffff66" strokeWidth="0.3" fill="none">
        <rect x="1" y="1" width="58" height="38" />
        <rect x={px(83)} y={py(21)} width={59 - px(83)} height={py(79) - py(21)} />
        <rect x={px(94)} y={py(37)} width={59 - px(94)} height={py(63) - py(37)} />
        <line x1={59} y1={py(44.6)} x2={59} y2={py(55.4)} stroke="#fff" strokeWidth="1" />
      </g>
      {g && (
        <>
          <line x1={px(g.x)} y1={py(g.y)} x2={59} y2={py(50)} stroke="var(--green)" strokeWidth="0.4" strokeDasharray="1 1" />
          <circle cx={px(g.x)} cy={py(g.y)} r={1.2 + g.xg * 7} fill="var(--green)" opacity="0.85" />
          <text x={px(g.x)} y={py(g.y) - 3 - g.xg * 7} fontSize="2.6" fill="#fff" textAnchor="middle" fontFamily="Outfit" fontWeight="700">{g.xg.toFixed(2)} xG · {g.speedKmh} km/h</text>
        </>
      )}
    </svg>
  );
}

function StatsRows({ snap }: { snap: Snapshot }) {
  const h = snap.teamStats[snap.match.home.id];
  const a = snap.teamStats[snap.match.away.id];
  if (!h || !a) return null;
  const rows: [string, number | string, number | string, number, number][] = [
    ["Possession", `${h.possession}%`, `${a.possession}%`, h.possession, a.possession],
    ["Expected goals", h.xg.toFixed(2), a.xg.toFixed(2), h.xg, a.xg],
    ["Total shots", h.shots, a.shots, h.shots, a.shots],
    ["Pass accuracy", `${h.passAccuracy}%`, `${a.passAccuracy}%`, h.passAccuracy, a.passAccuracy],
    ["Big chances", h.bigChances, a.bigChances, h.bigChances, a.bigChances],
    ["Top ball speed", `${h.topBallSpeed} km/h`, `${a.topBallSpeed} km/h`, h.topBallSpeed, a.topBallSpeed],
    ["Pressures", h.pressures, a.pressures, h.pressures, a.pressures],
  ];
  return (
    <div>
      {rows.map(([label, hv, av, hn, an]) => {
        const tot = hn + an || 1;
        return (
          <div key={label} style={{ padding: "7px 0" }}>
            <div className="row" style={{ fontWeight: 700 }}>
              <span>{hv}</span><span className="spacer" /><span className="muted small">{label}</span><span className="spacer" /><span>{av}</span>
            </div>
            <div className="row" style={{ gap: 4, marginTop: 4 }}>
              <div style={{ flex: hn / tot, height: 5, background: "var(--cyan)", borderRadius: 4 }} />
              <div style={{ flex: an / tot, height: 5, background: "var(--magenta)", borderRadius: 4 }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function WatchRow({ s, i, snap, bell, toggle }: { s: Storyline; i: number; snap: Snapshot; bell: boolean; toggle: () => void }) {
  const side = sideOf(snap, s.team);
  return (
    <div className="row" style={{ padding: "12px 0", borderBottom: "1px solid var(--line)", alignItems: "flex-start" }}>
      <b style={{ fontSize: 22, width: 22 }}>{i}</b>
      {s.player ? <Avatar initials={initialsOf(s, snap)} side={null} size={44} /> : <Badge team={s.team} home={side === "home"} size={44} />}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 800, fontSize: 17 }}>{s.question}</div>
        <div className="row" style={{ margin: "6px 0" }}>
          <ProbBar pct={s.pct} wide color={side === "away" ? "var(--magenta)" : "var(--cyan)"} />
          <b className="nowrap">{s.pct}%</b>
          {s.delta15 !== null && (s.delta15 > 0 ? <span className="up">▲</span> : s.delta15 < 0 ? <span className="down">▼</span> : null)}
        </div>
        <div className="small"><span className="muted">Why ·</span> {s.why}</div>
        <div className="small muted" style={{ marginTop: 3 }}>📖 {s.memoryLine}</div>
      </div>
      <button onClick={toggle} title="Alert me" style={{ background: "none", border: 0, fontSize: 22, color: bell ? "var(--green)" : "var(--muted)" }}>
        {bell ? "🔔" : "🔕"}
      </button>
    </div>
  );
}

export default function Fan({ snap, room }: { snap: Snapshot; room: string }) {
  const [tab, setTab] = useState<Tab>("moments");
  const [mode, setMode] = useLocal<Mode>("zs.mode", "casual");
  const [follow, setFollow] = useLocal<string>("zs.follow", "HFC-09");
  const [club, setClub] = useLocal<string>("zs.club", snap.match.home.id);
  const [metric, setMetric] = useLocal<string>("zs.metric", "xg");
  const [bells, setBells] = useLocal<string[]>("zs.bells", []);
  const [toast, setToast] = useState<string | null>(null);
  const lineups = usePoll(() => api.lineups(room), [room, Math.floor(snap.match.t / 60)]);
  const seen = useRef<Set<string>>(new Set());

  const players = useMemo(() => (lineups ? Object.values(lineups).flat() : []), [lineups]);
  const followed = players.find((p) => p.id === follow) ?? players.find((p) => p.position === "ST");
  const moments = snap.moments;
  const latest = moments[0] ?? null;
  const ranked = snap.ranked.map((id) => snap.storylines.find((s) => s.id === id)!).filter((s) => s && s.pct >= 1);
  const watch = [...ranked].sort((a, b) => (b.team === club ? 1 : 0) - (a.team === club ? 1 : 0) || b.score - a.score).slice(0, 4);
  const decided = snap.storylines.filter((s) => s.resolution === "happened" || s.resolution === "ruled_out").filter((s) => !s.id.startsWith("goal-")).slice(-3);

  // in-app alerts: only for storylines the fan follows (max 3 per match)
  useEffect(() => {
    for (const m of moments) {
      if (seen.current.has(m.id)) continue;
      seen.current.add(m.id);
      if (bells.includes(m.storyline) && seen.current.size > 1) {
        setToast(`🔔 ${m.title}`);
        window.setTimeout(() => setToast(null), 5000);
      }
    }
  }, [moments, bells]);

  const toggleBell = (id: string) => {
    if (bells.includes(id)) setBells(bells.filter((b) => b !== id));
    else if (bells.length < 3) setBells([...bells, id]);
  };
  const scorers = (team: string) => snap.match.goals.filter((g) => g.team === team).map((g) => `${g.playerInfo.last} ${g.minute}'`).join(", ");
  const m = snap.match;

  return (
    <div style={{ minHeight: "100vh", display: "flex", justifyContent: "center", background: "radial-gradient(circle at 50% 0%, #3a0842, #1d0022)" }}>
      <div style={{ width: "100%", maxWidth: 440, padding: "14px 14px 90px", position: "relative" }}>
        <div className="row" style={{ marginBottom: 10 }}>
          <Logo size={34} />
          <span className="spacer" />
          <Link to={`/desk${room === "demo" ? "" : `?room=${room}`}`} className="pill small">Media Desk ↗</Link>
        </div>
        <div className="panel" style={{ textAlign: "center", padding: "16px 10px" }}>
          <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
            <div style={{ width: 120 }}>
              <Badge team={m.home.id} home size={64} />
              <div style={{ fontWeight: 800, fontSize: 17, marginTop: 4 }}>{m.home.short}</div>
              <div className="muted small">{scorers(m.home.id)}</div>
            </div>
            <div>
              <div style={{ fontSize: 54, fontWeight: 900, letterSpacing: "-0.03em", lineHeight: 1 }}>{m.score.home} – {m.score.away}</div>
              <div style={{ fontWeight: 800, fontSize: 18, marginTop: 4 }}>{m.finished ? "FT" : `${m.minute}'`}</div>
              {!m.finished && <div style={{ color: "#ff2d55", fontWeight: 800, fontSize: 12 }}>● LIVE</div>}
            </div>
            <div style={{ width: 120 }}>
              <Badge team={m.away.id} home={false} size={64} />
              <div style={{ fontWeight: 800, fontSize: 17, marginTop: 4 }}>{m.away.short}</div>
              <div className="muted small">{scorers(m.away.id)}</div>
            </div>
          </div>
        </div>
        <div className="tabs" style={{ marginTop: 10, justifyContent: "space-between" }}>
          {([["moments", "Moments"], ["watch", "Watch for"], ["timeline", "Timeline"], ["stats", "Stats"], ["lineups", "Lineups"]] as [Tab, string][]).map(([k, l]) => (
            <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>
          ))}
        </div>

        {(tab === "moments" || tab === "watch") && (
          <div className="row" style={{ flexWrap: "wrap", gap: 8, margin: "8px 0" }}>
            <div className="seg">
              <button className={mode === "casual" ? "on" : ""} onClick={() => setMode("casual")}>Casual</button>
              <button className={mode === "analyst" ? "on" : ""} onClick={() => setMode("analyst")}>Analyst</button>
            </div>
            <select className="select" style={{ height: 32, borderRadius: 999, maxWidth: 170 }} value={follow} onChange={(e) => setFollow(e.target.value)}>
              {players.filter((p) => p.role !== "GK").map((p) => <option key={p.id} value={p.id}>Following {p.short}</option>)}
            </select>
            <select className="select" style={{ height: 32, borderRadius: 999 }} value={club} onChange={(e) => setClub(e.target.value)}>
              <option value={m.home.id}>{m.home.short}</option>
              <option value={m.away.id}>{m.away.short}</option>
            </select>
            {mode === "analyst" && (
              <select className="select" style={{ height: 32, borderRadius: 999 }} value={metric} onChange={(e) => setMetric(e.target.value)}>
                <option value="xg">Metric focus: xG</option>
                <option value="speed">Metric focus: speed</option>
                <option value="distance">Metric focus: distance</option>
              </select>
            )}
          </div>
        )}

        {tab === "moments" && (
          <>
            <Pitch snap={snap} lineups={lineups} moment={latest} follow={follow} />
            {moments.length === 0 && <div className="panel muted">No moments yet. They appear here the instant they happen, already written for you.</div>}
            {moments.slice(0, mode === "casual" ? 2 : 3).map((mm) => <MomentCard key={mm.id} m={mm} mode={mode} snap={snap} />)}
            {mode === "analyst" && (
              <div className="panel" style={{ marginBottom: 10 }}>
                <h3>Why it matters (data)</h3>
                {(ranked[0]?.drivers ?? []).concat(ranked[0] ? [ranked[0].why] : []).slice(0, 4).map((d, i) => <div key={i} className="small" style={{ padding: "3px 0" }}>• {d}</div>)}
                <div className="small muted">Control ↔ Chaos {snap.controlChaos.index.toFixed(2)} ({snap.controlChaos.label})</div>
              </div>
            )}
            {mode === "analyst" && <div className="panel" style={{ marginBottom: 10 }}><h3>Match stats</h3><StatsRows snap={snap} /></div>}
            {mode === "analyst" && <div className="panel" style={{ marginBottom: 10 }}><h3>Momentum</h3><Momentum data={snap.momentum} height={70} /></div>}
            {followed && (
              <div className="panel row" style={{ marginBottom: 10 }}>
                <Avatar initials={followed.initials} side={followed.team === m.home.id ? "home" : "away"} size={52} />
                <div style={{ flex: 1 }}>
                  <div className="row"><b style={{ fontSize: 17 }}>{followed.name}</b>{mode === "analyst" && <span className="tag Pre-approved">{followed.stats.rating}</span>}</div>
                  <div className="small muted">
                    {metric === "speed" && mode === "analyst" ? <b style={{ color: "#fff" }}>Top speed {followed.stats.top_speed || "—"} km/h · </b> : null}
                    {metric === "distance" && mode === "analyst" ? <b style={{ color: "#fff" }}>{followed.stats.distance_km.toFixed(1)} km covered · </b> : null}
                    {metric === "xg" && mode === "analyst" ? <b style={{ color: "#fff" }}>xG {followed.stats.xg.toFixed(2)} · </b> : null}
                    Distance {followed.stats.distance_km.toFixed(1)} km · Top speed {followed.stats.top_speed || "—"} km/h · Shots {followed.stats.shots}
                    {mode === "analyst" && <> · Passes {followed.stats.passes} ({followed.stats.passAccuracy ?? "—"}%) · difficulty {followed.stats.avgPassDifficulty ?? "—"}</>}
                  </div>
                </div>
              </div>
            )}
            {watch[0] && (
              <div className="panel" onClick={() => setTab("watch")} style={{ cursor: "pointer" }}>
                <div className="row"><b style={{ fontSize: 18 }}>Next to watch – {watch[0].question}</b><span className="spacer" /><b style={{ fontSize: 26 }}>{watch[0].pct}%</b></div>
                <div style={{ margin: "8px 0" }}><ProbBar pct={watch[0].pct} wide /></div>
                <div className="muted small">{watch[0].why}</div>
              </div>
            )}
          </>
        )}

        {tab === "watch" && (
          <div className="panel">
            <div style={{ fontWeight: 800, fontSize: 14, letterSpacing: "0.04em", color: "#c9a3ff" }}>COULD HAPPEN BEFORE FULL TIME</div>
            <div className="small muted">Live forecast · updates as the match changes</div>
            {watch.map((s, i) => <WatchRow key={s.id} s={s} i={i + 1} snap={snap} bell={bells.includes(s.id)} toggle={() => toggleBell(s.id)} />)}
            {watch.length === 0 && <div className="empty">Nothing on the horizon right now.</div>}
            {decided.length > 0 && (
              <>
                <div style={{ fontWeight: 800, fontSize: 14, letterSpacing: "0.04em", color: "#c9a3ff", marginTop: 14 }}>ALREADY DECIDED</div>
                {decided.map((s, i) => (
                  <div key={s.id} className="row" style={{ padding: "10px 0", borderBottom: "1px solid var(--line)" }}>
                    <b>{i + 1}</b>
                    <span className={`tag ${s.status}`}>{s.status}</span>
                    <span style={{ fontWeight: 700, textDecoration: s.resolution === "ruled_out" ? "line-through" : "none", color: s.resolution === "ruled_out" ? "var(--dim)" : "#fff" }}>
                      {s.title} · {s.resolvedMinute}'{s.calledMinute ? ` · called ${s.calledMinute <= 1 ? "pre-match" : `at ${s.calledMinute}'`}` : ""}
                    </span>
                  </div>
                ))}
              </>
            )}
            <div className="small muted" style={{ textAlign: "center", marginTop: 12 }}>Alerts only for what you follow · max 3 per match</div>
          </div>
        )}

        {tab === "timeline" && (
          <div className="panel">
            <ul className="feed">
              {snap.feed.map((it) => (
                <li key={it.id} className={it.kind}><span className="min">{it.minute}'</span><span className="ico">{it.kind === "goal" ? "⚽" : it.kind === "card" ? <i className="cardy" /> : it.kind === "sub" ? "⇅" : "◌"}</span><span>{it.text}</span></li>
              ))}
            </ul>
          </div>
        )}
        {tab === "stats" && (
          <>
            <div className="panel" style={{ marginBottom: 10 }}><StatsRows snap={snap} /></div>
            <div className="panel"><h3>Momentum</h3><Momentum data={snap.momentum} height={80} /></div>
          </>
        )}
        {tab === "lineups" && lineups && (
          <div className="panel">
            {Object.entries(lineups).map(([tid, ps]) => (
              <div key={tid} style={{ marginBottom: 14 }}>
                <h3>{tid === m.home.id ? m.home.name : m.away.name}</h3>
                {ps.filter((p) => p.onPitch).map((p) => (
                  <div key={p.id} className="row small" style={{ padding: "5px 0", borderBottom: "1px solid var(--line-soft)" }}>
                    <span className="mono dim" style={{ width: 22 }}>{p.number}</span>
                    <b style={{ flex: 1 }}>{p.name}</b>
                    <span className="muted">{p.position}</span>
                    <span className="tag Pre-approved" style={{ minWidth: 38 }}>{p.stats.rating}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}
        {toast && (
          <div style={{ position: "fixed", top: 16, left: "50%", transform: "translateX(-50%)", background: "#fff", color: "#37003c", padding: "10px 16px", borderRadius: 12, fontWeight: 800, boxShadow: "0 8px 30px #0008", zIndex: 50 }}>
            {toast}
          </div>
        )}
        <div style={{ position: "fixed", bottom: 0, left: "50%", transform: "translateX(-50%)", width: "100%", maxWidth: 440, background: "#1d0022", borderTop: "1px solid var(--line)", display: "flex", justifyContent: "space-around", padding: "10px 0 14px" }}>
          {["Matches", "News", "Following", "Alerts", "More"].map((x, i) => (
            <span key={x} style={{ fontWeight: 700, fontSize: 12, color: i === 0 ? "#fff" : "var(--muted)" }}>{x}</span>
          ))}
        </div>
      </div>
    </div>
  );
}
