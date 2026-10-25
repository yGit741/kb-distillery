import type { Predicate } from "../publicPredicate";
import type { ColorBy, SizeBy } from "../style";
import { DEFAULT_LAB, type LabConfig } from "./config";

export type LayoutMode = "anchored" | "free";

/** A saved view: one user story's answer to "what counts as important right now". It never breaks a principle. */
export interface Story {
  id: string;
  name: string;
  story: string;
  lab: Partial<LabConfig>;
  colorBy: ColorBy;
  sizeBy: SizeBy;
  layoutMode: LayoutMode;
  /** page types drawn */
  types: readonly string[];
  /** types whose every page is labelled (the legend's "Aa") */
  typeLabels?: readonly string[];
  /** A headline view: a pill in the views bar; `goal` is the one sentence its hover shows, then the questions and hint. */
  headline?: { label: string; goal: string; questions: readonly string[]; hint: string };
  /** Pages drawn at all, on top of the type filter (../publicPredicate). */
  predicate?: Predicate;
  /** Pages the view is built around: they and their neighbours are drawn, the rest hidden. */
  seed?: readonly string[];
  /** A tool panel the view opens (and the experiment flag it needs). */
  tool?: { id: string; flag?: string };
}

const CONCEPTS = ["topic", "question", "idea"] as const;
/** Map's drawn types: every page type except the collection hubs, whose course/book names duplicate the themes' labels. */
const MAP_TYPES = ["topic", "idea", "question", "person", "paper", "part", "lecture", "article", "video", "mail", "ai-chat", "blog-post"] as const;

/**
 * The thesis spine: generalization of over-parameterized networks met through Boolean analysis. The themes,
 * the open questions that touch both, the papers the direction rests on, and the book; one hop out is drawn.
 */
export const THESIS_SEED: readonly string[] = [
  "theme-boolean-analysis",
  "theme-implicit-regularization",
  "theme-learning-theory",
  "q-why-do-overparameterized-networks-generalize",
  "q-what-does-double-descent-say-about-implicit-regularization",
  "q-does-the-gradient-variance-bound-explain-the-sparse-parity-s",
  "q-what-are-the-discrete-counterparts-of-continuous-network-theory",
  "volume-hypothesis",
  "double-descent",
  "parity-function",
  "fourier-degree",
  "noise-stability",
  "paper-2019-implicit-regularization-in-deep-matrix-factorization",
  "paper-2019-deep-double-descent-where-bigger-models-and-more-data-hurt",
  "paper-2023-loss-landscapes-are-all-you-need",
  "paper-2025-do-neural-networks-need-gradient-descent-to-generalize",
  "book-2014-analysis-of-boolean-functions",
  "gil-kalai",
];

