/**
 * The graph's visual language, shared by every surface that draws a page as a node (Full Graph, Home, page mini
 * graph, citation view, the explorer's chips): which mark a type gets, its geometry, the source glyphs, the state
 * rings and the label style. Nothing here knows about a surface's features (views, filters, hulls, lab rail).
 */

/** One mark per type: sources and people solid (a person with initials), concepts a ring with one symbol inside, collections a ring inside a ring. */
export type NodeMark = "source" | "person" | "question" | "idea" | "topic" | "collection" | ConceptSymbol;
/** Ring symbols handed to concept types the table does not name (a kit's own types), in this order. */
export type ConceptSymbol = "equals" | "plus" | "triangle" | "diamond";
const CONCEPT_POOL: readonly NodeMark[] = ["idea", "equals", "plus", "triangle", "diamond", "topic", "question"];
/** The engine's own page types (a scope, a distilled think-note proposal): they keep their mark, never a pool symbol. */
const TOOL_TYPES: ReadonlySet<string> = new Set(["scope", "distilled-think"]);
/** Marks given by `registerTypeMarks` to the types the table does not name. */
let AUTO: Readonly<Record<string, NodeMark>> = {};

const MARK: Readonly<Record<string, NodeMark>> = {
  person: "person",
  question: "question",
  idea: "idea",
  topic: "topic",
  course: "collection",
  book: "collection",
  series: "collection",
  part: "collection",
};

/** A type's mark: the table's, else the one `registerTypeMarks` gave it, else a source. */
export const markOf = (type: string): NodeMark => MARK[type] ?? AUTO[type] ?? "source";

/**
 * Give every concept-layer type the table does not name (a kit's or a bundle's own) a mark of its own, so two types
 * never look alike: each takes the next symbol of the pool that no present type already uses. Every other type keeps
 * the mark it had (a source its glyph, the engine's own types theirs), so existing kbs look as before. Stable for a
 * given type list (it follows the list's order); called when a graph's schema loads.
 */
export function registerTypeMarks(types: readonly { id: string; layer: string }[]): void {
  const used = new Set<NodeMark>(types.map((t) => MARK[t.id]).filter((m): m is NodeMark => !!m));
  const next: Record<string, NodeMark> = {};
  for (const t of types) {
    if (MARK[t.id] || TOOL_TYPES.has(t.id)) continue;
    if (t.layer === "concept") {
      const m = CONCEPT_POOL.find((c) => !used.has(c)) ?? "idea";
      used.add(m);
      next[t.id] = m;
    }
  }
  AUTO = next;
}

/** The legend's mark key, in reading order. */
export const MARK_KEY: readonly { mark: NodeMark; label: string }[] = [
  { mark: "source", label: "Source" },
  { mark: "person", label: "Person" },
  { mark: "question", label: "Question" },
  { mark: "idea", label: "Idea" },
  { mark: "topic", label: "Topic" },
  { mark: "collection", label: "Collection" },
];

/** Hollow marks carry less ink than a solid dot of the same radius: drawn this much larger to read the same size. */
export const RING_BOOST = 1.15;

/** A mark's drawn radius for a size r: hollow marks get `RING_BOOST`, so a ring reads as big as a dot of radius r. */
export const inkRadius = (type: string, r: number): number => {
  const m = markOf(type);
  return m === "source" || m === "person" ? r : r * RING_BOOST;
};

/** How far a mark of radius r reaches, stroke included (a collection's outer ring): labels keep clear of this. */
export function outerRadius(type: string, r: number): number {
  const m = markOf(type);
  if (m === "collection") return r * (GEOMETRY.collectionOuter + GEOMETRY.collectionOuterStroke / 2);
  return m === "source" || m === "person" ? r : r * (1 + GEOMETRY.ringStroke / 2);
}

/**
 * Mark geometry as fractions of the radius r, read by both the canvas (`drawMark`) and the SVG (`NodeMarkSvg`), so
 * the two never drift: the ring's stroke, the idea's centre dot, the topic's three lines, the question's "?", the
 * collection's outer ring and a person's initials.
 */
