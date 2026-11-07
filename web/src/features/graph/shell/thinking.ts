import type { ToolStep } from "@/features/chat/sse";
import { citedSlugs } from "./cites";

/**
 * "Show my thinking" (flag `show-thinking`): what the agent looked at for one answer, read from its saved tool steps.
 * A step carries `round` (calls the model sent together), `kind`, `query`, `url`, `domains`, and the pages a search
 * returned (`seen`) or the step opened (`read`). Old messages have no `round`: each step is then its own round.
 * Everything here is pure; ./thinkingStore holds what the graph shows.
 */

export type Kind = "shortlist" | "meaning" | "graph" | "raw" | "alias" | "keyword" | "files" | "open" | "attachment" | "web-search" | "web-source" | "other";

export const KIND_LABEL: Record<Kind, string> = {
  shortlist: "shortlist",
  meaning: "meaning",
  graph: "graph query",
  raw: "raw source",
  alias: "alias",
  keyword: "keyword",
  files: "files",
  open: "open",
  attachment: "attachment",
  "web-search": "web search",
  "web-source": "web source",
  other: "",
};

const KINDS = new Set(Object.keys(KIND_LABEL));

/** The step's kind: the backend's own word, else a guess from the tool name (old messages). */
export function kindOf(t: ToolStep): Kind {
  if (t.kind && KINDS.has(t.kind)) return t.kind as Kind;
  const name = t.name.toLowerCase();
  if (name === "websearch") return "web-search";
  if (name === "webfetch") return "web-source";
  if (name === "read") return "open";
  if (name === "grep") return "keyword";
  if (name === "glob") return "files";
  return "other";
}

export const isWeb = (k: Kind) => k === "web-search" || k === "web-source";

export interface Round {
  /** 1-based, in the order the rounds started */
  n: number;
  steps: ToolStep[];
}

/** The steps grouped by the round they were sent in; a step without a round is a round of its own. */
export function roundsOf(trace: readonly ToolStep[] | undefined): Round[] {
  const out: ToolStep[][] = [];
  const byRound = new Map<number, ToolStep[]>();
  for (const t of trace ?? []) {
    if (t.round == null) {
      out.push([t]);
      continue;
    }
    const list = byRound.get(t.round);
    if (list) list.push(t);
    else {
      const fresh = [t];
      byRound.set(t.round, fresh);
      out.push(fresh);
    }
  }
  return out.map((steps, i) => ({ n: i + 1, steps }));
}

export function hostOf(url: string | undefined): string {
  if (!url) return "";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export interface WebSource {
  /** `web:<url>`, never a page slug */
  id: string;
  url: string;
  host: string;
  /** the wiki pages its round was about (opened or cited in the same round, else the round before): an inference */
  about: string[];
}

export interface Thinking {
  rounds: Round[];
  /** pages a search returned */
  found: Set<string>;
  /** pages the agent opened */
  opened: Set<string>;
  /** the answer's page links, numbered 1.. in order of first appearance */
  citeNo: Map<string, number>;
  webSearches: number;
  webSources: WebSource[];
  /** found, neither opened nor cited: the reader may mark one as missed */
  missable: string[];
  /** opened, not named in the answer */
  openedNotCited: string[];
}

export function thinkingOf(trace: readonly ToolStep[] | undefined, content: string): Thinking {
  const rounds = roundsOf(trace);
  const found = new Set<string>();
  const opened = new Set<string>();
  let webSearches = 0;
  const webSources: WebSource[] = [];
  const cited = citedSlugs(content);
  const citeNo = new Map(cited.map((s, i) => [s, i + 1] as const));
  const pagesOf = (r: Round | undefined) => {
    if (!r) return [];
    const ids = new Set<string>();
    for (const t of r.steps) {
      if (isWeb(kindOf(t))) continue;
      for (const s of t.read ?? []) ids.add(s);
      for (const s of t.seen ?? []) if (citeNo.has(s)) ids.add(s);
    }
    return [...ids];
  };
  rounds.forEach((r, i) => {
    for (const t of r.steps) {
      const k = kindOf(t);
      if (k === "web-search") webSearches++;
      if (k === "web-source" && t.url && !webSources.some((w) => w.url === t.url) && t.status !== "running" && !t.error) {
        const here = pagesOf(r);
        webSources.push({ id: `web:${t.url}`, url: t.url, host: hostOf(t.url), about: here.length ? here : pagesOf(rounds[i - 1]) });
      }
      if (isWeb(k)) continue;
      for (const s of t.seen ?? []) found.add(s);
      for (const s of t.read ?? []) opened.add(s);
    }
  });
  const missable = [...found].filter((s) => !opened.has(s) && !citeNo.has(s));
  const openedNotCited = [...opened].filter((s) => !citeNo.has(s));
  return { rounds, found, opened, citeNo, webSearches, webSources, missable, openedNotCited };
}

/** "5 opened · 11 found · 1 web search" */
export function summaryOf(t: Thinking): string {
  const parts = [`${t.opened.size} opened`, `${t.found.size} found`];
  if (t.webSearches) parts.push(`${t.webSearches} web search${t.webSearches === 1 ? "" : "es"}`);
  return parts.join(" · ");
}

/** The one live word while the answer streams. */
export function liveStatus(trace: readonly ToolStep[] | undefined, content: string): "looking" | "deciding" | "writing the answer" {
  if (content) return "writing the answer";
  return (trace ?? []).some((t) => t.status === "running") ? "looking" : "deciding";
}

/** What a finished call came back with ("found 8", "opened", "5 results"); null while it runs. */
export function resultOf(t: ToolStep): string | null {
  if (t.status === "running") return null;
  if (t.error || t.status === "error") return "failed";
  const k = kindOf(t);
  if (k === "web-search") return t.domains?.length ? `${t.domains.length} results` : "searched";
  if (k === "web-source") return "opened";
  if (t.seen?.length) return `found ${t.seen.length}`;
  if (t.read?.length) return "opened";
  return "done";
}

/** The role of every page that is part of the answer: cited beats opened beats found. */
export type Role = "found" | "opened" | "cited";

export function rolesOf(t: Thinking, done: boolean): Map<string, Role> {
  const roles = new Map<string, Role>();
  for (const s of t.found) roles.set(s, "found");
  for (const s of t.opened) roles.set(s, "opened");
  if (done) for (const s of t.citeNo.keys()) roles.set(s, "cited");
  return roles;
}

export const linkKey = (a: string, b: string) => (a < b ? `${a}|${b}` : `${b}|${a}`);

/**
 * Sources that pop onto the graph: a page of the source layer that is part of the answer (found or opened) but not
 * drawn in the calm graph. Each brings only its links to pages that are part of the answer (`links`, by linkKey);
 * its other links stay hidden. A raw read without a source slug brings nothing (it is a row in the list only).
 */
export function popSources(
  roles: ReadonlyMap<string, Role>,
  layerOf: (id: string) => string | undefined,
  drawn: ReadonlySet<string>,
  neighbors: ReadonlyMap<string, readonly string[]>,
): { pop: string[]; links: Set<string> } {
  const pop = [...roles.keys()].filter((id) => !drawn.has(id) && layerOf(id) === "source").sort();
  const links = new Set<string>();
  for (const id of pop) for (const n of neighbors.get(id) ?? []) if (roles.has(n) && n !== id) links.add(linkKey(id, n));
  return { pop, links };
}
