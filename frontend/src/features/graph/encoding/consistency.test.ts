/**
 * The graph-consistency guard (skills/app-ui, "Graph encoding"): one visual language on every graph.
 *
 * 1. A node is drawn by the shared encoding only: no `typeColor(` for a node and no `ctx.arc(` outside
 *    `encoding/`, except the listed files, each with its reason.
 * 2. The inheritance boundary: other surfaces import from `features/graph/encoding` (plus a short list of shared
 *    data modules), never from a Full-Graph-only feature; `encoding/` imports no Full-Graph-only feature.
 * 3. Every graph surface renders the shared legend, and every file that draws a graph is a listed surface.
 */
import { describe, expect, it } from "vitest";

const SRC = import.meta.glob("/src/**/*.{ts,tsx}", { query: "?raw", import: "default", eager: true }) as Record<string, string>;
const files = Object.entries(SRC)
  .map(([p, text]) => [p.replace(/^\/src\//, ""), text] as const)
  .filter(([p]) => !/\.test\.tsx?$/.test(p) && !p.startsWith("test/") && !p.startsWith("api/schema"));

const ENCODING = "features/graph/encoding/";

/** Files that call `.arc(` for something that is not a page's node, and why. */
const ARC_OK: Readonly<Record<string, string>> = {
  "features/graph/ForceGraph.tsx": "pointer hit areas (invisible), not marks",
  "features/home/SampleGraph.tsx": "pointer hit areas (invisible), not marks",
  "features/graph/GraphCanvas.tsx": "experiment halos (tools/decor) under a node, a Full Graph feature",
  "features/graph/rawLayer.ts": "raw piles: stacks of raw files, not pages (Full Graph feature)",
  "features/graph/magnet.ts": "the magnet hover bubble (Full Graph feature)",
  "features/graph/lab/draw.ts": "hulls and the label lens (Full Graph features)",
};

/** Files that call `typeColor(` for something that is not a node's colour, and why. */
const TYPE_COLOR_OK: Readonly<Record<string, string>> = {
  "features/graph/style.ts": "the colour-by-type channel itself (colorOf)",
  "features/graph/CitationView.tsx": "palette values of the citation-role channel, not a node's type",
};

/** Full-Graph-only features: no other surface and nothing in encoding/ may import them. */
const FULL_GRAPH_ONLY = [
  "views/",
  "lab/LabRail",
  "lab/draw",
  "lab/arcs",
  "lab/regions",
  "lab/hud",
  "lab/HoverCard",
  "FiltersPanel",
  "quickFilters",
  "rawLayer",
  "magnet",
  "basket",
  "NodeMenu",
  "menu",
  "Finder",
  "Legend",
  "GraphCanvas",
  "GraphScreen",
  "Toolbar",
  "LayoutPanel",
  "CorpusDrawer",
  "Inspector",
  "rules",
  "selection",
  "kalai/",
];

/** Shared non-visual graph modules other surfaces may import besides encoding/, and why. */
const SHARED_OK: Readonly<Record<string, string>> = {
  types: "the page-as-node data type",
  style: "colour and size computations (colorOf, areaSlots) behind the channels",
  graphData: "the link model (neighbour maps)",
  pageSearch: "page search",
  publicPredicate: "the public-page rule",
  SideReader: "the shared side reader",
  defaultView: "the Home → Full Graph link target",
  "lab/importance": "the importance score Home ranks labels by",
  "lab/config": "the default importance settings",
  store: "Home tours drive the Full Graph's state",
  "tools/chatDockStore": "the app-wide chat dock",
  fixtures: "test fixtures",
};

const graphImports = (text: string): string[] =>
  [...text.matchAll(/^import\s+(?!type\b)[^;]*?from\s+"@\/features\/graph\/([^"]+)"/gm)].map((m) => m[1]!);

const relImports = (text: string): string[] => [...text.matchAll(/^import\s+(?!type\b)[^;]*?from\s+"\.\.\/([^"]+)"/gm)].map((m) => m[1]!);

const fullGraphOnly = (mod: string) => FULL_GRAPH_ONLY.some((f) => (f.endsWith("/") ? mod.startsWith(f) : mod === f || mod.startsWith(`${f}/`)));

describe("graph consistency guard", () => {
  it("reads the app's sources", () => {
    expect(files.length).toBeGreaterThan(100);
  });

  it("draws nodes through the shared encoding only", () => {
    const arcs = files.filter(([p, t]) => !p.startsWith(ENCODING) && /\.arc\(/.test(t) && !ARC_OK[p]).map(([p]) => p);
    expect(arcs, "draw nodes with encoding drawNode, or list the file in ARC_OK with its reason").toEqual([]);
    const colours = files.filter(([p, t]) => !p.startsWith(ENCODING) && !p.startsWith("theme/") && /\btypeColor\(/.test(t) && !TYPE_COLOR_OK[p]).map(([p]) => p);
    expect(colours, "type is the mark: colour a node by its surface's colour channel").toEqual([]);
  });

  it("keeps Full-Graph-only features out of other surfaces", () => {
    const bad: string[] = [];
    for (const [p, t] of files) {
      if (p.startsWith("features/graph/")) continue;
      for (const mod of graphImports(t)) {
        if (mod === "encoding" || mod.startsWith("encoding/")) continue;
        if (fullGraphOnly(mod) || !SHARED_OK[mod]) bad.push(`${p} -> ${mod}`);
      }
    }
    expect(bad, "import from @/features/graph/encoding, or add a shared non-visual module to SHARED_OK").toEqual([]);
  });

  it("keeps encoding/ free of Full Graph features", () => {
    const bad: string[] = [];
    for (const [p, t] of files) {
      if (!p.startsWith(ENCODING)) continue;
      for (const mod of [...relImports(t), ...graphImports(t)]) if (fullGraphOnly(mod)) bad.push(`${p} -> ${mod}`);
    }
    expect(bad).toEqual([]);
  });

  /** Each file that draws a graph, and the file that renders its legend. */
  const SURFACES: Readonly<Record<string, string>> = {
    "features/graph/GraphCanvas.tsx": "features/graph/Legend.tsx",
    "features/graph/CitationView.tsx": "features/graph/CitationView.tsx",
    "features/home/SampleGraph.tsx": "features/home/ConceptExplorer.tsx",
    "features/pages/MiniGraph.tsx": "features/pages/MiniGraph.tsx",
  };

  it("lists every graph surface, and each renders the shared legend", () => {
    const drawers = files
      .filter(([p, t]) => !p.startsWith(ENCODING) && p !== "features/graph/ForceGraph.tsx" && /<ForceGraph\b|createForceGraph\(|aria-label="Neighbour graph"/.test(t))
      .map(([p]) => p)
      .sort();
    expect(drawers, "a new graph surface: add it to SURFACES with the file that renders its legend").toEqual(Object.keys(SURFACES).sort());
    const src = new Map(files);
    for (const [surface, legend] of Object.entries(SURFACES)) {
      const t = src.get(legend) ?? "";
      // the Full Graph's interactive legend is built from the shared atoms; the others render GraphLegend
      expect(/<GraphLegend\b/.test(t) || /<LegendTitle\b/.test(t), `${surface}: its legend (${legend})`).toBe(true);
    }
  });
});
