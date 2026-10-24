import type { SystemTab } from "@/routes/search";

/**
 * Pure shaping of the three snapshots System reads (lifecycle, ops, health) into one status strip and one
 * timeline. Each number comes from exactly one snapshot, so the strip cannot show two versions of a count.
 */

export type Tone = "ok" | "warn" | "bad" | "";

export interface Tile {
  id: string;
  label: string;
  value: string;
  hint: string;
  tone: Tone;
  tab: SystemTab;
}

/** The parts of the loosely typed snapshots that System reads. */
export interface LifecycleLike {
  version?: string;
  next_version?: string;
  github?: string;
  working?: { lanes?: Record<string, number> };
  infra_branches?: unknown[];
  timeline?: TimelineRow[];
}
export interface TimelineRow {
  sha: string;
  short?: string;
  date: string;
  subject: string;
  kind?: string;
  scope?: string;
  kb_version?: string | null;
  pr?: number | string | null;
}
export interface Thread {
  id: string;
  kind?: string;
  title: string;
  state?: string;
  status?: string;
  next?: string;
  age_hours?: number;
}
export interface Finding {
  severity?: string;
  kind?: string;
  detail?: string;
  fix?: string;
}
export interface Run {
  started: string;
  status?: string;
  duration?: number;
  errors?: number;
  warnings?: number;
  sync?: { commits?: number; pushed?: boolean; failed?: boolean };
  deploy?: { state?: string } | null;
  steps?: { name: string; status?: string }[];
}

/** Why a nightly run is not ok, most important first: a failed sync, a failed site deploy, then failed steps. */
export function runReason(run: Run): string {
  if (run.sync?.failed) return "sync failed";
  if (run.deploy?.state === "failed") return "site deploy failed";
  const bad = (run.steps ?? []).filter((s) => s.status === "error").map((s) => s.name);
  if (bad.length) return `${bad.join(", ")} failed`;
  if (run.errors) return `${run.errors} error${run.errors === 1 ? "" : "s"}`;
  if (run.warnings) return `${run.warnings} warning${run.warnings === 1 ? "" : "s"}`;
  return "";
}

/**
 * The Nightly tile follows the LATEST RUN's own outcome (meta/.ops/runs.jsonl, the timeline's source), not the
 * scheduler summary, which only says the job is installed and when it last started.
 */
function nightlyTile(ops: OpsLike | undefined, summary: string): Pick<Tile, "value" | "hint" | "tone"> {
  if (!ops) return { value: "…", hint: "", tone: "" };
  const last = [...(ops.runs ?? [])].sort((a, b) => Date.parse(b.started) - Date.parse(a.started))[0];
  if (!last) return summary ? { value: "no runs yet", hint: summary, tone: "warn" } : { value: "not installed", hint: "", tone: "warn" };
  const when = new Date(last.started).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  const t = tone(last.status) || (last.status === "failed" ? "bad" : "");
  const reason = runReason(last);
  return { value: last.status ?? "unknown", hint: [reason, when].filter(Boolean).join(" · "), tone: t || "warn" };
}
export interface OpsLike {
  threads?: Thread[];
  hygiene?: { errors?: number; warnings?: number; findings?: Finding[] };
  runs?: Run[];
  nightly?: { summary?: string; hint?: string | null };
}
export interface HealthLike {
  inbox_count?: number;
  values?: Record<string, number | string>;
  statuses?: Record<string, string>;
}

