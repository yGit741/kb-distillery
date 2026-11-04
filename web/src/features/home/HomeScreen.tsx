import { useMemo, useState } from "react";
import { Card } from "@/components/ui/card";
import { Empty, ErrorState, Loading } from "@/components/states";
import { useApiQuery } from "@/lib/useApiQuery";
import { SHARE_PROFILE } from "@/share/env";
import { isPublic } from "@/features/graph/publicPredicate";
import type { GNode } from "@/features/graph/types";
import { ConceptExplorer } from "./ConceptExplorer";
import { StartCard } from "./StartCard";
import { Glossary } from "./glossary";
import { drawPickable, indexVault, isPickable, rng, type Vault } from "./samplers";

export interface HomeHost {
  /** Open the full graph with these search params. */
  openGraph: (search: Record<string, string>) => void;
  /** Same target as a real link, for middle-click and copy. */
  graphHref: (search: Record<string, string>) => string;
  /** Read one page. */
  openPage: (slug: string) => void;
  pageHref: (slug: string) => string;
  /** Put the picked concept in the URL (`?concept=`), so Back and links restore it. */
  setConcept?: (slug: string) => void;
  /** Drop `?start` from the address after the Start card is dismissed. */
  closeStart?: () => void;
}

const newSeed = () => Math.floor(Math.random() * 2 ** 31);

/** The concept to show: the URL's when it is pickable here, else one drawn with `seed`. */
export function resolveConcept(v: Vault, wanted: string | undefined, seed: number, publicOnly: boolean): string | undefined {
  const keep = publicOnly ? isPublic : () => true;
  const n = wanted ? v.byId.get(wanted) : undefined;
  if (isPickable(n) && keep(n)) return n.id;
  return drawPickable(v, rng(seed), keep);
}

/**
 * Home is one intro card (approved mock v16): title and byline, the "How a page gets here" glossary, and the
 * inner card that picks a concept and shows its ego graph and the pipeline of one source it relies on.
 */
export function HomeScreen({ host, concept, startForced }: { host: HomeHost; concept?: string; startForced?: boolean }) {
  return (
    <>
      <StartCard forced={startForced} onDismissed={host.closeStart} />
      <HomeBody host={host} concept={concept} />
    </>
  );
}

function HomeBody({ host, concept: wanted }: { host: HomeHost; concept?: string }) {
  const q = useApiQuery(["graph", false], (d) => d.getGraph());
  const publicOnly = SHARE_PROFILE === "public";
  const [seed, setSeed] = useState(newSeed);
  const [local, setLocal] = useState<string | undefined>(undefined);
  const vault = useMemo(() => {
    const data = q.data;
    if (!data) return null;
    const links = (data.links as { source: string; target: string }[]).map((l) => ({ source: l.source, target: l.target }));
    return indexVault(data.nodes as GNode[], links);
  }, [q.data]);
  const concept = useMemo(() => (vault ? resolveConcept(vault, wanted ?? local, seed, publicOnly) : undefined), [vault, wanted, local, seed, publicOnly]);

  if (q.isPending) return <Loading label="Loading the graph" rows={4} />;
  if (q.isError) return <ErrorState title="Could not load the graph" error={q.error} onRetry={() => void q.refetch()} />;
  if (!vault || !concept) return <Empty>Nothing to show yet: digest a few sources and link them.</Empty>;

  const pick = (id: string) => {
    setLocal(id);
    setSeed(newSeed());
    host.setConcept?.(id);
  };
  const shuffle = () => {
    const s = newSeed();
    const next = drawPickable(vault, rng(s), publicOnly ? isPublic : undefined);
    setSeed(s);
    if (next) {
      setLocal(next);
      host.setConcept?.(next);
    }
  };

  return (
    <Card className="mx-auto w-full min-w-0 max-w-[1100px] px-4 pb-5 pt-4 sm:px-5" aria-labelledby="home-intro">
      <div>
        <h1 id="home-intro" className="text-[22px] font-semibold tracking-tight [text-wrap:balance]">
          A Map of the Knowledge That Interests Me
        </h1>
        <p className="mt-0.5 text-xs tracking-wide text-muted-foreground">Created by my research agent and me.</p>
      </div>
      <Glossary />
      <ConceptExplorer vault={vault} concept={concept} seed={seed} publicOnly={publicOnly} host={host} onPick={pick} onShuffle={shuffle} />
    </Card>
  );
}
