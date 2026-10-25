/**
 * Typed URL search params per screen. URL-worthy state (query, filters, the open item) lives here so a
 * link or a reload restores the view; cross-screen client state lives in src/lib/store.ts.
 * Add a field here (never in the registry) when a screen needs one; values are strings in the URL.
 */
type Raw = Record<string, unknown>;

/** TanStack parses `?q=2024` to a number; read everything back as a non-empty string. */
const str = (v: unknown): string | undefined => {
  if (typeof v === "string") return v || undefined;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  return undefined;
};
const oneOf = <T extends string>(v: unknown, allowed: readonly T[]): T | undefined => {
  const s = str(v);
  return s && (allowed as readonly string[]).includes(s) ? (s as T) : undefined;
};

export type ChatSearch = { session?: string; scope?: string; q?: string };
export type PagesSearch = { q?: string; layer?: string; type?: string; status?: string; area?: string; embed?: string; a?: string; b?: string };
export type GraphSearch = { select?: string; focus?: string; scope?: string; layer?: string; raw?: "1"; search?: string; pages?: string; from?: "home"; view?: string };
export type ScopesSearch = { scope?: string; draft?: string };
export type PipelineSearch = { format?: string; q?: string; depth?: string; collection?: string; status?: string; view?: string; group?: string; backlog?: "queued"; item?: string };
export type SystemTab = "overview" | "pipeline" | "history" | "health";
export const SYSTEM_TABS: readonly SystemTab[] = ["overview", "pipeline", "history", "health"];
/** System hosts the pipeline view, so it keeps the pipeline's params (its own `view` included) next to `tab`. */
export type SystemSearch = PipelineSearch & { tab?: SystemTab };
export type NoSearch = Record<string, never>;

export interface SearchById {
  home: NoSearch;
  graph: GraphSearch;
  pages: PagesSearch;
  chat: ChatSearch;
  scopes: ScopesSearch;
  pipeline: PipelineSearch;
  system: SystemSearch;
  lifecycle: NoSearch;
}

const clean = <T extends object>(o: T): T =>
  Object.fromEntries(Object.entries(o).filter(([, v]) => v !== undefined)) as T;

const pipelineSearch = (r: Raw): PipelineSearch =>
  clean({ format: str(r.format), q: str(r.q), depth: str(r.depth), collection: str(r.collection), status: str(r.status), view: str(r.view), group: str(r.group), backlog: oneOf(r.backlog, ["queued"] as const), item: str(r.item) });

export const SEARCH: { [K in keyof SearchById]: (raw: Raw) => SearchById[K] } = {
  home: () => ({}),
  lifecycle: () => ({}),
  chat: (r) => clean({ session: str(r.session), scope: str(r.scope), q: str(r.q) }),
  pages: (r) =>
    clean({ q: str(r.q), layer: str(r.layer), type: str(r.type), status: str(r.status), area: str(r.area), embed: str(r.embed), a: str(r.a), b: str(r.b) }),
  graph: (r) =>
    clean({
      select: str(r.select),
      focus: str(r.focus),
      scope: str(r.scope),
      layer: str(r.layer),
      search: str(r.search),
      pages: str(r.pages),
      raw: oneOf(r.raw, ["1"] as const),
      from: oneOf(r.from, ["home"] as const),
      view: str(r.view),
    }),
  scopes: (r) => clean({ scope: str(r.scope), draft: str(r.draft) }),
  system: (r) => clean({ ...pipelineSearch(r), tab: oneOf(r.tab, SYSTEM_TABS) }),
  pipeline: (r) => pipelineSearch(r),
};