export const GEOMETRY = {
  ringStroke: 0.24,
  ideaDot: 0.36,
  topicLineGap: 0.36,
  topicLineHalf: 0.42,
  topicLineStroke: 0.16,
  questionText: 1.25,
  textDy: 0.08,
  collectionOuter: 1.35,
  collectionOuterStroke: 0.14,
  initials2: 0.95,
  initials3: 0.78,
  /** the pool symbols (equals, plus, triangle, diamond): half-width of a bar or shape, and the bar stroke */
  symbolHalf: 0.42,
  symbolGap: 0.22,
  symbolStroke: 0.16,
} as const;

/** A pool symbol inside its ring, as one SVG path in a box centred at (x, y) for radius r; `fill` says how to paint it. */
export function symbolPath(mark: ConceptSymbol, x: number, y: number, r: number): { d: string; fill: boolean } {
  const h = r * GEOMETRY.symbolHalf;
  const g = r * GEOMETRY.symbolGap;
  if (mark === "equals") return { d: `M${x - h} ${y - g}h${2 * h}M${x - h} ${y + g}h${2 * h}`, fill: false };
  if (mark === "plus") return { d: `M${x - h} ${y}h${2 * h}M${x} ${y - h}v${2 * h}`, fill: false };
  // equilateral, centred on its centroid so it does not sit high in the ring
  if (mark === "triangle") return { d: `M${x} ${y - h}L${x + h * 0.87} ${y + h / 2}L${x - h * 0.87} ${y + h / 2}Z`, fill: true };
  return { d: `M${x} ${y - h}L${x + h} ${y}L${x} ${y + h}L${x - h} ${y}Z`, fill: true };
}
export const isConceptSymbol = (m: NodeMark): m is ConceptSymbol => m === "equals" || m === "plus" || m === "triangle" || m === "diamond";

/** Mail threads: still typed `conversation` in the vault until the schema renames it to `mail`. */
export const MAIL_TYPES: ReadonlySet<string> = new Set(["mail", "email", "conversation"]);
/** Legend names that differ from the schema's, until the schema catches up. */
export const TYPE_LABEL_OVERRIDE: Readonly<Record<string, string>> = { conversation: "Mail" };

/**
 * A source's glyph, drawn white inside its dot (canvas) or in the text colour (SVG): page (paper), text lines
 * (article, blog post, the rest), sparkle (AI chat), envelope (mail), play (lecture, video), book (part), and the raw
 * formats a source comes from: scissors (web clip), slides, image, pen (handwritten).
 */
export type SourceGlyph = "paper" | "text" | "sparkle" | "mail" | "play" | "book" | "clip" | "slides" | "image" | "handwritten";

const GLYPH: Readonly<Record<string, SourceGlyph>> = {
  paper: "paper",
  pdf: "paper",
  "ai-chat": "sparkle",
  chat: "sparkle",
  mail: "mail",
  email: "mail",
  conversation: "mail",
  lecture: "play",
  part: "book",
  book: "book",
  web: "clip",
  "web-clip": "clip",
  slides: "slides",
  image: "image",
  handwritten: "handwritten",
};

/** A source type's (or raw format's) glyph; anything unnamed reads as text lines. */
export const glyphOf = (type: string): SourceGlyph => GLYPH[type] ?? "text";

/** Every glyph with its plain name, for the legend's Sources row. */
export const GLYPH_LABEL: Readonly<Record<SourceGlyph, string>> = {
  paper: "Paper",
  text: "Article / post",
  sparkle: "AI chat",
  mail: "Mail",
  play: "Lecture",
  book: "Book part",
  clip: "Web clip",
  slides: "Slides",
  image: "Image",
  handwritten: "Handwritten",
};

/**
 * SVG paths of each source glyph in a 16 px box. The canvas draws the raw-format glyphs (clip, slides, image,
 * handwritten) from these same paths, so the two cannot drift.
 */
