import { DEPTHS } from "@/api/model";
import type { GraphSchema, TypeInfo } from "../schema";
import type { GLink, GNode, GraphModel } from "../types";
import type { ArtifactGraph, ArtifactNode, ArtifactView } from "./types";

/**
 * Pure: the artifact layer turned into the graph's own model, so the same canvas, legend, hover and selection draw it.
 * A template view draws one level of the containment tree at a time (drill-down): the children of the artifact it is
 * drilled into, plus the outside artifacts they link to, each link lifted to the drawn ancestor of its ends. The
 * Evidence view puts the concept pages next to the artifacts their cited facts are about.
 */

export const EVIDENCE = "evidence";

export interface ArtifactIndex {
  graph: ArtifactGraph;
  byId: ReadonlyMap<string, ArtifactNode>;
  children: ReadonlyMap<string | null, readonly string[]>;
  /** the parent that exists in the graph, else null (a root) */
  parent: (id: string) => string | null;
  /** fact id -> the artifacts it is about */
  factNodes: ReadonlyMap<string, ReadonlySet<string>>;
  /** page slug -> the artifacts its cited facts are about */
  pageNodes: ReadonlyMap<string, ReadonlySet<string>>;
  /** artifact -> the pages citing it or anything inside it */
  citedBy: ReadonlyMap<string, ReadonlySet<string>>;
  views: readonly ArtifactView[];
}

export interface Crumb {
  id: string | null;
  name: string;
}

export interface ArtifactScene {
  model: GraphModel;
  schema: GraphSchema;
  /** the types drawn */
  types: ReadonlySet<string>;
  /** the artifact drilled into after any automatic step down (null: the top) */
  focus: string | null;
  crumbs: Crumb[];
  /** children of the focus left out because no link of the view reaches them */
  hidden: number;
  colorBy: "area" | "type";
}

const add = <K, V>(m: Map<K, Set<V>>, k: K, v: V) => {
  const s = m.get(k);
  if (s) s.add(v);
  else m.set(k, new Set([v]));
};

export function indexArtifacts(graph: ArtifactGraph): ArtifactIndex {
  const byId = new Map(graph.nodes.map((n) => [n.id, n] as const));
  const parent = (id: string): string | null => {
    const p = byId.get(id)?.parent;
    return p && p !== id && byId.has(p) ? p : null;
  };
  const children = new Map<string | null, string[]>();
  for (const n of graph.nodes) {
    const p = parent(n.id);
    const list = children.get(p);
    if (list) list.push(n.id);
    else children.set(p, [n.id]);
  }
  const factNodes = new Map<string, Set<string>>();
  for (const card of Object.values(graph.cards ?? {})) for (const [fid, ids] of Object.entries(card.facts ?? {})) for (const id of ids) if (byId.has(id)) add(factNodes, fid, id);
  const pageNodes = new Map<string, Set<string>>();
  const citedBy = new Map<string, Set<string>>();
  for (const [slug, fids] of Object.entries(graph.cites ?? {})) {
    for (const fid of fids)
      for (const id of factNodes.get(fid) ?? []) {
        add(pageNodes, slug, id);
        for (let a: string | null = id, hops = 0; a && hops < 64; a = parent(a), hops++) add(citedBy, a, slug);
      }
  }
  const types = new Set(graph.nodes.map((n) => n.type));
  const views = (graph.views ?? []).filter((v) => v.types?.some((t) => types.has(t)));
  return { graph, byId, children, parent, factNodes, pageNodes, citedBy, views };
}

/** The ancestors of `id`, top first, `id` last (a cycle in the data cannot hang it). */
export function ancestry(ix: ArtifactIndex, id: string | null): string[] {
  const out: string[] = [];
  for (let a = id, hops = 0; a && hops < 64; a = ix.parent(a), hops++) out.unshift(a);
  return out;
}

const shortClass = (id: string) => id.replace(/^class:/, "").split("::").pop() || id;

/** What a node is coloured by in a view: its repository, its pipeline stage, or nothing (the type colours it). */
function areaOf(n: ArtifactNode, by: string | null | undefined): string[] {
  if (by === "repo") return n.repo ? [n.repo] : [];
  if (by === "stage") {
    if (typeof n.stage === "string") return [shortClass(n.stage)];
    if (n.type === "Class") return [shortClass(n.id)];
  }
  return [];
}

/** The code location of an artifact at its source host (its repository's `web` address, pinned commit), or null. */
export function permalink(graph: ArtifactGraph, n: ArtifactNode | undefined): string | null {
  if (!n) return null;
  if (typeof n.url === "string" && n.url) return n.url;
  const web = n.repo ? graph.repos?.[n.repo]?.web : undefined;
  if (!web || !n.path) return null;
  return `${web}${n.path.split("/").map(encodeURIComponent).join("/")}${typeof n.line === "number" ? `#L${n.line}` : ""}`;
}

/** Where an artifact sits, for a hover line: `repo/path:line`. */
export function placeOf(n: ArtifactNode): string {
  const at = n.path ? `${n.repo ? `${n.repo}/` : ""}${n.path}${typeof n.line === "number" ? `:${n.line}` : ""}` : (n.repo ?? "");
  return at;
}

