import { useCallback, useMemo, useRef } from "react";
import { Empty, ErrorState, Loading } from "@/components/states";
import { useApiQuery } from "@/lib/useApiQuery";
import { typeColor } from "@/theme/palette";
import { readCanvasColors, withAlpha } from "./canvasTheme";
import { fixedChannel, type ColorChannel } from "./encoding/channels";
import { citeNode, citeRadius, drawCite, type CiteNode } from "./encoding/cite";
import { GraphLegend } from "./encoding/GraphLegend";
import { ForceGraph, type ForceGraphHandle } from "./ForceGraph";
import { GENEALOGY_HOPS, genealogyOf, type GenealogyNode } from "./genealogy";
import type { SimLink, SimNode } from "./types";

type GNodeRole = CiteNode & { role: GenealogyNode["role"] };

/**
 * Colour = citation role: cited = blue, citing = red (palette colours, no map of its own), the paper itself in the
 * accent and ringed. Type stays the mark (every node here is a paper: a source dot with the page glyph).
 */
const roleChannel = (ring: string): ColorChannel =>
  fixedChannel("role", "citation role", (n) => (n as GNodeRole).role, [
    { key: "focus", label: "this paper", color: ring },
    { key: "cited", label: "it cites", color: typeColor("idea") },
    { key: "citing", label: "cites it", color: typeColor("paper") },
  ]);
const SIZE = { by: "citations", title: "citations" } as const;

const asNode = (n: GenealogyNode): GNodeRole => citeNode(n, { role: n.role });

interface Props {
  focus: string;
  /** Which pages exist as cataloged source papers. */
  isSource: (id: string) => boolean;
  titleOf: (id: string) => string;
  onPick: (id: string) => void;
}

/** One paper's citation genealogy (what it cites, what cites it, two hops each way) over GET /api/citations. */
export function CitationView({ focus, isSource, titleOf, onPick }: Props) {
  const q = useApiQuery(["citations"], (d) => d.getCitations(), { staleTime: 5 * 60_000 });
  const fg = useRef<ForceGraphHandle>(null);
  const hover = useRef<string | null>(null);
  const colors = useRef(readCanvasColors());
  const channel = useMemo(() => roleChannel(colors.current.ring), []);

  const g = useMemo(() => (q.data && !q.data.missing ? genealogyOf(q.data, focus, isSource) : null), [q.data, focus, isSource]);
  const data = useMemo(
    () => (g ? { nodes: g.nodes.map(asNode) as SimNode[], links: g.links.map((l) => ({ source: l.source, target: l.target, kind: "wikilink" as const })) as SimLink[] } : { nodes: [], links: [] }),
    [g],
  );
  const radius = useCallback((n: SimNode) => (n.id === focus ? 9 : citeRadius((n as CiteNode).citations)), [focus]);

  const draw = useCallback(
    (n: SimNode, ctx: CanvasRenderingContext2D, scale: number) => {
      const role = (n as GNodeRole).role;
      const hovered = hover.current === n.id;
      // the shared citation encoding: the paper's mark and glyph, the focus ring, the hover glow, the label
      drawCite(n, ctx, scale, { r: radius(n), color: channel.color(n), colors: colors.current, state: role === "focus" ? "focus" : hovered ? "hover" : null, label: role === "focus" || hovered });
    },
    [radius, channel],
  );

  if (q.isLoading) return <Loading label="Loading citations" rows={2} />;
  if (q.isError) return <ErrorState title="Could not load the citations." error={q.error} onRetry={() => void q.refetch()} />;
  if (q.data?.missing || !q.data?.nodes.length)
    return <Empty>No citation data yet. Fetch it with <code>python3 -m kb_distillery.search.citations fetch</code>.</Empty>;
  if (!g) return <Empty>No citation data for “{titleOf(focus)}” yet.</Empty>;

  const noop = () => {};
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-1.5 text-xs" data-testid="genealogy-bar">
        <span>
          Genealogy of <b>{titleOf(focus)}</b> · {GENEALOGY_HOPS} hops
        </span>
        {/* the shared legend: type (a paper), colour = citation role, size = citations */}
        <GraphLegend nodes={data.nodes} color={channel} size={SIZE} density="compact" />
        <span className="text-muted-foreground">
          it cites {g.cited} · cite it {g.citing}
        </span>
      </div>
      <div className="relative min-h-0 flex-1">
        <ForceGraph
          ref={fg}
          className="absolute inset-0"
          data={data}
          forces={{ charge: -60, linkDistance: 40, gravity: 0.3 }}
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
          onEngineStop={() => fg.current?.fit(undefined, 300)}
        />
      </div>
    </div>
  );
}
