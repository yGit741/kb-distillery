/**
 * The data model as shipped (schema 1.0; meta/schema.py LAYER_OF, AGENTS.md "Page layers").
 * Every page has a `layer` and a `type` inside it; sources also carry a `depth`.
 */
export const LAYER_TYPES = {
  source: ["paper", "part", "lecture", "article", "video", "conversation", "ai-chat", "blog-post"],
  collection: ["book", "notebook", "course", "series", "scope"], // scope is aux
  concept: ["idea", "topic", "question", "person", "distilled-think"], // distilled-think is aux
} as const;

export type Layer = keyof typeof LAYER_TYPES;
export type PageTypeOf<L extends Layer> = (typeof LAYER_TYPES)[L][number];
export type SourceType = PageTypeOf<"source">;
export type CollectionType = PageTypeOf<"collection">;
export type ConceptType = PageTypeOf<"concept">;
export type PageType = SourceType | CollectionType | ConceptType;

export const LAYERS = Object.keys(LAYER_TYPES) as Layer[];

/** Sources only, ordered: listed = cataloged, not read yet. */
export const DEPTHS = ["listed", "easy", "full", "deep"] as const;
export type Depth = (typeof DEPTHS)[number];

/** status: sources and collections to-read/reading/digested; ideas and topics seed/growing/solid;
 *  questions open/partial/resolved; distilled-think review/applied/archived; scopes active/parked. */
export type Status = string;
