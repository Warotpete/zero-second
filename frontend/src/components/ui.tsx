import { NavLink } from "react-router-dom";
import type { Snapshot, Status, Storyline } from "../types";

export function Logo({ size = 36 }: { size?: number }) {
  return (
    <div className="logo">
      <div className="logo-mark" style={{ width: size, height: size, fontSize: size * 0.53 }}>
        0″
      </div>
      Zero Second
    </div>
  );
}

const NAV = [
  ["/desk", "Live"],
  ["/desk/trace", "Agent Trace"],
  ["/desk/recap", "Recap"],
  ["/desk/memory", "Season Memory"],
  ["/fan", "Fan View"],
];

export function TopNav({ room }: { room: string }) {
  const q = room === "demo" ? "" : `?room=${room}`;
  return (
    <nav className="topnav">
      <Logo />
      <div className="navlinks">
        {NAV.map(([to, label]) => (
          <NavLink key={to} to={to + q} end className={({ isActive }) => (isActive ? "active" : "")}>
            {label}
          </NavLink>
        ))}
      </div>
      <div className="nav-right">
        <span className="pill small">Market UK</span>
        <div className="avatar-p">P</div>
        <span style={{ fontWeight: 700 }}>Producer</span>
      </div>
    </nav>
  );
}

/** Flat club badge: home = circle with wave, away = shield with chevron, others = generic. */
export function Badge({ team, home, size = 36 }: { team: string; home: boolean; size?: number }) {
  if (home) {
    return (
      <svg className="badge" width={size} height={size} viewBox="0 0 40 40" aria-label={team}>
        <circle cx="20" cy="20" r="19" fill="var(--home)" />
        <path d="M8 22c4-5 8-5 12 0s8 5 12 0" stroke="#fff" strokeWidth="3.4" fill="none" strokeLinecap="round" />
      </svg>
    );
  }
  return (
    <svg className="badge" width={size} height={size} viewBox="0 0 40 40" aria-label={team}>
      <path d="M5 4h30v16c0 9-7 14-15 17C12 34 5 29 5 20z" fill="var(--away)" />
      <path d="M12 15l8 8 8-8" stroke="#fff" strokeWidth="3.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Avatar({ initials, side, size = 36 }: { initials: string; side?: "home" | "away" | null; size?: number }) {
  return (
    <div className={`av ${side ?? ""}`} style={{ width: size, height: size, fontSize: size * 0.36 }}>
      {initials}
    </div>
  );
}

export function StatusTag({ status, extra }: { status: Status | string; extra?: string }) {
  return (
    <span className={`tag ${status}`}>
      {status}
      {extra ? <>&nbsp;{extra}</> : null}
    </span>
  );
}

export function ProbBar({ pct, color, wide }: { pct: number; color?: string; wide?: boolean }) {
  return (
    <div className={`bar ${wide ? "wide" : ""}`}>
      <i style={{ width: `${Math.max(2, Math.min(100, pct))}%`, background: color }} />
    </div>
  );
}

export function Spark({ values, color = "var(--cyan)" }: { values: number[]; color?: string }) {
  if (values.length < 2) return <svg width={56} height={20} />;
  const max = Math.max(10, ...values);
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * 54 + 1},${19 - (v / max) * 17}`).join(" ");
  return (
    <svg width={56} height={20}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  );
}

export function Momentum({ data, height = 110 }: { data: { minute: number; value: number }[]; height?: number }) {
  const w = 300;
  const mid = height / 2;
  const bw = w / 90;
  return (
    <svg viewBox={`0 0 ${w} ${height + 16}`} width="100%" role="img" aria-label="Match momentum">
      <line x1="0" x2={w} y1={mid} y2={mid} stroke="#6d4a75" strokeWidth="1" />
      {data.map((d) => {
        const h = (Math.abs(d.value) / 3) * (mid - 4);
        return (
          <rect
            key={d.minute}
            x={(d.minute - 1) * bw}
            y={d.value >= 0 ? mid - h : mid}
            width={bw * 0.72}
            height={Math.max(0.5, h)}
            fill={d.value >= 0 ? "var(--home)" : "var(--away)"}
            rx="1"
          />
        );
      })}
      {[0, 15, 30, 45, 60, 75, 90].map((m) => (
        <text key={m} x={Math.min(w - 10, m * bw)} y={height + 13} fontSize="9" fill="#c7b5cf" fontFamily="Outfit">
          {m}'
        </text>
      ))}
    </svg>
  );
}

export function ControlChaos({ cc }: { cc: Snapshot["controlChaos"] }) {
  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <b style={{ fontSize: 16 }}>Control ↔ Chaos</b>
        <span className="muted small">{cc.label}</span>
      </div>
      <div style={{ position: "relative", height: 14, margin: "10px 0 6px", borderRadius: 10, background: "linear-gradient(90deg, var(--cyan), var(--violet), var(--magenta))" }}>
        <span style={{ position: "absolute", left: `calc(${cc.index * 100}% - 9px)`, top: -3, width: 20, height: 20, borderRadius: "50%", background: "#fff", border: "3px solid var(--magenta)", transition: "left .5s" }} />
      </div>
      <div className="row small muted" style={{ justifyContent: "space-between" }}>
        <span>Controlled</span>
        <span>{cc.index.toFixed(2)}</span>
        <span>Chaos</span>
      </div>
    </div>
  );
}

export function MatchStrip({ snap, compact }: { snap: Snapshot; compact?: boolean }) {
  const m = snap.match;
  return (
    <div className="matchstrip">
      <Badge team={m.home.id} home size={compact ? 34 : 44} />
      <div className="tname">
        {m.home.id}
        {!compact && <small>{m.home.short}</small>}
      </div>
      <div className="score">
        {m.score.home} – {m.score.away}
      </div>
      <div className="tname" style={{ textAlign: "right" }}>
        {m.away.id}
        {!compact && <small>{m.away.short}</small>}
      </div>
      <Badge team={m.away.id} home={false} size={compact ? 34 : 44} />
      {m.finished ? <span className="ft">FT</span> : <span className="live">LIVE</span>}
      <span className="clockbig">{m.clock}</span>
    </div>
  );
}

export function sideOf(snap: Snapshot, team: string | null): "home" | "away" | null {
  if (!team) return null;
  return team === snap.match.home.id ? "home" : "away";
}

export function initialsOf(s: Storyline, _snap?: Snapshot): string {
  return s.initials || s.team.slice(0, 2);
}

export function Toggle({ on, label, onChange }: { on: boolean; label: string; onChange: (v: boolean) => void }) {
  return (
    <span className={`toggle ${on ? "on" : ""}`} onClick={() => onChange(!on)} role="switch" aria-checked={on}>
      <i />
      {label}
    </span>
  );
}

export function AgentBar({ snap }: { snap: Snapshot }) {
  const last = [...snap.audit].reverse().find((a) => a.actor.startsWith("Producer") || a.action === "Published");
  const names = ["Editor", "Writer", "Verifier", "Recap"];
  return (
    <div className="statusbar">
      <span className="mono">{snap.match.clock}</span>
      <span className="muted" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "48%" }}>
        {last ? `${last.clock} ${last.actor} ${last.action.toLowerCase()} · ${last.detail}` : "Waiting for the first storyline"}
      </span>
      <span className="spacer" />
      {names.map((n) => (
        <span key={n} className="nowrap">
          <span className={`dot ${snap.agents[n]?.state ?? ""}`} />
          {n}
        </span>
      ))}
      <span className="nowrap"><span className="dot" />Stats</span>
      <span className="nowrap"><span className="dot" />Season Memory</span>
      <span className="pill small" title="Agent back end">
        {snap.backend.startsWith("foundry") ? `Foundry · ${snap.backend.split(":")[1]}` : "Local writer"}
      </span>
    </div>
  );
}
