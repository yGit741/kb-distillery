import type { PreviewItem, QueueEntry } from "./model";

/**
 * Sample data for the edit preview while flag ui.edit-preview is dark: one source and the pages it touches. The
 * queue and the on-open integration replace this file.
 */
export const SAMPLE_ITEM: PreviewItem = {
  id: "sample-sparse-attention",
  title: "Scaling laws for sparse attention",
  before: [
    {
      id: "b-block-sparse",
      title: "\"Block-sparse attention\" is new here",
      why: "It is close to your page Sparse attention.",
      options: ["Add to Sparse attention", "Make a new page"],
      picked: 0,
    },
    {
      id: "b-split-scaling",
      title: "Scaling laws would cover three ideas",
      why: "Compute scaling, data scaling, and now sparse scaling.",
      options: ["Split it", "Keep one page"],
      picked: 1,
    },
  ],
  pages: [
    {
      slug: "attention",
      title: "Attention",
      type: "idea",
      areas: ["transformers"],
      protected: true,
      body: [
        "Attention lets each token weigh every other token in the sequence. The weights come from a softmax over scaled dot products of queries and keys.",
        {
          id: "a1",
          kind: "rewrite",
          before: "Full attention is required for strong performance on long-range tasks.",
          after: "Full attention is not required: block-sparse patterns match it on long-range tasks above 1B parameters.",
          quote: "Section 4.2: \"we find no measurable gap between full and block-sparse attention above 1B parameters\"",
        },
        "Cost grows quadratically with sequence length, which limits context size.",
        { id: "a2", kind: "addition", after: "With a fixed sparsity ratio the cost grows close to linearly.", quote: "Section 3, equation 7" },
      ],
      links: 1,
      fixes: 0,
      similar: [{ slug: "self-attention", title: "Self-attention", why: "same definition; 4 of 5 claims repeat" }],
    },
    {
      slug: "scaling-laws",
      title: "Scaling laws",
      type: "topic",
      areas: ["training"],
      body: [
        "Loss falls as a power law in parameters, data and compute, as long as none of the three is the bottleneck.",
        {
          id: "s1",
          kind: "rewrite",
          before: "The compute-optimal ratio is about 20 tokens per parameter.",
          after: "The compute-optimal ratio is about 20 tokens per parameter for dense models, and about 14 for block-sparse ones.",
          quote: "Table 2",
        },
        "Most results come from dense decoder-only models.",
      ],
      links: 0,
      fixes: 0,
      similar: [{ slug: "compute-optimal-training", title: "Compute-optimal training", why: "the token-per-parameter rule appears in both" }],
    },
    {
      slug: "sparse-attention",
      title: "Sparse attention",
      type: "idea",
      areas: ["transformers"],
      isNew: true,
      body: [
        {
          id: "n1",
          kind: "addition",
          after: "Sparse attention restricts each token to a subset of positions (local windows, strides or learned blocks), so cost grows close to linearly.",
          quote: "Section 2",
        },
        { id: "n2", kind: "addition", after: "Block-sparse patterns match full attention above about 1B parameters; see Attention.", quote: "Section 4.2" },
      ],
      links: 2,
      fixes: 0,
      similar: [{ slug: "linear-attention", title: "Linear attention", why: "both make attention cost close to linear" }],
    },
    {
      slug: "kv-cache",
      title: "KV cache",
      type: "idea",
      areas: ["inference"],
      body: [
        "The KV cache stores keys and values of past tokens so decoding does not recompute them.",
        { id: "k1", kind: "addition", after: "Block sparsity shrinks the cache in proportion to the sparsity ratio.", quote: "Section 5.1" },
        "Its size grows linearly with context length.",
      ],
      links: 0,
      fixes: 0,
      similar: [],
    },
    {
      slug: "flashattention",
      title: "FlashAttention",
      type: "idea",
      areas: ["inference"],
      body: ["FlashAttention computes exact attention in tiles that fit in on-chip memory, never building the full attention matrix."],
      links: 3,
      fixes: 1,
      similar: [],
    },
  ],
  leftOut: [
    {
      id: "l-transfer",
      title: "\"Sparsity patterns learned at small scale transfer to 10x larger models.\"",
      why: "Section 6",
      options: ["Add to Scaling laws", "New page", "Leave out"],
      picked: 2,
    },
    {
      id: "l-training-cost",
      title: "\"Training cost grows sub-linearly with context under block sparsity.\"",
      why: "Section 5.3",
      options: ["Add to KV cache", "New page", "Leave out"],
      picked: 0,
    },
  ],
};

export const SAMPLE_QUEUE: QueueEntry[] = [
  { id: SAMPLE_ITEM.id, title: SAMPLE_ITEM.title, note: "5 pages, 2 rewrites", protected: true },
  { id: "sample-moe", title: "Mixture of experts routing", note: "4 pages, 1 rewrite" },
  { id: "sample-flag", title: "Flag on Attention", note: "1 page, a correction", protected: true },
  { id: "sample-rope", title: "The RoPE paper", note: "waiting" },
  { id: "sample-lecture", title: "Lecture 7: long context", note: "waiting" },
];
