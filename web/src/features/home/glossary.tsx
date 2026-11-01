import { FileText, Image, Mail, MessageSquare, Newspaper, PenLine, Presentation, Scissors, Youtube, type LucideIcon } from "lucide-react";
import type { Depth } from "@/api/model";
import { ShapeIcon, SourceIcon } from "@/features/graph/encoding";
import { depthColor, UNKNOWN_COLOR } from "@/theme/palette";

/** The intro card's vocabulary (approved mock v16): Raw → Source → Concept, plus depth. */
export const RAW_FORMATS: readonly { label: string; icon: LucideIcon }[] = [
  { label: "Printed docs", icon: FileText },
  { label: "reMarkable", icon: PenLine },
  { label: "Slides", icon: Presentation },
  { label: "LLM chats", icon: MessageSquare },
  { label: "Emails", icon: Mail },
  { label: "Web Clipper", icon: Scissors },
  { label: "YouTube", icon: Youtube },
  { label: "WordPress", icon: Newspaper },
  { label: "Images", icon: Image },
];

/** Icon per raw card kind (kb_distillery.services.raw_card.kind_of). */
export const KIND_ICON: Record<string, LucideIcon> = {
  pdf: FileText,
  handwritten: PenLine,
  slides: Presentation,
  chat: MessageSquare,
  email: Mail,
  web: Scissors,
  youtube: Youtube,
  image: Image,
  other: FileText,
};

export const RAW_COLOR = UNKNOWN_COLOR;
export const CONCEPT_TYPES = [
  { type: "topic", label: "Topic", text: "a theme that groups ideas" },
  { type: "idea", label: "Idea", text: "one claim, result or technique" },
  { type: "question", label: "Question", text: "an open problem I care about" },
] as const;

/** The source types a page can be, each with the glyph the graphs draw inside its dot. */
export const SOURCE_TYPES = [
  { type: "paper", label: "Paper" },
  { type: "lecture", label: "Lecture" },
  { type: "article", label: "Article" },
  { type: "blog-post", label: "Blog post" },
  { type: "ai-chat", label: "Chat" },
] as const;

export const DEPTHS: readonly { depth: Depth; label: string; text: string }[] = [
  { depth: "listed", label: "Listed", text: "cataloged, not read" },
  { depth: "easy", label: "Easy", text: "skimmed" },
  { depth: "full", label: "Full", text: "read through, summarized" },
  { depth: "deep", label: "Deep", text: "read closely, linked to neighbours" },
];

export function Dot({ color, className = "" }: { color: string; className?: string }) {
  return <span aria-hidden className={`inline-block size-2 shrink-0 rounded-full ${className}`} style={{ background: color }} />;
}

export function DepthSwatch({ depth }: { depth: string }) {
  return <span aria-hidden className="inline-block size-2.5 shrink-0 rounded-[2px]" style={{ background: depthColor(depth) }} />;
}

/** The concept marks (topic, idea, question): the shapes the graphs draw. */
export function ConceptDots() {
  return (
    <>
      {CONCEPT_TYPES.map((c) => (
        <ShapeIcon key={c.type} shape={c.type} className="size-3.5" />
      ))}
    </>
  );
}

/** catalog → / digest → between the stages. */
export function StageArrow({ label }: { label: string }) {
  return (
    <div aria-hidden className="flex flex-col items-center justify-center self-center text-lg leading-none text-muted-foreground">
      <span className="text-[9.5px] uppercase tracking-wider">{label}</span>
      <span className="md:hidden">↓</span>
      <span className="max-md:hidden">→</span>
    </div>
  );
}

/** "How a page gets here": the three layers and the depth strip. */
export function Glossary() {
  return (
    <section aria-labelledby="home-glossary">
      <h2 id="home-glossary" className="mb-2 mt-4 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
        How a page gets here
      </h2>
      <div className="grid grid-cols-1 gap-2 md:grid-cols-[1.25fr_auto_1fr_auto_1fr]">
        <div className="min-w-0 rounded-lg border bg-muted/40 px-3 py-2.5 text-sm" data-gloss>
          <h3 className="flex items-center gap-2 text-[15px] font-semibold">
            <Dot color={RAW_COLOR} />
            Raw
          </h3>
          <p className="mb-2 mt-0.5 text-muted-foreground">The original file – immutable and never edited.</p>
          <ul className="flex flex-wrap justify-center gap-x-3 gap-y-1">
            {RAW_FORMATS.map(({ label, icon: Icon }) => (
              <li key={label} className="inline-flex items-center gap-1.5 whitespace-nowrap font-semibold">
                <Icon aria-hidden className="size-3.5" />
                {label}
              </li>
            ))}
          </ul>
        </div>
        <StageArrow label="catalog" />
        <div className="min-w-0 rounded-lg border bg-muted/40 px-3 py-2.5 text-sm" data-gloss>
          <h3 className="flex items-center gap-2 text-[15px] font-semibold">
            <ShapeIcon shape="source" className="size-3.5" />
            Source
          </h3>
          <p className="mb-2 mt-0.5 text-muted-foreground">One raw file ingested, cataloged and standardized into a Markdown page.</p>
          <ul className="flex flex-wrap justify-center gap-x-3 gap-y-1 font-semibold">
            {SOURCE_TYPES.map((t) => (
              <li key={t.type} className="inline-flex items-center gap-1.5 whitespace-nowrap">
                <SourceIcon type={t.type} />
                {t.label}
              </li>
            ))}
          </ul>
        </div>
        <StageArrow label="digest" />
        <div className="min-w-0 rounded-lg border bg-muted/40 px-3 py-2.5 text-sm" data-gloss>
          <h3 className="flex items-center gap-2 text-[15px] font-semibold">
            <ConceptDots />
            Concept
          </h3>
          <p className="mb-2 mt-0.5 text-muted-foreground">A note distilled from sources; a node in the graph.</p>
          <dl className="grid gap-0.5">
            {CONCEPT_TYPES.map((c) => (
              <div key={c.type} className="grid grid-cols-[auto_1fr] items-baseline gap-2">
                <dt className="flex items-center gap-1.5 whitespace-nowrap font-semibold">
                  <ShapeIcon shape={c.type} className="size-3.5" />
                  {c.label}
                </dt>
                <dd className="text-[13px] leading-snug text-muted-foreground">{c.text}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
      {/* one line when it fits; otherwise the label, then the four items as a tidy 2×2 grid (never a lone orphan) */}
      <div data-testid="home-depth" className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-muted-foreground xl:flex-nowrap xl:whitespace-nowrap xl:text-[11.5px]">
        <span className="text-[10.5px] uppercase tracking-wider">Depth · how closely a source was read</span>
        <span className="grid grid-cols-1 gap-x-4 gap-y-0.5 sm:grid-cols-2 xl:flex xl:gap-x-2.5">
          {DEPTHS.map((d) => (
            <span key={d.depth} className="inline-flex items-center gap-1">
              <DepthSwatch depth={d.depth} />
              <b className="font-semibold text-foreground">{d.label}</b> {d.text}
            </span>
          ))}
        </span>
      </div>
    </section>
  );
}
