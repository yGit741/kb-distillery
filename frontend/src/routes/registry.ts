/**
 * The route registry: ONE list drives the top nav, the ⌘K palette and the router.
 * `legacy` is the real path of the server-rendered page (meta/dashboard/serve.py), reached under
 * /legacy/... until the screen is ported. Order = meta/dashboard/shell.py TABS (Explore -> Pages).
 */
export interface RouteDef {
  id: string;
  path: string; // SPA path
  label: string;
  legacy: string; // legacy path on the stdlib dashboard
  ported: boolean;
  blurb: string;
}

export const ROUTES: readonly RouteDef[] = [
  { id: "home", path: "/", label: "Home", legacy: "/", ported: false, blurb: "Health, start page and recent activity." },
  { id: "graph", path: "/graph", label: "Graph", legacy: "/graph", ported: false, blurb: "Force-directed explorer of the whole vault." },
  { id: "pages", path: "/pages", label: "Pages", legacy: "/explore", ported: false, blurb: "Read, search and trace notes (the Explore tab)." },
  { id: "chat", path: "/chat", label: "Chat", legacy: "/chat", ported: false, blurb: "Read-only research agent over the wiki." },
  { id: "scopes", path: "/scopes", label: "Scopes", legacy: "/scopes", ported: false, blurb: "Named subsets of the vault for focused work." },
  { id: "pipeline", path: "/pipeline", label: "Pipeline", legacy: "/pipeline", ported: false, blurb: "Ingest and digestion status of every raw file." },
  { id: "ops", path: "/ops", label: "Ops", legacy: "/ops", ported: false, blurb: "Nightly sync, hygiene checks and report." },
  { id: "lifecycle", path: "/lifecycle", label: "Lifecycle", legacy: "/lifecycle", ported: true, blurb: "Versions, history, snapshots and working state." },
];

export const legacyHref = (r: RouteDef): string => `/legacy${r.legacy === "/" ? "" : r.legacy}`;

export const routeById = (id: string): RouteDef | undefined => ROUTES.find((r) => r.id === id);
