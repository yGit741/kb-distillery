import { storyById, type Story } from "../lab/views";

/**
 * "How this view is computed": the honest account behind every headline pill. Each section names what the
 * code does for that story — the page rule, the layout, the label ranking, and the graph algorithms (if
 * any). Kept next to the stories so the text changes when the configuration does.
 */
export interface Explain {
  filters: string;
  layout: string;
  ranking: string;
  /** graph algorithms the view runs, each with its definition; empty = "filter + layout only" */
  algorithms: readonly { name: string; what: string }[];
}

const ANCHORED = "Force-directed layout (d3-force) with the theme pages pinned on a ring, one per theme; every other page is pulled gently toward its primary theme's anchor. Orientation is stable between visits.";
const LABELS = "Labels are ranked by a degree-of-interest score (tier, evidence read, link count, open questions, betweenness between themes), placed greedily with a spatial hash so they never overlap, and budgeted by screen coverage (text may cover about 8% of the canvas at fit, growing with zoom).";

export const EXPLAIN: Record<string, Explain> = {
  map: {
    filters: "Pages drawn: themes, ideas, questions and people with at least one link, and sources only when read in depth (full or deep). Catalog stubs, skimmed imports (the blog posts), chats, orphans and the collection hubs (courses, books, series) are left out. One rule, `isPublic`, shared with the public snapshot.",
    layout: ANCHORED,
    ranking: LABELS,
    algorithms: [
      { name: "Region hulls", what: "For each theme, the convex hull (Andrew's monotone chain) of the 70% of its pages closest to the theme's median position, padded and drawn under the graph." },
      {
        name: "Theme spectrum (toggle Σ)",
        what: "Every themed page is a point x in {0,1}^k, one bit per theme it carries, so the vault is an empirical distribution on the cube. In the p-biased basis φ_S(x) = ∏_{i∈S} (x_i − p_i)/√(p_i(1−p_i)) (O'Donnell, Analysis of Boolean Functions, §8.4), the level-2 character correlation E[φ_i φ_j] over the vault's pages is the Pearson correlation of the two theme bits — equivalently the level-2 p-biased coefficient of the density of that distribution. Positive = my notes treat the two themes together more than chance: drawn as a solid chord between the theme anchors, width ∝ correlation. Big pairs whose co-occurrence is under half the chance count are drawn dashed (they never meet). Most pairs are negative: a page usually carries one theme.",
      },
    ],
  },
  thesis: {
    filters: "A fixed seed of pages (the two themes, the open questions touching both, the papers the direction rests on, O'Donnell's book) and every page one link away from the seed; everything else is hidden. Types: themes, ideas, questions, papers, book parts, people.",
    layout: ANCHORED,
    ranking: `${LABELS} Open questions and pages between the two themes weigh more here (wOpen 1.2, wBetween 1.6).`,
    algorithms: [
      { name: "1-hop neighbourhood", what: "Union of the seed with its adjacency in the undirected page graph (wikilinks, related, book links)." },
      { name: "Betweenness between themes", what: "A page's label score grows with how many theme pairs its neighbourhood spans." },
    ],
  },
  explore: {
    filters: "Concepts only (themes, ideas, questions). The Research directions panel opens with cards built from the whole vault.",
    layout: ANCHORED,
    ranking: `${LABELS} Here the gap term dominates (wGap 1.5): concepts many pages point at but few digested sources support.`,
    algorithms: [
      { name: "Theme spectrum", what: "Level-2 p-biased Fourier coefficients of the theme bits (see Map): big theme pairs whose observed co-occurrence is under half the expected count are gaps." },
      { name: "Holes", what: "Three themes that meet pairwise but (almost) never together: observed triple count at most a third of the Kirkwood estimate n·p_ab·p_bc·p_ac/(p_a·p_b·p_c), where p_ab is the share of pages carrying both a and b and p_a the share carrying a." },
      { name: "Reach", what: "For each direction, the open questions and ideas closest to every side: closeness = share of the page and its neighbours carrying the theme, a page scores by its weakest side." },
    ],
  },
};

export const explainOf = (id: string): Explain | undefined => EXPLAIN[id];

/** Every headline story must come with its explanation; a story without one would show an empty ⓘ. */
export const explained = (s: Story): boolean => !s.headline || !!EXPLAIN[s.id];

export const storyName = (id: string): string => storyById(id)?.headline?.label ?? storyById(id)?.name ?? id;
