import { useState } from "react";
import { api, usePoll } from "../api";
import { AgentBar, MatchStrip, StatusTag, TopNav } from "../components/ui";
import type { Snapshot } from "../types";

interface Calib {
  available: boolean;
  matches: number;
  samples: number;
  brier: number;
  brierBaseline: number;
  skill: number;
  bins: { lo: number; hi: number; n: number; predicted: number; actual: number }[];
}

function Calibration({ cal }: { cal: Calib | null }) {
  if (!cal || !cal.available) return <div className="empty">Calibration not run yet (python -m zerosecond.calibration)</div>;
  const W = 520, H = 220, P = 34;
  const x = (v: number) => P + v * (W - P - 10);
  const y = (v: number) => H - P - v * (H - P - 10);
  const near = [...cal.bins].filter((b) => b.predicted >= 0.1).sort((a, b) => b.n - a.n)[0] ?? cal.bins[0];
  return (
    <>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%">
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={y(0)} y2={y(1)} stroke="#4f1f57" strokeDasharray="3 4" />
            <line x1={x(0)} x2={x(1)} y1={y(t)} y2={y(t)} stroke="#4f1f57" strokeDasharray="3 4" />
            <text x={x(t)} y={H - 14} fontSize="11" fill="#c7b5cf" textAnchor="middle" fontFamily="Outfit">{t * 100}%</text>
            <text x={P - 6} y={y(t) + 4} fontSize="11" fill="#c7b5cf" textAnchor="end" fontFamily="Outfit">{t * 100}%</text>
          </g>
        ))}
        <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} stroke="#c9a3ff" strokeWidth="1.5" />
        {cal.bins.map((b) => (
          <g key={b.lo}>
            <circle cx={x(b.predicted)} cy={y(b.actual)} r={Math.max(4, Math.min(10, Math.sqrt(b.n) / 3))} fill="var(--green)" opacity="0.9">
              <title>{`${Math.round(b.lo * 100)}–${Math.round(b.hi * 100)}%: predicted ${(b.predicted * 100).toFixed(0)}%, actual ${(b.actual * 100).toFixed(0)}% (n=${b.n})`}</title>
            </circle>
          </g>
        ))}
        <text x={W / 2} y={H - 1} fontSize="12" fill="#fff" textAnchor="middle" fontFamily="Outfit" fontWeight="700">Predicted</text>
      </svg>
      <div className="small" style={{ textAlign: "center" }}>
        Storylines rated ~{Math.round(near.predicted * 100)}% happened <b style={{ color: "var(--green)" }}>{Math.round(near.actual * 100)}%</b> of the time ·
        Brier {cal.brier} vs {cal.brierBaseline} baseline (skill {Math.round(cal.skill * 100)}%) · {cal.matches} held-out matches, {cal.samples} forecasts
      </div>
    </>
  );
}