export const STORIES: readonly Story[] = [
  {
    id: "map",
    name: "Map: what is in my vault",
    story: "As a reader who opens this vault for the first time, I want the territory at a glance: every theme on a ring, the ideas and questions inside each, and only the sources I actually read, so that breadth shows without the noise of imports and stubs.",
    headline: {
      label: "Map",
      goal: "See what is in the vault: every theme, with the ideas and questions inside it.",
      questions: ["What is in my vault?", "How broad is it?", "Which themes do my notes combine?"],
      hint: "Themes on a ring, digested sources only",
    },
    predicate: "public",
    lab: { degBasis: "nohub", coverage: 8, regions: "auto", regionZoom: 0.8, hulls: true, questionLabels: "none", wrapT2: 100 },
    colorBy: "area",
    sizeBy: "evidence",
    layoutMode: "anchored",
    types: MAP_TYPES,
    typeLabels: ["topic"],
  },
  {
    id: "thesis",
    name: "Thesis: where I am heading",
    story: "As a student choosing a thesis, I want the spine of my direction — generalization of over-parameterized networks seen through Boolean analysis — with the questions, papers and concepts one hop around it, so that I can see what the direction already rests on.",
    headline: {
      label: "Thesis",
      goal: "See the thesis direction: its questions and what they rest on, one hop around the spine.",
      questions: ["Which questions am I pursuing?", "What is the generalization ↔ Boolean-analysis core?", "What does the direction rest on?"],
      hint: "The thesis spine and one hop around it",
    },
    seed: THESIS_SEED,
    lab: { wTier: 0.5, wEvidence: 0.4, wOpen: 1.2, wBetween: 1.6, coverage: 14, positions: 8, questionLabels: "short" },
    colorBy: "area",
    sizeBy: "evidence",
    layoutMode: "anchored",
    types: ["topic", "idea", "question", "paper", "part", "book", "person"],
    typeLabels: ["topic", "question"],
  },
  {
    id: "explore",
    name: "Explore: what is on my mind",
    story: "As a student still choosing, I want the empty intersections of my vault as research-direction cards, with the thin spots lit on the graph, so that I can see where my curiosity is pulling me and what reading would pay most.",
    headline: {
      label: "Explore",
      goal: "Find research directions in the gaps: themes I touch but never connect.",
      questions: ["What is on my mind?", "Where is my curiosity pulling me?", "Which themes do I touch but never connect?"],
      hint: "Research directions from the gaps between themes",
    },
    tool: { id: "kalai-directions", flag: "directions" },
    lab: { wTier: 0.3, wEvidence: 0, wDegree: 0.3, wGap: 1.5, sizeMode: "quantile" },
    colorBy: "evidence",
    sizeBy: "gap",
    layoutMode: "anchored",
    types: CONCEPTS,
  },
  {
    id: "orient",
    name: "Orient: what is in my vault",
    story: "As a student who has not picked a thesis, I open the graph to see the territory: which themes exist, which questions sit in each, and roughly how much I have read about each.",
    lab: { degBasis: "nohub", coverage: 8, regions: "auto", regionZoom: 0.8, hulls: true },
    colorBy: "area",
    sizeBy: "evidence",
    layoutMode: "anchored",
    types: CONCEPTS,
    typeLabels: ["topic"],
  },
  {
    id: "deeplook",
    name: "Theme deep-look",
    story: "I click one theme (or concept) and want only its neighbourhood readable: the rest fades, labels rank by importance minus distance from what I picked.",
    lab: { wPagerank: 0.5, coverage: 16, positions: 8, doiHops: 2, doiLambda: 0.25 },
    colorBy: "depth",
    sizeBy: "evidence",
    layoutMode: "anchored",
    types: ["topic", "idea", "question", "paper", "part", "person"],
  },
  {
    id: "context",
    name: "Concept in context",
    story: "I am reading about X and want to see where it fits: X, its sources and related ideas readable, one hop out, the rest faded.",
    lab: { coverage: 10, positions: 8, doiHops: 1, doiLambda: 0.3, lens: true },
    colorBy: "type",
    sizeBy: "evidence",
    layoutMode: "anchored",
    types: ["topic", "idea", "question", "paper", "part", "person", "article", "blog-post"],
  },
  {
    id: "questions",
    name: "Open questions first",
    story: "I want my open research questions as the landmarks, each with the concepts around it, to pick which one to push next.",
    lab: { wTier: 0.6, wEvidence: 0.6, wOpen: 1.5, coverage: 14, positions: 8, t2: 13, questionLabels: "short", charsQuestion: 26 },
    colorBy: "type",
    sizeBy: "evidence",
    layoutMode: "anchored",
    types: CONCEPTS,
    typeLabels: ["question", "topic"],
  },
  {
    id: "bridges",
    name: "Bridges between directions",
    story: "I want the concepts and papers between two themes (say boolean analysis and learning theory): intersections are where a thesis topic often hides.",
    lab: { wTier: 0.5, wEvidence: 0.3, wBetween: 1.6, positions: 8 },
    colorBy: "area",
    sizeBy: "score",
    layoutMode: "anchored",
    types: ["topic", "idea", "question", "paper"],
    typeLabels: ["topic"],
  },
  {
    id: "gaps",
    name: "Find thin spots",
    story: "I want concepts that many pages point at but few digested sources support: where reading next pays most.",
    lab: { wTier: 0.3, wEvidence: 0, wDegree: 0.3, wGap: 1.5, sizeMode: "quantile" },
    colorBy: "evidence",
    sizeBy: "gap",
    layoutMode: "anchored",
    types: CONCEPTS,
  },
  {
    id: "compare",
    name: "Compare directions",
    story: "I want to weigh two candidate directions: how big each cluster is, how much evidence backs it, which open questions it owns.",
    lab: { wEvidence: 1.2, wOpen: 0.6, wPagerank: 0.3, coverage: 16, positions: 8, regions: "with", hulls: true },
    colorBy: "area",
    sizeBy: "evidence",
    layoutMode: "anchored",
    types: CONCEPTS,
  },
  {
    id: "reading",
    name: "Reading queue",
    story: "I want the papers around my concepts, coloured by how deeply I read them, labelled so the well-connected but unread ones stand out.",
    lab: { wTier: 0.5, wEvidence: 0, wDegree: 0.6, wGap: 1, easyWeight: 0.3, positions: 8 },
    colorBy: "depth",
    sizeBy: "logdeg",
    layoutMode: "anchored",
    types: ["topic", "idea", "question", "paper", "part"],
  },
  {
    id: "people",
    name: "People and their work",
    story: "Before contacting a researcher I want to see who sits near which concept, and the papers that tie them in.",
    lab: { wTier: 0, wDegree: 0.4, positions: 8 },
    colorBy: "type",
    sizeBy: "evidence",
    layoutMode: "anchored",
    types: ["person", "topic", "paper", "idea"],
    typeLabels: ["person"],
  },
  {
    id: "hygiene",
    name: "Graph hygiene",
    story: "Once a week I want to see orphans and pages with almost no links, so the graph stays trustworthy.",
    lab: { wTier: 0.2, wEvidence: 0, wOrphan: 2, wOpen: 0, norm: "global", coverage: 14, sizeMode: "uniform", base: 11 },
    colorBy: "type",
    sizeBy: "uniform",
    layoutMode: "anchored",
    types: ["topic", "idea", "question", "person", "paper", "course", "book", "series"],
  },
  {
    id: "baseline",
    name: "Before the lab (old rule)",
    story: "The rule the graph used before: about 12 hub labels (collections, topics) ranked by link count; other pages only from 2× zoom. One label size, below the node, on a box.",
    lab: {
      wTier: 0, wEvidence: 0, wDegree: 1, wOpen: 0, norm: "global", degBasis: "all", scope: "screen", strategy: "count", count: 12,
      zoomGrowth: 1.5, pool: "hubs", positions: 1, avoidNodes: false, sizeMode: "uniform", base: 10, minPx: 2.5, textField: "title",
      maxChars: 42, bg: "box", weightTier: false, fade: 0, hysteresis: 0, perceptual: false,
      wrapT1: 0, wrapT2: 0, wrapT3: 0, maxLines: 1, forcedPill: false, leaderLines: false, edgeFlip: false, neighborBy: "score",
    },
    colorBy: "type",
    sizeBy: "connections",
    layoutMode: "free",
    types: ["topic", "question", "idea", "person"],
  },
];

export const DEFAULT_STORY = "map";

/** The pills of the views bar, in order. */
export const HEADLINE_STORIES: readonly Story[] = STORIES.filter((s) => s.headline);
/** Views reachable from "More": the rest, minus the lab leftovers that only compare label rules. */
export const MORE_STORIES: readonly Story[] = STORIES.filter((s) => !s.headline && !["baseline", "compare", "orient"].includes(s.id));

export const storyById = (id: string): Story | undefined => STORIES.find((s) => s.id === id);

/** The whole lab config of a story: the defaults plus its overrides (a story starts from the principles). */
export const storyLab = (s: Story): LabConfig => ({ ...DEFAULT_LAB, ...s.lab });
