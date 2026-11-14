import { useMemo, useState } from "react";
import { Card } from "@/components/ui/card";
import { Empty, ErrorState, Loading } from "@/components/states";
import { useApiQuery } from "@/lib/useApiQuery";
import { GRAPH_KEY } from "@/lib/query";
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
 * Home is one intro card (approved mock v16): title and byline, and the inner card that picks a concept and shows its ego graph and the pipeline of one source it relies on.
 */
export function HomeScreen({ host, concept, startForced, glossary }: { host: HomeHost; concept?: string; startForced?: boolean; glossary?: boolean }) {
  return (
    <>
      <StartCard forced={startForced} onDismissed={host.closeStart} />
      <MapCard host={host} concept={concept} intro={glossary ? { ...HOME_INTRO, glossary: true } : HOME_INTRO} />
    </>
  );
}

/** What the card says above the explorer. Home: the map's title; What is it?: its own title, the glossary above the explorer. */
export interface MapIntro {
  id: string;
  title: string;
  byline: string;
  /** "How a page gets here" (Raw -> Source -> Concept) and the reading depths, above Pick a Concept */
  glossary?: boolean;
}
const HOME_INTRO: MapIntro = { id: "home-intro", title: "A Map of the Knowledge That Interests Me", byline: "Created by my research agent and me." };

/** The map card: a title, optionally the glossary, and Pick a Concept (ego graph, one source's pipeline, Back). */
export function MapCard({ host, concept: wanted, intro = HOME_INTRO }: { host: HomeHost; concept?: string; intro?: MapIntro }) {
  const q = useApiQuery([...GRAPH_KEY], (d) => d.getGraph());
  const publicOnly = SHARE_PROFILE === "public";
  const [seed, setSeed] = useState(newSeed);
  const [local, setLocal] = useState<string | undefined>(undefined);
  // the concepts shown before this one, newest last: Back walks them (the URL is replaced on each pick, so the browser's Back cannot)
  const [trail, setTrail] = useState<string[]>([]);
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

  const leave = () => setTrail((t) => (t[t.length - 1] === concept ? t : [...t, concept].slice(-50)));
  const pick = (id: string) => {
    if (id !== concept) leave();
    setLocal(id);
    setSeed(newSeed());
    host.setConcept?.(id);
  };
  const shuffle = () => {
    const s = newSeed();
    const next = drawPickable(vault, rng(s), publicOnly ? isPublic : undefined);
    setSeed(s);
    if (next) {
      if (next !== concept) leave();
      setLocal(next);
      host.setConcept?.(next);
    }
  };

  // a concept that left the graph (or the public subset) since it was shown is skipped, not drawn at random
  const keep = (id: string) => {
    const n = vault.byId.get(id);
    return isPickable(n) && (!publicOnly || isPublic(n));
  };
  const live = trail.filter(keep);
  const back = () => {
    const prev = live[live.length - 1];
    if (!prev) return;
    setTrail(live.slice(0, -1));
    setLocal(prev);
    setSeed(newSeed());
    host.setConcept?.(prev);
  };

  return (
    <Card className="mx-auto w-full min-w-0 max-w-[1100px] px-4 pb-5 pt-4 sm:px-5" aria-labelledby={intro.id}>
      <div>
        <h1 id={intro.id} className="text-[22px] font-semibold tracking-tight [text-wrap:balance]">
          {intro.title}
        </h1>
        <p className="mt-0.5 text-xs tracking-wide text-muted-foreground">{intro.byline}</p>
      </div>
      {intro.glossary && <Glossary />}
      <ConceptExplorer vault={vault} concept={concept} seed={seed} publicOnly={publicOnly} host={host} onPick={pick} onShuffle={shuffle} onBack={live.length ? back : undefined} backTo={vault.byId.get(live[live.length - 1] ?? "")?.title || live[live.length - 1]} />
    </Card>
  );
}
