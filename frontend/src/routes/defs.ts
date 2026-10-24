/**
 * Static route metadata. `legacy` is the real path of the server-rendered page (backend/src/kb/dashboard),
 * reached under /legacy/... until the screen is ported. Order = palette order; `nav` picks the three top-bar tabs (Home · Graph · System).
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
  /** In the top bar. Everything else is reached from a screen or the ⌘K palette. */
  nav?: boolean;
}

export const ROUTE_DEFS: readonly RouteDef[] = [
  { id: "home", path: "/", label: "Home", legacy: "/", blurb: "Sample subgraphs and knowledge nodes of the vault.", nav: true },
  { id: "graph", path: "/graph", label: "Graph", legacy: "/graph", blurb: "Explore, read and ask about the whole vault.", nav: true },
  { id: "system", path: "/system", label: "System", legacy: "/ops", blurb: "Status, open work, timeline, pipeline, history and health.", nav: true },
  { id: "pages", path: "/pages", label: "Pages", legacy: "/explore", blurb: "Read, search and trace notes (the Explore tab).", extraPaths: ["/pages/$slug"] },
  { id: "chat", path: "/chat", label: "Chat", legacy: "/chat", blurb: "Read-only research agent over the wiki." },
  { id: "scopes", path: "/scopes", label: "Scopes", legacy: "/scopes", blurb: "Named subsets of the vault for focused work." },
  { id: "pipeline", path: "/pipeline", label: "Pipeline", legacy: "/pipeline", blurb: "Ingest and digestion status of every raw file." },
  { id: "lifecycle", path: "/lifecycle", label: "Lifecycle", legacy: "/lifecycle", blurb: "Versions, history, snapshots and working state." },
];

export const legacyHref = (r: Pick<RouteDef, "legacy">): string =>
  `/legacy${r.legacy === "/" ? "" : r.legacy}`;
