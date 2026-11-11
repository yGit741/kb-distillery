import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Empty, ErrorState, Loading } from "@/components/states";
import { Switch } from "@/components/ui/switch";
import { useApiQuery } from "@/lib/useApiQuery";
import { readCanvasColors, withAlpha } from "./canvasTheme";
import { CITE_STATUS, citationMap, missingGrid, statusRamp, type CitationMapNode, type CiteStatus, type VaultPaper } from "./citationMapData";
import { citeNode, citeRadius, drawCite, type CiteNode } from "./encoding/cite";
import { fixedChannel, type ColorChannel } from "./encoding/channels";
import { GraphLegend } from "./encoding/GraphLegend";
import { ForceGraph, type ForceGraphHandle } from "./ForceGraph";
import type { SimLink, SimNode } from "./types";

type MapNode = CiteNode & { isolated: boolean; status: CiteStatus };

/** Colour = how far the paper got, one ordered ramp red (no citation data) -> strongest green (deep digest); size = citations, arrows = cites. */
const statusChannel = (ok: string, bad: string): ColorChannel => {
  const ramp = statusRamp(ok, bad);
  const values = CITE_STATUS.map((s) => ({ ...s, color: ramp[s.key] }));
  const ch = fixedChannel("status", "paper status", (n) => (n as MapNode).status, values);
  // every step of the scale, even one with no paper, so the ramp reads as a scale
  return { ...ch, rows: (nodes) => {
    const got = new Map(ch.rows(nodes).map((r) => [r.label, r.count]));
    return values.map((v) => ({ label: v.label, color: v.color, count: got.get(v.label) ?? 0 }));
  } };
};
const FORCES = { charge: -60, linkDistance: 40, gravity: 0.3 };
/** A soft pull to the centre keeps small citation islands near the core (the papers without data are pinned). */
const ANCHOR = { target: (n: SimNode) => ((n as MapNode).status === "failed" ? null : ([0, 0] as const)), strength: 0.08 };
const SIZE = { by: "citations", title: "citations" } as const;

interface Props {
  /** Which pages exist as cataloged source papers. */
  isSource: (id: string) => boolean;
  /** The kb's paper pages (their depth colours the map; the ones without citation data are drawn red). */
  papers: readonly VaultPaper[];
  onPick: (id: string) => void;
}

