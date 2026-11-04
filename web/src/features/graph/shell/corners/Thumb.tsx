import { useMemo } from "react";

/** A small deterministic number generator, so a view's picture is the same on every render. */
function rng(seed: number): () => number {
  let s = seed;
  return () => {
    s = Math.sin(s) * 10000;
    return s - Math.floor(s);
  };
}
const hash = (text: string): number => [...text].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 100003, 7);

/**
 * The picture on a pinned-view row. It is a plain sketch of a graph (grey nodes, a few darker hubs), a different
 * one per view so rows are told apart at a glance; it does not claim to show the view's real pages.
 */
export function ViewThumb({ id, className }: { id: string; className?: string }) {
  const art = useMemo(() => {
    const r = rng(hash(id));
    const pts = Array.from({ length: 22 }, (_, i) => ({ x: 6 + r() * 88, y: 5 + r() * 54, hub: i % 7 === 0 }));
    const lines = Array.from({ length: 18 }, (_, i) => [pts[i % pts.length]!, pts[(i * 7 + 3) % pts.length]!] as const);
    return { pts, lines };
  }, [id]);
  return (
    <svg viewBox="0 0 100 64" preserveAspectRatio="xMidYMid slice" className={className} aria-hidden>
      <rect width="100" height="64" className="fill-card" />
      <g className="stroke-border" strokeWidth=".6">
        {art.lines.map(([a, b], i) => (
          <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} />
        ))}
      </g>
      {/* a dot is a round-capped stroke of no length: this sketch is not a node mark */}
      {art.pts.map((p, i) => (
        <path key={i} d={`M${p.x} ${p.y}h.01`} strokeLinecap="round" strokeWidth={p.hub ? 6 : 3.6} className={p.hub ? "stroke-primary" : "stroke-muted-foreground"} />
      ))}
    </svg>
  );
}

/**
 * The picture on a fan card: a dark page with a few lines (the first one coloured), like a document stack. Dark in
 * the light theme; in the dark theme an elevated dark surface, so the cards do not outshine the graph.
 */
export function CardThumb({ accent }: { accent: "primary" | "warn" }) {
  const line = "block h-[3px] rounded-sm bg-background/30 dark:bg-foreground/25";
  return (
    <span
      aria-hidden
      className="flex h-[50px] w-[72px] flex-none flex-col gap-1 rounded-[7px] bg-[color-mix(in_srgb,var(--foreground)_86%,var(--primary))] px-2 py-[7px] shadow-[var(--shadow)] dark:bg-[color-mix(in_srgb,var(--card)_80%,var(--primary))] dark:ring-1 dark:ring-border"
    >
      <i className={`block h-[3px] w-[48%] rounded-sm ${accent === "warn" ? "bg-warn" : "bg-primary"}`} />
      <i className={`${line} w-[88%]`} />
      <i className={`${line} w-full`} />
      <i className={`${line} w-[70%]`} />
    </span>
  );
}
