import { useFlag } from "@/flags/useFlag";

/**
 * Flag ui.data-system-split: the top bar is Home, Knowledge, Ingest, System. Knowledge folds Graph, Pages and Think
 * (chat lives in the graph's spark panel; "What is it?" is a card on Home). One place, so the shell and its tests agree.
 */

/** Routes that sit under Knowledge, in tab order. */
export const KNOWLEDGE_TABS: readonly { id: string; path: string; label: string }[] = [
  { id: "graph", path: "/graph", label: "Graph" },
  { id: "pages", path: "/pages", label: "Pages" },
  { id: "think", path: "/think", label: "Think" },
];

/** Top-level routes kept in the split bar, in order; Knowledge is inserted after Home. */
export const SPLIT_TOP: readonly string[] = ["home", "ingest", "system", "share"];

/** Whether a pathname belongs to Knowledge (`/pages/<slug>` included). */
export const inKnowledge = (pathname: string): boolean =>
  KNOWLEDGE_TABS.some((t) => pathname === t.path || pathname.startsWith(`${t.path}/`));

/**
 * The split is on only when Ingest exists: with ui.ingest off, Pipeline, Health and History would have no home,
 * so System keeps its nine tabs. Every split decision reads this, never the flag alone.
 */
export function useDataSystemSplit(): boolean {
  const split = useFlag("ui.data-system-split");
  const ingest = useFlag("ui.ingest");
  return split && ingest;
}
