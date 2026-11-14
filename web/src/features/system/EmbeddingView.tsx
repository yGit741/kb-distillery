import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useDataSource } from "@/api";
import { useFlag } from "@/flags/useFlag";
import type { EmbeddingReport } from "@/api/types";
import { CopyButton } from "@/components/CopyButton";
import { Empty, ErrorState, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useApiQuery } from "@/lib/useApiQuery";
import { cn } from "@/lib/utils";
import { clusterColor } from "@/theme/palette";

type Page = EmbeddingReport["missing"][number];
type Point = EmbeddingReport["points"][number];
type Axes = { x: number; y: number };

const BACKENDS = ["subscription", "api", "batch"] as const;
const BACKEND_LABEL: Record<string, string> = { subscription: "Subscription", api: "API", batch: "Batch API" };
const clusterLabel = (c: { id: number; name?: string | null }) => c.name || `Cluster ${c.id + 1}`;

/** Names by LLM: pick the billing backend, start the run, and say where the names stand. */
function NamesBar({ r }: { r: EmbeddingReport }) {
  const ds = useDataSource();
  const qc = useQueryClient();
  const names = r.names;
  const [backend, setBackend] = useState<string>(names?.default_backend ?? "subscription");
  const run = useMutation({ mutationFn: () => ds.nameEmbedding(backend), onSuccess: (data) => qc.setQueryData(["embedding"], data) });
  if (!names) return null;
  const serverRunning = names.state === "running";
  const running = serverRunning || run.isPending;
  const runBackend = serverRunning ? (names.backend ?? backend) : backend;
  // A refused click (409, 405) is shown until the next state the server reports; after that the server's word counts.
  const refused = run.error instanceof Error && run.data === undefined && run.failureCount > 0 ? run.error.message : null;
  const failure = names.state === "current" ? null : (refused ?? names.error);
  const made = names.at ? ` on ${BACKEND_LABEL[names.backend ?? ""] ?? names.backend}${names.usd ? `, $${names.usd.toFixed(2)}` : ""}` : "";
  const status =
    running ? `Naming on ${BACKEND_LABEL[runBackend]}. ${runBackend === "batch" ? "A batch can take hours; the names appear here when it is done." : "This takes about a minute."}`
    : names.state === "current" ? `Named by ${names.model}${made}.${names.failed ? ` ${names.failed} could not be named.` : ""}`
    : names.state === "stale" ? "The vectors changed since the names were made. Name them again."
    : "No names yet. An LLM can name each component and cluster from its pages.";
  return (
    <div className="flex flex-col gap-1.5 rounded-lg border p-3" data-testid="embedding-names">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="flex items-center gap-1" role="group" aria-label="Billing backend for naming">
          <span className="text-xs text-muted-foreground">Billing</span>
          {BACKENDS.map((b) => (
            <button
              key={b}
              type="button"
              aria-pressed={backend === b}
              disabled={running}
              onClick={() => setBackend(b)}
              className="rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-accent disabled:opacity-60 aria-pressed:bg-accent-soft aria-pressed:text-primary"
            >
              {BACKEND_LABEL[b]}
            </button>
          ))}
        </div>
        <Button size="sm" variant="secondary" disabled={running} onClick={() => run.mutate()}>
          {names.state === "current" ? "Name again" : "Name dimensions and clusters"}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground" aria-live="polite">{status}</p>
      {failure && !running && <p className="text-xs text-bad" role="alert">The last run made no names: {failure}</p>}
    </div>
  );
}

const pct = (v: number) => `${(v * 100).toFixed(1)}%`;

const REBUILD = "pixi run vectors-build";
const W = 1000;
const H = 600;
const PAD = 16;
const pageTo = (slug: string) => `/pages/${encodeURIComponent(slug)}` as "/";

function PageChips({ label, hint, pages }: { label: string; hint: string; pages: Page[] }) {
  if (!pages.length) return null;
  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-sm">
        <span className="font-medium">{label}</span> <span className="text-muted-foreground">({pages.length}) {hint}</span>
      </p>
      <ul className="flex flex-wrap gap-1.5">
        {pages.slice(0, 40).map((p) => (
          <li key={p.slug} className="min-w-0 max-w-full">
            <Link to={pageTo(p.slug)} title={p.title} className="block max-w-full truncate rounded-full border px-2 py-0.5 text-xs hover:bg-accent">
              {p.title}
            </Link>
          </li>
        ))}
        {pages.length > 40 && <li className="px-1 py-0.5 text-xs text-muted-foreground">and {pages.length - 40} more</li>}
      </ul>
    </div>
  );
}

