/**
 * The graph's visual language, shared by every surface that draws a page as a node (Full Graph, Home, page mini
 * graph, citation view, the explorer's chips): which mark a type gets, its geometry, the source glyphs, the state
 * rings and the label style. Nothing here knows about a surface's features (views, filters, hulls, lab rail).
 */

/** One mark per type: sources and people solid (a person with initials), concepts a ring with one symbol inside, collections a ring inside a ring. */
export type NodeMark = "source" | "person" | "question" | "idea" | "topic" | "collection";

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

/** A type's mark; every type the table does not name is a source. */
export const markOf = (type: string): NodeMark => MARK[type] ?? "source";

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
} as const;

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
  glow: 14,
  glowAlpha: 0.45,
} as const;
export type NodeState = "selected" | "focus" | "drawn" | "hover" | null;

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
