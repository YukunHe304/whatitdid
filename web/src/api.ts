// The server's shapes, mirrored. Ids only — every display string comes from /api/strings.

export type PhaseId = string;

export interface Finding {
  kind: string;
  severity: number;
  turns: number[];
  facts: Record<string, unknown>;
}

export interface Turn {
  turn: number;
  phase: Record<PhaseId, number>;
  noul: Record<string, number>;
  targeting: number | null;
  narration_changed_label: boolean;
  top: PhaseId | null;
  top_p: number | null;
  tool: string | null;
  command: string;
  n_actions: number;
  observation: string;
  observation_len: number;
  narration: string;
  narration_len: number;
  kept_word: boolean | null;
  marks: string[];
}

export interface Report {
  agent: string;
  model: string | null;
  source: string;
  labeler: string;
  questions: string;
  phases: PhaseId[];
  n_turns: number;
  mix: Record<PhaseId, number>;
  stats: Record<string, number>;
  truthfulness: number | null;
  stated: number;
  carried: number;
  label_failures: { total?: number; by_cause?: Record<string, number> };
  findings: Finding[];
  per_turn: Turn[];
}

export interface MetricRow {
  id: string;
  group: "phase" | "metric";
  delta: number;
  low: number;
  high: number;
  improved: number;
  n: number;
  solid: boolean;
  noise: number | null;
  verdict: "above_noise" | "within_noise" | "unstable" | "no_baseline";
}

export interface CompareResult {
  metrics: MetricRow[];
  tasks: { shared: string[]; n: number };
  questions: string;
  rounds: number;
  noise: { source: string; n_runs?: number; n_pairs?: number; about?: string };
}

export interface Strings {
  lang: string;
  phases: Record<string, string>;
  metrics: Record<string, string>;
  metric_help: Record<string, string>;
  findings: Record<string, string>;
  ui: Record<string, string>;
}

export interface Config {
  demo_only: boolean;
  has_key: boolean;
  lang: string;
  langs: string[];
  version: string;
  question_sets: { id: string; phases: string[]; roles: Record<string, string[]> }[];
}

export interface WatchState {
  id: string;
  root: string;
  state: "running" | "stopped" | "error";
  error: string | null;
  questions: string;
  seconds: number;
  found: number;
  done: { problem: string; n_turns: number; seconds: number }[];
  failed: { problem: string; why: string }[];
}

export interface Job {
  id: string;
  name: string;
  state: "running" | "done" | "error";
  done: number;
  total: number;
  error: string | null;
  result: string | null;
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail ?? res.statusText);
  }
  return res.json() as Promise<T>;
}

export const api = {
  config: () => fetch("api/config").then(json<Config>),
  strings: (lang: string) => fetch(`api/strings/${lang}`).then(json<Strings>),
  demoAgents: () => fetch("api/demo/agents").then(json<Record<string, Report>>),
  // On GitHub Pages there is no server to POST to, so the comparison is pre-computed and
  // served as a file. Try the real endpoint first and fall back to it.
  demoCompare: async () => {
    try {
      return await fetch("api/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ demo: true }),
      }).then(json<CompareResult>);
    } catch {
      return fetch("api/compare.json").then(json<CompareResult>);
    }
  },
  compare: (payload: Record<string, unknown>) =>
    fetch("api/compare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(json<CompareResult>),
  reports: () => fetch("api/reports").then(json<{ id: string; agent: string }[]>),
  report: (id: string) => fetch(`api/reports/${id}`).then(json<Report>),
  job: (id: string) => fetch(`api/jobs/${id}`).then(json<Job>),
  startWatch: (root: string, questions: string) =>
    fetch("api/watch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ root, questions }),
    }).then(json<WatchState>),
  watch: (id: string) => fetch(`api/watch/${id}`).then(json<WatchState>),
  stopWatch: (id: string) =>
    fetch(`api/watch/${id}/stop`, { method: "POST" }).then(json<WatchState>),
  profileFile: (file: File, questions: string) => {
    const form = new FormData();
    form.append("file", file);
    return fetch(`api/profile?questions=${encodeURIComponent(questions)}`, {
      method: "POST",
      body: form,
    }).then(json<{ job: string; name: string }>);
  },
  profilePath: (path: string, questions: string) =>
    fetch(
      `api/profile?path=${encodeURIComponent(path)}&questions=${encodeURIComponent(questions)}`,
      { method: "POST" },
    ).then(json<{ job: string; name: string }>),
  setKey: (key: string) =>
    fetch("api/config/key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key }),
    }).then(json<{ stored: boolean; has_key: boolean }>),
};

// Kept in step with report.py so a page and its printable report never disagree.
export const PHASE_COLORS: Record<string, string> = {
  survey: "#7c9cbf",
  localize: "#6aa9a0",
  inspect: "#d4a06a",
  probe: "#c0797c",
  repair: "#a88bc4",
  verify: "#7fb27a",
  report: "#c9b073",
  other: "#9a9a9a",
  read: "#d4a06a",
  reproduce: "#c0797c",
  edit: "#a88bc4",
  test: "#7fb27a",
  revert: "#b08968",
};
const SPARES = ["#7c9cbf", "#6aa9a0", "#d4a06a", "#c0797c", "#a88bc4", "#7fb27a", "#c9b073"];

export function phaseColor(phase: string, order: string[] = []): string {
  if (PHASE_COLORS[phase]) return PHASE_COLORS[phase];
  const i = order.indexOf(phase);
  return i >= 0 ? SPARES[i % SPARES.length] : "#9a9a9a";
}

export function findingText(finding: Finding, templates: Record<string, string>,
                            phases: Record<string, string>): string {
  const template = templates[finding.kind] ?? finding.kind;
  const facts: Record<string, string> = {};
  for (const [key, value] of Object.entries(finding.facts ?? {})) {
    facts[key] = Array.isArray(value)
      ? value.map((v) => phases[String(v)] ?? String(v)).join(", ")
      : String(value);
  }
  return template.replace(/\{(\w+)\}/g, (whole, key) => facts[key] ?? whole);
}