/** Every cataloged paper and who cites whom among them, over GET /api/citations. */
export function CitationMap({ isSource, papers, onPick }: Props) {
  const q = useApiQuery(["citations"], (d) => d.getCitations(), { staleTime: 5 * 60_000 });
  const fg = useRef<ForceGraphHandle>(null);
  const hover = useRef<string | null>(null);
  const colors = useRef(readCanvasColors());
  const channel = useMemo(() => statusChannel(colors.current.ok ?? colors.current.muted, colors.current.bad ?? colors.current.warn), []);
  const [showUnlinked, setShowUnlinked] = useState(false);

  const m = useMemo(() => (q.data && !q.data.missing ? citationMap(q.data, isSource, papers) : null), [q.data, isSource, papers]);
  const data = useMemo(() => {
    if (!m) return { nodes: [] as SimNode[], links: [] as SimLink[] };
    const shown = m.nodes.filter((n) => showUnlinked || !n.isolated || n.status === "failed");
    const spots = missingGrid(shown.filter((n) => n.status === "failed").length);
    let i = 0;
    const nodes = shown.map((n: CitationMapNode) => {
      const node = citeNode(n, { isolated: n.isolated, status: n.status });
      // the papers without data sit pinned in their own grid beside the core, out of the simulation's way
      if (n.status === "failed") {
        const p = spots[i++]!;
        Object.assign(node, { x: p.x, y: p.y, fx: p.x, fy: p.y });
      }
      return node;
    });
    return { nodes: nodes as SimNode[], links: m.links.map((l) => ({ source: l.source, target: l.target, kind: "wikilink" as const })) as SimLink[] };
  }, [m, showUnlinked]);
  const radius = useCallback((n: SimNode) => ((n as MapNode).status === "failed" ? 3 : citeRadius((n as CiteNode).citations)), []);

  // fit once the layout settles (onEngineStop), again when the unlinked toggle changes, and when the sheet is resized
  const host = useRef<HTMLDivElement>(null);
  const fit = useCallback(() => fg.current?.fit(undefined, 300), []);
  /** Once the core has settled: move the grid of papers without data right beside it, then fit both. */
  const settle = useCallback(() => {
    const ns = fg.current?.nodes() ?? [];
    const core = ns.filter((n) => (n as MapNode).status !== "failed" && n.x != null && n.y != null);
    const missing = ns.filter((n) => (n as MapNode).status === "failed");
    if (core.length && missing.length) {
      const right = Math.max(...core.map((n) => n.x!));
      const ys = core.map((n) => n.y!);
      const spots = missingGrid(missing.length, right, (Math.min(...ys) + Math.max(...ys)) / 2);
      missing.forEach((n, i) => Object.assign(n, { x: spots[i]!.x, y: spots[i]!.y, fx: spots[i]!.x, fy: spots[i]!.y }));
      fg.current?.refresh();
    }
    fit();
  }, [fit]);
  useEffect(() => {
    const el = host.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    let t: ReturnType<typeof setTimeout> | undefined;
    const ro = new ResizeObserver(() => {
      clearTimeout(t);
      t = setTimeout(fit, 150);
    });
    ro.observe(el);
    return () => {
      clearTimeout(t);
      ro.disconnect();
    };
  }, [fit, m]);
  useEffect(() => {
    const t = setTimeout(fit, 600);
    return () => clearTimeout(t);
  }, [fit, showUnlinked]);

  const draw = useCallback(
    (n: SimNode, ctx: CanvasRenderingContext2D, scale: number) => {
      const hovered = hover.current === n.id;
      drawCite(n, ctx, scale, { r: radius(n), color: channel.color(n), colors: colors.current, state: hovered ? "hover" : null, label: hovered, faded: (n as MapNode).isolated && (n as MapNode).status !== "failed" && !hovered });
    },
    [radius, channel],
  );

  if (q.isLoading) return <Loading label="Loading citations" rows={2} />;
  if (q.isError) return <ErrorState title="Could not load the citations." error={q.error} onRetry={() => void q.refetch()} />;
  if (!m || (!m.papers && !m.withoutData))
    return <Empty>No citation data yet. Fetch it with <code>python3 -m kb_distillery.search.citations fetch</code>.</Empty>;

  const noop = () => {};
  return (
    <div className="flex h-full min-h-[24rem] flex-col">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-1.5 text-xs" data-testid="citation-map-bar">
        <span>
          {m.papers} papers · {m.links.length} cite links · {m.withoutData} without data
        </span>
        <GraphLegend nodes={data.nodes} color={channel} size={SIZE} density="compact" />
        <label className="ml-auto flex items-center gap-2 text-muted-foreground">
          <Switch checked={showUnlinked} onCheckedChange={setShowUnlinked} aria-label="Show unlinked papers" />
          unlinked with data ({m.papers - m.linked})
        </label>
      </div>
      <div ref={host} className="relative min-h-0 flex-1">
        <ForceGraph
          ref={fg}
          className="absolute inset-0"
          data={data}
          forces={FORCES}
          anchor={ANCHOR}
          arrows
          nodeRadius={radius}
          drawNode={draw}
          drawFramePost={noop}
          drawLinkAfter={noop}
          linkColor={() => withAlpha(colors.current.link, 0.5)}
          linkWidth={() => 0.8}
          linkLabel={() => ""}
          onNodeHover={(n: SimNode | null) => {
            hover.current = n?.id ?? null;
            fg.current?.refresh();
          }}
          onNodeClick={(n: SimNode) => onPick(n.id)}
          onLinkClick={noop}
          onBackgroundClick={noop}
          onZoom={noop}
          onEngineStop={settle}
        />
      </div>
    </div>
  );
}
