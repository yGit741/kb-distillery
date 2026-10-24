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
}

const CONCEPTS = ["topic", "question", "idea"] as const;

export const STORIES: readonly Story[] = [
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
    lab: { wTier: 0.6, wEvidence: 0.6, wOpen: 1.5, coverage: 14, positions: 8, t2: 13 },
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
    },
    colorBy: "type",
    sizeBy: "connections",
    layoutMode: "free",
    types: ["topic", "question", "idea", "person"],
  },
];

export const DEFAULT_STORY = "orient";

export const storyById = (id: string): Story | undefined => STORIES.find((s) => s.id === id);

/** The whole lab config of a story: the defaults plus its overrides (a story starts from the principles). */
export const storyLab = (s: Story): LabConfig => ({ ...DEFAULT_LAB, ...s.lab });
