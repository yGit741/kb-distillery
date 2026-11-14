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
  /** The tab the tile opens on its own screen (System or, flag ui.data-system-split, Ingest). */
  tab: string;
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
export interface QueueEntry {
  pr?: number | string | null;
  branch?: string | null;
  pid?: number | null;
  age?: number;
  held?: number;
  alive?: boolean | null;
  stale?: boolean;
}
export interface QueueLike {
  holder?: QueueEntry | null;
  waiters?: QueueEntry[];
  stale_after?: number;
}

const ago = (sec: number) => (sec < 120 ? `${Math.round(sec)}s` : sec < 7200 ? `${Math.floor(sec / 60)}m` : `${Math.floor(sec / 3600)}h`);
const who = (e: QueueEntry) => (e.pr ? `#${e.pr}` : e.branch ?? "?");

/**
 * The Merges tile reads the live merge queue (`ship merge` serialization): idle is ok, waiters are warn, and a
 * holder past the stale limit or with a dead pid is bad (the next merger will reclaim it, but something hung).
 * A snapshot without a queue field (old backend, unreadable file) is "unknown", never a silent ok.
 */
function mergesTile(ops: OpsLike | undefined): Pick<Tile, "value" | "hint" | "tone"> {
  if (!ops) return { value: "…", hint: "", tone: "" };
  const q = ops.queue;
  if (!q) return { value: "unknown", hint: "queue state unavailable", tone: "warn" };
  const h = q.holder;
  if (!h) return { value: "idle", hint: "no merge running", tone: "ok" };
  const waiters = q.waiters ?? [];
  const held = num(h.held ?? h.age);
  const limit = num(q.stale_after) || 1200;
  const dead = h.alive === false;
  const hung = dead || h.stale || held > limit;
  const why = dead ? (h.pid != null ? `pid ${h.pid} dead` : "holder dead") : hung ? `stale, held ${ago(held)}` : `merging ${ago(held)}`;
  const wait = waiters.length ? `${waiters.length} waiting (${waiters.map(who).join(", ")})` : "";
  return {
    value: hung ? `${who(h)} stuck` : `${who(h)} merging`,
    hint: [why, wait].filter(Boolean).join(" · "),
    tone: hung ? "bad" : waiters.length ? "warn" : "ok",
  };
}

export interface DeployLike {
  live_sha?: string | null;
  main_sha?: string | null;
  behind?: boolean | null;
  behind_minutes?: number | null;
  deploying?: string | null;
  last_outcome?: string | null;
  last_sha?: string | null;
  last_reason?: string;
  queued?: string[];
  rollbacks_7d?: number;
  owner_installed?: boolean;
  owner_alive?: boolean;
}

/** Minutes live may trail main before the Deploy tile turns bad. */
export const DEPLOY_BEHIND_LIMIT = 30;
const sha7 = (s?: string | null) => (s ? s.slice(0, 7) : "?");

/**
 * The Deploy tile reads the deploy owner (kb_distillery.publish.cloudflare.owner) vs origin/main. Bad wins over everything: a failed or
 * rollback-failed last outcome, the owner not installed / not running, or live != main past the limit. Missing
 * data is "unknown" (warn), never ok — a green tile next to a failed reality is the bug this tile exists to avoid.
 */
function deployTile(ops: OpsLike | undefined): Pick<Tile, "value" | "hint" | "tone"> {
  if (!ops) return { value: "…", hint: "", tone: "" };
  const d = ops.deploy;
  if (!d) return { value: "unknown", hint: "deploy state unavailable", tone: "warn" };
  const rb = num(d.rollbacks_7d);
  const extra = [
    (d.queued ?? []).length ? `queued ${(d.queued ?? []).map(sha7).join(", ")}` : "",
    rb ? `${plural(rb, "rollback")} in 7 d` : "",
  ];
  const hint = (...bits: string[]) => [...bits, ...extra].filter(Boolean).join(" · ");
  const outcome = d.last_outcome ?? "";
  const reason = (d.last_reason ?? "").slice(0, 120);
  if (outcome === "failed" || outcome === "rollback-failed")
    return { value: `${outcome} ${sha7(d.last_sha)}`, hint: hint(reason), tone: "bad" };
  if (!d.owner_installed) return { value: "owner not installed", hint: hint("pixi run install-deploy-owner"), tone: "bad" };
  if (!d.owner_alive) return { value: "owner not running", hint: hint("no heartbeat from kb_distillery.publish.cloudflare.owner"), tone: "bad" };
  if (d.behind == null) return { value: "unknown", hint: hint(d.live_sha ? "origin/main unreadable" : "no live sha recorded"), tone: "warn" };
  const mins = num(d.behind_minutes);
  if (d.behind && mins > DEPLOY_BEHIND_LIMIT)
    return { value: `behind ${mins} min`, hint: hint(`live ${sha7(d.live_sha)} ≠ main ${sha7(d.main_sha)}`, outcome === "rolled-back" ? reason : ""), tone: "bad" };
  if (d.deploying) return { value: `deploying ${sha7(d.deploying)}`, hint: hint(`live ${sha7(d.live_sha)}`), tone: "warn" };
  if (d.behind) return { value: `behind ${mins} min`, hint: hint(`live ${sha7(d.live_sha)} ≠ main ${sha7(d.main_sha)}`), tone: "warn" };
  return { value: "live = main", hint: hint(sha7(d.live_sha), outcome === "rolled-back" ? `last rolled back: ${reason}` : ""), tone: "ok" };
}