export const GLYPH_SVG: Readonly<Record<SourceGlyph, { d: string; fill?: boolean }>> = {
  paper: { d: "M4 2h5.5L12 4.5V14H4zM6 8h4M6 10.5h4" },
  sparkle: { d: "M8 1.8c.4 2.9 1.6 4.8 6.2 6.2-4.6 1.4-5.8 3.3-6.2 6.2-.4-2.9-1.6-4.8-6.2-6.2C6.4 6.6 7.6 4.7 8 1.8z", fill: true },
  mail: { d: "M2.5 4h11v8h-11zM2.5 4 8 8.6 13.5 4" },
  play: { d: "M5 3.5 12 8l-7 4.5z", fill: true },
  book: { d: "M8 4.5C6.5 3.5 4.5 3.5 2.5 4v8c2-.5 4-.5 5.5.5 1.5-1 3.5-1 5.5-.5V4c-2-.5-4-.5-5.5.5zM8 4.5v8" },
  text: { d: "M3 5h10M3 8h10M3 11h6" },
  clip: { d: "M4.6 11.6a1.4 1.4 0 1 0 0 .01M11.4 11.6a1.4 1.4 0 1 0 0 .01M5.6 10.4 11 2.5M10.4 10.4 5 2.5" },
  slides: { d: "M2.5 3h11v7.5h-11zM8 10.5v3M5.5 13.5h5" },
  image: { d: "M2.5 3h11v10h-11zM2.5 11l3.5-3.5 2.5 2.5 1.5-1.5 3.5 3.5" },
  handwritten: { d: "M5 10 12 3M2.5 13.5c1.5-1.5 3-1.5 4 0s3 1.5 6.5-.5" },
};

/** A mark's radius in a 16 px icon box, so every mark (stroke included) fills about the same square. */
export const ICON_R: Readonly<Record<NodeMark, number>> = { source: 6.6, person: 6.8, question: 5.8, idea: 5.8, topic: 5.8, collection: 5.2, equals: 5.8, plus: 5.8, triangle: 5.8, diamond: 5.8 };

/** On-screen radius from which a source shows its type glyph (below it, a plain dot); a hovered source always does. */
export const SOURCE_GLYPH_PX = 8;

/**
 * One state language, in screen px: the selection ring sits `gap` outside the mark; the hovered page gets a soft
 * glow in its own colour (`glow` px wide), not a ring; the focus (Home's picked concept) is a slightly heavier ring;
 * the drawn source (Home's pipeline) the selection ring.
 */
export const STATE = {
  gap: 3,
  selected: { width: 2, alpha: 0.95 },
  focus: { width: 2.5, alpha: 0.95 },
  drawn: { width: 2, alpha: 0.95 },
  hoverRing: { width: 1.5, alpha: 0.55 },
  favorite: { width: 1, alpha: 0.4 },
  glow: 14,
  glowAlpha: 0.45,
} as const;
export type NodeState = "selected" | "focus" | "drawn" | "hover" | "favorite" | null;

/** One label style: text halo width in px (the page's background colour behind the text), and the smallest label. */
export const LABEL = {
  halo: 3.5,
  minPx: 11,
} as const;

/** A person's initials: first + last name; people who would share them get the surname's second letter too. */
export function personInitials(nodes: readonly { id: string; type: string; title?: string | null }[]): Map<string, string> {
  const base = new Map<string, { two: string; three: string }>();
  for (const n of nodes) {
    if (n.type !== "person") continue;
    const words = (n.title || n.id).replace(/[^\p{L}\s-]/gu, " ").split(/[\s-]+/).filter(Boolean);
    const first = words[0] ?? "?";
    const last = words.length > 1 ? words[words.length - 1]! : "";
    const two = (first[0]! + (last[0] ?? "")).toUpperCase();
    base.set(n.id, { two, three: two + (last[1] ?? "").toLowerCase() });
  }
  const count = new Map<string, number>();
  for (const { two } of base.values()) count.set(two, (count.get(two) ?? 0) + 1);
  return new Map([...base].map(([id, b]) => [id, (count.get(b.two) ?? 0) > 1 ? b.three : b.two]));
}
