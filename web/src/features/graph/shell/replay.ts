import type { ToolStep } from "@/features/chat/sse";

/**
 * Replaying how an answer was built (flag `spark-chat`): the agent's saved tool steps carry the pages a search
 * returned (`seen`) and the pages it opened (`read`). Everything here is pure; ./replayStore holds the state on screen.
 */
export type ReplayRole = "seen" | "read" | "cited";

/** The most "one link away, not read" pages shown at the last step. */
export const MAX_CANDIDATES = 5;

/** The steps that say something about pages: only those can be scrubbed to. */
export function replaySteps(trace: readonly ToolStep[] | undefined): ToolStep[] {
  return (trace ?? []).filter((t) => (t.seen?.length ?? 0) + (t.read?.length ?? 0) > 0);
}

export const hasReplay = (trace: readonly ToolStep[] | undefined): boolean => replaySteps(trace).length > 0;

export interface ReplayView {
  /** what each page of the trail is so far: read beats seen; a page the answer links is cited */
  roles: Map<string, ReplayRole>;
  /** the pages the current step touched */
  current: Set<string>;
  /** consecutive read pages, in the order they were opened */
  path: [string, string][];
  /** the last step: the marks can be placed */
  atEnd: boolean;
}

/** The trail up to and including step `at` of `steps` (from `replaySteps`). A cited page shows from the moment it is in the trail; all of them at the last step. */
export function viewAt(steps: readonly ToolStep[], at: number, cited: readonly string[]): ReplayView {
  const last = steps.length - 1;
  const i = Math.max(0, Math.min(at, last));
  const roles = new Map<string, ReplayRole>();
  const order: string[] = [];
  for (const step of steps.slice(0, i + 1)) {
    for (const s of step.seen ?? []) if (!roles.has(s)) roles.set(s, "seen");
    for (const r of step.read ?? []) {
      if (roles.get(r) !== "read") roles.set(r, "read");
      if (!order.includes(r)) order.push(r);
    }
  }
  const atEnd = i >= last;
  for (const c of cited) if (atEnd || roles.has(c)) roles.set(c, "cited");
  const now = steps[i];
  const current = new Set([...(now?.seen ?? []), ...(now?.read ?? [])]);
  const path: [string, string][] = order.slice(1).map((b, n) => [order[n]!, b]);
  return { roles, current, path, atEnd };
}

/**
 * Pages one link away from a page the agent read, not read themselves: ranked by how many read pages link to them
 * (then by slug, so the same trail always shows the same five). `neighbors` is the graph's adjacency.
 */
export function candidatesOf(
  read: Iterable<string>,
  neighbors: ReadonlyMap<string, readonly string[]>,
  skip: ReadonlySet<string>,
  visible: ReadonlySet<string>,
  max = MAX_CANDIDATES,
): string[] {
  const readSet = new Set(read);
  const count = new Map<string, number>();
  for (const r of readSet) {
    for (const n of new Set(neighbors.get(r) ?? [])) {
      if (readSet.has(n) || skip.has(n) || !visible.has(n)) continue;
      count.set(n, (count.get(n) ?? 0) + 1);
    }
  }
  return [...count.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, max).map(([id]) => id);
}

/** The context the next message carries for the marks: pages the agent missed, citations to re-check. */
export function marksContext(missed: readonly string[], bad: readonly string[], label: (slug: string) => string): string {
  const lines: string[] = [];
  if (missed.length) lines.push(`Also read: ${missed.map(label).join(", ")}`);
  if (bad.length) lines.push(`Re-check these citations: ${bad.map(label).join(", ")}`);
  return lines.join("\n");
}
