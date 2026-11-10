import { flag, type FlagName } from "@/flags";

/**
 * Static route metadata. Order = palette order; `nav` picks the top-bar tabs (Home · Graph · System · Chat · Think · What is it?).
 * Which screen a route shows is NOT decided here: it follows the feature folders (see registry.ts).
 */
export interface RouteDef {
  id: string;
  path: string; // SPA path (relative to the /app basepath)
  label: string;
  blurb: string;
  /** More paths served by the same screen, e.g. /pages/$slug. */
  extraPaths?: readonly string[];
  /** In the top bar. Everything else is reached from a screen or the ⌘K palette. */
  nav?: boolean;
  /** A build flag (meta/flags.toml) that must be on in this env for the route to exist. Absent: always on. */
  flag?: FlagName;
  /** A runtime flag: the route is in the build, but only offered (palette) and shown (screen) while it is on. */
  runtimeFlag?: FlagName;
  /** Folded into another screen (a tab of it, and/or search params such as Home's `start`): where that screen exists the path redirects there and the palette skips it. */
  movedTo?: { id: string; tab?: string; search?: Record<string, string | number | boolean> };
}

const ALL_ROUTE_DEFS: readonly RouteDef[] = [
  { id: "home", path: "/", label: "Home", blurb: "Sample subgraphs and knowledge nodes of the vault.", nav: true },
  { id: "graph", path: "/graph", label: "Graph", blurb: "Explore, read and ask about the whole vault.", nav: true },
  { id: "system", path: "/system", label: "System", blurb: "Status, open work, timeline, pipeline, history and health.", nav: true },
  { id: "pages", path: "/pages", label: "Pages", blurb: "Read, search and trace notes (the Explore tab).", extraPaths: ["/pages/$slug"] },
  { id: "chat", path: "/chat", label: "Chat", blurb: "Read-only research agent over the wiki.", extraPaths: ["/chat/$id"], nav: true },
  { id: "relations", path: "/relations", label: "Relations", blurb: "Review the LLM relation proposals by confidence.", movedTo: { id: "graph", search: { tool: "relations" } } },
  { id: "scopes", path: "/scopes", label: "Scopes", blurb: "Named subsets of the vault for focused work.", movedTo: { id: "graph", search: { tool: "scopes" } } },
  { id: "pipeline", path: "/pipeline", label: "Pipeline", blurb: "Ingest and digestion status of every raw file.", movedTo: { id: "system", search: { tab: "pipeline" } } },
  { id: "lifecycle", path: "/lifecycle", label: "Lifecycle", blurb: "Versions, history, snapshots and working state.", flag: "screen.lifecycle", movedTo: { id: "system", search: { tab: "history" } } },
  { id: "share", path: "/share", label: "Share", blurb: "Public snapshots of the private site.", flag: "screen.share", nav: true },
  { id: "think", path: "/think", label: "Think", blurb: "Your own slow notes: edit, and capture quick thoughts.", flag: "screen.think", nav: true },
  { id: "about", path: "/what-is-it", label: "What is it?", blurb: "How a file becomes a page in this map: raw, source, concept, and reading depth.", nav: true },
  { id: "start", path: "/start", label: "Start", blurb: "How to add and edit knowledge, and how to build a feature.", flag: "screen.start", movedTo: { id: "home", search: { start: true } } },
  { id: "covector", path: "/covector", label: "Covector", blurb: "Interactive picture of a covector acting on a vector.", runtimeFlag: "research-tools" },
  { id: "proposals", path: "/proposals", label: "Proposals", blurb: "Review agent changes to pages, hunk by hunk, and apply what you accept.", extraPaths: ["/proposals/$id"], runtimeFlag: "ui.proposals" },
  { id: "ingest", path: "/ingest", label: "Ingest", blurb: "Drop a paper or paste a link; the new pages arrive as a proposal to review.", runtimeFlag: "ui.ingest", nav: true },
  // A route whose flag is off in this env is dropped here (screen.share: private site only).
];

export const routeDefsNow = (): RouteDef[] => ALL_ROUTE_DEFS.filter((d) => !d.flag || flag(d.flag));
export const ROUTE_DEFS: readonly RouteDef[] = routeDefsNow();

/** Whether a route is offered now: its runtime flag, if any, is on (it can arrive after start, see flags/load.ts). */
export const routeOffered = (d: Pick<RouteDef, "runtimeFlag">): boolean => !d.runtimeFlag || flag(d.runtimeFlag);
