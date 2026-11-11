import { useMemo } from "react";
import { colorChannel, GraphLegend, NodeMarkG } from "@/features/graph/encoding";
import { areaSlots } from "@/features/graph/style";
import type { GNode } from "@/features/graph/types";
import { cn } from "@/lib/utils";
import type { PreviewPage } from "./model";

const W = 320;
const H = 200;
const R = 8;

/** A touched page as a graph node, for the shared encoding (mark by type, colour by theme). */
function node(p: PreviewPage): GNode {
  return { id: p.slug, label: p.title, title: p.title, type: p.type, layer: "concept", areas: p.areas, year: null, inDegree: 0, outDegree: 0, path: "", added: "" } as unknown as GNode;
}

/** Pages on an ellipse around the source, first page at the top; fixed, so a decision never moves a node. */
function place(i: number, n: number): { x: number; y: number } {
  const a = -Math.PI / 2 + (i / Math.max(n, 1)) * Math.PI * 2;
  return { x: W / 2 + Math.cos(a) * 104, y: H / 2 - 6 + Math.sin(a) * 62 };
}

/**
 * The pages one queued item touches, around the item itself: the mark is the page's type, a dashed spoke is a
 * page this item creates, a ring is the page being read and a tick is a page with nothing left to decide.
 */
export function TouchedGraph({ pages, shown, current, done, onPick }: { pages: PreviewPage[]; shown: number; current: string | null; done: (p: PreviewPage) => boolean; onPick: (slug: string) => void }) {
  const nodes = useMemo(() => pages.map(node), [pages]);
  const color = useMemo(() => colorChannel("area", { areas: areaSlots(nodes) }), [nodes]);
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-1 px-3 pb-2">
      <svg viewBox={`0 0 ${W} ${H}`} role="group" aria-label="Pages this touches" className="min-h-0 w-full flex-1">
        {pages.slice(0, shown).map((p, i) => {
          const { x, y } = place(i, pages.length);
          return <line key={p.slug} x1={W / 2} y1={H / 2 - 6} x2={x} y2={y} className="stroke-border" strokeWidth={1.2} strokeDasharray={p.isNew ? "3 3" : undefined} />;
        })}
        <rect x={W / 2 - 6} y={H / 2 - 12} width={12} height={12} rx={3} className="fill-accent-soft stroke-primary" />
        {pages.slice(0, shown).map((p, i) => {
          const { x, y } = place(i, pages.length);
          const on = p.slug === current;
          return (
            <g key={p.slug} role="button" tabIndex={0} aria-label={`Open ${p.title}`} aria-current={on || undefined} className="cursor-pointer outline-none [&:focus-visible_.focus-ring]:stroke-primary" onClick={() => onPick(p.slug)} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onPick(p.slug))}>
              <circle cx={x} cy={y} r={R + 4} fill="none" strokeWidth={1.5} className={cn("focus-ring", on ? "stroke-primary" : "stroke-transparent")} />
              <NodeMarkG type={p.type} x={x} y={y} r={R} color={color.color(nodes[i]!)} background="var(--card)" glyph />
              {done(p) && <path d={`M${x + R - 1},${y - R - 1} l3,3 l5,-6`} fill="none" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" className="stroke-foreground" />}
              <text x={x} y={y + R + 13} textAnchor="middle" fontSize={11} className={on ? "fill-foreground" : "fill-muted-foreground"}>
                {p.title}
              </text>
            </g>
          );
        })}
      </svg>
      <GraphLegend nodes={nodes} color={color} density="compact" />
    </div>
  );
}
