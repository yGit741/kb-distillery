import { useMemo } from "react";
import { useAreaPalette } from "../../style";

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

/** Which picture a loop card shows: one per kind of view; a pinned view (no kind) gets a small graph of its own. */
export type ThumbKind = "concepts" | "sources" | "citations" | "topics" | "map" | "missing";

type P = [number, number];
/** a dot: a round-capped stroke of no length (these pictures are sketches, not node marks) */
const Dot = ({ at, r, hue, cls }: { at: P; r: number; hue?: string; cls?: string }) => (
  <path d={`M${at[0].toFixed(1)} ${at[1].toFixed(1)}h.01`} strokeLinecap="round" strokeWidth={r * 2} stroke={hue} className={cls} />
);
const Edges = ({ pairs, dashed }: { pairs: readonly (readonly [P, P])[]; dashed?: boolean }) => (
  <g className="stroke-border" strokeWidth=".8" strokeDasharray={dashed ? "2 1.6" : undefined}>
    {pairs.map(([a, b], i) => (
      <line key={i} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} />
    ))}
  </g>
);
/** loose clumps: `k` centres, points scattered around them */
function clumps(r: () => number, k: number, per: number, spread: number): { at: P; c: number }[] {
  const centres: P[] = Array.from({ length: k }, (_, i) => [16 + ((i + 0.5) / k) * 68 + (r() - 0.5) * 8, 14 + r() * 36]);
  return centres.flatMap((c, ci) => Array.from({ length: per }, () => ({ at: [c[0] + (r() - 0.5) * spread, c[1] + (r() - 0.5) * spread * 0.8] as P, c: ci })));
}

/**
 * Flag graph-corners: the picture on a loop card, in the area colours (as in the Fan Design mockup). Each kind of view
 * has its own sketch so the cards tell apart at a glance: Concepts ringed marks linked together, Sources small solid
 * dots in loose clumps, Citations a tree of arrows, Topics clumps of one colour each, the Meaning map dots between two
 * axes, Missing links grey pages with dashed pairs. A pinned view gets a small graph seeded by its id. None of them
 * claims to show the kb's own pages.
 */
