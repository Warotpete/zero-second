export type Status =
  | "Watching"
  | "Rising"
  | "Writing"
  | "Ready"
  | "Pre-approved"
  | "Happened"
  | "Near miss"
  | "Ruled out"
  | "Unresolved";

export interface Team {
  id: string;
  name: string;
  short: string;
  form?: string;
}

export interface PlayerRef {
  id: string;
  name: string;
  short: string;
  last: string;
  initials: string;
  team: string;
  number: number;
  position: string;
}

export interface Storyline {
  id: string;
  kind: string;
  team: string;
  opp: string;
  player: string | null;
  initials: string;
  title: string;
  question: string;
  impact: "HIGH" | "MED" | "LOW";
  memoryLine: string;
  memoryFact: string | null;
  trigger: string;
  p: number;
  pct: number;
  delta15: number | null;
  isNew: boolean;
  score: number;
  peakPct: number;
  peakMinute: number;
  why: string;
  drivers: string[];
  status: Status;
  prep: string;
  resolution: string | null;
  resolvedMinute: number | null;
  resolutionNote: string;
  calledMinute: number | null;
  calledPct: number | null;
  versionsReady: number;
  approvedBy: string | null;
  spark: number[];
  activatedMinute: number;
}

export interface Version {
  key: "en_analyst" | "en_casual" | "th_casual" | "overlay";
  lang: string;
  audience: string;
  text: string;
  sub?: string;
  gloss?: string;
  faultInjected?: boolean;
}

export interface Content {
  storyline: string;
  versions: Version[];
  template: Version[];
  angle: string;
  state: string;
  reactive: boolean;
  readyClock: string | null;
  approvedBy: string | null;
  approvedClock: string | null;
  publishedClock: string | null;
  drafts: { attempt: number; versions: Version[]; issues: string[] }[];
  backend: string;
  slots: string[];
}

export interface TraceStep {
  clock: string;
  t: number;
  lane: string;
  label: string;
  kind: string;
  ms: number;
  wall: number;
  issues?: string[];
}

export interface Audit {
  clock: string;
  actor: string;
  action: string;
  detail: string;
  storyline: string | null;
  level: string;
}

export interface Moment {
  id: string;
  storyline: string;
  kind: string;
  title: string;
  team: string | null;
  player: string | null;
  minute: number;
  clock: string;
  versions: Version[];
  reactive: boolean;
  calledMinute: number | null;
  calledPct: number | null;
  approvedBy: string | null;
}

export interface FeedItem {
  id: string;
  t: number;
  minute: number;
  kind: string;
  team: string | null;
  player: string | null;
  text: string;
  data: Record<string, unknown>;
}

export interface TeamStats {
  possession: number;
  xg: number;
  shots: number;
  onTarget: number;
  bigChances: number;
  passes: number;
  passAccuracy: number;
  tackles: number;
  interceptions: number;
  pressures: number;
  fouls: number;
  yellow: number;
  red: number;
  topBallSpeed: number;
  topShotSpeed: number;
  boxTouches: number;
}

export interface Goal {
  id: string;
  minute: number;
  x: number;
  y: number;
  team: string;
  player: string;
  xg: number;
  speedKmh: number;
  assist: string | null;
  playerInfo: PlayerRef;
}

export interface Snapshot {
  room: string;
  seed: number;
  scenario: boolean;
  version: number;
  backend: string;
  match: {
    id: string;
    matchweek: number;
    home: Team;
    away: Team;
    score: { home: number; away: number };
    clock: string;
    t: number;
    minute: number;
    period: number;
    finished: boolean;
    venue: string;
    goals: Goal[];
  };
  control: { playing: boolean; speed: number; speeds: number[]; autopilot: boolean; faultInjection: boolean };
  feed: FeedItem[];
  momentum: { minute: number; value: number }[];
  controlChaos: { index: number; label: string };
  teamStats: Record<string, TeamStats>;
  ball: { x: number; y: number; team: string | null; type: string | null };
  tags: { player: PlayerRef; text: string; minute: number; data: { speedKmh?: number } }[];
  storylines: Storyline[];
  ranked: string[];
  evidence: Record<string, { id: string; minute: number | null; text: string }[]>;
  content: Record<string, Content>;
  traces: Record<string, TraceStep[]>;
  audit: Audit[];
  moments: Moment[];
  overlays: unknown[];
  agents: Record<string, { state: string; since: number }>;
  recap: null | {
    text: { broadcaster: string; casual: string; analyst: string };
    state: string;
    backend: string;
    approvedBy: string | null;
  };
}

export interface LineupPlayer extends PlayerRef {
  onPitch: boolean;
  role: string;
  baseX: number;
  baseY: number;
  stats: {
    goals: number;
    shots: number;
    xg: number;
    passes: number;
    passAccuracy: number | null;
    avgPassDifficulty: number | null;
    distance_km: number;
    top_speed: number;
    rating: number;
    tackles: number;
    box_touches: number;
  };
}