/** Hygiene finding kinds produced by the backend staleness rules (staleness.KINDS) — keep the two lists in step. */
export const STALE_KINDS = ["idle-branch", "missing-worktree", "detached-worktree", "idle-pr"];

/** Short name of a stale finding for the tile hint: the branch / PR / path its detail starts with. */
function staleName(f: Finding): string {
  const d = f.detail ?? "";
  const pr = /^PR #(\d+)/.exec(d);
  if (pr) return `#${pr[1]}`;
  const head = d.split(/[: ]/)[0] ?? "";
  return head.split("/").slice(-2).join("/") || (f.kind ?? "?");
}

/**
 * The Stale work tile counts the staleness findings of the ops snapshot's hygiene run (the same rules as
 * `ship status` and `ship prune --stale`): none is ok, any is warn, and the hint names the first three.
 */
function staleTile(ops: OpsLike | undefined): Pick<Tile, "value" | "hint" | "tone"> {
  const hy = ops?.hygiene;
  if (!hy) return { value: "…", hint: "", tone: "" };
  const items = (hy.findings ?? []).filter((f) => STALE_KINDS.includes(f.kind ?? ""));
  if (!items.length) return { value: "none", hint: "no idle branches, worktrees or PRs", tone: "ok" };
  const top = items.slice(0, 3).map(staleName).join(", ");
  return { value: String(items.length), hint: items.length > 3 ? `${top}, …` : top, tone: "warn" };
}

export interface OpsLike {
  queue?: QueueLike | null;
  deploy?: DeployLike | null;
  threads?: Thread[];
  hygiene?: { errors?: number; warnings?: number; findings?: Finding[] };
  runs?: Run[];
  nightly?: { summary?: string; hint?: string | null };
  /** False when the kb uses none of nightly / deploy owner / a publisher: those tiles are left out. Absent = show. */
  maintainer?: boolean;
}

/** The tiles and filters that only mean something to a kb running the owner's operations. */
export const OWNER_TILES: readonly string[] = ["nightly", "merges", "deploy"];
export const showOwnerOps = (ops?: OpsLike): boolean => ops?.maintainer !== false;
export interface HealthLike {
  generated_at?: string;
  inbox_count?: number;
  compression_pct?: number;
  wiki_pages?: number;
  raw_files?: number;
  /** Chart series of the health page: in_degree, lint_phases_ms, coherence_by_kind, lint_by_category. */
  graphs?: Record<string, Record<string, unknown>>;
  values?: Record<string, number | string>;
  statuses?: Record<string, string>;
}

