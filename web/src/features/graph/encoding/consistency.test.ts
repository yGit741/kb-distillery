/**
 * The graph-consistency guard (.claude/skills/app-ui, "Graph encoding"): one visual language on every graph.
 *
 * 1. A node is drawn by the shared encoding only: no `typeColor(` for a node, and no hand-drawn circle (`.arc(`,
 *    `<circle`) outside `encoding/`, except the listed files, each pinned to its count and reason.
 * 2. The inheritance boundary: other surfaces import `features/graph/encoding` plus a short list of shared data
 *    modules, never a Full Graph module; `encoding/` imports only itself and an explicit list.
 * 3. Every file that draws a graph is a listed surface whose host renders it next to the shared legend.
 */
import { describe, expect, it } from "vitest";

const SRC = import.meta.glob("/src/**/*.{ts,tsx}", { query: "?raw", import: "default", eager: true }) as Record<string, string>;
const files = Object.entries(SRC)
  .map(([p, text]) => [p.replace(/^\/src\//, ""), text] as const)
  .filter(([p]) => !/\.test\.tsx?$/.test(p) && !p.startsWith("test/") && !p.startsWith("api/schema"));
const src = new Map(files);

const ENCODING = "features/graph/encoding/";
const GRAPH = "features/graph/";

const count = (text: string, re: RegExp) => (text.match(re) ?? []).length;

/** Files that draw a circle that is not a page's node: the exact count, and why. A new circle needs a new reason. */
const CIRCLE_OK: Readonly<Record<string, { n: number; why: string }>> = {
  "features/graph/ForceGraph.tsx": { n: 1, why: "pointer hit areas (invisible), not marks" },
  "features/home/SampleGraph.tsx": { n: 1, why: "pointer hit areas (invisible), not marks" },
  "features/graph/GraphCanvas.tsx": { n: 1, why: "experiment halos (tools/decor) under a node, a Full Graph feature" },
  "features/graph/rawLayer.ts": { n: 4, why: "raw piles: stacks of raw files, not pages (Full Graph feature)" },
  "features/graph/shell/thinkingDraw.ts": { n: 5, why: "show-thinking: the citation badge, the hover ring and the temporary web-source mark (not a page), never a page mark" },
  "features/graph/shell/replayDraw.ts": { n: 2, why: "the replay's trail rings around a mark (Full Graph feature, flag spark-chat), never a mark itself" },
  "features/graph/magnet.ts": { n: 2, why: "the magnet hover bubble (Full Graph feature)" },
  "features/graph/lab/draw.ts": { n: 2, why: "the label lens (Full Graph feature)" },
  "features/home/FullGraphIcon.tsx": { n: 4, why: "the Open in Full Graph icon" },
  "features/pages/MiniGraph.tsx": { n: 2, why: "the focus ring and the keyboard focus ring around a mark" },
  "features/covector/CovectorScreen.tsx": { n: 1, why: "the dot at the tip of the test vector in the covector picture, not a page" },
};

/** Files that call `typeColor` for something that is not a node's colour: the exact count, and why. */
const TYPE_COLOR_OK: Readonly<Record<string, { n: number; why: string }>> = {
  "features/graph/style.ts": { n: 1, why: "the colour-by-type channel itself (colorOf)" },
  "features/graph/CitationView.tsx": { n: 2, why: "palette values of the citation-role channel, not a node's type" },
};

/** Shared non-visual graph modules other surfaces may import, and who may (`*` = any file). */
const SHARED_OK: Readonly<Record<string, { who: string; why: string }>> = {
  "features/graph/types": { who: "*", why: "the page-as-node data type" },
  "features/graph/style": { who: "*", why: "colour and size computations (colorOf, areaSlots) behind the channels" },
  "features/graph/graphData": { who: "*", why: "the link model (neighbour maps)" },
  "features/graph/pageSearch": { who: "*", why: "page search" },
  "features/graph/publicPredicate": { who: "*", why: "the public-page rule" },
  "features/graph/SideReader": { who: "*", why: "the shared side reader" },
  "features/graph/defaultView": { who: "features/home/index.tsx", why: "the Home → Full Graph link target" },
  "features/graph/lab/importance": { who: "features/home/", why: "the importance score Home ranks labels by" },
  "features/graph/lab/config": { who: "features/home/samplers.ts", why: "the default importance settings" },
  // grandfathered: a Home tour drives the Full Graph's own state, and the chat dock is app-wide
  "features/graph/store": { who: "features/home/tours.ts", why: "Home tours drive the Full Graph's state" },
  "features/graph/shell/SearchOverlay": { who: "app/", why: "the search line as a sheet on every screen" },
  "features/graph/tools/chatDockStore": { who: "app/", why: "the app-wide chat dock" },
};

/** What `encoding/` may import from the graph feature besides itself: shared computations only. */
const ENCODING_DEPS = new Set(["features/graph/style", "features/graph/legendModel", "features/graph/types", "features/graph/displayNames"]);

/** Every module specifier in a file: imports (type ones too), re-exports and dynamic imports, any quotes. */
const specifiers = (text: string): string[] => [
  ...[...text.matchAll(/\bfrom\s+["']([^"']+)["']/g)].map((m) => m[1]!),
  ...[...text.matchAll(/\bimport\s*\(\s*["']([^"']+)["']\s*\)/g)].map((m) => m[1]!),
  ...[...text.matchAll(/^\s*import\s+["']([^"']+)["']/gm)].map((m) => m[1]!),
];

/** A specifier as a path under src/ without extension ("features/graph/style"), or null for a package. */
function resolve(from: string, spec: string): string | null {
  if (spec.startsWith("@/")) return spec.slice(2).replace(/\/index$/, "");
  if (!spec.startsWith(".")) return null;
  const parts = from.split("/").slice(0, -1);
  for (const s of spec.split("/")) {
    if (s === "..") parts.pop();
    else if (s !== ".") parts.push(s);
  }
  return parts.join("/").replace(/\.(tsx?|css)$/, "").replace(/\/index$/, "");
}

const graphTargets = (p: string, t: string) =>
  specifiers(t)
    .map((s) => resolve(p, s))
    .filter((r): r is string => !!r && (r === "features/graph" || r.startsWith(GRAPH)));

describe("graph consistency guard", () => {
  it("reads the app's sources", () => {
    expect(files.length).toBeGreaterThan(100);
    expect(resolve("features/home/a.tsx", "../graph/Legend")).toBe("features/graph/Legend");
    expect(specifiers(`import type { X } from '@/features/graph/GraphCanvas';\nexport * from "../graph/rawLayer";\nconst m = import("@/features/graph/basket");`)).toEqual([
      "@/features/graph/GraphCanvas",
      "../graph/rawLayer",
      "@/features/graph/basket",
    ]);
  });

  it("draws nodes through the shared encoding only", () => {
    const circles = files
      .filter(([p]) => !p.startsWith(ENCODING))
      .map(([p, t]) => [p, count(t, /\.arc\s*\(|\.ellipse\s*\(|<circle\b/g)] as const)
      .filter(([p, n]) => n > 0 && CIRCLE_OK[p]?.n !== n)
      .map(([p, n]) => `${p}: ${n}`);
    expect(circles, "draw nodes with encoding drawNode / NodeMarkG, or list the circle in CIRCLE_OK with its reason").toEqual([]);
    const colours = files
      .filter(([p]) => !p.startsWith(ENCODING) && !p.startsWith("theme/"))
      // every use outside import statements (an alias `typeColor as tc` still names typeColor in its import)
      .map(([p, t]) => [p, count(t.replace(/^\s*import\b[^;]*;/gms, (m) => (/\btypeColor\s+as\b/.test(m) ? "typeColor" : "")), /\btypeColor\b/g)] as const)
      .filter(([p, n]) => n > 0 && TYPE_COLOR_OK[p]?.n !== n)
      .map(([p, n]) => `${p}: ${n}`);
    expect(colours, "type is the mark: colour a node by its surface's colour channel").toEqual([]);
  });

  it("keeps the Full Graph's modules out of other surfaces", () => {
    const bad: string[] = [];
    for (const [p, t] of files) {
      if (p.startsWith(GRAPH)) continue;
      for (const r of graphTargets(p, t)) {
        if (r === "features/graph/encoding" || r.startsWith(ENCODING)) continue;
        const ok = SHARED_OK[r];
        if (!ok || (ok.who !== "*" && !p.startsWith(ok.who))) bad.push(`${p} -> ${r}`);
      }
    }
    expect(bad, "import from @/features/graph/encoding, or add a shared non-visual module to SHARED_OK with who may use it").toEqual([]);
  });

  it("keeps encoding/ free of the Full Graph", () => {
    const bad: string[] = [];
    for (const [p, t] of files) {
      if (!p.startsWith(ENCODING)) continue;
      for (const r of graphTargets(p, t)) if (!r.startsWith(ENCODING) && !ENCODING_DEPS.has(r)) bad.push(`${p} -> ${r}`);
    }
    expect(bad).toEqual([]);
  });

  /** Each file that draws a graph: the host that renders it, the component name, and how its legend is shown. */
  const SURFACES: Readonly<Record<string, { host: string; component: string; legend: "GraphLegend" | "Legend" }>> = {
    "features/graph/GraphCanvas.tsx": { host: "features/graph/GraphScreen.tsx", component: "GraphCanvas", legend: "Legend" },
    "features/graph/CitationView.tsx": { host: "features/graph/CitationView.tsx", component: "ForceGraph", legend: "GraphLegend" },
    "features/home/SampleGraph.tsx": { host: "features/home/ConceptExplorer.tsx", component: "SampleGraph", legend: "GraphLegend" },
    "features/pages/MiniGraph.tsx": { host: "features/pages/MiniGraph.tsx", component: "NodeMarkG", legend: "GraphLegend" },
  };

  it("lists every graph surface, and each host renders it beside the shared legend", () => {
    const drawers = files
      .filter(([p, t]) => !p.startsWith(ENCODING) && p !== "features/graph/ForceGraph.tsx" && /<ForceGraph\b|createForceGraph\(|\bdrawNode(?:Mark)?\(\s*ctx|<NodeMarkG\b/.test(t))
      .map(([p]) => p)
      .sort();
    expect(drawers, "a new graph surface: add it to SURFACES with its host and legend").toEqual(Object.keys(SURFACES).sort());
    for (const [surface, s] of Object.entries(SURFACES)) {
      const host = src.get(s.host) ?? "";
      expect(new RegExp(`<${s.component}\\b`).test(host), `${s.host} renders ${s.component}`).toBe(true);
      expect(new RegExp(`<${s.legend}\\b`).test(host), `${surface}: ${s.host} renders <${s.legend}>`).toBe(true);
    }
    // only the Full Graph keeps its own interactive legend, built from the shared atoms
    expect(/<LegendTitle\b/.test(src.get("features/graph/Legend.tsx") ?? "")).toBe(true);
    expect(/<LegendSwatch\b/.test(src.get("features/graph/Legend.tsx") ?? "")).toBe(true);
  });
});
