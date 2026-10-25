import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { AgentBar, Avatar, Badge, ControlChaos, MatchStrip, Momentum, ProbBar, Spark, StatusTag, Toggle, TopNav, initialsOf, sideOf } from "../components/ui";
import type { FeedItem, Snapshot, Storyline, Version } from "../types";

const JUMPS = [1, 30, 60, 63, 66, 72, 77, 80, 89, 91];
function WithSlots({ text }: { text: string }) {
  return (
    <>
      {text.split(/({[a-z_]+})/).map((part, i) =>
        /^{[a-z_]+}$/.test(part) ? (
          <span key={i} title="Live slot: filled from the Stats Engine at the moment it happens" style={{ background: "#5a1265", color: "var(--green)", borderRadius: 6, padding: "0 6px", fontSize: "0.8em", fontFamily: "var(--mono)", fontWeight: 500 }}>
            {part.slice(1, -1).replace("_", " ")}
          </span>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  );
}

const VERSION_LABEL: Record<string, string> = { en_analyst: "Analyst", en_casual: "Casual", overlay: "Overlay" };

function FeedIcon({ it }: { it: FeedItem }) {
  if (it.kind === "goal") return <span className="ico">⚽</span>;
  if (it.kind === "card") return <span className="ico">{String(it.text).startsWith("Red") ? <i className="cardr" /> : <i className="cardy" />}</span>;
  if (it.kind === "sub") return <span className="ico" style={{ color: "var(--green)" }}>⇅</span>;
  if (it.kind === "pressure") return <span className="ico" style={{ color: "var(--cyan)" }}>▮▮</span>;
  if (it.kind === "chance") return <span className="ico" style={{ color: "var(--amber)" }}>◎</span>;
  if (it.kind === "ht" || it.kind === "ft") return <span className="ico">⏸</span>;
  return <span className="ico muted">◌</span>;
}

export function ReplayControls({ snap, room }: { snap: Snapshot; room: string }) {
  const c = snap.control;
  const [seed, setSeed] = useState("");
  return (
    <div className="filters">
      <button className={`pill ${c.playing ? "" : "solid-green"}`} onClick={() => api.control(room, c.playing ? "pause" : "play")} disabled={snap.match.finished}>
        {c.playing ? "❚❚ Pause" : "▶ Play"}
      </button>
      <div className="seg" title="Replay speed (match seconds per second)">
        {c.speeds.map((s) => (
          <button key={s} className={c.speed === s ? "on" : ""} onClick={() => api.control(room, "speed", s)}>
            {s === 1 ? "Real time" : `${s}×`}
          </button>
        ))}
      </div>
      <span className="muted small" style={{ marginLeft: 6 }}>Jump</span>
      <div className="seg">
        {JUMPS.map((m) => (
          <button key={m} onClick={() => api.jump(room, m)}>
            {m === 1 ? "KO" : m === 91 ? "FT" : `${m}'`}
          </button>
        ))}
      </div>
      <span className="spacer" />
      <Toggle on={c.autopilot} label="Autopilot producer" onChange={(v) => api.control(room, "autopilot", v ? 1 : 0)} />
      <Toggle on={c.faultInjection} label="Fault injection" onChange={(v) => api.control(room, "fault", v ? 1 : 0)} />
      <select className="select" value="" onChange={(e) => e.target.value && api.newMatch(room, e.target.value === "scenario" ? undefined : Number(e.target.value))}>
        <option value="">New match…</option>
        <option value="scenario">Demo: Harbour City v Northvale</option>
        <option value={String(Math.floor(Math.random() * 9000) + 1000)}>Random seed</option>
      </select>
      <input
        className="select"
        style={{ width: 110 }}
        placeholder="seed #"
        value={seed}
        onChange={(e) => setSeed(e.target.value.replace(/\D/g, ""))}
        onKeyDown={(e) => e.key === "Enter" && seed && api.newMatch(room, Number(seed))}
      />
      <span className="pill small mono" title="Seed of this synthetic match">seed: {snap.seed}</span>
    </div>
  );
}

function Rundown({ snap, sel, setSel }: { snap: Snapshot; sel: string | null; setSel: (id: string) => void }) {
  const byId = useMemo(() => Object.fromEntries(snap.storylines.map((s) => [s.id, s])), [snap.storylines]);
  const active = snap.ranked.map((id) => byId[id]).filter((s) => s && s.pct >= 1).slice(0, 7);
  const decided = snap.storylines
    .filter((s) => s.resolution && (s.resolution !== "unresolved" || s.peakPct >= 10) && !s.id.startsWith("goal-"))
    .sort((a, b) => (b.resolvedMinute ?? 0) - (a.resolvedMinute ?? 0))
    .slice(0, 5);
  const row = (s: Storyline, i: number | null) => {
    const content = snap.content[s.id];
    const side = sideOf(snap, s.team);
    const isTeam = !s.player;
    const resolved = !!s.resolution;
    return (
      <tr key={s.id} className={`${sel === s.id ? "sel" : ""} ${resolved ? "resolved" : ""} ${s.resolution === "ruled_out" ? "struck" : ""}`} onClick={() => setSel(s.id)}>
        <td className="rank">{i ?? "–"}</td>
        <td className="st">
          <div className="row">
            {isTeam ? <Badge team={s.team} home={side === "home"} size={34} /> : <Avatar initials={initialsOf(s, snap)} side={side} size={34} />}
            <div>
              <div className="title">{s.title}</div>
              <div className="memline">📖 {s.memoryLine}</div>
            </div>
          </div>
        </td>
        <td>
          <div className="prob">
            <b>{resolved ? (s.resolution === "happened" ? "✓" : "—") : `${s.pct}%`}</b>
            {!resolved && <ProbBar pct={s.pct} color={side === "away" ? "var(--magenta)" : "var(--cyan)"} />}
          </div>
        </td>
        <td className="nowrap">
          {resolved ? null : s.delta15 === null ? <span className="muted">new</span> : s.delta15 >= 0 ? <span className="up">+{s.delta15} ▲</span> : <span className="down">{s.delta15} ▼</span>}
        </td>
        <td className="small" style={{ fontWeight: 700 }}>{s.impact}</td>
        <td>
          <StatusTag status={s.status} extra={s.status === "Pre-approved" && content?.approvedClock ? content.approvedClock : s.resolvedMinute ? `${s.resolvedMinute}'` : undefined} />
        </td>
        <td className="small">{s.versionsReady ? `${s.versionsReady}/4` : "0/4"}</td>
        <td>{!resolved && <Spark values={s.spark} color={side === "away" ? "var(--magenta)" : "var(--cyan)"} />}</td>
      </tr>
    );
  };
  return (
    <div className="panel scroll">
      <div className="panel-head">
        <h2>Rundown · Story Radar</h2>
        <span className="sub">Ranked by probability × impact · updates live</span>
      </div>
      <table className="rundown">
        <thead>
          <tr>
            <th>#</th><th>STORYLINE</th><th>PROB</th><th>Δ15'</th><th>IMPACT</th><th>STATUS</th><th>VERS.</th><th />
          </tr>
        </thead>
        <tbody>
          {active.map((s, i) => row(s, i + 1))}
          {active.length === 0 && (
            <tr><td colSpan={8} className="empty">No live storylines right now</td></tr>
          )}
          {decided.length > 0 && (
            <tr><td colSpan={8} style={{ paddingTop: 16, fontSize: 11, letterSpacing: "0.06em", color: "var(--muted)", fontWeight: 700 }}>ALREADY DECIDED</td></tr>
          )}
          {decided.map((s) => row(s, null))}
        </tbody>
      </table>
      <div className="kbd">↑↓ select · A approve · E edit · H hold · R revoke</div>
      <div className="legend">
        {["Rising", "Writing", "Ready", "Pre-approved", "Happened", "Near miss", "Ruled out"].map((s) => <StatusTag key={s} status={s} />)}
      </div>
    </div>
  );
}

function Preview({ snap, sid, room }: { snap: Snapshot; sid: string | null; room: string }) {
  const [tab, setTab] = useState<string>("en_analyst");
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [issues, setIssues] = useState<string[]>([]);
  const s = snap.storylines.find((x) => x.id === sid);
  const c = sid ? snap.content[sid] : undefined;
  useEffect(() => { setEditing(false); setIssues([]); }, [sid]);
  if (!s) return <div className="panel"><h2>Item preview</h2><div className="empty">Select a storyline</div></div>;
  const versions: Version[] = c?.versions ?? [];
  const v = versions.find((x) => x.key === tab);
  const overlay = versions.find((x) => x.key === "overlay");
  const ev = snap.evidence[s.id] ?? [];
  const status = c?.state === "pre_approved" ? `Pre-approved by ${c.approvedBy} ${c.approvedClock} · publishes automatically on trigger`
    : c?.state === "published" ? `Published ${c.publishedClock} · approved by ${c.approvedBy}`
    : c?.state === "ready" ? `Ready ${c.readyClock} · awaiting pre-approval`
    : c?.state === "awaiting_approval" ? "Happened · content waiting for approval"
    : c?.state === "held" ? "On hold" : s.status === "Writing" ? "Agents are writing…" : "Not prepared yet";
  const save = async () => {
    const r = await api.edit(room, s.id, tab, draft);
    if (r.ok) { setEditing(false); setIssues([]); } else setIssues(r.issues || ["rejected"]);
  };
  return (
    <div className="panel scroll">
      <h2 style={{ marginBottom: 2 }}>Item preview · {s.title}</h2>
      <div className="muted small" style={{ marginBottom: 10 }}>{status}{c?.reactive ? " · reactive (not forecast)" : ""}</div>
      {!s.resolution && (
        <div className="small" style={{ marginBottom: 10, lineHeight: 1.5 }}>
          <b>What could happen:</b> {s.question} &nbsp;<b>How likely:</b> {s.pct}% &nbsp;<b>Why rising:</b> {s.why}
          <br /><b>Why it matters:</b> {s.memoryLine} <span className="muted">(Season Memory)</span>
        </div>
      )}
      {versions.length > 0 ? (
        <>
          <div className="tabs">
            {versions.map((x) => (
              <button key={x.key} className={tab === x.key ? "on" : ""} onClick={() => { setTab(x.key); setEditing(false); }}>{VERSION_LABEL[x.key]}</button>
            ))}
          </div>
          {v && v.key !== "overlay" && (
            <div className="copybox">
              <div className="row" style={{ justifyContent: "flex-end", marginBottom: 6 }}>
                <span className="tag verified">Verified ✓</span>
              </div>
              {editing ? (
                <>
                  <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={4} style={{ width: "100%", background: "#12001a", color: "#fff", border: "1px solid var(--line)", borderRadius: 8, padding: 10, fontFamily: "inherit", fontSize: 15 }} />
                  {issues.length > 0 && <div className="small" style={{ color: "#ff6b97", marginTop: 6 }}>Verifier rejected: {issues.join("; ")}</div>}
                  <div className="row" style={{ marginTop: 8 }}>
                    <button className="pill solid-green small" onClick={save}>Save & re-verify</button>
                    <button className="pill small" onClick={() => setEditing(false)}>Cancel</button>
                  </div>
                </>
              ) : (
                <>
                  <p><WithSlots text={v.text} /></p>
                </>
              )}
            </div>
          )}
          {overlay && (tab === "overlay" || tab === "en_analyst") && (
            <>
              <div className="muted small" style={{ marginTop: 10 }}>Overlay preview</div>
              <div className="overlay-frame">
                <div className="lower-third">
                  {s.player && <Avatar initials={initialsOf(s, snap)} side={sideOf(snap, s.team)} size={42} />}
                  <div>
                    <b><WithSlots text={overlay.text} /></b>
                    <span><WithSlots text={overlay.sub ?? ""} /></span>
                  </div>
                </div>
              </div>
              <div className="mono small muted" style={{ marginTop: 6 }}>
                overlay.json · in 00:00 · out 00:08 · trigger {s.trigger}
              </div>
            </>
          )}
          <div className="row" style={{ marginTop: 12, flexWrap: "wrap" }}>
            {c && ["ready", "held", "awaiting_approval"].includes(c.state) && (
              <button className="pill solid-green" onClick={() => api.act(room, s.id, "approve")}>{c.state === "awaiting_approval" ? "Approve & publish" : "Pre-approve"}</button>
            )}
            {c && v && v.key !== "overlay" && !editing && c.state !== "published" && (
              <button className="pill" onClick={() => { setDraft(v.text); setEditing(true); }}>Edit</button>
            )}
            {c && ["ready", "pre_approved"].includes(c.state) && <button className="pill" onClick={() => api.act(room, s.id, "hold")}>Hold</button>}
            {c?.state === "pre_approved" && <button className="pill" onClick={() => api.act(room, s.id, "revoke")}>Revoke approval</button>}
          </div>
        </>
      ) : (
        <div className="empty">{s.status === "Writing" ? "Writer and Verifier agents are preparing 4 versions…" : "Story Radar has not flagged this one for preparation yet."}</div>
      )}
      {ev.length > 0 && (
        <>
          <div className="hr" />
          <h3>Evidence</h3>
          {ev.map((e) => (
            <div key={e.id} className="row small" style={{ padding: "5px 0", borderBottom: "1px solid var(--line-soft)" }}>
              {e.minute ? <span>{e.text}</span> : <span>📖 {e.text}</span>}
              <span className="spacer" />
              <span className="mono dim">{e.id.slice(-10)}</span>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

export default function Live({ snap, room }: { snap: Snapshot; room: string }) {
  const [sel, setSel] = useState<string | null>(null);
  const ranked = snap.ranked;
  const current = sel && snap.storylines.some((s) => s.id === sel) ? sel : ranked[0] ?? snap.storylines[0]?.id ?? null;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).tagName === "TEXTAREA" || (e.target as HTMLElement).tagName === "INPUT") return;
      const list = ranked;
      const i = current ? list.indexOf(current) : -1;
      if (e.key === "ArrowDown") setSel(list[Math.min(list.length - 1, i + 1)] ?? current);
      if (e.key === "ArrowUp") setSel(list[Math.max(0, i - 1)] ?? current);
      if (!current) return;
      if (e.key.toLowerCase() === "a") api.act(room, current, "approve");
      if (e.key.toLowerCase() === "h") api.act(room, current, "hold");
      if (e.key.toLowerCase() === "r") api.act(room, current, "revoke");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ranked, current, room]);

  const top = ranked.slice(0, 2).map((id) => snap.storylines.find((s) => s.id === id)!).filter(Boolean);
  const lastDecided = [...snap.storylines].filter((s) => s.resolution && s.resolution !== "unresolved" && !s.id.startsWith("goal-")).sort((a, b) => (b.resolvedMinute ?? 0) - (a.resolvedMinute ?? 0))[0];
  const lastSub = snap.feed.find((f) => f.kind === "sub");
  const chips = [
    ...top.map((s) => ({ ic: "📊", text: `${s.title} · ${s.pct}% · ${s.status.toLowerCase()}` })),
    lastDecided ? { ic: "🛡", text: `${lastDecided.title} ${lastDecided.status.toLowerCase()} ${lastDecided.resolvedMinute}'` } : null,
    lastSub ? { ic: "⇅", text: `${lastSub.text} ${lastSub.minute}'` } : null,
  ].filter(Boolean) as { ic: string; text: string }[];

  return (
    <div className="page">
      <TopNav room={room} />
      <div className="chips">
        {chips.map((c, i) => (
          <div key={i} className="chip"><span className="ic">{c.ic}</span>{c.text}</div>
        ))}
      </div>
      <div className="banner">
        <h1>Media Desk</h1>
        <div className="right"><MatchStrip snap={snap} /></div>
      </div>
      <ReplayControls snap={snap} room={room} />
      <div className="grid3">
        <div className="panel scroll">
          <h2>Match feed</h2>
          <ul className="feed">
            {snap.feed.slice(0, 9).map((it) => (
              <li key={it.id} className={it.kind}>
                <span className="min">{it.minute}'</span>
                <FeedIcon it={it} />
                <span>{it.text}</span>
              </li>
            ))}
            {snap.feed.length === 0 && <li><span /> <span /> <span className="muted">Kick-off soon</span></li>}
          </ul>
          <h3 style={{ marginTop: 16 }}>Momentum</h3>
          <Momentum data={snap.momentum} />
          <div className="hr" />
          <ControlChaos cc={snap.controlChaos} />
          <div className="hr" />
          <div className="small muted">
            xG {snap.teamStats[snap.match.home.id]?.xg.toFixed(2)} – {snap.teamStats[snap.match.away.id]?.xg.toFixed(2)} · shots {snap.teamStats[snap.match.home.id]?.shots} – {snap.teamStats[snap.match.away.id]?.shots}
          </div>
        </div>
        <Rundown snap={snap} sel={current} setSel={setSel} />
        <Preview snap={snap} sid={current} room={room} />
      </div>
      <AgentBar snap={snap} />
    </div>
  );
}
