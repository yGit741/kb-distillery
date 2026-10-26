import { Shuffle } from "lucide-react";
import { FullGraphIcon } from "./FullGraphIcon";
import { useId, useMemo, useState, type KeyboardEvent } from "react";
import { findPages } from "@/features/graph/pageSearch";
import { isPublic } from "@/features/graph/publicPredicate";
import { colorChannel, GraphLegend, NodeMarkSvg } from "@/features/graph/encoding";
import { SideReader } from "@/features/graph/SideReader";
import { areaSlots } from "@/features/graph/style";
import type { GNode } from "@/features/graph/types";
import { cn } from "@/lib/utils";
import { PipelineStrip } from "./PipelineStrip";
import { egoSample, graphSearch, isPickable, pickSource, rng, type SourceDraw, type Vault } from "./samplers";
import { SampleGraph } from "./SampleGraph";
import type { HomeHost } from "./HomeScreen";

/** Matches the combobox lists. */
export const COMBO_LIMIT = 8;

/** Concept matches for the combobox: topics, ideas and questions only. */
export function matchConcepts(nodes: readonly GNode[], q: string, limit = COMBO_LIMIT): GNode[] {
  return findPages(nodes.filter(isPickable), q, limit);
}

/** A full-width combobox (↑ ↓ Enter Esc) showing the picked concept's title, centred. */
function ConceptCombo({ nodes, value, onPick }: { nodes: readonly GNode[]; value: GNode; onPick: (id: string) => void }) {
  const [text, setText] = useState<string | null>(null);
  const [active, setActive] = useState(0);
  const list = useId();
  const hits = useMemo(() => (text ? matchConcepts(nodes, text) : []), [nodes, text]);
  const open = text !== null && hits.length > 0;
  const choose = (id: string) => {
    setText(null);
    onPick(id);
  };
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" && open) {
      e.preventDefault();
      setActive((a) => (a + 1) % hits.length);
    } else if (e.key === "ArrowUp" && open) {
      e.preventDefault();
      setActive((a) => (a - 1 + hits.length) % hits.length);
    } else if (e.key === "Enter" && open) {
      e.preventDefault();
      choose(hits[active]!.id);
    } else if (e.key === "Escape") {
      setText(null);
      (e.target as HTMLInputElement).blur();
    }
  };
  return (
    <div className="relative min-w-0 flex-1">
      <label className="flex h-8 items-center gap-2 rounded-full bg-muted px-3 focus-within:ring-2 focus-within:ring-ring">
        <input
          type="text"
          role="combobox"
          aria-label="Pick a concept"
          aria-expanded={open}
          aria-controls={list}
          aria-autocomplete="list"
          aria-activedescendant={open ? `${list}-${active}` : undefined}
          spellCheck={false}
          value={text ?? (value.title || value.id)}
          onFocus={(e) => e.target.select()}
          onChange={(e) => {
            setText(e.target.value);
            setActive(0);
          }}
          onBlur={() => setTimeout(() => setText(null), 120)}
          onKeyDown={onKey}
          className="min-w-0 flex-1 bg-transparent text-center text-[13.5px] outline-none"
        />
      </label>
      {open && (
        <ul id={list} role="listbox" aria-label="Concepts" className="absolute inset-x-0 top-full z-30 mt-1 rounded-lg border bg-popover p-1 text-sm shadow-[var(--shadow)]">
          {hits.map((n, i) => (
            <li
              key={n.id}
              id={`${list}-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => {
                e.preventDefault();
                choose(n.id);
              }}
              onMouseEnter={() => setActive(i)}
              className={cn("flex cursor-pointer items-center gap-2 rounded-md px-2 py-1", i === active && "bg-accent")}
            >
              <NodeMarkSvg type={n.type} className="size-3.5 text-muted-foreground" />
              <span className="truncate">{n.title || n.id}</span>
              <span className="ml-auto shrink-0 text-xs text-muted-foreground">{n.type}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** The graph card's fixed height in px, legend included: the page below never moves between draws. */
export const EGO_HEIGHT = 330;
/** The card sizes a node by its links inside the sample (./SampleGraph radii). */
const SIZE = { by: "degree", title: "links" } as const;
/** The compact legend's fixed strip at the card's foot (two lines at most), inside EGO_HEIGHT. */
export const LEGEND_HEIGHT = 44;

/** A clicked source in the ego graph as a draw: direct when it links the concept, else through a linked idea. */
export function drawFor(vault: Vault, concept: string, source: string, sample: { nodes: readonly string[] }): SourceDraw {
  const direct = vault.allNeighbors.get(concept)?.includes(source);
  if (direct) return { id: source, via: null };
  const inSample = new Set(sample.nodes);
  const via = [...(vault.allNeighbors.get(source) ?? [])].find((id) => id !== concept && inSample.has(id) && vault.allNeighbors.get(concept)?.includes(id) && vault.byId.get(id)?.type === "idea");
  return { id: source, via: via ?? null };
}

/**
 * The inner card, stacked: Pick a Concept (shuffle) + combobox; the concept's ego graph at a fixed height (Full
 * Graph at the bar's right end); the pipeline of one source it relies on. Clicking a source node swaps the pipeline to it (and
 * rings it), clicking a topic, idea or question picks it, anything else opens the reader. `seed` rerolls the
 * source; the concept lives in the URL (`?concept=`).
 */
export function ConceptExplorer({
  vault,
  concept,
  seed,
  publicOnly,
  host,
  onPick,
  onShuffle,
}: {
  vault: Vault;
  concept: string;
  seed: number;
  publicOnly: boolean;
  host: HomeHost;
  onPick: (id: string) => void;
  onShuffle: () => void;
}) {
  const [reader, setReader] = useState<string | null>(null);
  const node = vault.byId.get(concept)!;
  const nodes = useMemo(() => [...vault.byId.values()].filter((n) => !publicOnly || isPublic(n)), [vault, publicOnly]);
  // a clicked source belongs to one (concept, seed) draw: ignored as soon as either changes
  const [pick, setChosen0] = useState<{ key: string; id: string } | null>(null);
  const key = `${concept}|${seed}`;
  const chosen = pick?.key === key ? pick.id : null;
  const setChosen = (id: string) => setChosen0({ key, id });
  const drawn = useMemo(() => pickSource(vault, concept, rng(seed), publicOnly), [vault, concept, seed, publicOnly]);
  const sample = useMemo(() => egoSample(vault, concept, drawn), [vault, concept, drawn]);
  const draw = useMemo(() => (chosen && chosen !== drawn?.id ? drawFor(vault, concept, chosen, sample) : drawn), [chosen, drawn, vault, concept, sample]);
  const search = graphSearch(sample, sample.focus, draw?.id ?? null);
  // colour = theme, like the Full Graph's Map: area slots ranked over the whole vault (as the Full Graph ranks its
  // model), passed to the channel rather than set globally, so a theme keeps its colour and nothing else is touched
  const color = useMemo(() => colorChannel("area", { areas: areaSlots([...vault.byId.values()]) }), [vault]);
  const drawnNodes = useMemo(() => sample.nodes.map((id) => vault.byId.get(id)).filter((n): n is GNode => !!n), [sample, vault]);
  const pickNode = (id: string) => {
    const n = vault.byId.get(id);
    if (n?.layer === "source") setChosen(id);
    else if (isPickable(n)) onPick(id);
    else setReader(id);
  };
  return (
    <section aria-label="Pick a concept" data-tour="home-start" className="mt-4 rounded-xl border bg-muted/25 p-3 text-[13.5px]">
      <div className="flex h-11 items-center gap-3 rounded-xl border bg-card px-1.5">
        <button
          type="button"
          onClick={onShuffle}
          title="Shuffle"
          className="inline-flex shrink-0 items-center gap-1.5 rounded-full px-2 py-1 text-foreground hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Shuffle aria-hidden className="size-4" strokeWidth={2.4} />
          <span className="text-sm font-semibold">Pick a Concept</span>
        </button>
        <ConceptCombo nodes={nodes} value={node} onPick={onPick} />
        <a
          href={host.graphHref(search)}
          onClick={(e) => {
            if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
            e.preventDefault();
            host.openGraph(search);
          }}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-full px-2 py-1 text-sm font-semibold text-foreground hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <FullGraphIcon className="size-4 shrink-0" />
          <span>Open in Full Graph</span>
        </a>
      </div>
      <div className="mt-2.5 flex flex-col gap-3">
        <div className="relative flex min-w-0 flex-col rounded-lg border bg-card" style={{ height: EGO_HEIGHT }} data-testid="home-ego">
          <div className="relative min-h-0 flex-1">
            <SampleGraph fill sample={sample} byId={vault.byId} imp={vault.imp} ring={draw?.id ?? null} color={color} onPick={pickNode} />
          </div>
          {/* the shared legend, compact, in a fixed strip: its content changes with the draw, its height never */}
          <div className="flex shrink-0 items-center justify-center overflow-hidden border-t px-3 py-1" style={{ height: LEGEND_HEIGHT }} data-testid="home-legend">
            <GraphLegend nodes={drawnNodes} color={color} size={SIZE} density="compact" maxColors={6} className="justify-center" />
          </div>
        </div>
        <PipelineStrip vault={vault} concept={concept} draw={draw} onPick={onPick} onRead={setReader} />
      </div>
      {reader && (
        <div className="pointer-events-none fixed inset-x-0 bottom-0 top-12 z-40">
          <SideReader slug={reader} title={vault.byId.get(reader)?.title || reader} pageHref={host.pageHref(reader)} onClose={() => setReader(null)} />
        </div>
      )}
    </section>
  );
}
