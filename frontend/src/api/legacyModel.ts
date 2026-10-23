/**
 * DELETE after data-model stage 7.
 *
 * The ONLY module allowed to name the old page types (theme, bare concept, distilled-think, ...)
 * and the old `digestion-status` field. Until the vault migration lands, the live backend still
 * emits the old 16 types; the http DataSource passes every page through `fromLegacy` at the
 * boundary, so everything downstream (palette, props, stores, filters, tests) speaks only
 * type / kind / depth.
 */
import type { Depth, Kind, PageType } from "./model";

const SOURCE_KINDS = ["paper", "article", "blog-post", "video", "lecture", "conversation", "ai-chat", "part"] as const;
const COLLECTION_KINDS = ["book", "notebook", "course", "series"] as const;

export interface LegacyNode {
  type?: string | null;
  status?: string | null;
  depth?: string | null;
  "digestion-status"?: string | null;
  [k: string]: unknown;
}

export interface ModelTag {
  type: PageType;
  kind: Kind;
  /** Only sources carry a depth. */
  depth?: Depth;
  /** Transient draft artifact (old `distilled-think`): not a page type in the new model. */
  draft?: boolean;
}

/** Old type -> new (type, kind). `null` = not a page (graph-only node such as a scope). */
export function legacyTypeToModel(oldType: string | null | undefined): Pick<ModelTag, "type" | "kind" | "draft"> | null {
  const t = oldType ?? "";
  if ((SOURCE_KINDS as readonly string[]).includes(t)) return { type: "source", kind: t as Kind };
  if ((COLLECTION_KINDS as readonly string[]).includes(t)) return { type: "collection", kind: t as Kind };
  switch (t) {
    case "theme": return { type: "concept", kind: "topic" };
    case "concept": return { type: "concept", kind: "idea" };
    case "question": return { type: "concept", kind: "question" };
    case "person": return { type: "concept", kind: "person" };
    case "distilled-think": return { type: "concept", kind: "idea", draft: true };
    default: return null;
  }
}

const DEPTHS: readonly string[] = ["catalog", "easy", "full", "deep"];

export function fromLegacy(node: LegacyNode): ModelTag | null {
  const base = legacyTypeToModel(node.type);
  if (!base) return null;
  const raw = node.depth ?? node["digestion-status"] ?? null;
  const depth = base.type === "source" && raw && DEPTHS.includes(raw) ? (raw as Depth) : undefined;
  return depth ? { ...base, depth } : base;
}