const num = (v: unknown) => (typeof v === "number" ? v : Number(v) || 0);
const tone = (s?: string): Tone => (s === "ok" || s === "warn" || s === "bad" ? s : s === "error" ? "bad" : "");
const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? "" : "s"}`;

/** Nine tiles (six when the kb runs no owner operations); a tile whose snapshot has not arrived yet shows "…". */
export function tiles(lc?: LifecycleLike, ops?: OpsLike, health?: HealthLike): Tile[] {
  const threads = ops?.threads ?? [];
  const stale = threads.filter((t) => t.status === "warn" || t.status === "bad").length;
  const hy = ops?.hygiene;
  const v = health?.values ?? {};
  const st = health?.statuses ?? {};
  const dirty = Object.values(lc?.working?.lanes ?? {}).reduce((a, b) => a + num(b), 0);
  const nightly = ops?.nightly?.summary ?? "";
  const all: Tile[] = [
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
    {
      id: "merges",
      label: "Merges",
      ...mergesTile(ops),
      tab: "overview",
    },
    {
      id: "deploy",
      label: "Deploy",
      ...deployTile(ops),
      tab: "overview",
    },
    {
      id: "stale",
      label: "Stale work",
      ...staleTile(ops),
      tab: "overview",
    },
  ];
  return showOwnerOps(ops) ? all : all.filter((t) => !OWNER_TILES.includes(t.id));
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

/* ---- flag ui.data-system-split: the strip and the events split by owner (Ingest: data, System: machine) ---- */

/** Ingest's four tiles: Inbox, Queue, Lint, Version. Each tile opens an Ingest tab. */
export function ingestTiles(lc?: LifecycleLike, health?: HealthLike): Tile[] {
  const v = health?.values ?? {};
  const st = health?.statuses ?? {};
  const dirty = Object.values(lc?.working?.lanes ?? {}).reduce((a, b) => a + num(b), 0);
  const inbox = num(health?.inbox_count);
  return [
    {
      id: "inbox",
      label: "Inbox",
      value: health ? String(inbox) : "…",
      hint: health ? "files waiting to be sorted" : "",
      tone: health ? (inbox ? "warn" : "ok") : "",
      tab: "pipeline",
    },
    {
      id: "queue",
      label: "Queue",
      value: health ? String(num(v.queued)) : "…",
      hint: health ? `to digest · ${plural(num(v.partial_books), "partial book")}` : "",
      tone: "",
      tab: "pipeline",
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
      id: "version",
      label: "Version",
      value: lc?.version ? `kb-${lc.version}` : "…",
      hint: lc ? (dirty ? plural(dirty, "uncommitted file") : "working tree clean") : "",
      tone: lc ? (dirty ? "warn" : "ok") : "",
      tab: "history",
    },
  ];
}

/**
 * System's three tiles: Nightly, Deploy, Open work. Open work folds in the old Open work, Stale work, Merges and
 * Hygiene tiles: its tone is the worst of the four and its hint says what is behind it. Without owner operations
 * only Open work is left.
 */
export function systemTiles(ops?: OpsLike): Tile[] {
  const all: Tile[] = [
    { id: "nightly", label: "Nightly", ...nightlyTile(ops, ops?.nightly?.summary ?? ""), tab: "overview" },
    { id: "deploy", label: "Deploy", ...deployTile(ops), tab: "overview" },
    { id: "work", label: "Open work", ...openWorkTile(ops), tab: "overview" },
  ];
  return showOwnerOps(ops) ? all : all.filter((t) => t.id === "work");
}

const WORST: Tone[] = ["bad", "warn", "ok", ""];
const worst = (...ts: Tone[]): Tone => WORST.find((w) => ts.includes(w)) ?? "";

function openWorkTile(ops: OpsLike | undefined): Pick<Tile, "value" | "hint" | "tone"> {
  if (!ops) return { value: "…", hint: "", tone: "" };
  const threads = ops.threads ?? [];
  const attention = threads.filter((t) => t.status === "warn" || t.status === "bad").length;
  const hy = ops.hygiene;
  const hyTone: Tone = hy ? (num(hy.errors) ? "bad" : num(hy.warnings) ? "warn" : "ok") : "";
  const merges = mergesTile(ops);
  const stale = staleTile(ops);
  const hint = [
    attention ? `${attention} need attention` : "",
    showOwnerOps(ops) ? (merges.value === "idle" ? "merges idle" : `merge ${merges.value}`) : "",
    stale.value === "none" ? "nothing stale" : stale.value !== "…" ? `${stale.value} stale` : "",
    hy && (num(hy.errors) || num(hy.warnings)) ? `hygiene ${num(hy.errors)} / ${num(hy.warnings)}` : "",
  ];
  return {
    value: String(threads.length),
    hint: hint.filter(Boolean).join(" · "),
    tone: worst(attention ? "warn" : "ok", hyTone, showOwnerOps(ops) ? merges.tone : "", stale.tone),
  };
}

/** Ingest "Recent data changes": knowledge steps only, newest first. */
export const dataChanges = (lc?: LifecycleLike, limit = 8): Event[] => timeline(lc, undefined, 200).filter((e) => e.kind === "knowledge").slice(0, limit);
/** System Dev "Recent merges": tooling merges only, newest first. */
export const recentMerges = (lc?: LifecycleLike, limit = 8): Event[] => timeline(lc, undefined, 200).filter((e) => e.kind === "tooling").slice(0, limit);
/** System Overview "Recent runs": nightly jobs (with how the site deploy in each ended), newest first. */
export const recentRuns = (ops?: OpsLike, limit = 8): Event[] => timeline(undefined, ops, 200).slice(0, limit);
