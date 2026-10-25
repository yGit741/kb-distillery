import { cn } from "@/lib/utils";
import { glyphOf, GLYPH_SVG, markOf, type NodeMark } from "./spec";

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