function gnode(ix: ArtifactIndex, n: ArtifactNode, area: string[], degree: { in: number; out: number }, outside: boolean): GNode {
  const kids = ix.children.get(n.id)?.length ?? 0;
  const cited = ix.citedBy.get(n.id)?.size ?? 0;
  const lines = [
    [n.type, placeOf(n)].filter(Boolean).join(" · "),
    [kids ? `${kids} inside` : "", typeof n.commits === "number" ? `${n.commits} commit${n.commits === 1 ? "" : "s"}` : "", cited ? `cited by ${cited} page${cited === 1 ? "" : "s"}` : "", outside ? "outside this level" : ""].filter(Boolean).join(" · "),
    typeof n.doc === "string" ? n.doc : "",
  ].filter(Boolean);
  const title = n.name || n.id;
  return {
    id: n.id,
    slug: n.id,
    title,
    label: title,
    type: n.type,
    layer: "artifact",
    areas: area,
    added: "",
    changed: typeof n.last_change === "string" ? n.last_change : "",
    depth: "",
    maturity: "",
    inDegree: degree.in,
    outDegree: degree.out,
    path: n.path ?? "",
    preview: lines.join("\n"),
    properties: { ...(kids ? { children: String(kids) } : {}), ...(outside ? { outside: "1" } : {}), ...(n.repo ? { repo: n.repo } : {}) },
  };
}

function schemaFor(types: readonly string[], extra: readonly TypeInfo[] = []): GraphSchema {
  const own = types.map((id): TypeInfo => ({ id, label: id, layer: "artifact" }));
  return { types: [...extra, ...own], defaultVisible: [...extra.map((t) => t.id), ...types], depths: DEPTHS };
}

/** Types in the template's order (graph.json `types`), then any other. */
function ordered(ix: ArtifactIndex, present: ReadonlySet<string>): string[] {
  const order = Object.keys(ix.graph.types ?? {});
  return [...present].sort((a, b) => (order.indexOf(a) + 1 || 999) - (order.indexOf(b) + 1 || 999) || a.localeCompare(b));
}

/**
 * One level of a template view. `focus` null is the top (the repositories); a top with a single repository steps into
 * it at once. Links of the view's relations are lifted to the drawn ancestors of their ends and merged; a link inside
 * one drawn node disappears into it.
 */
export function viewScene(ix: ArtifactIndex, view: ArtifactView, focus: string | null): ArtifactScene {
  const kinds = new Set(view.relations ?? []);
  const links = ix.graph.links.filter((l) => (!kinds.size || kinds.has(l.kind)) && ix.byId.has(l.source) && ix.byId.has(l.target));
  const flat = view.nest === "none";
  let at = flat ? null : focus && ix.byId.has(focus) ? focus : null;

  const level = (f: string | null) => {
    const chain = new Set<string | null>([null, ...ancestry(ix, f)]);
    const lift = (x: string): string | null => {
      if (flat) return x;
      if (chain.has(x)) return null;
      let y = x;
      for (let hops = 0; hops < 64; hops++) {
        const p = ix.parent(y);
        if (chain.has(p)) return y;
        y = p!;
      }
      return null;
    };
    const inside = (x: string) => flat || f === null || ancestry(ix, ix.parent(x)).includes(f);
    const merged = new Map<string, { source: string; target: string; kind: string; weight: number }>();
    for (const l of links) {
      if (f !== null && !inside(l.source) && !inside(l.target)) continue;
      let a = lift(l.source);
      let b = lift(l.target);
      if (!a || !b || a === b) continue;
      if (ix.graph.relations?.[l.kind]?.directed === false && b < a) [a, b] = [b, a];
      const key = `${a}|${b}|${l.kind}`;
      const m = merged.get(key);
      if (m) m.weight += l.weight ?? 1;
      else merged.set(key, { source: a, target: b, kind: l.kind, weight: l.weight ?? 1 });
    }
    return merged;
  };

  let merged = level(at);
  if (!flat && at === null) {
    // a top with one repository (or one with nothing drawn between several) opens inside the only one with content
    const tops = new Set([...merged.values()].flatMap((m) => [m.source, m.target]));
    const roots = ix.children.get(null) ?? [];
    const only = tops.size === 1 ? [...tops][0]! : roots.length === 1 ? roots[0]! : null;
    if (only && ix.children.get(only)?.length) {
      at = only;
      merged = level(at);
    }
  }

  const deg = new Map<string, { in: number; out: number }>();
  for (const m of merged.values()) {
    deg.set(m.source, { in: deg.get(m.source)?.in ?? 0, out: (deg.get(m.source)?.out ?? 0) + 1 });
    deg.set(m.target, { in: (deg.get(m.target)?.in ?? 0) + 1, out: deg.get(m.target)?.out ?? 0 });
  }
  const own = new Set(flat ? [] : (ix.children.get(at) ?? []));
  const nodes = [...deg.keys()].map((id) => gnode(ix, ix.byId.get(id)!, areaOf(ix.byId.get(id)!, view.color_by), deg.get(id)!, !flat && at !== null && !own.has(id)));
  const glinks: GLink[] = [...merged.values()].map((m) => ({ source: m.source, target: m.target, kind: "related", rel: m.kind, count: m.weight }));
  const present = new Set(nodes.map((n) => n.type));
  const types = ordered(ix, present);
  const drawn = new Set(deg.keys());
  return {
    model: { nodes, links: glinks, conceptLinks: [], kbs: [] },
    schema: schemaFor(types),
    types: new Set(types),
    focus: at,
    crumbs: [{ id: null, name: "All" }, ...ancestry(ix, at).map((id) => ({ id, name: ix.byId.get(id)?.name || id }))],
    hidden: [...own].filter((id) => !drawn.has(id)).length,
    colorBy: view.color_by === "repo" || view.color_by === "stage" ? "area" : "type",
  };
}

