import { Network, Shuffle } from "lucide-react";
import { useId, useMemo, useState, type KeyboardEvent } from "react";
import { findPages } from "@/features/graph/pageSearch";
import { isPublic } from "@/features/graph/publicPredicate";
import { SideReader } from "@/features/graph/SideReader";
import type { GNode } from "@/features/graph/types";
import { cn } from "@/lib/utils";
import { typeColor } from "@/theme/palette";
import { Dot } from "./glossary";
import { PipelineStrip } from "./PipelineStrip";
import { egoSample, graphSearch, isPickable, pickSource, rng, type Vault } from "./samplers";
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
      <label className="flex items-center gap-2 rounded-full border bg-card px-3 py-1 focus-within:ring-2 focus-within:ring-ring">
        <Network aria-hidden className="size-3.5 shrink-0 text-muted-foreground" />
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
              <Dot color={typeColor(n.type)} />
              <span className="truncate">{n.title || n.id}</span>
              <span className="ml-auto shrink-0 text-xs text-muted-foreground">{n.type}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * The inner card: Pick a Concept (shuffle) + combobox, the concept's ego graph (Full Graph inside it), and the
 * pipeline of one source it relies on. `seed` rerolls the source; the concept lives in the URL (`?concept=`).
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
  const draw = useMemo(() => pickSource(vault, concept, rng(seed), publicOnly), [vault, concept, seed, publicOnly]);
  const sample = useMemo(() => egoSample(vault, concept, draw), [vault, concept, draw]);
  const search = graphSearch(sample);
  const pickNode = (id: string) => (isPickable(vault.byId.get(id)) ? onPick(id) : setReader(id));
  return (
    <section aria-label="Pick a concept" data-tour="home-start" className="mt-4 rounded-xl border bg-muted/25 p-3 text-[13.5px]">
      <div className="flex items-center gap-3">
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
      </div>
      <div className="mt-2.5 grid grid-cols-1 items-stretch gap-3 md:grid-cols-[300px_1fr]">
        <div className="relative min-h-[220px] min-w-0 rounded-lg border bg-card">
          <SampleGraph fill sample={sample} byId={vault.byId} imp={vault.imp} ring={draw?.id ?? null} onPick={pickNode} />
          <a
            href={host.graphHref(search)}
            onClick={(e) => {
              if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
              e.preventDefault();
              host.openGraph(search);
            }}
            className="absolute bottom-2 right-2 z-10 inline-flex items-center gap-1 rounded-full border bg-card/90 px-2 py-0.5 text-[11.5px] text-muted-foreground hover:border-primary hover:text-foreground"
          >
            <Network aria-hidden className="size-3.5" /> Full Graph
          </a>
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
