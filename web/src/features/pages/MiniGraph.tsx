import { Link } from "@tanstack/react-router";
import { useMemo } from "react";
import { colorChannel, GraphLegend, NodeMarkG, personInitials } from "@/features/graph/encoding";
import { areaSlots } from "@/features/graph/style";
import type { GNode } from "@/features/graph/types";
import { cardNode, ringLayout, titleOf, type LinkGraph } from "./lib";
import { pageTo, usePageSearch } from "./parts";

const trunc = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

/** From this radius (SVG px) a source shows its type glyph inside its dot. */
const GLYPH_R = 7;
/** The ring sizes a neighbour by its links (./lib ringLayout). */
const SIZE = { by: "degree", title: "links" } as const;

/**
 * The page and its neighbours on a ring: solid = links to, dashed = linked from, thick = both. Nodes use the shared
 * encoding (type = mark, colour = theme like the Full Graph's Map) and the compact legend sits under the ring.
 */
export function MiniGraph({ g, slug }: { g: LinkGraph; slug: string }) {
  const ring = useMemo(() => ringLayout(g, slug), [g, slug]);
  const search = usePageSearch();
  // theme colours ranked over every page, the way the Full Graph ranks its model
  const color = useMemo(() => colorChannel("area", { areas: areaSlots([...g.byId.values()]) }), [g]);
  const nodes = useMemo(
    () => [slug, ...ring.nodes.map((n) => n.id)].map((id) => g.byId.get(id)).filter((c) => !!c).map(cardNode),
    [g, slug, ring],
  );
  const byId = useMemo(() => new Map<string, GNode>(nodes.map((n) => [n.id, n])), [nodes]);
  const initials = useMemo(() => personInitials(nodes), [nodes]);
  const mark = (id: string, x: number, y: number, r: number) => {
    const n = byId.get(id);
    if (!n) return null;
    return <NodeMarkG type={n.type} x={x} y={y} r={r} color={color.color(n)} background="var(--card)" initials={initials.get(id)} glyph={r >= GLYPH_R} />;
  };
  if (!ring.total) return <p className="text-sm text-muted-foreground">No links yet.</p>;
  const { size, centre } = ring;
  const labelled = ring.nodes.length <= 20;
  const pad = labelled ? 72 : 12;
  const at = new Map(ring.nodes.map((n) => [n.id, n]));
  return (
    <div className="flex flex-col gap-2">
      <svg viewBox={`${-pad} -6 ${size + pad * 2} ${size + 12}`} role="group" aria-label="Neighbour graph" className="w-full">
        {ring.cross.map(([s, t]) => {
          const a = at.get(s)!;
          const b = at.get(t)!;
          return (
            <path
              key={`${s}>${t}`}
              d={`M${a.x},${a.y} Q${centre},${centre} ${b.x},${b.y}`}
              className="fill-none stroke-border"
              strokeWidth={0.8}
            />
          );
        })}
        {ring.nodes.map((n) => (
          <line
            key={n.id}
            x1={centre}
            y1={centre}
            x2={n.x}
            y2={n.y}
            className={n.dir === "in" ? "stroke-muted-foreground" : "stroke-primary"}
            strokeWidth={n.dir === "both" ? 2.2 : 1.2}
            strokeDasharray={n.dir === "in" ? "4 3" : undefined}
          />
        ))}
        {/* the page itself: the focus ring of the shared state language */}
        <circle cx={centre} cy={centre} r={11 + 3} fill="none" className="stroke-primary" strokeWidth={2.5} />
        {mark(slug, centre, centre, 11)}
        {ring.nodes.map((n) => {
          const right = Math.cos(n.angle) >= 0;
          const title = titleOf(g, n.id);
          return (
            <Link key={n.id} to={pageTo(n.id)} search={search} aria-label={title} className="outline-none [&:focus-visible_.focus-ring]:stroke-primary">
              <title>{title}</title>
              {/* keyboard focus: a ring of its own, so the mark keeps its strokes */}
              <circle cx={n.x} cy={n.y} r={n.radius + 3} fill="none" stroke="transparent" strokeWidth={2} className="focus-ring" />
              {mark(n.id, n.x, n.y, n.radius)}
              {labelled && (
                <text
                  x={n.x + (right ? n.radius + 3 : -n.radius - 3)}
                  y={n.y + 3}
                  textAnchor={right ? "start" : "end"}
                  className="fill-foreground"
                  fontSize={9}
                >
                  {trunc(title, 15)}
                </text>
              )}
            </Link>
          );
        })}
      </svg>
      <GraphLegend nodes={nodes} color={color} size={SIZE} density="compact" />
      <p className="flex flex-wrap items-center gap-x-3 text-xs text-muted-foreground">
        <span>solid: links to</span>
        <span>dashed: linked from</span>
        <span>thick: both</span>
        {ring.total > ring.nodes.length && <span>showing {ring.nodes.length} of {ring.total}</span>}
      </p>
    </div>
  );
}
