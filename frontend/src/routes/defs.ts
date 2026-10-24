/**
 * Static route metadata. `legacy` is the real path of the server-rendered page (backend/src/kb/dashboard),
 * reached under /legacy/... until the screen is ported. Order = the dashboard tabs (Explore -> Pages).
 * Which routes are ported is NOT decided here: it follows the feature folders (see registry.ts).
 */
export interface RouteDef {
  id: string;
  path: string; // SPA path (relative to the /app basepath)
  label: string;
  legacy: string; // legacy path on the stdlib dashboard
  blurb: string;
  /** More paths served by the same screen, e.g. /pages/$slug. */
  extraPaths?: readonly string[];
}

export const ROUTE_DEFS: readonly RouteDef[] = [
  { id: "home", path: "/", label: "Home", legacy: "/", blurb: "Small live graphs that sample the vault; each opens in the full graph." },
  { id: "graph", path: "/graph", label: "Graph", legacy: "/graph", blurb: "Force-directed explorer of the whole vault." },
  { id: "pages", path: "/pages", label: "Pages", legacy: "/explore", blurb: "Read, search and trace notes (the Explore tab).", extraPaths: ["/pages/$slug"] },
  { id: "chat", path: "/chat", label: "Chat", legacy: "/chat", blurb: "Read-only research agent over the wiki." },
  { id: "scopes", path: "/scopes", label: "Scopes", legacy: "/scopes", blurb: "Named subsets of the vault for focused work." },
  { id: "pipeline", path: "/pipeline", label: "Pipeline", legacy: "/pipeline", blurb: "Ingest and digestion status of every raw file." },
  { id: "ops", path: "/ops", label: "Ops", legacy: "/ops", blurb: "Nightly sync, hygiene checks and report." },
  { id: "lifecycle", path: "/lifecycle", label: "Lifecycle", legacy: "/lifecycle", blurb: "Versions, history, snapshots and working state." },
];

export const legacyHref = (r: Pick<RouteDef, "legacy">): string =>
  `/legacy${r.legacy === "/" ? "" : r.legacy}`;
