import { useState } from "react";
import { AgentBar, MatchStrip, Toggle, TopNav } from "../components/ui";
import type { Snapshot } from "../types";

const LANES: [string, string][] = [
  ["Story Radar (model)", "var(--cyan)"],
  ["Editor agent", "#fff"],
  ["Tools (MCP)", "#c9a3ff"],
  ["Writer agent", "#c9a3ff"],
  ["Verifier agent", "var(--magenta)"],
  ["Producer", "var(--green)"],
];

function stepClass(lane: string, kind: string) {
  if (kind === "reject") return "reject";
  if (kind === "fallback") return "fallback";
  if (kind === "tool") return "tool";
  if (kind === "radar") return "radar";
  if (kind === "trigger") return "trigger";
  if (lane === "Verifier agent" || kind === "approve" || kind === "publish") return "verified";
  if (lane === "Writer agent") return "writer";
  return "ok";
}

export default function Trace({ snap, room }: { snap: Snapshot; room: string }) {
  const ids = Object.keys(snap.traces);
  const [sel, setSel] = useState<string>("");
  const [errorsOnly, setErrorsOnly] = useState(false);
  const [scope, setScope] = useState<"story" | "all">("story");
  const sid = sel && snap.traces[sel] ? sel : ids.find((i) => snap.traces[i].some((t) => t.kind === "reject")) ?? ids[0];
  const steps = sid ? snap.traces[sid] : [];
  const s = snap.storylines.find((x) => x.id === sid);
  const c = sid ? snap.content[sid] : undefined;
  // consecutive steps in the same lane render as one group so they never overlap
  const groups: { lane: string; start: number; steps: typeof steps }[] = [];
  steps.forEach((st, i) => {
    const g = groups[groups.length - 1];
    if (g && g.lane === st.lane) g.steps.push(st);
    else groups.push({ lane: st.lane, start: i, steps: [st] });
  });
  const n = Math.max(groups.length, 1);
  groups.forEach((g, k) => (g.start = k));
  const first = steps[0]?.clock;
  const last = steps[steps.length - 1]?.clock;
  const audit = snap.audit.filter((a) => (scope === "all" || a.storyline === sid) && (!errorsOnly || a.level === "error"));
  const title = (id: string) => snap.storylines.find((x) => x.id === id)?.title ?? id;

  return (
    <div className="page">
      <TopNav room={room} />
      <div className="banner">
        <h1>Agent Trace</h1>
        <div className="right" style={{ textAlign: "right" }}>
          <div style={{ fontSize: 30, fontWeight: 800, color: "#fff" }}>{s?.title ?? "—"}</div>
          <div className="mono" style={{ fontSize: 16 }}>{first} → {last}</div>
        </div>
      </div>
      <div className="filters">
        <select className="select" value={sid ?? ""} onChange={(e) => setSel(e.target.value)}>
          {ids.map((id) => (
            <option key={id} value={id}>Storyline: {title(id)}{snap.traces[id].some((t) => t.kind === "reject") ? "  (rejection)" : ""}</option>
          ))}
        </select>
        <Toggle on={errorsOnly} label="Errors only" onChange={setErrorsOnly} />
        <div className="seg">
          <button className={scope === "story" ? "on" : ""} onClick={() => setScope("story")}>This storyline</button>
          <button className={scope === "all" ? "on" : ""} onClick={() => setScope("all")}>All activity</button>
        </div>
        <span className="spacer" />
        <MatchStrip snap={snap} compact />
      </div>
      {!sid ? (
        <div className="empty">No agent activity yet. Press play or jump ahead on the Live page.</div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 330px", gap: 14, padding: "0 24px 14px" }}>
          <div className="panel">
            <div className="panel-head">
              <h2>Storyline trace</h2>
              <span className="mono muted">{sid}</span>
              <span className="sub">{c?.backend?.startsWith("foundry") ? `Microsoft Foundry · ${c.backend.split(":")[1]}` : "Local deterministic writer"}</span>
            </div>
            <div className="lanes">
              {LANES.map(([lane, color]) => (
                <div className="lane" key={lane}>
                  <div className="lane-label"><span className="dot" style={{ background: color }} />{lane}</div>
                  <div className="lane-track">
                    {groups.filter((g) => g.lane === lane).map((g) => (
                      <div key={g.start} style={{ position: "absolute", top: "50%", transform: "translateY(-50%)", left: `${(g.start / n) * 86}%`, display: "flex", gap: 6, maxWidth: `${100 - (g.start / n) * 86}%`, flexWrap: "wrap" }}>
                        {g.steps.map((st, j) => (
                          <div
                            key={j}
                            className={`step ${stepClass(lane, st.kind)}`}
                            style={{ position: "static", transform: "none" }}
                            title={`${st.clock} · ${st.label}${st.ms ? ` · ${st.ms} ms` : ""}${st.issues ? "\n" + st.issues.join("\n") : ""}`}
                          >
                            {st.kind === "reject" ? "✗ " : ""}{st.label}
                            {st.ms > 0 && <span style={{ opacity: 0.65, fontWeight: 500 }}> · {st.ms} ms</span>}
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            {c?.drafts && c.drafts.length > 0 && (
              <>
                <div className="hr" />
                <h3>Rejected draft</h3>
                {c.drafts.map((d) => (
                  <div key={d.attempt} className="small" style={{ marginBottom: 8 }}>
                    <span className="tag reject">Rejected · attempt {d.attempt + 1}</span>{" "}
                    <span style={{ color: "#ff9ab8" }}>{d.issues.join("; ")}</span>
                    <div className="copybox" style={{ marginTop: 6 }}>
                      <span style={{ textDecoration: "line-through", opacity: 0.8 }}>{d.versions.find((v) => v.key === "en_analyst")?.text}</span>
                    </div>
                  </div>
                ))}
              </>
            )}
          </div>
          <div className="panel">
            <h2>Shared state</h2>
            <div className="kv">
              <div>storyline</div><div>{sid}</div>
              <div>probability</div><div>{s ? (s.p).toFixed(2) : "—"}</div>
              <div>impact</div><div>{s?.impact}</div>
              <div>trigger</div><div>{s?.trigger}</div>
              <div>versions</div><div>{c?.versions.length ?? 0}</div>
              <div>verified</div><div>{c && c.versions.length ? "true" : "false"}</div>
              <div>state</div><div>{c?.state ?? s?.status}</div>
              <div>approved_by</div><div>{c?.approvedBy ?? "—"}</div>
              <div>markets</div><div>UK</div>
              <div>slots</div><div>{c?.slots.join(", ")}</div>
            </div>
            <h3 style={{ marginTop: 16 }}>Evidence</h3>
            {(snap.evidence[sid] ?? []).map((e) => (
              <div key={e.id} className="row small" style={{ padding: "6px 0", borderBottom: "1px solid var(--line-soft)" }}>
                {e.minute ? e.text : `📖 ${e.text}`}<span className="spacer" />›
              </div>
            ))}
            {s?.resolution && <div className="small muted" style={{ marginTop: 8 }}>Resolved: {s.status} · {s.resolutionNote}</div>}
          </div>
        </div>
      )}
      <div className="panel" style={{ margin: "0 24px 14px" }}>
        <h2>Audit log</h2>
        <table className="audit">
          <thead>
            <tr><th>TIME</th><th>ACTOR</th><th>ACTION</th><th>DETAIL</th>{scope === "all" && <th>STORYLINE</th>}</tr>
          </thead>
          <tbody>
            {audit.slice(-40).reverse().map((a, i) => (
              <tr key={i} className={a.level}>
                <td>{a.clock}</td><td>{a.actor}</td><td>{a.action}</td><td>{a.detail}</td>
                {scope === "all" && <td className="dim">{a.storyline ? title(a.storyline) : ""}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <AgentBar snap={snap} />
    </div>
  );
}