function HealthCard({ r }: { r: EmbeddingReport }) {
  const behind = r.missing.length + r.changed.length + r.removed.length;
  const state = !r.built ? "Not built yet" : r.ok ? "Up to date" : behind ? "Behind the cards" : "Needs attention";
  const facts: [string, string][] = [
    ["Vectors", `${r.vectors.toLocaleString()} of ${r.cards.toLocaleString()} cards`],
    ["Dimensions", r.dim ? r.dim.toLocaleString() : "none"],
    ["Model", r.model ?? "none"],
  ];
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <span aria-hidden className={cn("size-2 rounded-full", r.ok ? "bg-ok" : "bg-warn")} />
          <span data-testid="embedding-state">{state}</span>
        </CardTitle>
        <CardDescription>One vector per page card (title and summary){r.built && !r.ok && !behind ? `. ${r.line}` : ", compared with the cards as they are now."}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
          {facts.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-muted-foreground">{k}</dt>
              <dd className="min-w-0 break-words tabular-nums">{v}</dd>
            </div>
          ))}
        </dl>
        {!r.ok && (
          <div className="flex items-center gap-2">
            <code className="min-w-0 flex-1 truncate rounded bg-muted px-2 py-1 text-xs">{REBUILD}</code>
            <CopyButton text={REBUILD} />
          </div>
        )}
        <PageChips label="Changed" hint="edited since their vector was made" pages={r.changed} />
        <PageChips label="Missing" hint="have a card but no vector" pages={r.missing} />
        <PageChips label="Removed" hint="have a vector but no card any more" pages={r.removed} />
      </CardContent>
    </Card>
  );
}

function AxisPicker({ label, value, count, onPick, titles }: { label: string; value: number; count: number; onPick: (i: number) => void; titles: (string | undefined)[] }) {
  return (
    <div className="flex items-center gap-1" role="group" aria-label={`${label} axis component`}>
      <span className="w-12 text-xs text-muted-foreground">{label} axis</span>
      {Array.from({ length: count }, (_, i) => (
        <button
          key={i}
          type="button"
          aria-pressed={value === i}
          title={titles[i]}
          onClick={() => onPick(i)}
          className="size-6 rounded-md text-xs tabular-nums text-muted-foreground hover:bg-accent aria-pressed:bg-accent-soft aria-pressed:text-primary"
        >
          {i + 1}
        </button>
      ))}
    </div>
  );
}