const num = (v: unknown) => (typeof v === "number" ? v : Number(v) || 0);
const tone = (s?: string): Tone => (s === "ok" || s === "warn" || s === "bad" ? s : s === "error" ? "bad" : "");
const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? "" : "s"}`;

/** Six tiles; a tile whose snapshot has not arrived yet shows "…". */
export function tiles(lc?: LifecycleLike, ops?: OpsLike, health?: HealthLike): Tile[] {
  const threads = ops?.threads ?? [];
  const stale = threads.filter((t) => t.status === "warn" || t.status === "bad").length;
  const hy = ops?.hygiene;
  const v = health?.values ?? {};
  const st = health?.statuses ?? {};
  const dirty = Object.values(lc?.working?.lanes ?? {}).reduce((a, b) => a + num(b), 0);
  const nightly = ops?.nightly?.summary ?? "";
  return [
    {
      id: "version",
      label: "Knowledge version",
      value: lc?.version ? `kb-${lc.version}` : "…",
      hint: lc ? (dirty ? `${plural(dirty, "uncommitted file")}` : "working tree clean") : "",
      tone: lc ? (dirty ? "warn" : "ok") : "",
      tab: "history",
    },
    {
      id: "work",
      label: "Open work",
      value: ops ? String(threads.length) : "…",
      hint: ops ? (stale ? `${stale} need attention` : "nothing stale") : "",
      tone: ops ? (stale ? "warn" : "ok") : "",
      tab: "overview",
    },
    {
      id: "hygiene",
      label: "Hygiene",
      value: hy ? `${num(hy.errors)} / ${num(hy.warnings)}` : "…",
      hint: hy ? "errors / warnings" : "",
      tone: hy ? (num(hy.errors) ? "bad" : num(hy.warnings) ? "warn" : "ok") : "",
      tab: "overview",
    },
    {
      id: "lint",
      label: "Lint",
      value: health ? `${num(v.errors)} / ${num(v.warnings)}` : "…",
      hint: health ? "errors / warnings" : "",
      tone: health ? (num(v.errors) ? "bad" : tone(st.warnings) || "ok") : "",
      tab: "health",
    },
    {
      id: "backlog",
      label: "Backlog",
      value: health ? String(num(v.queued)) : "…",
      hint: health ? `queued · ${num(health.inbox_count)} in inbox · ${num(v.partial_books)} partial books` : "",
      tone: health ? (num(health.inbox_count) ? "warn" : "") : "",
      tab: "pipeline",
    },
    {
      id: "nightly",
      label: "Nightly",
      ...nightlyTile(ops, nightly),
      tab: "overview",
    },
  ];
}

export type EventKind = "knowledge" | "tooling" | "nightly";

export interface Event {
  at: string;
  kind: EventKind;
  title: string;
  sub: string;
  href?: string;
  tone: Tone;
}

/** kb steps, merges and nightly runs on one time axis, newest first. */
export function timeline(lc?: LifecycleLike, ops?: OpsLike, limit = 80): Event[] {
  const out: Event[] = [];
  for (const r of lc?.timeline ?? []) {
    const knowledge = r.kind === "kb";
    out.push({
      at: r.date,
      kind: knowledge ? "knowledge" : "tooling",
      title: r.subject,
      sub: [r.short ?? r.sha.slice(0, 9), knowledge && r.kb_version ? `kb-${r.kb_version}` : "", r.pr ? `#${r.pr}` : ""].filter(Boolean).join(" · "),
      href: lc?.github ? `${lc.github}/commit/${r.sha}` : undefined,
      tone: "",
    });
  }
  for (const run of ops?.runs ?? []) {
    const bits = [
      run.duration ? `${Math.round(run.duration)} s` : "",
      run.sync ? (run.sync.failed ? "sync failed" : `${plural(num(run.sync.commits), "commit")}${run.sync.pushed ? " pushed" : ""}`) : "",
      run.warnings ? plural(num(run.warnings), "warning") : "",
      run.errors ? plural(num(run.errors), "error") : "",
      run.deploy?.state ? `site ${run.deploy.state}` : "",
    ];
    out.push({ at: run.started, kind: "nightly", title: `Nightly run — ${run.status ?? "unknown"}`, sub: bits.filter(Boolean).join(" · "), tone: tone(run.status) });
  }
  return out.sort((a, b) => Date.parse(b.at) - Date.parse(a.at)).slice(0, limit);
}

/** Threads that ask for something first, then findings not tied to a thread. */
export function needsYou(ops?: OpsLike): { threads: Thread[]; findings: Finding[] } {
  const rank = (t: Thread) => (t.status === "bad" ? 0 : t.status === "warn" ? 1 : 2);
  const threads = [...(ops?.threads ?? [])].sort((a, b) => rank(a) - rank(b) || (b.age_hours ?? 0) - (a.age_hours ?? 0));
  return { threads, findings: ops?.hygiene?.findings ?? [] };
}
