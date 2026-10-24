import { ArrowUpRight, Shuffle } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, ErrorState, Loading } from "@/components/states";
import { useApiQuery } from "@/lib/useApiQuery";
import { cn } from "@/lib/utils";
import { SHARE_PROFILE } from "@/share/env";
import { typeColor } from "@/theme/palette";
import type { GNode } from "@/features/graph/types";
import { curated, graphSearch, indexVault, RANDOM_ORDER, rng, SAMPLERS, sampleNode, type CardDef, type NodeKind, type NodeSample, type Sample, type Vault } from "./samplers";
import { SampleGraph } from "./SampleGraph";
import { NodeCard } from "./NodeCard";

export interface HomeHost {
  /** Open the full graph with these search params. */
  openGraph: (search: Record<string, string>) => void;
  /** Same target as a real link, for middle-click and copy. */
  graphHref: (search: Record<string, string>) => string;
  /** Read one page. */
  openPage: (slug: string) => void;
  pageHref: (slug: string) => string;
}

const newSeed = () => Math.floor(Math.random() * 2 ** 31);

/**
 * Longest title a card shows whole. Titles are never cut: a draw whose title is longer is skipped.
 * TODO(user): a real fit (measure against the card width) instead of a character budget.
 */
export const TITLE_MAX = 90;
/** Draws tried before giving up on a fitting title. */
const TRIES = 24;
const fits = (title: string) => title.length <= TITLE_MAX;

const CONCEPT_KINDS: readonly NodeKind[] = ["idea", "question"];

/** One subgraph per seed: a curated story or a random sampler, the first whose title fits. */
export function drawSubgraph(v: Vault, stories: readonly Sample[], seed: number): Sample | null {
  const rand = rng(seed);
  for (let i = 0; i < TRIES; i++) {
    const pickStory = stories.length > 0 && rand() < 0.3;
    const s = pickStory
      ? stories[Math.floor(rand() * stories.length)]
      : SAMPLERS[RANDOM_ORDER[Math.floor(rand() * RANDOM_ORDER.length)]!](v, rand);
    if (s && fits(s.title)) return s;
  }
  return null;
}

/** One concept (idea or question) per seed, the first whose title fits. */
export function drawConcept(v: Vault, seed: number): NodeSample | null {
  const rand = rng(seed);
  for (let i = 0; i < TRIES; i++) {
    const s = sampleNode(v, CONCEPT_KINDS[Math.floor(rand() * CONCEPT_KINDS.length)]!, rand);
    const n = s && v.byId.get(s.id);
    if (s && n && fits(n.title || n.id)) return s;
  }
  return null;
}

function SampleCard({ sample, vault, host, onReroll }: { sample: Sample; vault: Vault; host: HomeHost; onReroll?: () => void }) {
  const search = graphSearch(sample);
  return (
    <Card className="flex h-full min-h-0 min-w-0 flex-col" data-tour={`home-card-${sample.kind}`}>
      <CardHeader>
        <CardTitle className="text-lg leading-snug">{sample.title}</CardTitle>
        {sample.caption && <CardDescription>{sample.caption}</CardDescription>}
      </CardHeader>
      <CardContent className="min-h-0 flex-1 py-0">
        <SampleGraph fill sample={sample} byId={vault.byId} score={vault.score} onOpen={(id) => host.openGraph(graphSearch(sample, id))} />
      </CardContent>
      <div className="flex items-center justify-between gap-2 p-4 pt-3">
        <span className="text-xs text-muted-foreground">{sample.nodes.length} pages</span>
        <div className="flex gap-1">
          {onReroll && (
            <Button variant="ghost" size="sm" onClick={onReroll} aria-label="Another subgraph">
              <Shuffle aria-hidden /> Another
            </Button>
          )}
          <Button variant="outline" size="sm" asChild>
            <a
              href={host.graphHref(search)}
              onClick={(e) => {
                if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
                e.preventDefault();
                host.openGraph(search);
              }}
            >
              Open in full graph <ArrowUpRight aria-hidden />
            </a>
          </Button>
        </div>
      </div>
    </Card>
  );
}

