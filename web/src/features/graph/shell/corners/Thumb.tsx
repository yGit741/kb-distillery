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
export type ThumbKind =
  | "concepts" | "sources" | "citations" | "topics" | "map" | "missing" | "code" | "flow" | "evidence"
  // flag graph.artifacts: the layer's own card, and one picture per kind of view of the intermediate layers
  | "layers" | "deps" | "pack" | "chords" | "switches" | "ribbons" | "pipeline" | "build" | "outputs" | "arcs" | "facts";

const ART_THUMB: Readonly<Record<string, ThumbKind>> = {
  dependencies: "deps",
  structure: "pack",
  "change-coupling": "chords",
  options: "switches",
  "symbol-flow": "ribbons",
  "model-pipeline": "pipeline",
  build: "build",
  outputs: "outputs",
};

/**
 * Flag graph.artifacts: the picture of a template's view. The code toolkit's views are known by id; another template's
 * view gets the picture of what it draws (its relations and types), and a containment picture when nothing says more.
 */
export function artifactThumb(v: { id: string; types?: readonly string[] | null; relations?: readonly string[] | null; nest?: string | null }): ThumbKind {
  const known = ART_THUMB[v.id];
  if (known) return known;
  const rel = new Set(v.relations ?? []);
  const has = (...kinds: string[]) => kinds.some((k) => rel.has(k));
  if (has("imports", "depends-on")) return "deps";
  if (has("co-changes")) return "chords";
  if (v.types?.includes("Option")) return "switches";
  if (has("produces", "consumes")) return "ribbons";
  if (v.nest === "none" || has("feeds", "loads")) return "pipeline";
  if (has("builds", "links")) return "build";
  if (has("writes")) return "outputs";
  return "pack";
}

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
/** a round shape as a path of two arcs: a container, a ring, a knob (a sketch like the dots, not a node mark) */
const Round = ({ at, r, ...rest }: { at: P; r: number } & React.SVGProps<SVGPathElement>) => (
  <path d={`M${at[0] - r} ${at[1]}a${r} ${r} 0 1 0 ${2 * r} 0a${r} ${r} 0 1 0 ${-2 * r} 0z`} {...rest} />
);
/** a link that leaves and arrives level, bending in between (left to right) */
const flow = (a: P, b: P): string => {
  const m = (a[0] + b[0]) / 2;
  return `M${a[0]} ${a[1]}C${m} ${a[1]} ${m} ${b[1]} ${b[0]} ${b[1]}`;
};
/** a small rounded square: a file, a table, a piece of code */
const Tile = ({ at, s, hue, cls }: { at: P; s: number; hue?: string; cls?: string }) => (
  <rect x={at[0] - s / 2} y={at[1] - s / 2} width={s} height={s} rx={s * 0.28} fill={hue} className={cls} />
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
  } else if (kind === "code") {
    // an artifact view that nests: a few folders, each a ring of files, linked across
    const folders: P[] = [[24, 22], [70, 18], [48, 46], [82, 46]];
    const files = folders.flatMap((c, ci) => Array.from({ length: 4 }, (_, i): { at: P; c: number } => ({ at: [c[0] + Math.cos(i * 1.6 + ci) * 9, c[1] + Math.sin(i * 1.6 + ci) * 7], c: ci })));
    body = (
      <>
        <Edges pairs={[[folders[0]!, folders[1]!], [folders[0]!, folders[2]!], [folders[2]!, folders[3]!], [folders[1]!, folders[3]!]]} />
        {folders.map((c, i) => (
          <g key={`f${i}`}>
            <Dot at={c} r={5.2} hue={hue(i)} />
            <Dot at={c} r={4} cls="stroke-card" />
          </g>
        ))}
        {files.map((f, i) => (
          <Dot key={i} at={f.at} r={1.5} hue={hue(f.c)} />
        ))}
      </>
    );
  } else if (kind === "flow") {
    // an artifact view drawn flat: a pipeline, stage to stage
    const stages: P[][] = [[[12, 20], [12, 44]], [[38, 14], [38, 32], [38, 50]], [[64, 22], [64, 42]], [[88, 32]]];
    const pairs: [P, P][] = stages.slice(1).flatMap((col, ci) => col.flatMap((b) => stages[ci]!.map((a): [P, P] => [a, b])));
    body = (
      <>
        <Edges pairs={pairs} />
        {stages.flatMap((col, ci) => col.map((p, i) => <Dot key={`${ci}-${i}`} at={p} r={ci === 3 ? 3.6 : 2.6} hue={hue(ci)} />))}
      </>
    );
  } else if (kind === "evidence") {
    // pages above, the files their facts cite below
    const pages: P[] = [[18, 16], [42, 12], [66, 16], [86, 12]];
    const files: P[] = [[10, 50], [26, 52], [40, 48], [56, 52], [72, 49], [90, 52]];
    const cites: [P, P][] = [[pages[0]!, files[0]!], [pages[0]!, files[1]!], [pages[1]!, files[2]!], [pages[1]!, files[3]!], [pages[2]!, files[3]!], [pages[2]!, files[4]!], [pages[3]!, files[5]!]];
    body = (
      <>
        <Edges pairs={cites} dashed />
        {pages.map((p, i) => (
          <g key={`p${i}`}>
            <Dot at={p} r={3.6} hue={hue(i)} />
            <Dot at={p} r={2.3} cls="stroke-card" />
            <Dot at={p} r={1} hue={hue(i)} />
          </g>
        ))}
        {files.map((p, i) => (
          <Dot key={`f${i}`} at={p} r={2} cls="stroke-muted-foreground" />
        ))}
      </>
    );
  } else if (kind === "layers") {
    // the layer's own card: three planes, the middle one (what the builder makes between sources and concepts) lit
    const plane = (y: number) => `50,${y - 8} 80,${y} 50,${y + 8} 20,${y}`;
    const dots: [number, P[]][] = [
      [35, [[40, 35], [52, 37], [61, 34]]],
      [25, [[38, 25], [50, 23], [57, 27], [64, 24]]],
      [15, [[44, 15], [55, 16]]],
    ];
    body = (
      <>
        {dots.map(([y, pts], i) => (
          <g key={y}>
            <polygon points={plane(y)} fill={hue(i === 1 ? 0 : i + 1)} fillOpacity={i === 1 ? 0.34 : 0.13} stroke={hue(i === 1 ? 0 : i + 1)} strokeOpacity={i === 1 ? 1 : 0.55} strokeWidth=".9" strokeLinejoin="round" />
            {pts.map((p, k) => (
              <Dot key={k} at={p} r={i === 1 ? 1.5 : 1.1} hue={hue(i === 1 ? 0 : i + 1)} />
            ))}
          </g>
        ))}
      </>
    );
  } else if (kind === "deps") {
    // who imports whom: three ranks, left to right
    const cols: P[][] = [[[28, 13], [28, 26], [28, 39]], [[54, 11], [54, 24], [54, 38]], [[80, 17], [80, 33]]];
    const links: [number, number, number][] = [[0, 0, 0], [0, 0, 1], [0, 1, 1], [0, 2, 1], [0, 2, 2], [1, 0, 0], [1, 1, 0], [1, 1, 1], [1, 2, 1]];
    body = (
      <>
        <g fill="none" strokeWidth="1.1" strokeLinecap="round">
          {links.map(([c, i, j], k) => (
            <path key={k} d={flow([cols[c]![i]![0] + 3, cols[c]![i]![1]], [cols[c + 1]![j]![0] - 3.6, cols[c + 1]![j]![1]])} stroke={hue(c)} strokeOpacity=".5" />
          ))}
        </g>
        {cols.flatMap((col, c) => col.map((p, i) => <Tile key={`${c}-${i}`} at={p} s={c === 2 ? 8 : 6.2} hue={hue(c)} />))}
      </>
    );
  } else if (kind === "pack") {
    // containment: repositories holding folders holding files, and a call or two across
    const groups: { c: P; r: number; kids: [number, number, number][] }[] = [
      { c: [36, 25], r: 16.5, kids: [[29, 20, 5.2], [41, 19, 6], [35, 32, 6.2]] },
      { c: [70, 26], r: 14.5, kids: [[64, 21, 4.8], [75, 23, 5.4], [69, 33, 5]] },
    ];
    body = (
      <>
        {groups.map((g, gi) => (
          <g key={gi}>
            <Round at={g.c} r={g.r} fill={hue(gi)} fillOpacity=".1" stroke={hue(gi)} strokeOpacity=".5" strokeWidth=".8" />
            {g.kids.map(([x, y, r], k) => (
              <g key={k}>
                <Round at={[x, y]} r={r} fill={hue(gi)} fillOpacity=".26" stroke={hue(gi)} strokeWidth=".8" />
                <Dot at={[x - r * 0.3, y - r * 0.15]} r={0.95} hue={hue(gi)} />
                <Dot at={[x + r * 0.35, y + r * 0.05]} r={0.95} hue={hue(gi)} />
                <Dot at={[x, y + r * 0.45]} r={0.95} hue={hue(gi)} />
              </g>
            ))}
          </g>
        ))}
        <g fill="none" strokeWidth=".9" strokeLinecap="round" className="stroke-muted-foreground">
          <path d="M41 19Q52 9 64 21" />
          <path d="M35 32Q52 43 69 33" />
        </g>
      </>
    );
  } else if (kind === "chords") {
    // files that change together: a ring of files, bigger the more they change, chords thicker the more they change together
    const size = [3.1, 1.7, 2.4, 1.5, 2.7, 1.6, 2.2, 1.5, 2];
    const at = (i: number): P => [52 + 15.5 * Math.cos(((i * 40 - 90) * Math.PI) / 180), 25 + 15.5 * Math.sin(((i * 40 - 90) * Math.PI) / 180)];
    const chords: [number, number, number][] = [[0, 4, 2.2], [0, 2, 1.4], [2, 6, 1], [4, 7, 1.6], [1, 5, 0.7], [3, 8, 0.8], [6, 8, 1.2]];
    body = (
      <>
        <Round at={[52, 25]} r={15.5} fill="none" className="stroke-border" strokeWidth=".7" />
        <g fill="none" strokeLinecap="round">
          {chords.map(([a, b, w], k) => {
            const [p, q] = [at(a), at(b)];
            // pulled toward the centre, so the chords bow like a chord diagram's
            const c: P = [52 + ((p[0] + q[0]) / 2 - 52) * 0.25, 25 + ((p[1] + q[1]) / 2 - 25) * 0.25];
            return <path key={k} d={`M${p[0].toFixed(1)} ${p[1].toFixed(1)}Q${c[0].toFixed(1)} ${c[1].toFixed(1)} ${q[0].toFixed(1)} ${q[1].toFixed(1)}`} stroke={hue(a)} strokeOpacity=".45" strokeWidth={w} />;
          })}
        </g>
        {size.map((r, i) => (
          <Dot key={i} at={at(i)} r={r} hue={hue(i)} />
        ))}
      </>
    );
  } else if (kind === "switches") {
    // options: switches on the left, the code that reads each on the right
    const pills: [number, boolean][] = [[13, true], [25, false], [37, true]];
    const code: P[] = [[66, 11], [80, 18], [68, 26], [82, 33], [70, 40]];
    const reads: [number, number][] = [[0, 0], [0, 1], [1, 2], [2, 3], [2, 4]];
    body = (
      <>
        <g fill="none" strokeWidth="1" strokeLinecap="round">
          {reads.map(([p, c], k) => (
            <path key={k} d={flow([37.5, pills[p]![0]], [code[c]![0] - 3.4, code[c]![1]])} stroke={pills[p]![1] ? hue(p) : undefined} className={pills[p]![1] ? undefined : "stroke-muted-foreground/60"} strokeOpacity=".55" strokeDasharray={pills[p]![1] ? undefined : "1.8 1.6"} />
          ))}
        </g>
        {pills.map(([y, on], i) => (
          <g key={i}>
            <rect x="24" y={y - 3.3} width="12.6" height="6.6" rx="3.3" fill={on ? hue(i) : undefined} className={on ? undefined : "fill-muted-foreground/35"} />
            <Round at={[on ? 33.3 : 27.3, y]} r={2.2} className="fill-card" />
          </g>
        ))}
        {code.map((p, k) => {
          const by = reads.find(([, c]) => c === k)![0];
          return <Tile key={k} at={p} s={6} hue={pills[by]![1] ? hue(by) : undefined} cls={pills[by]![1] ? undefined : "fill-muted-foreground/50"} />;
        })}
      </>
    );
  } else if (kind === "ribbons") {
    // who produces a symbol and who waits for it: producers, symbols, consumers, joined by bands
    const bars: [number, number, number, number][] = [
      [22, 9, 19, 0], [22, 21, 29, 1], [22, 31, 41, 2],
      [50, 10, 17, 0], [50, 19, 27, 1], [50, 29, 33, 2], [50, 35, 41, 2],
      [78, 9, 21, 0], [78, 24, 32, 1], [78, 34, 41, 2],
    ];
    const bands: [P, P, number, number][] = [
      [[24.4, 12], [50, 13.5], 5, 0], [[24.4, 17], [50, 21], 3.4, 0], [[24.4, 25], [50, 24.5], 5, 1], [[24.4, 33.5], [50, 31], 3.6, 2], [[24.4, 38.5], [50, 38], 4.6, 2],
      [[52.4, 13.5], [78, 13], 5, 0], [[52.4, 21], [78, 18.5], 3.4, 0], [[52.4, 24.5], [78, 28], 5, 1], [[52.4, 31], [78, 30.5], 2.6, 2], [[52.4, 38], [78, 37.5], 5, 2],
    ];
    body = (
      <>
        <g fill="none">
          {bands.map(([a, b, w, h], k) => (
            <path key={k} d={flow(a, b)} stroke={hue(h)} strokeOpacity=".32" strokeWidth={w} />
          ))}
        </g>
        {bars.map(([x, y0, y1, h], k) => (
          <rect key={k} x={x} y={y0} width="2.4" height={y1 - y0} rx=".8" fill={hue(h)} />
        ))}
      </>
    );
  } else if (kind === "pipeline") {
    // a model pipeline: stage after stage, each a block of layers, the tensors passed along
    const blocks: [number, number][] = [[22, 28], [40, 21], [58, 14], [76, 22]];
    body = (
      <>
        {blocks.map(([x, h], i) => (
          <g key={i}>
            <rect x={x} y={25 - h / 2} width="9" height={h} rx="2" fill={hue(i)} fillOpacity=".22" stroke={hue(i)} strokeWidth=".9" />
            {[-0.25, 0, 0.25].map((f) => (
              <line key={f} x1={x + 2} x2={x + 7} y1={25 + f * h} y2={25 + f * h} stroke={hue(i)} strokeOpacity=".7" strokeWidth=".9" strokeLinecap="round" />
            ))}
          </g>
        ))}
        <g fill="none" strokeWidth=".9" strokeLinecap="round" strokeLinejoin="round" className="stroke-muted-foreground">
          {[...blocks.slice(1).map(([x]) => x - 1.6), 90.4].map((x, i) => (
            <path key={i} d={`M${x - 5.6} 25H${x}M${x - 2} 23l2 2l-2 2`} />
          ))}
        </g>
        <Dot at={[93.6, 25]} r={2.4} hue={hue(4)} />
      </>
    );
  } else if (kind === "build") {
    // the build: files compiled into libraries, libraries linked into what ships
    const leaves: [P, number][] = [[[24, 9], 0], [[24, 15], 0], [[24, 21], 0], [[24, 30], 1], [[24, 36], 1], [[24, 41], 1]];
    const libs: P[] = [[52, 15], [52, 35.5]];
    body = (
      <>
        <g fill="none" strokeLinecap="round">
          {leaves.map(([p, g], k) => (
            <path key={k} d={flow([p[0] + 2.4, p[1]], [libs[g]![0] - 5, libs[g]![1]])} stroke={hue(g)} strokeOpacity=".5" strokeWidth=".9" />
          ))}
          {libs.map((l, g) => (
            <path key={g} d={flow([l[0] + 5, l[1]], [72.6, 25.5])} stroke={hue(g)} strokeOpacity=".6" strokeWidth="1.7" />
          ))}
        </g>
        {leaves.map(([p, g], k) => (
          <Tile key={k} at={p} s={4.2} hue={hue(g)} />
        ))}
        {libs.map((l, g) => (
          <g key={g}>
            <Round at={l} r={4.8} fill={hue(g)} fillOpacity=".24" stroke={hue(g)} strokeWidth="1" />
            <Dot at={l} r={1.6} hue={hue(g)} />
          </g>
        ))}
        <rect x="73" y="18.5" width="14" height="14" rx="3.4" fill={hue(2)} />
        <path d="M76.6 25.6l2.4 2.4l4.6-5" fill="none" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="stroke-card" />
      </>
    );
  } else if (kind === "outputs") {
    // the outputs: code on the left, the tables and formats it writes on the right
    const writers: P[] = [[26, 13], [26, 25.5], [26, 38]];
    const tables: [number, number][] = [[9, 0], [28, 1]];
    const writes: [number, number][] = [[0, 0], [1, 0], [1, 1], [2, 1]];
    body = (
      <>
        <g fill="none" strokeWidth="1" strokeLinecap="round">
          {writes.map(([w, t], k) => (
            <path key={k} d={flow([writers[w]![0] + 3.4, writers[w]![1]], [59, tables[t]![0] + 6.5])} stroke={hue(tables[t]![1])} strokeOpacity=".5" />
          ))}
        </g>
        {writers.map((p, k) => (
          <Tile key={k} at={p} s={6} cls="fill-muted-foreground/60" />
        ))}
        {tables.map(([y, h]) => (
          <g key={y}>
            <rect x="60" y={y} width="25" height="13" rx="1.8" className="fill-card" stroke={hue(h)} strokeWidth=".9" />
            <path d={`M60 ${y + 1.8}a1.8 1.8 0 0 1 1.8-1.8h21.4a1.8 1.8 0 0 1 1.8 1.8v2.2h-25z`} fill={hue(h)} />
            <path d={`M60.6 ${y + 7}h23.8M60.6 ${y + 10}h23.8M68.4 ${y + 4}v9M76.8 ${y + 4}v9`} fill="none" stroke={hue(h)} strokeOpacity=".4" strokeWidth=".6" />
          </g>
        ))}
      </>
    );
  } else if (kind === "arcs") {
    // citations: the papers in a line, an arc from each to the paper it cites; the most cited are the biggest
    const xs = [16, 27, 37, 48, 58, 69, 79, 88];
    const size = [3.2, 1.6, 2.5, 1.5, 2.9, 1.6, 2, 1.5];
    const cites: [number, number][] = [[1, 0], [2, 0], [4, 0], [3, 2], [4, 2], [6, 2], [5, 4], [6, 4], [7, 4], [7, 5]];
    body = (
      <>
        <g fill="none" strokeWidth=".9" strokeLinecap="round">
          {cites.map(([from, to], k) => {
            const r = (xs[from]! - xs[to]!) / 2;
            return <path key={k} d={`M${xs[to]} 38A${r} ${r} 0 0 1 ${xs[from]} 38`} stroke={hue(to)} strokeOpacity=".55" />;
          })}
        </g>
        {xs.map((x, i) => (
          <Dot key={i} at={[x, 38]} r={size[i]!} hue={hue(i)} />
        ))}
      </>
    );
  } else if (kind === "facts") {
    // evidence: pages above, the pieces of code their facts are about below
    const pages: P[] = [[32, 13], [50, 12], [68, 13], [86, 12]];
    const code: P[] = [[20, 37], [34, 38], [48, 37], [62, 38], [76, 37], [90, 38]];
    const cites: [number, number][] = [[0, 0], [0, 1], [1, 2], [1, 3], [2, 3], [2, 4], [3, 5]];
    body = (
      <>
        <g fill="none" strokeWidth=".9" strokeDasharray="2 1.6" strokeLinecap="round">
          {cites.map(([p, c], k) => (
            <path key={k} d={`M${pages[p]![0]} ${pages[p]![1] + 4}C${pages[p]![0]} 26 ${code[c]![0]} 26 ${code[c]![0]} ${code[c]![1] - 3.4}`} stroke={hue(p)} strokeOpacity=".6" />
          ))}
        </g>
        {pages.map((p, i) => (
          <g key={i}>
            <Dot at={p} r={3.6} hue={hue(i)} />
            <Dot at={p} r={2.3} cls="stroke-card" />
            <Dot at={p} r={1} hue={hue(i)} />
          </g>
        ))}
        {code.map((p, k) => (
          <Tile key={k} at={p} s={5.4} cls="fill-muted-foreground/60" />
        ))}
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
