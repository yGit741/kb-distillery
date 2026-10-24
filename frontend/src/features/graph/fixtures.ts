import type { GraphSnapshot } from "@/api";
import type { GNode } from "./types";

export const node = (id: string, o: Partial<GNode> = {}): GNode => ({
  id,
  label: id,
  title: id.replace(/-/g, " "),
  type: "topic",
  layer: "concept",
  status: "growing",
  depth: "",
  areas: [],
  year: null,
  inDegree: 0,
  outDegree: 0,
  path: `wiki/${id}.md`,
  preview: "",
  properties: {},
  ...o,
});

export const sampleNodes: GNode[] = [
  node("topic-learning-theory", { inDegree: 5, outDegree: 3, areas: ["learning-theory"] }),
  node("idea-margin", { type: "idea", inDegree: 2, outDegree: 1, areas: ["learning-theory", "optimization-theory"] }),
  node("q-why-big-nets-work", { type: "question", status: "open", inDegree: 1, outDegree: 1 }),
  node("jane-doe", { type: "person", status: "", inDegree: 0, outDegree: 2 }),
  node("course-runi-rl", { type: "course", layer: "collection", status: "reading", inDegree: 6, outDegree: 0 }),
  node("2019-fine-grained", { type: "paper", layer: "source", depth: "full", status: "digested", year: 2019, inDegree: 1, outDegree: 3 }),
  node("2020-listed-paper", { type: "paper", layer: "source", depth: "listed", status: "to-read", year: 2020, inDegree: 0, outDegree: 1 }),
];

export const sampleLinks = [
  { source: "2019-fine-grained", target: "topic-learning-theory", kind: "wikilink" as const },
  { source: "2019-fine-grained", target: "idea-margin", kind: "wikilink" as const },
  { source: "2020-listed-paper", target: "idea-margin", kind: "related" as const },
  { source: "topic-learning-theory", target: "idea-margin", kind: "wikilink" as const },
  { source: "course-runi-rl", target: "2019-fine-grained", kind: "wikilink" as const },
  { source: "q-why-big-nets-work", target: "topic-learning-theory", kind: "wikilink" as const },
  { source: "jane-doe", target: "topic-learning-theory", kind: "wikilink" as const },
];

export const sampleSnapshot = (over: Partial<GraphSnapshot> = {}): GraphSnapshot => ({
  concept_links: [{ source: "idea-margin", target: "topic-learning-theory", shared: 1 }],
  etag: "e1",
  facets: { areas: [], statuses: [], types: [] },
  generated_at: "2026-10-24T10:00:00Z",
  link_count: sampleLinks.length,
  links: sampleLinks,
  node_count: sampleNodes.length,
  nodes: sampleNodes,
  schema: {
    types: [
      { id: "paper", label: "Paper", layer: "source" },
      { id: "course", label: "Course", layer: "collection" },
      { id: "topic", label: "Topic", layer: "concept" },
      { id: "idea", label: "Idea", layer: "concept" },
      { id: "question", label: "Question", layer: "concept" },
      { id: "person", label: "Person", layer: "concept" },
    ],
    default_visible: ["topic", "idea", "question"],
  },
  ...over,
});

/** A `?layer=raw` snapshot: two piles (and a skipped inbox), pile links, and the files of one paper with an ink companion. */
export const rawSnapshot = () =>
  ({
    ...sampleSnapshot(),
    layer: "raw",
    piles: [
      { format: "printed-docs", count: 10, source: 4, partial: 0, queued: 3, skip: 1, companions: 2, pages_fed: 2, links_to_pages: { "2019-fine-grained": 3, "idea-margin": 2, "not-a-page": 9 } },
      { format: "emails", count: 3, source: 0, partial: 0, queued: 3, skip: 0, companions: 0, pages_fed: 0, links_to_pages: {} },
      { format: "inbox", count: 5, source: 0, partial: 0, queued: 5, skip: 0, companions: 0, pages_fed: 0, links_to_pages: {} },
      { format: "images", count: 0, source: 0, partial: 0, queued: 0, skip: 0, companions: 0, pages_fed: 0, links_to_pages: {} },
    ],
    pile_links: [
      { source: "printed-docs", target: "emails", kind: "hub", count: 2 },
      { source: "printed-docs", target: "emails", kind: "page", count: 9 },
      { source: "printed-docs", target: "inbox", kind: "hub", count: 1 },
    ],
    raw_nodes: [
      { id: "raw:raw/printed-docs/a.pdf", path: "raw/printed-docs/a.pdf", format: "printed-docs", ext: "pdf", disposition: "source", companion_of: null, collection: [], slug: "2019-fine-grained", year: 2019, title: "A" },
      { id: "raw:raw/printed-docs/a-ink.pdf", path: "raw/printed-docs/a-ink.pdf", format: "printed-docs", ext: "pdf", disposition: "ink", companion_of: "raw/printed-docs/a.pdf", collection: [], slug: "2019-fine-grained", year: null, title: "ink" },
    ],
    raw_links: [
      { source: "raw:raw/printed-docs/a.pdf", target: "2019-fine-grained", kind: "source" },
      { source: "raw:raw/printed-docs/a-ink.pdf", target: "2019-fine-grained", kind: "source" },
    ],
  }) as unknown as GraphSnapshot;