const TERMS: readonly { term: string; color?: string; text: string }[] = [
  { term: "Source", color: typeColor("paper"), text: "something read: a paper, lecture, article, blog post or chat." },
  { term: "Concept", text: "a note distilled from sources — a topic, idea or question." },
  { term: "Topic", color: typeColor("topic"), text: "a broad theme that groups ideas." },
  { term: "Idea", color: typeColor("idea"), text: "one claim, result or technique." },
  { term: "Question", color: typeColor("question"), text: "an open problem — a thesis candidate." },
  { term: "Depth", text: "how closely a source was read: listed, easy, full, deep." },
];

function Intro() {
  return (
    <Card className="min-w-0 sm:col-span-2" aria-labelledby="home-intro">
      <CardHeader className="gap-3">
        <div>
          <CardTitle id="home-intro" className="text-lg">
            A map of what I read toward an MSc thesis in theoretical ML
          </CardTitle>
          <CardDescription>The topic is not chosen yet. Every source I read is distilled into linked notes; the graph shows where they meet.</CardDescription>
        </div>
        <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-2 lg:grid-cols-3">
          {TERMS.map((t) => (
            <div key={t.term} className="flex min-w-0 items-baseline gap-1.5">
              <dt className="flex shrink-0 items-center gap-1.5 font-medium">
                {t.color && <span aria-hidden className="size-2 rounded-full" style={{ background: t.color }} />}
                {t.term}
              </dt>
              <dd className="min-w-0 text-muted-foreground">{t.text}</dd>
            </div>
          ))}
        </dl>
      </CardHeader>
    </Card>
  );
}

/**
 * Home fits one screen: an intro with the vocabulary on top, then two draws side by side — a subgraph and a
 * concept. Each "Another" draws again; only draws whose title fits whole are shown. Both open in the full graph.
 */
export function HomeScreen({ host, cards = [] }: { host: HomeHost; cards?: readonly CardDef[] }) {
  const q = useApiQuery(["graph", false], (d) => d.getGraph());
  const [subSeed, setSubSeed] = useState(newSeed);
  const [conceptSeed, setConceptSeed] = useState(newSeed);
  const vault = useMemo(() => {
    const data = q.data;
    if (!data) return null;
    const links = (data.links as { source: string; target: string }[]).map((l) => ({ source: l.source, target: l.target }));
    return indexVault(data.nodes as GNode[], links);
  }, [q.data]);
  const stories = useMemo(() => (vault ? cards.map((c) => curated(vault, c)).filter((s): s is Sample => !!s) : []), [vault, cards]);
  const sub = useMemo(() => (vault ? drawSubgraph(vault, stories, subSeed) : null), [vault, stories, subSeed]);
  const concept = useMemo(() => (vault ? drawConcept(vault, conceptSeed) : null), [vault, conceptSeed]);

  if (q.isPending) return <Loading label="Loading the graph" rows={4} />;
  if (q.isError) return <ErrorState title="Could not load the graph" error={q.error} onRetry={() => void q.refetch()} />;
  if (!vault || (!sub && !concept)) return <Empty>Nothing to sample yet: digest a few sources and link them.</Empty>;

  return (
    <div
      className={cn(
        "grid w-full grid-cols-1 gap-4 sm:grid-cols-2 sm:grid-rows-[auto_minmax(0,1fr)] sm:overflow-hidden",
        // the header (3rem), main's padding (2rem) and, on a share build, the one-line footer
        SHARE_PROFILE ? "sm:h-[calc(100dvh-7.25rem)]" : "sm:h-[calc(100dvh-5rem)]",
      )}
    >
      <Intro />
      <section className="flex min-h-0 min-w-0 flex-col gap-2" aria-labelledby="home-subgraph">
        <h2 id="home-subgraph" className="text-base font-semibold">
          Draw a Subgraph
        </h2>
        <div className="min-h-0 flex-1">{sub && <SampleCard sample={sub} vault={vault} host={host} onReroll={() => setSubSeed(newSeed())} />}</div>
      </section>
      <section className="flex min-h-0 min-w-0 flex-col gap-2" aria-labelledby="home-concept">
        <h2 id="home-concept" className="text-base font-semibold">
          Draw a Concept
        </h2>
        <div className="min-h-0 flex-1">{concept && <NodeCard sample={concept} vault={vault} host={host} onReroll={() => setConceptSeed(newSeed())} />}</div>
      </section>
    </div>
  );
}
