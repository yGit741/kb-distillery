import { X } from "lucide-react";
import { useEffect, useMemo } from "react";
import type { EmbeddingReport } from "@/api/types";
import { useFlag } from "@/flags/useFlag";
import { useKb } from "@/lib/store";
import { useApiQuery } from "@/lib/useApiQuery";
import { cn } from "@/lib/utils";
import type { NeighborMap } from "../graphData";
import { BUTTON, EDGE } from "../shell/corners/geometry";
import { useGraphUi } from "../store";
import { setTopics } from "../style";
import type { GNode } from "../types";
import { axisCount, axisLabel, closeness, componentsOf, missingPairs, orphansIn, topicIndex, type Orphan, type Pair } from "./model";
import { leaveEmbed, useEmbedView } from "./store";

const FLAG = "ui.embedding-views";

/** The embedding, fetched only while the flag is on (the System screen shares the query and its names). */
export function useEmbedding(): { report: EmbeddingReport | undefined; settled: boolean } {
  const on = useFlag(FLAG);
  const q = useApiQuery(["embedding"], (d) => d.getEmbedding(), { enabled: on, staleTime: 60_000, retry: false });
  const r = on ? q.data : undefined;
  return { report: r && r.built && r.points.length ? r : undefined, settled: q.isError || q.isSuccess };
}

const fmt = (v: number) => v.toFixed(2);

/**
 * The embedding views on the graph (flag ui.embedding-views): it hands the canvas the topics, the components and the
 * missing-links lens, and draws the meaning map's axis card and the missing-links list.
 */
export function EmbeddingLayer({ nodes, neighbors }: { nodes: readonly GNode[]; neighbors: NeighborMap }) {
  const on = useFlag(FLAG);
  const { report: r, settled } = useEmbedding();
  const view = useEmbedView((s) => s.view);
  const colorBy = useGraphUi((s) => s.colorBy);

  // topics and components for the canvas; without data (or with the flag off) a topic colouring falls back to theme
  useEffect(() => {
    if (r) {
      const t = topicIndex(r);
      setTopics(t.of, t.names);
      useEmbedView.getState().set({ pc: componentsOf(r.points) });
    } else {
      setTopics(new Map(), new Map());
      useEmbedView.getState().set({ pc: null });
    }
  }, [r]);
  useEffect(() => {
    if (!on && (useEmbedView.getState().view || useGraphUi.getState().colorBy === "topic")) leaveEmbed();
  }, [on]);
  // a topic colouring kept from an earlier visit, once it is known there is nothing to colour by
  useEffect(() => {
    if (colorBy === "topic" && on && !r && settled) useGraphUi.setState({ colorBy: "area" });
  }, [colorBy, on, r, settled]);
  // a colouring or a named view picked by hand leaves the topic views
  useEffect(
    () =>
      useGraphUi.subscribe((s, prev) => {
        const v = useEmbedView.getState().view;
        if (!v) return;
        if ((v === "topics" || v === "map") && s.colorBy !== "topic" && prev.colorBy === "topic") useEmbedView.getState().set({ view: null });
        else if (s.story && s.story !== prev.story) leaveEmbed();
      }),
    [],
  );
  useEffect(() => () => leaveEmbed(false), []);

  const known = useMemo(() => new Set(nodes.map((n) => n.id)), [nodes]);
  const pairs = useMemo(() => (r ? missingPairs(r.near ?? [], known, neighbors) : []), [r, known, neighbors]);
  const orphans = useMemo(() => (r ? orphansIn(r.isolated ?? [], known) : []), [r, known]);
  useEffect(() => {
    const pages = new Set<string>();
    for (const p of pairs) pages.add(p.a.slug).add(p.b.slug);
    useEmbedView.getState().set({ lens: view === "missing" ? { pairs, pages } : null });
  }, [view, pairs]);

  if (!on || !r || !view) return null;
  if (view === "map") return <MeaningCard r={r} />;
  if (view === "missing") return <MissingList pairs={pairs} orphans={orphans} />;
  return null;
}

const CARD = "pointer-events-auto rounded-xl bg-card shadow-[var(--shadow)]";

function Close({ label }: { label: string }) {
  return (
    <button type="button" aria-label={label} title={label} onClick={() => leaveEmbed()} className="grid size-6 flex-none place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground">
      <X className="size-3.5" strokeWidth={1.8} aria-hidden />
    </button>
  );
}

function AxisPick({ label, value, other, count, r, onPick }: { label: string; value: number; other: number; count: number; r: EmbeddingReport; onPick: (i: number) => void }) {
  return (
    <label className="flex min-w-0 items-center gap-2 text-[11.5px]">
      <span className="w-3 flex-none font-semibold text-muted-foreground">{label}</span>
      <select
        aria-label={`${label} axis`}
        value={value}
        onChange={(e) => onPick(Number(e.target.value))}
        className="min-w-0 flex-1 truncate rounded-md border bg-card px-1 py-0.5 text-[11.5px]"
      >
        {Array.from({ length: count }, (_, i) => (
          <option key={i} value={i} disabled={i === other}>
            {axisLabel(r, i)}
          </option>
        ))}
      </select>
    </label>
  );
}

