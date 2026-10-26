import { cn } from "@/lib/utils";
import { GEOMETRY as G, glyphOf, GLYPH_SVG, markOf, type NodeMark } from "./spec";

/** Each mark's radius in the 16 px icon box, so every mark (with its stroke) fills about the same square. */
const ICON_R: Readonly<Record<NodeMark, number>> = { source: 6, person: 6.8, question: 5.8, idea: 5.8, topic: 5.8, collection: 5.2 };

/**
 * A type's mark in the text colour: the canvas `drawMark`, drawn from the same `GEOMETRY` (fractions of r), so a
 * chip, a legend row and a node show one picture. The mark is the type, so the chip carries no colour.
 */
export function ShapeIcon({ shape, initials = "GK", className = "size-3.5" }: { shape: NodeMark; initials?: string; className?: string }) {
  const r = ICON_R[shape];
  const ring = <circle cx="8" cy="8" r={r} fill="none" stroke="currentColor" strokeWidth={r * G.ringStroke} />;
  const text = (s: string, px: number, cls: string) => (
    <text x="8" y={8 + r * G.textDy} textAnchor="middle" dominantBaseline="central" fontSize={px} fontWeight="700" className={cls}>
      {s}
    </text>
  );
  const line = (i: number) => `M${8 - r * G.topicLineHalf} ${8 + i * r * G.topicLineGap}h${2 * r * G.topicLineHalf}`;
  return (
    <svg viewBox="0 0 16 16" className={cn(className, "shrink-0")} aria-hidden data-mark={shape}>
      {shape === "source" && <circle cx="8" cy="8" r={r} fill="currentColor" />}
      {shape === "person" && (
        <>
          <circle cx="8" cy="8" r={r} fill="currentColor" />
          {text(initials, r * (initials.length > 2 ? G.initials3 : G.initials2), "fill-background")}
        </>
      )}
      {shape === "question" && (
        <>
          {ring}
          {text("?", r * G.questionText, "fill-current")}
        </>
      )}
      {shape === "idea" && (
        <>
          {ring}
          <circle cx="8" cy="8" r={r * G.ideaDot} fill="currentColor" />
        </>
      )}
      {shape === "topic" && (
        <>
          {ring}
          <path d={[-1, 0, 1].map(line).join("")} stroke="currentColor" strokeWidth={r * G.topicLineStroke} strokeLinecap="round" />
        </>
      )}
      {shape === "collection" && (
        <>
          <circle cx="8" cy="8" r={r * G.collectionOuter} fill="none" stroke="currentColor" strokeWidth={r * G.collectionOuterStroke} />
          {ring}
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
