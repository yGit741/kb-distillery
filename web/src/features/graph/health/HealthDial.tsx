import { useEffect, useMemo, useRef } from "react";
import { cn } from "@/lib/utils";
import { SourceIcon } from "../encoding/NodeMarkSvg";
import type { SourceGlyph } from "../encoding/spec";
import type { NeighborMap } from "../graphData";
import { useCorners } from "../shell/corners/cornersStore";
import { EDGE } from "../shell/corners/geometry";
import { useGraphUi } from "../store";
import type { GNode } from "../types";
import { useHealth } from "./healthStore";
import { fedConcepts, kindLine, sourceKinds, type KindStat } from "./model";

const RING = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
const SPOT_IN_MS = 120;
const SPOT_OUT_MS = 160;
const BOX = 40;
const C = BOX / 2;
const R = 16.5;
const TAU = 2 * Math.PI;
/** a kind's row and the gap under it; the caption and the gap above the first row, px */
const PITCH = 52;
const HEAD = 28;
/** how far the dial's line runs past its first and last kind, in rows */
const OVER = 0.6;
/** how far the middle of the dial stands out from its two ends, px: deeper with more kinds */
export const bulge = (kinds: number): number => (kinds > 2 ? Math.min(40, 14 + 3 * (kinds - 1)) : 0);

const at = (f: number): string => `${(C + R * Math.sin(TAU * f)).toFixed(2)} ${(C - R * Math.cos(TAU * f)).toFixed(2)}`;
/** An arc of the ring between two fractions of a turn, clockwise from the top. */
export function ringArc(from: number, to: number): string {
  if (to - from >= 0.9999) return `M${at(0)}A${R} ${R} 0 1 1 ${at(0.5)}A${R} ${R} 0 1 1 ${at(0)}`;
  return `M${at(from)}A${R} ${R} 0 ${to - from > 0.5 ? 1 : 0} 1 ${at(to)}`;
}

/**
 * A kind's ring: the part in use is drawn in the text grey, the part that feeds no concept in the problem colour,
 * and what is still waiting is left as the empty track. Paths, never circles: this is a gauge, not a page mark.
 */
function KindRing({ k }: { k: KindStat }) {
  const used = k.total ? k.healthy / k.total : 0;
  const lost = k.total ? k.unlinked / k.total : 0;
  return (
    <svg viewBox={`0 0 ${BOX} ${BOX}`} className="size-10" aria-hidden>
      <path d={ringArc(0, 1)} fill="none" strokeWidth={3} className="stroke-border" />
      {used > 0 && <path data-part="healthy" d={ringArc(0, used)} fill="none" strokeWidth={3} strokeLinecap="butt" className="stroke-muted-foreground" />}
      {lost > 0 && <path data-part="unlinked" d={ringArc(used, used + lost)} fill="none" strokeWidth={3} strokeLinecap="butt" style={{ stroke: "var(--bad)" }} />}
    </svg>
  );
}

interface Props {
  nodes: readonly GNode[];
  neighbors: NeighborMap;
  byId: ReadonlyMap<string, GNode>;
}

/**
 * The Health view's dial (flag knowledge-health): the source kinds on a shallow arc at the left edge, one ring each,
 * bare over the graph like the shell's other corners (a ring sits on its own small disc; the names float beside it).
 * It reads health by kind while the map beside it reads health by concept. Resting the pointer on a kind lights the
 * concepts it feeds on the map; pressing it goes inside the kind (./KindView).
 */
export function HealthDial({ nodes, neighbors, byId }: Props) {
  const kinds = useMemo(() => sourceKinds(nodes, neighbors, byId), [nodes, neighbors, byId]);
  const enter = useHealth((s) => s.enter);
  // a fan or the pinned list opening on the left takes the dial's place while it is open
  const covered = useCorners((s) => s.order.includes("pins") || s.order.includes("agent"));
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const spot = (kind: SourceGlyph | null) => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => useGraphUi.setState({ spotIds: kind ? fedConcepts(kind, nodes, neighbors, byId) : null }), kind ? SPOT_IN_MS : SPOT_OUT_MS);
  };
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
      useGraphUi.setState({ spotIds: null });
    },
    [],
  );
  if (!kinds.length) return null;
  const last = Math.max(1, kinds.length - 1);
  const deep = bulge(kinds.length);
  // the dial's line: the parabola the rings sit on, run a little past both ends
  const k = 1 + (2 * OVER) / last;
  const mid = HEAD + C + 2 + (last * PITCH) / 2;
  const reach = (k * last * PITCH) / 2;
  const edge = C + 2 + deep * (1 - k * k);
  const line = `M${edge.toFixed(1)} ${(mid - reach).toFixed(1)}Q${(2 * (C + 2 + deep) - edge).toFixed(1)} ${mid.toFixed(1)} ${edge.toFixed(1)} ${(mid + reach).toFixed(1)}`;
  return (
    <div
      data-health="dial"
      role="group"
      aria-label="Sources by kind"
      className={cn("absolute top-1/2 z-[23] flex -translate-y-1/2 flex-col items-start gap-2 py-1 transition-opacity duration-150 motion-reduce:transition-none", covered ? "pointer-events-none opacity-0" : "opacity-100")}
      style={{ left: EDGE }}
    >
      {deep > 0 && (
        <svg aria-hidden className="pointer-events-none absolute left-0 top-0 -z-10 overflow-visible" width={BOX} height={HEAD + kinds.length * PITCH}>
          <path data-part="dial-line" d={line} fill="none" strokeWidth={1} strokeLinecap="round" className="stroke-border" />
        </svg>
      )}
      <div className="h-4 pl-1 text-[11px] leading-4 text-muted-foreground">Sources by kind</div>
      {kinds.map((kind, i) => {
        const t = (2 * i) / last - 1;
        return (
          <button
            key={kind.kind}
            type="button"
            data-kind={kind.kind}
            aria-label={`${kind.label}: ${kind.total} sources, ${kindLine(kind)}. Open`}
            title={`Open ${kind.label.toLowerCase()}`}
            onClick={() => {
              spot(null);
              enter(kind.kind);
            }}
            onPointerEnter={() => spot(kind.kind)}
            onPointerLeave={() => spot(null)}
            onFocus={() => spot(kind.kind)}
            onBlur={() => spot(null)}
            className={cn("group pointer-events-auto flex flex-none items-center gap-2.5 rounded-full p-0.5 pr-3 text-left", RING)}
            style={{ marginLeft: Math.round(deep * (1 - t * t)) }}
          >
            <span className="relative grid size-10 flex-none place-items-center rounded-full bg-card shadow-[var(--shadow)]">
              <KindRing k={kind} />
              <SourceIcon type={kind.type} className="absolute size-4 text-muted-foreground transition-colors group-hover:text-foreground motion-reduce:transition-none" />
            </span>
            <span className="min-w-0 leading-tight">
              <span className="block whitespace-nowrap text-[12px] text-foreground">
                {kind.label} <span className="tabular-nums text-muted-foreground">{kind.total}</span>
              </span>
              <span className="block whitespace-nowrap text-[11px] text-muted-foreground">{kindLine(kind)}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
