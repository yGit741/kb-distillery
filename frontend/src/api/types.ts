/**
 * Hand-written response types. Lifecycle mirrors build_lifecycle_snapshot() in
 * meta/dashboard/lifecycle_data.py. Phase 2 replaces this file with generated OpenAPI types.
 */

export type CommitKind = "kb" | "infra" | "pr-merge" | "sync-merge" | "unknown";

export interface TimelineRow {
  sha: string;
  short: string;
  date: string; // ISO 8601
  subject: string;
  kind: CommitKind;
  type: string | null;
  scope: string | null;
  summary: string | null;
  kb_version: string | null;
  pr: number | null;
  retro: boolean;
  parents: string[];
  op: string | null;
  target: string | null;
  reverts: string | null;
  reverted_by: string | null;
  snapshot_tag: string | null;
}

export interface SnapshotTag {
  tag: string;
  date: string;
  label: string;
}

export interface InfraBranch {
  name: string;
  date: string;
  last: string;
  ahead: number;
  behind: number;
}

export interface StaleWorktree {
  branch: string;
  path: string;
  merged: boolean;
  ahead: number | string;
  dirty: number;
}

export interface WorkingState {
  lanes: { knowledge: number; tooling: number; other?: number } & Record<string, number>;
  knowledge: string[];
  tooling: string[];
  think_dirty: number;
  sessions: {
    ingest: { sha1?: string; raw?: string }[];
    distill: { think?: string; mode?: string }[];
    researcher: string[];
    ops: { op: string; target: string; summary: string; started: string } | null;
  };
  unpushed: number | null;
}

export interface NightlyState {
  plist_installed: boolean;
  log: string;
  installed?: boolean;
  loaded?: boolean;
  last_run?: string | null;
  summary?: string;
  hint?: string | null;
}

export interface LifecycleSnapshot {
  generated_at: string;
  branch: string;
  head: string;
  version: string | null;
  next_version: string;
  github: string | null;
  schema: { version: string; applied: string[]; pending: string[] };
  policy: { hooks_installed: boolean; mode: string; strict: boolean };
  timeline: TimelineRow[];
  snapshots: SnapshotTag[];
  stats: { kb_steps: number; pr_merges: number; ops_30d: Record<string, number>; undone: number };
  // Absent from a snapshot captured for the shared site (they are not fixed by a commit).
  working?: WorkingState;
  infra_branches?: InfraBranch[];
  nightly?: NightlyState;
  stale_worktrees?: StaleWorktree[];
}

/** /api/share/status */
export interface ShareChip {
  label: string;
  cls: string;
  title: string;
  href: string;
}
export interface ShareStatus {
  status: Record<string, unknown> | null;
  chip: ShareChip | null;
}

export type { GraphNode } from "./model";