function MapCard({ r, axes, setAxes }: { r: EmbeddingReport; axes: Axes; setAxes: (a: Axes) => void }) {
  const navigate = useNavigate();
  const [pinned, setPinned] = useState<number | null>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const [point, setPoint] = useState<Point | null>(null);
  const active = hovered ?? pinned;
  const count = r.components?.length ?? 0;
  // A report with fewer components than the picked axis (after a rebuild) falls back to the first two.
  if (count > 1 && (axes.x >= count || axes.y >= count)) axes = { x: 0, y: 1 };
  const at = (p: Point, i: number, fallback: number) => p.pc?.[i] ?? fallback;
  const titles = (r.components ?? []).map((c) => (c.low_name && c.high_name ? `${c.low_name} to ${c.high_name}` : undefined));
  const axisName = (i: number) => titles[i] ?? `component ${i + 1}`;
  const nameOf = new Map(r.clusters.map((c) => [c.id, clusterLabel(c)]));
  const x = (p: Point) => PAD + at(p, axes.x, p.x) * (W - 2 * PAD);
  const y = (p: Point) => PAD + (1 - at(p, axes.y, p.y)) * (H - 2 * PAD);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Semantic map</CardTitle>
        <CardDescription>
          Each dot is a page, placed along two principal components of the vectors, so pages close in meaning sit close together. {r.k} clusters, separation {r.silhouette.toFixed(2)} (silhouette, 1 is perfectly apart).
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="flex min-w-0 flex-col gap-1">
          {count > 2 && (
            <div className="flex flex-wrap gap-x-6 gap-y-1">
              <AxisPicker label="X" value={axes.x} count={count} onPick={(i) => setAxes({ ...axes, x: i })} titles={titles} />
              <AxisPicker label="Y" value={axes.y} count={count} onPick={(i) => setAxes({ ...axes, y: i })} titles={titles} />
            </div>
          )}
          <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Map of ${r.points.length} pages in ${r.k} clusters`} className="w-full rounded-lg border bg-background">
            {r.points.map((p) => (
              <circle
                key={p.slug}
                data-cluster={p.cluster}
                cx={x(p)}
                cy={y(p)}
                r={point?.slug === p.slug ? 8 : 5}
                fill={clusterColor(p.cluster)}
                opacity={active === null || active === p.cluster ? 0.85 : 0.12}
                className="cursor-pointer stroke-background"
                strokeWidth={1}
                onMouseEnter={() => setPoint(p)}
                onMouseLeave={() => setPoint((cur) => (cur?.slug === p.slug ? null : cur))}
                onClick={() => void navigate({ to: pageTo(p.slug) })}
              />
            ))}
          </svg>
          <p className="h-5 truncate text-xs text-muted-foreground" aria-live="polite">
            {point ? `${point.title} · ${nameOf.get(point.cluster) ?? `cluster ${point.cluster + 1}`}` : count > 1 ? `Left to right: ${axisName(axes.x)}. Bottom to top: ${axisName(axes.y)}.` : "Hover a dot for its page, click to open it."}
          </p>
        </div>
        <div className="flex min-w-0 flex-col gap-1">
          <p className="text-xs font-medium text-muted-foreground">Colour = cluster (largest first). Click one to keep it highlighted.</p>
          <ul className="flex flex-col" onMouseLeave={() => setHovered(null)}>
            {r.clusters.map((c) => (
              <li key={c.id} className="border-b last:border-b-0" onMouseEnter={() => setHovered(c.id)}>
                <button
                  type="button"
                  aria-pressed={pinned === c.id}
                  onClick={() => setPinned((cur) => (cur === c.id ? null : c.id))}
                  className="flex w-full items-center gap-2 rounded-md px-1 pt-2 text-left text-sm hover:bg-accent aria-pressed:bg-accent-soft"
                >
                  <span aria-hidden className="size-3 shrink-0 rounded-full" style={{ background: clusterColor(c.id) }} />
                  <span className="min-w-0 font-medium">{clusterLabel(c)}</span>
                  <span className="text-muted-foreground tabular-nums">{c.size} pages</span>
                  <span className="ml-auto text-xs text-muted-foreground tabular-nums" title="Mean cosine of its pages to the cluster centre">
                    cohesion {c.cohesion.toFixed(2)}
                  </span>
                </button>
                {c.why && <p className="px-1 pl-6 text-xs">{c.why}</p>}
                <p className="px-1 pb-2 pl-6 text-xs text-muted-foreground">
                  {c.central.map((p, i) => (
                    <span key={p.slug}>
                      {i > 0 && " · "}
                      <Link to={pageTo(p.slug)} className="hover:text-foreground hover:underline">
                        {p.title}
                      </Link>
                    </span>
                  ))}
                </p>
              </li>
            ))}
          </ul>
        </div>
      </CardContent>
    </Card>
  );
}

function DimensionsCard({ r, axes, setAxes }: { r: EmbeddingReport; axes: Axes; setAxes: (a: Axes) => void }) {
  const spectrum = r.spectrum ?? [];
  const components = r.components ?? [];
  if (!components.length) return null;
  const top = Math.max(...spectrum, 1e-9);
  const shown = spectrum.reduce((a, b) => a + b, 0);
  const ends = (pages: Page[]) =>
    pages.map((p, i) => (
      <span key={p.slug}>
        {i > 0 && " · "}
        <Link to={pageTo(p.slug)} className="hover:text-foreground hover:underline">
          {p.title}
        </Link>
      </span>
    ));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Dimensions</CardTitle>
        <CardDescription>
          The {r.dim.toLocaleString()} raw dimensions mean nothing one by one. Principal components do: each is a direction along which the pages really differ, read from the pages at its two ends.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <NamesBar r={r} />
        <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
          <dt className="text-muted-foreground" title="Participation ratio: how many directions the variance is really spread over">Effective dimensions</dt>
          <dd className="tabular-nums" data-testid="embedding-effective-dim">about {Math.round(r.effective_dim ?? 0)} of {r.dim.toLocaleString()}</dd>
          <dt className="text-muted-foreground">First {spectrum.length} components explain</dt>
          <dd className="tabular-nums">{pct(shown)} of the variance</dd>
          <dt className="text-muted-foreground" title="Mean cosine between two pages. Near 1 would mean every vector points the same way">Mean similarity of two pages</dt>
          <dd className="tabular-nums">{(r.mean_cosine ?? 0).toFixed(2)}</dd>
        </dl>
        <div>
          <p className="mb-1 text-xs font-medium text-muted-foreground">Variance explained by each component</p>
          <div className="flex h-24 items-end gap-1" role="img" aria-label={`Variance explained by the first ${spectrum.length} components`}>
            {spectrum.map((v, i) => (
              <div key={i} className="flex h-full min-w-0 flex-1 flex-col justify-end" title={`Component ${i + 1}: ${pct(v)}`}>
                <div className="rounded-t bg-primary/60" style={{ height: `${Math.max(2, (v / top) * 100)}%` }} />
              </div>
            ))}
          </div>
          <div className="flex gap-1 text-[11px] text-muted-foreground tabular-nums">
            {spectrum.map((_, i) => (
              <span key={i} className="min-w-0 flex-1 text-center">{i + 1}</span>
            ))}
          </div>
        </div>
        <ul className="flex flex-col">
          {components.map((c) => (
            <li key={c.index} className="grid gap-x-4 gap-y-1 border-b py-2 text-sm last:border-b-0 lg:grid-cols-[15rem_minmax(0,1fr)_minmax(0,1fr)]">
              {c.low_name && c.high_name && (
                <p className="lg:col-span-3">
                  <span className="font-medium">{c.low_name}</span>
                  <span className="text-muted-foreground"> to </span>
                  <span className="font-medium">{c.high_name}</span>
                  {c.why && <span className="text-muted-foreground"> · {c.why}</span>}
                </p>
              )}
              <div className="flex items-baseline gap-2">
                <span className="whitespace-nowrap font-medium">Component {c.index + 1}</span>
                <span className="text-xs text-muted-foreground tabular-nums">{pct(c.variance)}</span>
                <button
                  type="button"
                  aria-label={`Show component ${c.index + 1} on the map`}
                  disabled={axes.x === c.index}
                  onClick={() => setAxes({ x: c.index, y: axes.y === c.index ? axes.x : axes.y })}
                  className="ml-auto whitespace-nowrap rounded-md px-1.5 py-0.5 text-xs text-primary hover:bg-accent disabled:text-muted-foreground disabled:hover:bg-transparent lg:ml-0"
                >
                  {axes.x === c.index ? "on X axis" : "Show on map"}
                </button>
              </div>
              <p className="min-w-0 text-xs text-muted-foreground">
                <span className="font-medium text-foreground">{c.low_name ?? "Low end"}: </span>
                {ends(c.low)}
              </p>
              <p className="min-w-0 text-xs text-muted-foreground">
                <span className="font-medium text-foreground">{c.high_name ?? "High end"}: </span>
                {ends(c.high)}
              </p>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

type Similarity = NonNullable<EmbeddingReport["similarity"]>;

/** The bar a cosine falls in. */
const binOf = (sim: Similarity, v: number) => {
  const next = sim.edges.findIndex((e, i) => i > 0 && v < e);
  return next < 0 ? sim.counts.length - 1 : next - 1; // at or past the last edge (a cosine of 1): the last bar
};

function PairExamples({ sim, bin }: { sim: Similarity; bin: number }) {
  const [seed, setSeed] = useState(0);
  const lo = sim.edges[bin] as number;
  const hi = sim.edges[bin + 1] as number;
  // `sim.pairs` and the bar's count tie the cached examples to this build of the vectors.
  const q = useApiQuery(["embedding-pairs", sim.pairs, sim.counts[bin], lo, hi, seed], (d) => d.getEmbeddingPairs(lo, hi, seed), { staleTime: 60_000, placeholderData: (prev) => prev });
  const more = !!q.data && q.data.count > q.data.pairs.length;
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <div className="flex items-center gap-2">
        <p className="text-sm">
          <span className="font-medium">Pairs between {lo.toFixed(3)} and {hi.toFixed(3)}</span>{" "}
          <span className="text-muted-foreground tabular-nums">({(sim.counts[bin] ?? 0).toLocaleString()} pairs)</span>
        </p>
        <Button size="sm" variant="secondary" className="ml-auto" disabled={!more || q.isPlaceholderData} title={q.data && !more ? "These are all the pairs in this range" : undefined} onClick={() => setSeed((n) => n + 1)}>
          Show others
        </Button>
      </div>
      <div className="min-h-56">
        {q.error ? (
          <ErrorState title="Could not load example pairs" error={q.error} onRetry={() => void q.refetch()} />
        ) : !q.data ? (
          <Loading label="Picking example pairs" rows={2} />
        ) : !q.data.pairs.length ? (
          <Empty>No pairs in this range.</Empty>
        ) : (
          <ul className={cn("flex flex-col transition-opacity", q.isPlaceholderData && "opacity-50")}>
            {q.data.pairs.map((d) => (
              <li key={`${d.a.slug}|${d.b.slug}`} className="flex items-baseline gap-3 border-b py-1.5 text-sm last:border-b-0">
                <span className="w-12 shrink-0 text-xs text-muted-foreground tabular-nums">{d.cosine.toFixed(3)}</span>
                <span className="min-w-0 break-words">
                  <Link to={pageTo(d.a.slug)} className="hover:underline">{d.a.title}</Link>
                  <span className="text-muted-foreground"> and </span>
                  <Link to={pageTo(d.b.slug)} className="hover:underline">{d.b.title}</Link>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function SimilarityCard({ sim }: { sim: Similarity }) {
  const p = sim.percentiles;
  const near = sim.nearest_percentiles;
  const [bin, setBin] = useState(() => binOf(sim, near.p50 ?? 0));
  const top = Math.max(...sim.counts, 1);
  const topNear = Math.max(...sim.nearest, 1);
  const marks = sim.edges.slice(0, -1).map((e, i) => (Math.round(e * 1000) % 100 === 0 ? e.toFixed(1) : i === 0 ? e.toFixed(2) : ""));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Similarity</CardTitle>
        <CardDescription>
          What a cosine means in this knowledge base: the similarity of {sim.sampled ? `the pairs among a random ${sim.pages.toLocaleString()} pages` : "every pair of pages"} ({sim.pairs.toLocaleString()} pairs). Click a bar to read random pairs that are that similar.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
          <dt className="text-muted-foreground">Two random pages</dt>
          <dd className="tabular-nums" data-testid="embedding-pair-median">typically {(p.p50 ?? 0).toFixed(2)}, and 9 in 10 between {(p.p5 ?? 0).toFixed(2)} and {(p.p95 ?? 0).toFixed(2)}</dd>
          <dt className="text-muted-foreground">A page and its nearest neighbour</dt>
          <dd className="tabular-nums">typically {(near.p50 ?? 0).toFixed(2)}, and 9 in 10 between {(near.p5 ?? 0).toFixed(2)} and {(near.p95 ?? 0).toFixed(2)}</dd>
          <dt className="text-muted-foreground">Unusually close</dt>
          <dd className="tabular-nums">above {(p.p99 ?? 0).toFixed(2)} (only 1 pair in 100)</dd>
        </dl>
        <div>
          <p className="mb-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5"><span aria-hidden className="size-2.5 rounded-sm bg-primary/60" />All pairs</span>
            <span className="flex items-center gap-1.5"><span aria-hidden className="h-0.5 w-3 bg-foreground" />Each page with its nearest neighbour</span>
            <span>Each series is scaled to its own tallest bar.</span>
          </p>
          <div className="flex h-32 items-stretch gap-px" role="group" aria-label="Pair similarity histogram">
            {sim.counts.map((c, i) => (
              <button
                key={i}
                type="button"
                aria-pressed={bin === i}
                aria-label={`${(sim.edges[i] as number).toFixed(3)} to ${(sim.edges[i + 1] as number).toFixed(3)}: ${c.toLocaleString()} pairs`}
                title={`${(sim.edges[i] as number).toFixed(3)} to ${(sim.edges[i + 1] as number).toFixed(3)}: ${c.toLocaleString()} pairs, ${(sim.nearest[i] ?? 0).toLocaleString()} nearest neighbours`}
                onClick={() => setBin(i)}
                className="relative flex min-w-0 flex-1 flex-col justify-end rounded-t hover:bg-accent aria-pressed:bg-accent-soft"
              >
                <span className="block w-full rounded-t bg-primary/60" style={{ height: c ? `${Math.max(1.5, (c / top) * 100)}%` : 0 }} />
                {!!sim.nearest[i] && <span aria-hidden className="absolute inset-x-0 h-0.5 bg-foreground" style={{ bottom: `${((sim.nearest[i] as number) / topNear) * 100}%` }} />}
              </button>
            ))}
          </div>
          <div className="flex gap-px text-[11px] text-muted-foreground tabular-nums" aria-hidden>
            {marks.map((m, i) => (
              <span key={i} className="min-w-0 flex-1 overflow-visible whitespace-nowrap">{m}</span>
            ))}
          </div>
        </div>
        <PairExamples key={bin} sim={sim} bin={bin} />
      </CardContent>
    </Card>
  );
}

function DuplicatesCard({ r }: { r: EmbeddingReport }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Very similar pages</CardTitle>
        <CardDescription>Pairs with cosine at or above {r.duplicate_cosine}: usually the same page twice, or two summaries that say too little.</CardDescription>
      </CardHeader>
      <CardContent>
        {!r.duplicates.length ? (
          <Empty>No pairs that close.</Empty>
        ) : (
          <ul className="flex flex-col">
            {r.duplicates.map((d) => (
              <li key={`${d.a.slug}|${d.b.slug}`} className="flex items-baseline gap-3 border-b py-1.5 text-sm last:border-b-0">
                <span className="w-12 shrink-0 text-xs text-muted-foreground tabular-nums">{d.cosine.toFixed(3)}</span>
                <span className="min-w-0 break-words">
                  <Link to={pageTo(d.a.slug)} className="hover:underline">{d.a.title}</Link>
                  <span className="text-muted-foreground"> and </span>
                  <Link to={pageTo(d.b.slug)} className="hover:underline">{d.b.title}</Link>
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

/** Embedding: is the vector store there and current, and how the pages group by meaning (0 LLM, from the card vectors). */
export function EmbeddingView() {
  // While a naming run is going, ask again every few seconds so the names appear when it ends.
  const q = useApiQuery(["embedding"], (d) => d.getEmbedding(), { staleTime: 60_000, refetchInterval: (query) => (query.state.data?.names?.state === "running" ? 4000 : false) });
  const [axes, setAxes] = useState<Axes>({ x: 0, y: 1 });
  // flag ui.embedding-views: the views of meaning live in the graph; System keeps the status and the names
  const inGraph = useFlag("ui.embedding-views");
  if (q.error) return <ErrorState title="Could not load the embedding report" error={q.error} onRetry={() => void q.refetch()} />;
  if (!q.data) return <Loading label="Reading the vectors" rows={3} />;
  const r = q.data;
  const emptyText = !r.built ? "No vector store yet: build it with the command above, then reload." : r.ok ? "No vectors to map yet." : r.line;
  return (
    <div className="flex flex-col gap-4">
      <HealthCard r={r} />
      {inGraph ? (
        <>
          {r.names && (
            <Card>
              <CardHeader>
                <CardTitle>Names</CardTitle>
                <CardDescription>An LLM names each topic and each direction of meaning from its pages; the graph uses these names.</CardDescription>
              </CardHeader>
              <CardContent>
                <NamesBar r={r} />
              </CardContent>
            </Card>
          )}
          <p className="text-sm text-muted-foreground" data-testid="embedding-in-graph">
            Topics, Meaning map and Missing links live in the graph&apos;s pinned views.
          </p>
          {!!r.points.length && <DuplicatesCard r={r} />}
        </>
      ) : (
        <>
          {r.points.length ? <MapCard r={r} axes={axes} setAxes={setAxes} /> : <Empty>{emptyText}</Empty>}
          {!!r.points.length && <DimensionsCard r={r} axes={axes} setAxes={setAxes} />}
          {!!r.points.length && r.similarity && <SimilarityCard sim={r.similarity} />}
          {!!r.points.length && <DuplicatesCard r={r} />}
        </>
      )}
    </div>
  );
}