/** The meaning map's card: what each axis means (and a picker for it), and how close "close" is here. */
function MeaningCard({ r }: { r: EmbeddingReport }) {
  const axes = useEmbedView((s) => s.axes);
  const count = axisCount(r);
  const c = closeness(r.similarity);
  const pick = (k: 0 | 1) => (i: number) => {
    const next: [number, number] = [axes[0], axes[1]];
    next[k] = i;
    useEmbedView.getState().set({ axes: next });
  };
  return (
    <div
      data-testid="meaning-card"
      role="group"
      aria-label="Meaning map"
      className={cn(CARD, "absolute z-[18] flex w-[300px] flex-col gap-1.5 px-3 py-2.5")}
      // bottom left, above the agent corner: the middle of the canvas stays the map's
      style={{ left: EDGE, bottom: EDGE + BUTTON + 10 }}
    >
      <div className="flex items-center gap-2">
        <p className="flex-1 text-[12px] font-semibold">Meaning map</p>
        <Close label="Leave the meaning map" />
      </div>
      <AxisPick label="x" value={axes[0]} other={axes[1]} count={count} r={r} onPick={pick(0)} />
      <AxisPick label="y" value={axes[1]} other={axes[0]} count={count} r={r} onPick={pick(1)} />
      {c && (
        <p className="text-[11px] leading-snug text-muted-foreground" data-testid="closeness">
          How close is close? Two pages: median {fmt(c.pairs)}, most between {fmt(c.low)} and {fmt(c.high)}. A page and its nearest neighbour: median {fmt(c.nearest)}.
        </p>
      )}
    </div>
  );
}

/** The missing-links list: pairs close in meaning with no link either way, and the semantic orphans. */
function MissingList({ pairs, orphans }: { pairs: readonly Pair[]; orphans: readonly Orphan[] }) {
  const tab = useEmbedView((s) => s.tab);
  const show = (ids: string[]) => {
    useKb.getState().setSelection(ids);
    if (ids[0]) useGraphUi.getState().requestFocus(ids[0], false);
  };
  const TAB = "rounded-full border px-2 py-0.5 text-[11px] text-muted-foreground aria-pressed:border-primary aria-pressed:text-primary";
  return (
    <div
      data-testid="missing-links"
      role="complementary"
      aria-label="Missing links"
      className={cn(CARD, "absolute z-[18] flex w-[300px] flex-col p-3")}
      // clear of the colour dots on the right edge
      style={{ right: EDGE + 22, top: EDGE + BUTTON + 4, bottom: EDGE + BUTTON + 30 }}
    >
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-[13px] font-semibold">Close in meaning, not linked</p>
          <p className="text-[11.5px] text-muted-foreground">Pairs above 0.80 with no link either way, dashed on the graph.</p>
        </div>
        <Close label="Leave missing links" />
      </div>
      <div className="my-2 flex gap-1.5" role="group" aria-label="List">
        <button type="button" aria-pressed={tab === "pairs"} className={TAB} onClick={() => useEmbedView.getState().set({ tab: "pairs" })}>
          Missing links {pairs.length}
        </button>
        <button type="button" aria-pressed={tab === "orphans"} className={TAB} onClick={() => useEmbedView.getState().set({ tab: "orphans" })}>
          Semantic orphans {orphans.length}
        </button>
      </div>
      <ul className="min-h-0 flex-1 overflow-y-auto">
        {tab === "pairs" &&
          (pairs.length ? (
            pairs.map((p) => (
              <li key={`${p.a.slug}|${p.b.slug}`} className="border-t">
                <button type="button" onClick={() => show([p.a.slug, p.b.slug])} className="grid w-full grid-cols-[1fr_auto] gap-x-2 py-1.5 text-left hover:bg-accent/60">
                  <span className="truncate text-[12px] font-medium">{p.a.title}</span>
                  <span className="row-span-2 self-center text-[11.5px] tabular-nums text-muted-foreground">{fmt(p.cosine)}</span>
                  <span className="truncate text-[12px] font-medium">{p.b.title}</span>
                </button>
              </li>
            ))
          ) : (
            <li className="py-2 text-[11.5px] text-muted-foreground">Every close pair is already linked.</li>
          ))}
        {tab === "orphans" &&
          (orphans.length ? (
            orphans.map((o) => (
              <li key={o.slug} className="border-t">
                <button type="button" onClick={() => show([o.slug])} className="grid w-full grid-cols-[1fr_auto] gap-x-2 py-1.5 text-left hover:bg-accent/60">
                  <span className="truncate text-[12px] font-medium">{o.title}</span>
                  <span className="text-[11.5px] tabular-nums text-muted-foreground" title="Cosine to its nearest page">
                    {fmt(o.nearest)}
                  </span>
                </button>
              </li>
            ))
          ) : (
            <li className="py-2 text-[11.5px] text-muted-foreground">No page stands far from the rest.</li>
          ))}
      </ul>
    </div>
  );
}
