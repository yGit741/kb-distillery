import type { TimelineRow } from "@/api";

/** Snapshot names: lowercase letters, digits and inner hyphens; `kb` is the main site. */
export const NAME_RE = /^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/;

export const validName = (n: string): boolean => NAME_RE.test(n) && n !== "kb";

export interface VersionOption {
  tag: string; // kb-x.y.z
  date: string; // YYYY-MM-DD
  subject: string;
}

/** The picker: every knowledge step on main (newest first), from the lifecycle snapshot's timeline. */
export function versionOptions(timeline: readonly TimelineRow[]): VersionOption[] {
  return timeline
    .filter((r) => r.kind === "kb" && r.kb_version)
    .map((r) => ({
      tag: `kb-${r.kb_version}`,
      date: r.date.slice(0, 10),
      subject: (r.summary ?? r.subject).slice(0, 60),
    }));
}

export function snapshotCommand(name: string, version: string, replace: boolean): string {
  const n = name.trim().toLowerCase();
  return `pixi run share -- snapshot ${validName(n) ? n : "<name>"} ${version || "<version>"}${replace ? " --replace" : ""}`;
}

export const historyCommand = (name: string): string => `pixi run share -- history ${name}`;
export const rollbackCommand = (worker: string): string => `pixi run share -- rollback --worker ${worker}`;
export const PRUNE_APPLY = "pixi run share -- prune --apply";
export const SETUP_COMMAND = "pbpaste | npx wrangler@4.151.3 secret put CF_API_TOKEN --name kb && pbcopy < /dev/null";
