import { cn } from "@/lib/utils";
import { glyphOf, markOf, type NodeMark, type SourceGlyph } from "./spec";

/** A type's mark in the text colour (the canvas `drawMark` in SVG): the mark is the type, so the chip carries no colour. */
export function ShapeIcon({ shape, className = "size-3.5" }: { shape: NodeMark; className?: string }) {
  const ring = <circle cx="8" cy="8" r="5.6" fill="none" stroke="currentColor" strokeWidth="1.5" />;
  return (
    <svg viewBox="0 0 16 16" className={cn(className, "shrink-0")} aria-hidden>
      {shape === "source" && <circle cx="8" cy="8" r="6" fill="currentColor" />}
      {shape === "person" && (
        <>
          <circle cx="8" cy="8" r="7" fill="currentColor" />
          <text x="8" y="8.6" textAnchor="middle" dominantBaseline="middle" fontSize="6.4" fontWeight="700" className="fill-background">
            GK
          </text>
        </>
      )}
      {shape === "question" && (
        <>
          {ring}
          <text x="8" y="8.8" textAnchor="middle" dominantBaseline="middle" fontSize="7.5" fontWeight="700" fill="currentColor">
            ?
          </text>
        </>
      )}
      {shape === "idea" && (
        <>
          {ring}
          <circle cx="8" cy="8" r="2" fill="currentColor" />
        </>
      )}
      {shape === "topic" && (
        <>
          {ring}
          <path d="M5.6 5.9h4.8M5.6 8h4.8M5.6 10.1h4.8" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
        </>
      )}
      {shape === "collection" && (
        <>
          <circle cx="8" cy="8" r="7.2" fill="none" stroke="currentColor" strokeWidth="0.9" />
          <circle cx="8" cy="8" r="4.6" fill="none" stroke="currentColor" strokeWidth="1.4" />
        </>
      )}
    </svg>
  );
}

/** SVG paths of each source glyph in a 16 px box: the same pictures `drawGlyph` draws inside a source dot. */
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

/** A source type's (or raw format's) icon: the glyph the canvas draws inside a zoomed or hovered source dot. */
export function SourceIcon({ type, className = "size-3.5" }: { type: string; className?: string }) {
  const g = GLYPH_SVG[glyphOf(type)];
  return (
    <svg viewBox="0 0 16 16" className={cn(className, "shrink-0")} aria-hidden>
      {g.fill ? (
        <path d={g.d} fill="currentColor" />
      ) : (
        <path d={g.d} fill="none" stroke="currentColor" strokeWidth={1.3} strokeLinecap="round" strokeLinejoin="round" />
      )}
    </svg>
  );
}

/** A page's symbol for chips and titles: its type's mark, or for a source its glyph. */
export function NodeMarkSvg({ type, className }: { type: string; className?: string }) {
  const mark = markOf(type);
  return mark === "source" ? <SourceIcon type={type} className={className} /> : <ShapeIcon shape={mark} className={className} />;
}
