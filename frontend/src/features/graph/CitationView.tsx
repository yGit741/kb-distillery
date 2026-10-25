import { useCallback, useMemo, useRef } from "react";
import { Empty, ErrorState, Loading } from "@/components/states";
import { useApiQuery } from "@/lib/useApiQuery";
import { typeColor } from "@/theme/palette";
import { readCanvasColors, withAlpha } from "./canvasTheme";
import { ForceGraph, type ForceGraphHandle } from "./ForceGraph";
import { GENEALOGY_HOPS, genealogyOf, type GenealogyNode } from "./genealogy";
import type { SimLink, SimNode } from "./types";

type CiteNode = SimNode & { role: GenealogyNode["role"]; citations: number };

/** cited = blue (idea), citing = red (paper), the focus is ringed in the accent: palette colours, no map of its own. */
const roleColor = (role: GenealogyNode["role"], ring: string) => (role === "focus" ? ring : role === "cited" ? typeColor("idea") : typeColor("paper"));

const asNode = (n: GenealogyNode): CiteNode => ({
  id: n.id,
  label: n.title,
  title: n.title,
  type: "paper",
  layer: "source",
  status: "",
  depth: "",
  areas: [],
  year: n.year,
  inDegree: 0,
  outDegree: 0,
  path: "",
  added: "",
  changed: "",
  preview: "",
  properties: {},
  role: n.role,
  citations: n.citationCount,
});

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

  const g = useMemo(() => (q.data && !q.data.missing ? genealogyOf(q.data, focus, isSource) : null), [q.data, focus, isSource]);
  const data = useMemo(
    () => (g ? { nodes: g.nodes.map(asNode) as SimNode[], links: g.links.map((l) => ({ source: l.source, target: l.target, kind: "wikilink" as const })) as SimLink[] } : { nodes: [], links: [] }),
    [g],
  );
  const radius = useCallback((n: SimNode) => (n.id === focus ? 9 : 3 + Math.min(Math.log2(1 + ((n as CiteNode).citations ?? 0)), 7)), [focus]);

  const draw = useCallback(
    (n: SimNode, ctx: CanvasRenderingContext2D, scale: number) => {
      if (n.x == null || n.y == null) return;
      const c = colors.current;
      const role = (n as CiteNode).role;
      ctx.beginPath();
      ctx.arc(n.x, n.y, radius(n), 0, 2 * Math.PI);
      ctx.fillStyle = roleColor(role, c.ring);
      ctx.fill();
      if (role === "focus" || hover.current === n.id) {
        ctx.lineWidth = 2 / scale;
        ctx.strokeStyle = c.text;
        ctx.stroke();
        const size = Math.max(11 / scale, 3);
        ctx.font = `${size}px ${c.font}`;
        const text = `${n.title}${n.year ? ` (${n.year})` : ""}`;
        const w = ctx.measureText(text).width;
        ctx.fillStyle = withAlpha(c.background, 0.88);
        ctx.fillRect(n.x - w / 2 - 2 / scale, n.y + radius(n) + 3 / scale, w + 4 / scale, size + 3 / scale);
        ctx.fillStyle = c.text;
        ctx.fillText(text, n.x - w / 2, n.y + radius(n) + 3 / scale + size);
      }
    },
    [radius],
  );

  if (q.isLoading) return <Loading label="Loading citations" rows={2} />;
  if (q.isError) return <ErrorState title="Could not load the citations." error={q.error} onRetry={() => void q.refetch()} />;
  if (q.data?.missing || !q.data?.nodes.length)
    return <Empty>No citation data yet. Fetch it with <code>python3 -m kb.search.citations fetch</code>.</Empty>;
  if (!g) return <Empty>No citation data for “{titleOf(focus)}” yet.</Empty>;

  const noop = () => {};
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-1.5 text-xs" data-testid="genealogy-bar">
        <span>
          Genealogy of <b>{titleOf(focus)}</b> · {GENEALOGY_HOPS} hops
        </span>
        <span className="flex items-center gap-1">
          <i className="inline-block size-2.5 rounded-full" style={{ background: roleColor("cited", colors.current.ring) }} />
          it cites {g.cited}
        </span>
        <span className="flex items-center gap-1">
          <i className="inline-block size-2.5 rounded-full" style={{ background: roleColor("citing", colors.current.ring) }} />
          cite it {g.citing}
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
