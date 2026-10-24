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
