import { CALM_GRAPH, CALM_STORY, storyById, storyOffered, THESIS_SEED } from "../../lab/views";
import { flag } from "@/flags";
import { QUICK_OFF } from "../../quickFilters";
import type { GraphSchema } from "../../schema";
import type { GNode } from "../../types";

/** One card of the VIEW section: a saved view spec (applied with `applySpec`) and the pages it draws. */
export interface ViewCard {
  id: string;
  name: string;
  /** the count, with its unit ("136 pages", "46 questions") */
  count: string;
  spec: Record<string, unknown>;
}

const DAY = 86_400_000;
export const RECENT_DAYS = 7;
const n = (k: number, unit: string) =>
  `${k.toLocaleString("en-US")} ${unit}${k === 1 ? "" : "s"}`;

/**
 * The views the corner offers, each built from the kb's own pages and schema; a view that does not fit this kb
 * (no pages for it) is left out. Concepts and Sources are the kb's two layers, Recent the last week's additions,
 * Thesis and Gaps the named views of lab/views.ts.
 */
export function viewCards(
  nodes: readonly GNode[],
  schema: GraphSchema,
  now = Date.now(),
): ViewCard[] {
  const out: ViewCard[] = [];
  const typesOf = (layer: string) =>
    schema.types.filter((t) => t.layer === layer).map((t) => t.id);
  const inLayer = (layer: string) =>
    nodes.filter((x) => x.layer === layer).length;
  const stand = (types: string[]) => ({
    v: 1,
    story: "",
    types,
    depths: null,
    hiddenKeys: [],
    quick: QUICK_OFF,
  });

  // flag calm-graph: Concepts and Sources are named views (layers resolved per kb), so the switcher can mark them
  const calm = flag(CALM_GRAPH);
  const concepts = inLayer("concept");
  if (concepts)
    out.push({
      id: "concepts",
      name: "Concepts",
      count: n(concepts, "page"),
      spec: calm ? { v: 1, story: CALM_STORY } : stand(typesOf("concept")),
    });

  const ids = new Set(nodes.map((x) => x.id));
  const spine = THESIS_SEED.filter((s) => ids.has(s)).length;
  const thesis = storyById("thesis");
  if (thesis && storyOffered(thesis) && spine)
    out.push({
      id: "thesis",
      name: "Thesis",
      count: n(spine, "page"),
      spec: { v: 1, story: "thesis" },
    });

  const since = now - RECENT_DAYS * DAY;
  const recent = nodes.filter((x) => Date.parse(x.added || "") >= since).length;
  if (recent)
    out.push({
      id: "recent",
      name: "Recent",
      count: `${recent.toLocaleString("en-US")} this week`,
      spec: {
        ...stand([]),
        types: "all",
        quick: { ...QUICK_OFF, recent: RECENT_DAYS },
      },
    });

  const gaps = storyById("gaps");
  const open = nodes.filter((x) => x.type === "question").length;
  if (gaps && open)
    out.push({
      id: "gaps",
      name: "Gaps",
      count: n(open, "question"),
      spec: { v: 1, story: "gaps" },
    });

  const sources = inLayer("source");
  if (sources)
    out.push({
      id: "sources",
      name: "Sources",
      count: sources.toLocaleString("en-US"),
      spec: calm ? { v: 1, story: "sources" } : stand(typesOf("source")),
    });
  return out;
}

/** The card the graph is showing now: Recent while its filter is on, else the named view with the card's id. */
export function activeCard(
  cards: readonly ViewCard[],
  ui: { story: string; quick: { recent?: unknown } },
): string | null {
  if (ui.quick.recent) return cards.some((c) => c.id === "recent") ? "recent" : null;
  return ui.story && cards.some((c) => c.id === ui.story) ? ui.story : null;
}

/** The newest source pages (by the day they were added), for the SOURCES AND CHATS section. */
export function recentSources(nodes: readonly GNode[], limit = 3): GNode[] {
  return nodes
    .filter((x) => x.layer === "source" && x.added)
    .sort((a, b) => Date.parse(b.added) - Date.parse(a.added))
    .slice(0, limit);
}
