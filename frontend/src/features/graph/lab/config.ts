/**
 * Settings of the label rail (ported from the Label Lab artifact). Every field is a knob in ./LabRail; the
 * defaults are the research-backed ones (coverage ~12%, radical-law growth, three tiers >= 11 px, top-first
 * placement, labels chosen for the whole graph so a pan never reshuffles them).
 */
export type Norm = "type" | "global";
export type DegBasis = "visible" | "nohub" | "all";
export type Strategy = "coverage" | "count" | "threshold" | "all";
export type LabelScope = "world" | "screen";
export type Pool = "all" | "hubs";
export type SizeMode = "tiers" | "quantile" | "continuous" | "uniform";
export type TextField = "short" | "title" | "slug";
export type LabelBg = "halo" | "box" | "none";
export type Regions = "off" | "auto" | "with";
export type Positions = 1 | 4 | 8;
export type NeighborBy = "weight" | "score";
export type QuestionLabels = "none" | "short" | "full";

export interface LabConfig {
  // importance
  wTier: number;
  wEvidence: number;
  easyWeight: number;
  wDegree: number;
  degBasis: DegBasis;
  wPagerank: number;
  wBetween: number;
  wOpen: number;
  wGap: number;
  wOrphan: number;
  norm: Norm;
  // which labels show
  scope: LabelScope;
  strategy: Strategy;
  coverage: number;
  count: number;
  threshold: number;
  zoomGrowth: number;
  pool: Pool;
  hoverNeighbors: boolean;
  neighborCap: number;
  lens: boolean;
  lensR: number;
  lensMax: number;
  // focus
  doiHops: number;
  doiLambda: number;
  // placement
  declutter: boolean;
  positions: Positions;
  avoidNodes: boolean;
  pad: number;
  /** a label pushed off the canvas tries the mirrored offset before it is dropped */
  edgeFlip: boolean;
  /** a forced label squeezed out of every adjacent slot moves out on a ring with a leader line */
  leaderLines: boolean;
  /** which neighbours of a clicked page get a label: by edge weight (stable) or by score */
  neighborBy: NeighborBy;
  forcedPill: boolean;
  // typography
  sizeMode: SizeMode;
  base: number;
  t1: number;
  t2: number;
  t3: number;
  zoomScale: number;
  minPx: number;
  weightTier: boolean;
  textField: TextField;
  maxChars: number;
  /** wrap width per tier in px (0 = a character cut on one line) and the lines allowed */
  wrapT1: number;
  wrapT2: number;
  wrapT3: number;
  maxLines: number;
  charsT3: number;
  /** questions: hidden until hovered or clicked, cut to charsQuestion, or like any page */
  questionLabels: QuestionLabels;
  charsQuestion: number;
  bg: LabelBg;
  // stability
  fade: number;
  hysteresis: number;
  // regions
  regions: Regions;
  regionZoom: number;
  regionsSuppress: boolean;
  hulls: boolean;
  /** hull core: pages within mean + sigma·sd of the median (0 = the closest 70%) */
  hullSigma: number;
  // nodes
  nodeRange: number;
  perceptual: boolean;
}

export const DEFAULT_LAB: LabConfig = {
  wTier: 1,
  wEvidence: 1,
  easyWeight: 0.5,
  wDegree: 0,
  degBasis: "visible",
  wPagerank: 0,
  wBetween: 0,
  wOpen: 0.3,
  wGap: 0,
  wOrphan: 0,
  norm: "type",
  scope: "world",
  strategy: "coverage",
  coverage: 12,
  count: 12,
  threshold: 0.55,
  zoomGrowth: 0.5,
  pool: "all",
  hoverNeighbors: true,
  // a click labels its few strongest neighbours, not twenty: emphasis stays meaningful
  neighborCap: 6,
  lens: false,
  lensR: 90,
  lensMax: 20,
  doiHops: 0,
  doiLambda: 0.25,
  declutter: true,
  positions: 4,
  avoidNodes: true,
  pad: 2,
  edgeFlip: true,
  leaderLines: true,
  neighborBy: "weight",
  // no pills: the hovered page's glow and its whole title mark the focus
  forcedPill: false,
  // label size by importance rank (top 5% / next 20% / rest), so size and showing mean the same thing
  sizeMode: "quantile",
  base: 12,
  t1: 17,
  t2: 13.5,
  t3: 11.5,
  zoomScale: 0,
  minPx: 11,
  weightTier: true,
  textField: "short",
  maxChars: 28,
  wrapT1: 160,
  wrapT2: 110,
  wrapT3: 0,
  maxLines: 2,
  charsT3: 26,
  questionLabels: "none",
  charsQuestion: 26,
  bg: "halo",
  fade: 250,
  // labels already on screen hold their place harder, so a zoom reshuffles fewer of them
  hysteresis: 0.35,
  regions: "off",
  regionZoom: 0.9,
  regionsSuppress: true,
  hulls: false,
  hullSigma: 2,
  nodeRange: 2.2,
  perceptual: true,
};

/** Keep only known keys of the right type (stored settings may come from an older version). */
export function sanitizeLab(raw: unknown): LabConfig {
  const out: Record<string, unknown> = { ...DEFAULT_LAB };
  if (typeof raw === "object" && raw !== null) {
    for (const k of Object.keys(DEFAULT_LAB) as (keyof LabConfig)[]) {
      const v = (raw as Record<string, unknown>)[k];
      if (v !== undefined && typeof v === typeof DEFAULT_LAB[k]) out[k] = v;
    }
    // enumerations: an unknown value falls back to the default
    if (!["none", "short", "full"].includes(out["questionLabels"] as string)) out["questionLabels"] = DEFAULT_LAB.questionLabels;
    if (!["weight", "score"].includes(out["neighborBy"] as string)) out["neighborBy"] = DEFAULT_LAB.neighborBy;
  }
  return out as unknown as LabConfig;
}

/** Label tier of a type: 1 topics and collections, 2 ideas, questions, people, 3 sources. */
export function tierOf(type: string): 1 | 2 | 3 {
  if (type === "topic" || type === "course" || type === "book" || type === "series") return 1;
  if (type === "idea" || type === "question" || type === "person") return 2;
  return 3;
}

/** A-priori importance of a type (the "type tier" signal): topic > question > idea > person > collection > source. */
export const TYPE_RANK: Readonly<Record<string, number>> = {
  topic: 1,
  question: 0.85,
  idea: 0.7,
  person: 0.6,
  course: 0.55,
  book: 0.55,
  series: 0.5,
  paper: 0.4,
  part: 0.4,
  mail: 0.3,
  "blog-post": 0.25,
  article: 0.2,
  "ai-chat": 0.2,
};

/** How much a source counts as evidence by how deeply it was read (easy is a knob). */
export const DEPTH_WEIGHT: Readonly<Record<string, number>> = { listed: 0, easy: 1, full: 2, deep: 3 };
