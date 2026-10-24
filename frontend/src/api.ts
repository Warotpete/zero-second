import { useEffect, useRef, useState } from "react";
import type { LineupPlayer, Snapshot } from "./types";

export function roomFromUrl(): string {
  const q = new URLSearchParams(window.location.search).get("room");
  return (q || "demo").replace(/[^a-z0-9-]/gi, "").slice(0, 32) || "demo";
}

async function post(path: string, body: unknown = {}) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  return r.json();
}

export const api = {
  control: (room: string, action: string, value?: number) => post(`/api/rooms/${room}/control`, { action, value }),
  jump: (room: string, minute: number) => post(`/api/rooms/${room}/jump`, { minute }),
  newMatch: (room: string, seed?: number) => post(`/api/rooms/${room}/new`, { seed }),
  act: (room: string, sid: string, action: "approve" | "hold" | "revoke") => post(`/api/rooms/${room}/storylines/${encodeURIComponent(sid)}/${action}`),
  edit: (room: string, sid: string, key: string, text: string) => post(`/api/rooms/${room}/storylines/${encodeURIComponent(sid)}/edit`, { key, text }),
  approveRecap: (room: string) => post(`/api/rooms/${room}/recap/approve`),
  memory: (room: string) => fetch(`/api/rooms/${room}/memory`).then((r) => r.json()),
  lineups: (room: string): Promise<Record<string, LineupPlayer[]>> => fetch(`/api/rooms/${room}/lineups`).then((r) => r.json()),
  calibration: () => fetch(`/api/calibration`).then((r) => r.json()),
};

/** Live room state over Server-Sent Events, with polling fallback. */
export function useRoom(room: string): Snapshot | null {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const es = useRef<EventSource | null>(null);
  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const r = await fetch(`/api/rooms/${room}/state`);
        if (!cancelled) setSnap(await r.json());
      } catch {
        /* retry */
      }
      if (!cancelled) timer = window.setTimeout(poll, 1000);
    };
    try {
      const src = new EventSource(`/api/rooms/${room}/stream`);
      es.current = src;
      src.onmessage = (ev) => !cancelled && setSnap(JSON.parse(ev.data));
      src.onerror = () => {
        src.close();
        if (!cancelled && timer === undefined) poll();
      };
    } catch {
      poll();
    }
    return () => {
      cancelled = true;
      es.current?.close();
      if (timer) window.clearTimeout(timer);
    };
  }, [room]);
  return snap;
}

export function usePoll<T>(fn: () => Promise<T>, deps: unknown[], every = 0): T | null {
  const [v, setV] = useState<T | null>(null);
  useEffect(() => {
    let cancelled = false;
    let t: number | undefined;
    const run = async () => {
      try {
        const x = await fn();
        if (!cancelled) setV(x);
      } catch {
        /* ignore */
      }
      if (every && !cancelled) t = window.setTimeout(run, every);
    };
    run();
    return () => {
      cancelled = true;
      if (t) window.clearTimeout(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return v;
}
