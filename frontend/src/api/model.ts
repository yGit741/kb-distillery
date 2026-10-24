/** The data model vocabulary. Three page types, each with a kind; sources have a depth. */
export const SOURCE_KINDS = ["paper", "article", "blog-post", "video", "lecture", "conversation", "ai-chat", "part"] as const;
export const COLLECTION_KINDS = ["book", "notebook", "course", "series"] as const;
export const CONCEPT_KINDS = ["idea", "topic", "question", "person"] as const;

export type SourceKind = (typeof SOURCE_KINDS)[number];
export type CollectionKind = (typeof COLLECTION_KINDS)[number];
export type ConceptKind = (typeof CONCEPT_KINDS)[number];
export type Kind = SourceKind | CollectionKind | ConceptKind;
export type PageType = "source" | "collection" | "concept";

export const DEPTHS = ["catalog", "easy", "full", "deep"] as const;
export type Depth = (typeof DEPTHS)[number];

/** A node of the vault graph, in new-model words (already translated at the API boundary). */
export interface GraphNode {
  slug: string;
  title: string;
  type: PageType;
  kind: Kind;
  depth?: Depth;
  draft?: boolean;
  status: string;
  areas: string[];
}