export function GraphThumb({ kind, seed, className }: { kind?: ThumbKind; seed: string; className?: string }) {
  const hues = useAreaPalette();
  const hue = (i: number) => hues[((i % hues.length) + hues.length) % hues.length]!;
  const art = useMemo(() => {
    const r = rng(hash(seed));
    const pts: P[] = Array.from({ length: 16 }, () => [8 + r() * 84, 7 + r() * 50]);
    const pairs = Array.from({ length: 12 }, (_, i) => [pts[i]!, pts[(i * 5 + 3) % 16]!] as const);
    return { pts, pairs };
  }, [seed]);
  const r = rng(hash(seed) + 3);
  let body: React.ReactNode;
  if (kind === "concepts") {
    const { pts, pairs } = art;
    body = (
      <>
        <Edges pairs={pairs} />
        {pts.slice(0, 13).map((p, i) => (
          <g key={i}>
            <Dot at={p} r={i % 5 ? 3.3 : 4.3} hue={hue(i)} />
            <Dot at={p} r={i % 5 ? 2.1 : 2.9} cls="stroke-card" />
            <Dot at={p} r={i % 5 ? 0.9 : 1.3} hue={hue(i)} />
          </g>
        ))}
      </>
    );
  } else if (kind === "sources") {
    const pts = clumps(r, 3, 8, 26);
    body = (
      <>
        <Edges pairs={pts.slice(0, 10).map((p, i) => [p.at, pts[(i * 3 + 4) % pts.length]!.at] as const)} />
        {pts.map((p, i) => (
          <Dot key={i} at={p.at} r={i % 6 ? 1.9 : 2.6} hue={hue(i % 4 ? 1 : 0)} />
        ))}
      </>
    );
  } else if (kind === "citations") {
    // one founding paper at the top, cited by three, each cited in turn
    const root: P = [50, 11];
    const mid: P[] = [[24, 30], [50, 31], [76, 29]];
    const leaves: P[] = [[12, 52], [28, 53], [42, 52], [58, 53], [72, 52], [88, 51]];
    const cites: [P, P][] = [...mid.map((m): [P, P] => [m, root]), ...leaves.map((l, i): [P, P] => [l, mid[Math.min(2, Math.floor(i / 2))]!])];
    body = (
      <>
        <g className="stroke-muted-foreground" strokeWidth=".7">
          {cites.map(([a, b], i) => {
            const d = Math.hypot(b[0] - a[0], b[1] - a[1]);
            const rr = b === root ? 5.2 : 3.6;
            const e: P = [b[0] - ((b[0] - a[0]) * rr) / d, b[1] - ((b[1] - a[1]) * rr) / d];
            const ux = (b[0] - a[0]) / d;
            const uy = (b[1] - a[1]) / d;
            return (
              <g key={i}>
                <line x1={a[0]} y1={a[1]} x2={e[0]} y2={e[1]} />
                <path d={`M${e[0]} ${e[1]}l${(-ux * 2.6 + uy * 1.4).toFixed(2)} ${(-uy * 2.6 - ux * 1.4).toFixed(2)}M${e[0]} ${e[1]}l${(-ux * 2.6 - uy * 1.4).toFixed(2)} ${(-uy * 2.6 + ux * 1.4).toFixed(2)}`} />
              </g>
            );
          })}
        </g>
        <Dot at={root} r={4.4} hue={hue(0)} />
        {mid.map((m, i) => (
          <Dot key={`m${i}`} at={m} r={3} hue={hue(1 + i)} />
        ))}
        {leaves.map((l, i) => (
          <Dot key={`l${i}`} at={l} r={2.1} hue={hue(4 + (i % 3))} />
        ))}
      </>
    );
  } else if (kind === "topics") {
    const pts = clumps(r, 4, 7, 20);
    body = (
      <>
        <Edges pairs={pts.filter((_, i) => i % 7 < 3).map((p, i, a) => [p.at, a[(i + 1) % a.length]!.at] as const)} />
        {pts.map((p, i) => (
          <Dot key={i} at={p.at} r={2.2} hue={hue(p.c)} />
        ))}
      </>
    );
  } else if (kind === "map") {
    const pts = clumps(r, 3, 7, 22).map((p) => ({ ...p, at: [Math.max(16, p.at[0]), Math.min(50, p.at[1])] as P }));
    body = (
      <>
        <path d="M11 6V55H94" fill="none" className="stroke-muted-foreground" strokeWidth=".8" />
        {pts.map((p, i) => (
          <Dot key={i} at={p.at} r={2} hue={hue(p.c)} />
        ))}
      </>
    );
  } else if (kind === "missing") {
    const pts = art.pts;
    const pairs: [P, P][] = [[pts[0]!, pts[5]!], [pts[2]!, pts[9]!], [pts[7]!, pts[12]!]];
    body = (
      <>
        <Edges pairs={art.pairs.slice(0, 6)} />
        <g strokeWidth=".9" strokeDasharray="2.2 1.6">
          {pairs.map(([a, b], i) => (
            <line key={i} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke={hue(i)} />
          ))}
        </g>
        {pts.map((p, i) => {
          const pi = pairs.findIndex(([a, b]) => a === p || b === p);
          return <Dot key={i} at={p} r={pi >= 0 ? 2.6 : 2} hue={pi >= 0 ? hue(pi) : undefined} cls={pi >= 0 ? undefined : "stroke-muted-foreground/50"} />;
        })}
      </>
    );
  } else {
    // a pinned view: the mockup's mini graph, sixteen pages and twelve links
    const off = hash(seed) % hues.length;
    body = (
      <>
        <Edges pairs={art.pairs} />
        {art.pts.map((p, i) => (
          <Dot key={i} at={p} r={i % 5 ? 2.4 : 3.6} hue={hue(i + off)} />
        ))}
      </>
    );
  }
  return (
    <svg viewBox="0 0 100 64" preserveAspectRatio="xMidYMid slice" className={className} aria-hidden>
      <rect width="100" height="64" className="fill-card" />
      {body}
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
