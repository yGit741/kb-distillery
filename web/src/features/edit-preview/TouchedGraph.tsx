import { useMemo } from "react";
import { colorChannel, GraphLegend, NodeMarkG } from "@/features/graph/encoding";
import { areaSlots } from "@/features/graph/style";
import type { GNode } from "@/features/graph/types";
import { cn } from "@/lib/utils";
import type { PreviewPage } from "./model";

/** What the graph needs from a touched page (an edit preview page, or a page of a proposal). */
export type TouchedPage = Pick<PreviewPage, "slug" | "title" | "type" | "areas" | "isNew">;

const R = 8;
/** Two sizes of one drawing: a side card (narrow) and the plan pop-up (wide). Labels sit outside the ring, so they never cross. */
const SIZE = { card: { w: 320, h: 200, rx: 58, ry: 66, chars: 16 }, wide: { w: 640, h: 300, rx: 150, ry: 104, chars: 30 } } as const;
type Size = (typeof SIZE)[keyof typeof SIZE];

/** A title in whole words up to `max` characters; the full title stays in the node's tooltip. */
export function fitTitle(title: string, max: number): string {
  if (title.length <= max) return title;
  const words = title.split(/\s+/);
  let out = words[0]!.slice(0, max);
  for (const w of words.slice(1)) {
    if (out.length + 1 + w.length > max - 2) break;
    out += ` ${w}`;
  }
  return `${out} …`;
}

/** A touched page as a graph node, for the shared encoding (mark by type, colour by theme). */
function node(p: TouchedPage): GNode {
  return { id: p.slug, label: p.title, title: p.title, type: p.type, layer: "concept", areas: p.areas, year: null, inDegree: 0, outDegree: 0, path: "", added: "" } as unknown as GNode;
}

/** Pages on an ellipse around the source, first page at the top; fixed, so a decision never moves a node. */
function place(i: number, n: number, z: Size): { x: number; y: number; cos: number; sin: number } {
  const a = -Math.PI / 2 + (i / Math.max(n, 1)) * Math.PI * 2;
  const cos = Math.cos(a);
  const sin = Math.sin(a);
  return { x: z.w / 2 + cos * z.rx, y: z.h / 2 + sin * z.ry, cos, sin };
}

/** Where a node's label goes: beside it on the outer side, or above / below for the top and bottom nodes. */
function labelAt(p: { x: number; y: number; cos: number; sin: number }): { x: number; y: number; anchor: "start" | "middle" | "end" } {
  if (Math.abs(p.cos) < 0.2) return { x: p.x, y: p.sin < 0 ? p.y - R - 7 : p.y + R + 14, anchor: "middle" };
  return { x: p.x + (p.cos > 0 ? R + 6 : -R - 6), y: p.y + 4, anchor: p.cos > 0 ? "start" : "end" };
}

/**
 * The pages one queued item touches, around the item itself: the mark is the page's type, a dashed spoke is a
 * page this item creates, a ring is the page being read and a tick is a page with nothing left to decide.
 */
export function TouchedGraph<T extends TouchedPage>({ pages, shown, current, done, onPick, wide }: { pages: T[]; shown: number; current: string | null; done: (p: T) => boolean; onPick: (slug: string) => void; wide?: boolean }) {
  const z = wide ? SIZE.wide : SIZE.card;
  const nodes = useMemo(() => pages.map(node), [pages]);
  const color = useMemo(() => colorChannel("area", { areas: areaSlots(nodes) }), [nodes]);
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-1 px-3 pb-2">
      <svg viewBox={`0 0 ${z.w} ${z.h}`} role="group" aria-label="Pages this touches" className="min-h-0 w-full flex-1">
        {pages.slice(0, shown).map((p, i) => {
          const { x, y } = place(i, pages.length, z);
          return <line key={p.slug} x1={z.w / 2} y1={z.h / 2} x2={x} y2={y} className="stroke-border" strokeWidth={1.2} strokeDasharray={p.isNew ? "3 3" : undefined} />;
        })}
        <rect x={z.w / 2 - 6} y={z.h / 2 - 6} width={12} height={12} rx={3} className="fill-accent-soft stroke-primary" />
        {pages.slice(0, shown).map((p, i) => {
          const at = place(i, pages.length, z);
          const { x, y } = at;
          const label = labelAt(at);
          const on = p.slug === current;
          return (
            <g key={p.slug} role="button" tabIndex={0} aria-label={`Open ${p.title}`} aria-current={on || undefined} className="cursor-pointer outline-none [&:focus-visible_.focus-ring]:stroke-primary" onClick={() => onPick(p.slug)} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onPick(p.slug))}>
              <circle cx={x} cy={y} r={R + 4} fill="none" strokeWidth={1.5} className={cn("focus-ring", on ? "stroke-primary" : "stroke-transparent")} />
              <NodeMarkG type={p.type} x={x} y={y} r={R} color={color.color(nodes[i]!)} background="var(--card)" glyph />
              {done(p) && <path d={`M${x + R - 1},${y - R - 1} l3,3 l5,-6`} fill="none" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" className="stroke-foreground" />}
              <title>{p.title}</title>
              <text x={label.x} y={label.y} textAnchor={label.anchor} fontSize={11} className={on ? "fill-foreground" : "fill-muted-foreground"}>
                {fitTitle(p.title, z.chars)}
              </text>
            </g>
          );
        })}
      </svg>
      <GraphLegend nodes={nodes} color={color} density="compact" />
    </div>
  );
}
