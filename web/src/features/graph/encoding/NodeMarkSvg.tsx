import { cn } from "@/lib/utils";
import { GEOMETRY as G, glyphOf, GLYPH_SVG, ICON_R, markOf, type NodeMark } from "./spec";


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
/**
 * One page as a node in SVG at (x, y), radius r: the canvas `drawNode` in SVG (the same GEOMETRY, the same glyph
 * paths), for SVG graphs (page mini graph) and icons. `color` fills or strokes the mark; `background` fills a ring.
 */
export function NodeMarkG({
  type,
  x,
  y,
  r,
  color,
  background = "none",
  initials = "",
  glyph = false,
  glyphColor = "#fff",
}: {
  type: string;
  x: number;
  y: number;
  r: number;
  color: string;
  background?: string;
  initials?: string;
  glyph?: boolean;
  glyphColor?: string;
}) {
  const mark = markOf(type);
  const ring = <circle cx={x} cy={y} r={r} fill={background} stroke={color} strokeWidth={r * G.ringStroke} />;
  const text = (s: string, px: number, fill: string) => (
    <text x={x} y={y + r * G.textDy} textAnchor="middle" dominantBaseline="central" fontSize={px} fontWeight="700" fill={fill}>
      {s}
    </text>
  );
  if (mark === "question")
    return (
      <g data-mark={mark}>
        {ring}
        {text("?", r * G.questionText, color)}
      </g>
    );
  if (mark === "idea")
    return (
      <g data-mark={mark}>
        {ring}
        <circle cx={x} cy={y} r={r * G.ideaDot} fill={color} />
      </g>
    );
  if (mark === "topic") {
    const line = (i: number) => `M${x - r * G.topicLineHalf} ${y + i * r * G.topicLineGap}h${2 * r * G.topicLineHalf}`;
    return (
      <g data-mark={mark}>
        {ring}
        <path d={[-1, 0, 1].map(line).join("")} stroke={color} strokeWidth={r * G.topicLineStroke} strokeLinecap="round" />
      </g>
    );
  }
  if (mark === "collection")
    return (
      <g data-mark={mark}>
        <circle cx={x} cy={y} r={r * G.collectionOuter} fill="none" stroke={color} strokeWidth={r * G.collectionOuterStroke} />
        {ring}
      </g>
    );
  const k = r / 10;
  const g = GLYPH_SVG[glyphOf(type)];
  return (
    <g data-mark={mark}>
      <circle cx={x} cy={y} r={r} fill={color} />
      {mark === "person" && initials && text(initials, r * (initials.length > 2 ? G.initials3 : G.initials2), glyphColor)}
      {mark === "source" && glyph && (
        <path
          d={g.d}
          transform={`translate(${x - 8 * k} ${y - 8 * k}) scale(${k})`}
          {...(g.fill ? { fill: glyphColor } : { fill: "none", stroke: glyphColor, strokeWidth: 1.2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const })}
        />
      )}
    </g>
  );
}

/**
 * A page's chip: its node exactly as the graphs draw it (mark, colour, a source's glyph), for lists and panels.
 * Without a colour it takes the text colour, so the mark alone says the type.
 */
export function NodeSwatch({ type, color = "currentColor", className = "size-3.5" }: { type: string; color?: string; className?: string }) {
  const r = ICON_R[markOf(type)];
  return (
    <svg viewBox="0 0 16 16" className={cn(className, "shrink-0")} aria-hidden data-swatch={markOf(type)}>
      <NodeMarkG type={type} x={8} y={8} r={r} color={color} glyph glyphColor="var(--card)" />
    </svg>
  );
}
