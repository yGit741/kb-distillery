import { ArrowUpRight, Shuffle } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, ErrorState, Loading } from "@/components/states";
import { useApiQuery } from "@/lib/useApiQuery";
import type { GNode } from "@/features/graph/types";
import { curated, graphSearch, indexVault, sampleAll, type CardDef, type Sample, type SampleKind, type Vault } from "./samplers";
import { SampleGraph } from "./SampleGraph";

export interface HomeHost {
  /** Open the full graph with these search params. */
  openGraph: (search: Record<string, string>) => void;
  /** Same target as a real link, for middle-click and copy. */
  graphHref: (search: Record<string, string>) => string;
}

const newSeed = () => Math.floor(Math.random() * 2 ** 31);

function SampleCard({ sample, vault, host, onReroll }: { sample: Sample; vault: Vault; host: HomeHost; onReroll?: () => void }) {
  const search = graphSearch(sample);
  return (
    <Card className="flex min-w-0 flex-col" data-tour={`home-card-${sample.kind}`}>
      <CardHeader>
        <CardTitle className="truncate text-base" title={sample.title}>
          {sample.title}
        </CardTitle>
        {sample.caption && <CardDescription className="line-clamp-2">{sample.caption}</CardDescription>}
      </CardHeader>
      <CardContent className="py-0">
        <SampleGraph sample={sample} byId={vault.byId} score={vault.score} onOpen={(id) => host.openGraph(graphSearch(sample, id))} />
      </CardContent>
      <div className="mt-auto flex items-center justify-between gap-2 p-4 pt-3">
        <span className="text-xs text-muted-foreground">{sample.nodes.length} pages</span>
        <div className="flex gap-1">
          {onReroll && (
            <Button variant="ghost" size="sm" onClick={onReroll} aria-label={`Another ${sample.kind} sample`}>
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

const GRID = "grid grid-cols-1 gap-4 sm:grid-cols-[repeat(auto-fill,minmax(300px,1fr))]";

/**
 * Home: small live graphs that sample the vault. Hand-picked cards (from a share profile) come first; the
 * random samplers follow, one per kind, each with its own reroll. Every card opens in the full graph.
 */
export function HomeScreen({ host, cards = [] }: { host: HomeHost; cards?: readonly CardDef[] }) {
  const q = useApiQuery(["graph", false], (d) => d.getGraph());
  const [seeds, setSeeds] = useState<Partial<Record<SampleKind, number>>>(() => ({
    random: newSeed(),
    bridge: newSeed(),
    question: newSeed(),
    newest: newSeed(),
    thin: newSeed(),
  }));
  const vault = useMemo(() => {
    const data = q.data;
    if (!data) return null;
    const links = (data.links as { source: string; target: string }[]).map((l) => ({ source: l.source, target: l.target }));
    return indexVault(data.nodes as GNode[], links);
  }, [q.data]);
  const stories = useMemo(() => (vault ? cards.map((c) => curated(vault, c)).filter((s): s is Sample => !!s) : []), [vault, cards]);
  const samples = useMemo(() => (vault ? sampleAll(vault, seeds) : []), [vault, seeds]);

  if (q.isPending) return <Loading label="Loading the graph" rows={4} />;
  if (q.isError) return <ErrorState title="Could not load the graph" error={q.error} onRetry={() => void q.refetch()} />;
  if (!vault || (!stories.length && !samples.length)) return <Empty>Nothing to sample yet: digest a few sources and link them.</Empty>;

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-4">
      {stories.length > 0 && (
        <section className="flex flex-col gap-3" aria-label="Stories">
          <div className={GRID}>
            {stories.map((s) => (
              <SampleCard key={`c-${s.title}`} sample={s} vault={vault} host={host} />
            ))}
          </div>
        </section>
      )}
      <section className="flex flex-col gap-3" aria-label="Samples">
        {stories.length > 0 && <h2 className="text-sm font-medium text-muted-foreground">Explore more</h2>}
        <div className={GRID}>
          {samples.map((s) => (
            <SampleCard key={s.kind} sample={s} vault={vault} host={host} onReroll={() => setSeeds((p) => ({ ...p, [s.kind]: newSeed() }))} />
          ))}
        </div>
      </section>
    </div>
  );
}
