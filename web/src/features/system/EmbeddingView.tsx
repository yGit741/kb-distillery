import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import type { EmbeddingReport } from "@/api/types";
import { CopyButton } from "@/components/CopyButton";
import { Empty, ErrorState, Loading } from "@/components/states";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useApiQuery } from "@/lib/useApiQuery";
import { cn } from "@/lib/utils";
import { clusterColor } from "@/theme/palette";

type Page = EmbeddingReport["missing"][number];
type Point = EmbeddingReport["points"][number];

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

function MapCard({ r }: { r: EmbeddingReport }) {
  const navigate = useNavigate();
  const [pinned, setPinned] = useState<number | null>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const [point, setPoint] = useState<Point | null>(null);
  const active = hovered ?? pinned;
  const x = (p: Point) => PAD + p.x * (W - 2 * PAD);
  const y = (p: Point) => PAD + (1 - p.y) * (H - 2 * PAD);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Semantic map</CardTitle>
        <CardDescription>
          Each dot is a page, placed by the two main directions of its vector, so pages close in meaning sit close together. {r.k} clusters, separation {r.silhouette.toFixed(2)} (silhouette, 1 is perfectly apart).
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="flex min-w-0 flex-col gap-1">
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
            {point ? `${point.title} · cluster ${point.cluster + 1}` : "Hover a dot for its page, click to open it."}
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
                  <span className="font-medium">Cluster {c.id + 1}</span>
                  <span className="text-muted-foreground tabular-nums">{c.size} pages</span>
                  <span className="ml-auto text-xs text-muted-foreground tabular-nums" title="Mean cosine of its pages to the cluster centre">
                    cohesion {c.cohesion.toFixed(2)}
                  </span>
                </button>
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
  const q = useApiQuery(["embedding"], (d) => d.getEmbedding(), { staleTime: 60_000 });
  if (q.error) return <ErrorState title="Could not load the embedding report" error={q.error} onRetry={() => void q.refetch()} />;
  if (!q.data) return <Loading label="Reading the vectors" rows={3} />;
  const r = q.data;
  return (
    <div className="flex flex-col gap-4">
      <HealthCard r={r} />
      {r.points.length ? <MapCard r={r} /> : <Empty>{r.built ? "No vectors to map yet." : "No vector store yet: build it with the command above, then reload."}</Empty>}
      {!!r.points.length && <DuplicatesCard r={r} />}
    </div>
  );
}