export default function Recap({ snap, room }: { snap: Snapshot; room: string }) {
  const [tab, setTab] = useState<"broadcaster" | "casual" | "analyst">("broadcaster");
  const cal = usePoll<Calib>(api.calibration, []);
  const lines = snap.storylines
    .filter((s) => s.resolution && !s.id.startsWith("goal-") && (s.resolution !== "unresolved" || s.peakPct >= 8))
    .sort((a, b) => (a.resolvedMinute ?? 0) - (b.resolvedMinute ?? 0));
  const recap = snap.recap;
  const marks = lines.filter((s) => s.resolvedMinute);
  return (
    <div className="page">
      <TopNav room={room} />
      <div className="banner">
        <h1>Match Recap</h1>
        <div className="right"><MatchStrip snap={snap} /></div>
      </div>
      <div className="filters" style={{ justifyContent: "center" }}>
        <span className="roundbtn">‹</span>
        <b style={{ fontSize: 16 }}>Matchweek {snap.match.matchweek} · {snap.match.home.short} v {snap.match.away.short}</b>
        <span className="roundbtn">›</span>
      </div>
      {!snap.match.finished && (
        <div className="banner-note" style={{ margin: "0 24px 12px" }}>
          The match is still live ({snap.match.clock}). Outcomes below update as storylines resolve; the Recap agent writes the recaps at the final whistle.
        </div>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "1.1fr 1fr", gap: 14, padding: "0 24px 14px" }}>
        <div style={{ display: "grid", gap: 14 }}>
          <div className="panel">
            <h2>Storyline outcomes</h2>
            <svg viewBox="0 0 600 46" width="100%">
              <line x1="10" x2="590" y1="30" y2="30" stroke="#fff" strokeWidth="1.5" />
              {[0, 15, 30, 45, 60, 75, 90].map((m) => (
                <g key={m}>
                  <line x1={10 + (m / 90) * 580} x2={10 + (m / 90) * 580} y1="26" y2="34" stroke="#fff" />
                  <text x={10 + (m / 90) * 580} y="45" fontSize="10" fill="#c7b5cf" textAnchor="middle" fontFamily="Outfit">{m}'</text>
                </g>
              ))}
              {marks.map((s) => (
                <circle key={s.id} cx={10 + (Math.min(90, s.resolvedMinute!) / 90) * 580} cy="30" r="6" fill={s.resolution === "happened" ? "var(--green)" : s.resolution === "near_miss" ? "var(--magenta)" : "#8f7898"}>
                  <title>{s.title}</title>
                </circle>
              ))}
            </svg>
            <table className="rundown" style={{ marginTop: 6 }}>
              <thead><tr><th>STORYLINE</th><th>PEAK PROB</th><th>CALLED</th><th>RESOLVED</th><th>OUTCOME</th></tr></thead>
              <tbody>
                {lines.map((s) => (
                  <tr key={s.id} className={s.resolution === "ruled_out" ? "struck" : ""}>
                    <td className="title">{s.title}</td>
                    <td>{s.peakPct}% <span className="muted small">at {s.peakMinute}'</span></td>
                    <td className="small">{s.calledMinute ? (s.calledMinute <= 1 ? "pre-match" : `${s.calledMinute}'`) : "—"}</td>
                    <td>{s.resolvedMinute}'</td>
                    <td>
                      <StatusTag status={s.status} />
                      <div className="small muted" style={{ marginTop: 3 }}>{s.resolutionNote}</div>
                    </td>
                  </tr>
                ))}
                {lines.length === 0 && <tr><td colSpan={5} className="empty">Nothing resolved yet</td></tr>}
              </tbody>
            </table>
          </div>
          <div className="panel">
            <h2>Forecast accuracy · held-out simulated matches</h2>
            <Calibration cal={cal} />
          </div>
        </div>
        <div className="panel">
          <div className="row">
            <h2 style={{ margin: 0 }}>Recaps</h2>
            <span className="spacer" />
            {recap && <span className="tag verified">Verified ✓</span>}
          </div>
          <div className="tabs" style={{ marginTop: 10 }}>
            {(["broadcaster", "casual", "analyst"] as const).map((t) => (
              <button key={t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>{t === "casual" ? "Casual fan" : t[0].toUpperCase() + t.slice(1)}</button>
            ))}
          </div>
          {recap ? (
            <>
              <p style={{ fontSize: 20, fontWeight: 700, lineHeight: 1.45 }}>
                {recap.text[tab].split(/(\[[a-z0-9-]+\])/i).map((part, i) =>
                  /^\[.*\]$/.test(part) ? <sup key={i} className="mono" style={{ color: "#c9a3ff", fontSize: 11, fontWeight: 500 }}>{part}</sup> : <span key={i}>{part}</span>,
                )}
              </p>
              <div className="muted small">Written by the Recap agent ({recap.backend === "local" ? "local writer" : recap.backend}) from the storyline lifecycle log · {recap.approvedBy ? `approved by ${recap.approvedBy}` : "awaiting approval"}</div>
              <div className="row" style={{ marginTop: 16 }}>
                <button className="pill solid-green" onClick={() => api.approveRecap(room)} disabled={!!recap.approvedBy}>Approve recap</button>
                <a className="pill" href={`/api/rooms/${room}/overlays.json`} target="_blank" rel="noreferrer">Export overlay pack</a>
                <button className="pill" onClick={() => navigator.clipboard?.writeText(recap.text[tab])}>Copy</button>
              </div>
            </>
          ) : (
            <div className="empty">The recap is generated at the final whistle. Jump to FT on the Live page.</div>
          )}
        </div>
      </div>
      <AgentBar snap={snap} />
    </div>
  );
}
