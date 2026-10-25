import type { GNode } from "./types";

/**
 * Presentation names, local to the app until the vault carries them (a `label:` field per page, an area
 * registry): the graph, the legend and the hover card show these; the pages themselves are untouched.
 */
export const AREA_DISPLAY: Readonly<Record<string, string>> = {
  "boolean-analysis": "Boolean analysis",
  "learning-theory": "Learning theory",
  "implicit-regularization": "Implicit regularization",
  "implicit-bias-of-gradient-descent": "Implicit bias of GD",
  "optimization-theory": "Optimization",
  "tensor-factorization": "Tensor factorization",
  "complex-nn": "Complex-valued NNs",
  "complex-valued-neural-networks": "Complex-valued NNs",
  "info-theory": "Information theory",
  "fourier-analysis": "Fourier analysis",
  "adv-nlp": "NLP",
  "adv-ml": "Advanced ML",
  "adv-stats": "Advanced statistics",
  "prob-models": "Probabilistic models",
  statistics: "Statistics",
  quantum: "Quantum computing",
  rl: "Reinforcement learning",
  transformer: "Transformers",
  "chain-of-thought": "Chain of thought",
  "depth-vs-width": "Depth vs width",
  "double-descent": "Double descent",
};

/** Hand-picked short labels for pages whose titles do not shorten well by rule. */
export const PAGE_DISPLAY: Readonly<Record<string, string>> = {
  "book-2014-analysis-of-boolean-functions": "O'Donnell: Boolean functions",
  "book-2014-understanding-machine-learning": "Understanding ML",
  "series-gil-kalai-blog": "Kalai's blog",
  "series-karpathy-zero-to-hero": "Zero to Hero",
};

/** An area's display name; a slug it does not know is title-cased ("adv-stats" -> "Adv stats"). */
export function areaDisplay(slug?: string | null): string {
  if (!slug) return "";
  const known = AREA_DISPLAY[slug];
  if (known) return known;
  const words = slug.split("-").filter(Boolean);
  return words.map((w, i) => (i === 0 ? w.charAt(0).toUpperCase() + w.slice(1) : w)).join(" ");
}

/** A page's hand-picked short label, when it has one. */
export const pageDisplay = (n: Pick<GNode, "id">): string | undefined => PAGE_DISPLAY[n.id];
