import { api, usePoll } from "../api";
import { AgentBar, Avatar, MatchStrip, TopNav } from "../components/ui";
import type { Snapshot } from "../types";

interface Arc {
  player: string; name: string; short: string; team: string; role: string; clubGoals: number; seasonGoals: number;
  apps: number; lastGoalMw: number | null; droppedMw: number | null; noGoalSinceDropped: boolean; signedThisWeek: boolean;
}
interface Mem {
  matchweek: number;
  table: { pos: number; team: string; name: string; p: number; w: number; d: number; l: number; gd: number; pts: number }[];
  form: Record<string, string>;
  h2h: { season: string; mw: number; home: string; away: string; hg: number; ag: number; factId: string }[];
  cleanSheets: Record<string, { keeperName: string; streak: number; factId: string }>;
  lateWinners: Record<string, { count: number; matchweeks: number[]; factId: string }>;
  players: Arc[];
  topScorers: { name: string; team: string; goals: number }[];
  names: Record<string, string>;
  teams: Record<string, { name: string; short: string }>;
}

function Form({ s }: { s: string }) {
  const c: Record<string, string> = { W: "var(--green)", D: "#8f7898", L: "var(--magenta)" };
  return <span className="row" style={{ gap: 4 }}>{s.split("").map((x, i) => <b key={i} style={{ background: c[x], color: x === "W" ? "#2a0030" : "#fff", borderRadius: 5, width: 22, textAlign: "center", fontSize: 12, padding: "2px 0" }}>{x}</b>)}</span>;
}

export default function Memory({ snap, room }: { snap: Snapshot; room: string }) {
  const mem = usePoll<Mem>(() => api.memory(room), [room, snap.seed]);
  const home = snap.match.home.id, away = snap.match.away.id;
  const notable = (mem?.players ?? []).filter((p) => p.role !== "GK" && (p.seasonGoals > 0 || p.droppedMw || p.signedThisWeek)).sort((a, b) => b.clubGoals - a.clubGoals);
  return (
    <div className="page">
      <TopNav room={room} />
      <div className="banner">
        <h1>Season Memory</h1>
        <div className="right"><MatchStrip snap={snap} /></div>
      </div>
      <div className="filters">
        <span className="muted">Every fact here is computed from the generated season and carries an id agents must cite. The Verifier rejects anything else.</span>
      </div>
      {!mem ? <div className="empty">Loading…</div> : (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1.1fr", gap: 14, padding: "0 24px 14px" }}>
          <div className="panel">
            <h2>This fixture</h2>
            {[home, away].map((t) => (
              <div key={t} className="row" style={{ padding: "8px 0", borderBottom: "1px solid var(--line-soft)" }}>
                <b style={{ width: 130 }}>{mem.teams[t].short}</b><Form s={mem.form[t]} />
              </div>
            ))}
            <h3 style={{ marginTop: 14 }}>Head to head</h3>
            {mem.h2h.map((r) => (
              <div key={r.factId} className="row small" style={{ padding: "6px 0", borderBottom: "1px solid var(--line-soft)" }}>
                <span className="muted" style={{ width: 90 }}>{r.season === "2026/27" ? `MW${r.mw}` : `${r.season} MW${r.mw}`}</span>
                <b>{mem.teams[r.home].short} {r.hg}–{r.ag} {mem.teams[r.away].short}</b>
                <span className="spacer" /><span className="mono dim">{r.factId}</span>
              </div>
            ))}
            <h3 style={{ marginTop: 14 }}>Streaks</h3>
            {[home, away].map((t) => (
              <div key={t} className="small" style={{ padding: "5px 0" }}>
                📖 {mem.cleanSheets[t].keeperName}: <b>{mem.cleanSheets[t].streak}</b> clean sheets in a row · {mem.teams[t].short} late winners this season: <b>{mem.lateWinners[t].count}</b>
                {mem.lateWinners[t].matchweeks.length > 0 && <span className="muted"> (MW{mem.lateWinners[t].matchweeks.join(", MW")})</span>}
              </div>
            ))}
          </div>
          <div className="panel scroll" style={{ maxHeight: 640 }}>
            <h2>Player arcs</h2>
            {notable.map((p) => (
              <div key={p.player} className="row" style={{ padding: "8px 0", borderBottom: "1px solid var(--line-soft)" }}>
                <Avatar initials={p.name.split(" ").map((x) => x[0]).join("").slice(0, 2)} side={p.team === home ? "home" : "away"} size={34} />
                <div style={{ flex: 1 }}>
                  <b>{p.name}</b> <span className="muted small">{mem.teams[p.team].short}</span>
                  <div className="small muted">
                    {p.clubGoals} club goals · {p.seasonGoals} this season · {p.apps} apps
                    {p.droppedMw ? ` · dropped MW${p.droppedMw}${p.noGoalSinceDropped ? ", no goal since" : ""}` : ""}
                    {p.signedThisWeek ? " · signed this week" : ""}
                  </div>
                </div>
              </div>
            ))}
          </div>
          <div className="panel scroll" style={{ maxHeight: 640 }}>
            <h2>Table · after MW{mem.matchweek - 1}</h2>
            <table className="audit">
              <thead><tr><th>#</th><th>CLUB</th><th>P</th><th>W</th><th>D</th><th>L</th><th>GD</th><th>PTS</th></tr></thead>
              <tbody>
                {mem.table.map((r) => (
                  <tr key={r.team} style={{ fontWeight: r.team === home || r.team === away ? 800 : 400, color: r.team === home ? "var(--cyan)" : r.team === away ? "#ff6b97" : undefined }}>
                    <td>{r.pos}</td><td style={{ fontFamily: "var(--font)" }}>{r.name}</td><td>{r.p}</td><td>{r.w}</td><td>{r.d}</td><td>{r.l}</td><td>{r.gd}</td><td>{r.pts}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <h3 style={{ marginTop: 14 }}>Top scorers</h3>
            {mem.topScorers.slice(0, 6).map((s) => <div key={s.name} className="small row" style={{ padding: "3px 0" }}><span style={{ flex: 1 }}>{s.name} <span className="muted">{mem.teams[s.team].short}</span></span><b>{s.goals}</b></div>)}
          </div>
        </div>
      )}
      <AgentBar snap={snap} />
    </div>
  );
}