/** The file an artifact is in (itself when it is one, or has no file above it): what the Evidence view draws. */
function fileOf(ix: ArtifactIndex, id: string): string {
  for (let a: string | null = id, hops = 0; a && hops < 64; a = ix.parent(a), hops++) if (ix.byId.get(a)?.type === "File") return a;
  return id;
}

/**
 * The Evidence view: every concept page that cites a fact, the files those facts are about, a `cites` link from page
 * to file, and the page links among those pages. The Concepts view never draws these links; this is where they are.
 */
export function evidenceScene(ix: ArtifactIndex, concepts: GraphModel, conceptSchema: GraphSchema): ArtifactScene {
  const pages = new Map(concepts.nodes.map((n) => [n.slug ?? n.id, n] as const));
  const cites = new Map<string, { source: string; target: string; weight: number }>();
  const shownPages = new Set<string>();
  for (const [slug, ids] of ix.pageNodes) {
    const page = pages.get(slug);
    if (!page) continue;
    for (const id of ids) {
      const f = fileOf(ix, id);
      const key = `${page.id}|${f}`;
      const c = cites.get(key);
      if (c) c.weight++;
      else cites.set(key, { source: page.id, target: f, weight: 1 });
      shownPages.add(page.id);
    }
  }
  const deg = new Map<string, { in: number; out: number }>();
  const bump = (id: string, k: "in" | "out") => deg.set(id, { in: (deg.get(id)?.in ?? 0) + (k === "in" ? 1 : 0), out: (deg.get(id)?.out ?? 0) + (k === "out" ? 1 : 0) });
  const glinks: GLink[] = [];
  for (const c of cites.values()) {
    glinks.push({ source: c.source, target: c.target, kind: "related", rel: "cites", count: c.weight });
    bump(c.source, "out");
    bump(c.target, "in");
  }
  for (const l of concepts.links) if (shownPages.has(l.source) && shownPages.has(l.target)) glinks.push({ ...l });
  const files = [...new Set([...cites.values()].map((c) => c.target))];
  const nodes: GNode[] = [
    ...concepts.nodes.filter((n) => shownPages.has(n.id)).map((n) => ({ ...n, inDegree: deg.get(n.id)?.in ?? 0, outDegree: deg.get(n.id)?.out ?? 0 })),
    ...files.map((id) => gnode(ix, ix.byId.get(id)!, [], deg.get(id) ?? { in: 0, out: 0 }, false)),
  ];
  const pageTypes = [...new Set(nodes.filter((n) => n.layer !== "artifact").map((n) => n.type))];
  const extra = pageTypes.map((id) => conceptSchema.types.find((t) => t.id === id) ?? { id, label: id, layer: "concept" as const });
  const artTypes = ordered(ix, new Set(files.map((id) => ix.byId.get(id)!.type)));
  return {
    model: { nodes, links: glinks, conceptLinks: [], kbs: concepts.kbs ?? [] },
    schema: schemaFor(artTypes, extra),
    types: new Set([...pageTypes, ...artTypes]),
    focus: null,
    crumbs: [],
    hidden: 0,
    colorBy: "type",
  };
}

/** The artifacts a page's cited facts are about, and how many facts it cites. */
export function citedByPage(ix: ArtifactIndex, slug: string): { facts: number; nodes: readonly string[] } {
  return { facts: ix.graph.cites?.[slug]?.length ?? 0, nodes: [...(ix.pageNodes.get(slug) ?? [])] };
}

/** A view can step inside an artifact: it nests, and something inside is of a type it draws. */
export function drillable(ix: ArtifactIndex, view: ArtifactView | undefined, id: string): boolean {
  if (!view || view.nest === "none") return false;
  const types = new Set(view.types);
  return (ix.children.get(id) ?? []).some((c) => types.has(ix.byId.get(c)?.type ?? ""));
}

/** The view that draws an artifact best: the first whose types include it and whose links touch it or its inside. */
export function viewFor(ix: ArtifactIndex, id: string): ArtifactView | undefined {
  const n = ix.byId.get(id);
  if (!n) return undefined;
  return ix.views.find((v) => v.types.includes(n.type)) ?? ix.views[0];
}
