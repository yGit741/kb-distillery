import { Link } from "@tanstack/react-router";
import { typeColor } from "@/theme/palette";
import { ringLayout, titleOf, type LinkGraph } from "./lib";
import { pageTo } from "./parts";

const trunc = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

/** The page and its neighbours on a ring: solid = links to, dashed = linked from, thick = both. */
export function MiniGraph({ g, slug }: { g: LinkGraph; slug: string }) {
  const ring = ringLayout(g, slug);
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
        <circle cx={centre} cy={centre} r={11} fill={typeColor(g.byId.get(slug)?.type)} className="stroke-foreground" strokeWidth={1.5} />
        {ring.nodes.map((n) => {
          const right = Math.cos(n.angle) >= 0;
          const title = titleOf(g, n.id);
          return (
            <Link key={n.id} to={pageTo(n.id)} aria-label={title} className="outline-none [&:focus-visible_circle]:stroke-primary [&:focus-visible_circle]:stroke-2">
              <title>{title}</title>
              <circle cx={n.x} cy={n.y} r={n.radius} fill={typeColor(g.byId.get(n.id)?.type)} />
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
      <p className="flex flex-wrap items-center gap-x-3 text-xs text-muted-foreground">
        <span>solid: links to</span>
        <span>dashed: linked from</span>
        <span>thick: both</span>
        {ring.total > ring.nodes.length && <span>showing {ring.nodes.length} of {ring.total}</span>}
      </p>
    </div>
  );
}
