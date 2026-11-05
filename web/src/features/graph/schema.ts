import { DEPTHS, LAYER_TYPES, LAYERS, type Layer } from "@/api/model";

export interface TypeInfo {
  id: string;
  label: string;
  layer: Layer;
}

export interface GraphSchema {
  /** Every type in layer order (the legend rows). */
  types: TypeInfo[];
  /** The types drawn when the graph opens: the concept layer, minus people. */
  defaultVisible: string[];
  depths: readonly string[];
}

const title = (id: string) => id.replace(/-/g, " ").replace(/^./, (c) => c.toUpperCase());
const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null;
const isLayer = (v: unknown): v is Layer => typeof v === "string" && (LAYERS as string[]).includes(v);

export const FALLBACK_DEFAULT_VISIBLE = ["topic", "idea", "question"];

/** The `schema` object of /api/graph (types with label and layer, default_visible). Falls back to src/api/model.ts. */
export function parseSchema(raw: unknown): GraphSchema {
  const types: TypeInfo[] = [];
  if (isObj(raw) && Array.isArray(raw["types"])) {
    for (const t of raw["types"] as unknown[]) {
      if (!isObj(t) || typeof t["id"] !== "string" || !isLayer(t["layer"])) continue;
      types.push({ id: t["id"], label: typeof t["label"] === "string" ? t["label"] : title(t["id"]), layer: t["layer"] });
    }
  }
  if (!types.length) {
    for (const layer of LAYERS) for (const id of LAYER_TYPES[layer]) types.push({ id, label: title(id), layer });
  }
  const dv = isObj(raw) && Array.isArray(raw["default_visible"]) ? (raw["default_visible"] as unknown[]).filter((x): x is string => typeof x === "string") : [];
  return { types, defaultVisible: dv.length ? dv : FALLBACK_DEFAULT_VISIBLE, depths: DEPTHS };
}

/**
 * The layer of a type the kit does not define (an OKF bundle's `Source`, `Concept`, `Comparison` imported into the
 * base kit): a name that says source, document, paper or article is a source; anything else is a concept, so it is
 * drawn as an idea-like ring and the Map shows it.
 */
export function inferLayer(type: string): Layer {
  return !type || /source|document|paper|article|^doc$/i.test(type) ? "source" : "concept";
}

/** The schema plus every type the data carries that the kit does not define, each in its inferred layer. */
export function withDataTypes(schema: GraphSchema, inData: readonly string[]): GraphSchema {
  const known = new Set(schema.types.map((t) => t.id));
  const extra = [...new Set(inData)].filter((id) => id && !known.has(id)).sort();
  if (!extra.length) return schema;
  return { ...schema, types: [...schema.types, ...extra.map((id) => ({ id, label: title(id), layer: inferLayer(id) }))] };
}

/** Types present in the data first (in schema order), then any unknown type the data carries. */
export function presentTypes(schema: GraphSchema, inData: readonly string[]): TypeInfo[] {
  const have = new Set(inData);
  const known = schema.types.filter((t) => have.has(t.id));
  const extra = [...have].filter((id) => !schema.types.some((t) => t.id === id)).sort();
  return [...known, ...extra.map((id) => ({ id, label: title(id || "unknown"), layer: inferLayer(id) }))];
}

export const typeLabel = (schema: GraphSchema, id: string): string =>
  schema.types.find((t) => t.id === id)?.label ?? title(id || "unknown");
