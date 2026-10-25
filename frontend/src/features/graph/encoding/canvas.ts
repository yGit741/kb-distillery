import { withAlpha } from "./theme";
import { GEOMETRY as G, glyphOf, markOf, STATE, type NodeMark, type NodeState, type SourceGlyph } from "./spec";

/** A source glyph (`glyphOf(type)`) of a dot of radius r at (x, y), in `color` (white inside a coloured dot). */
export function drawSourceGlyph(ctx: CanvasRenderingContext2D, type: string, x: number, y: number, r: number, color = "#fff"): void {
  drawGlyph(ctx, glyphOf(type), x, y, r, color);
}

export function drawGlyph(ctx: CanvasRenderingContext2D, glyph: SourceGlyph, x: number, y: number, r: number, color = "#fff"): void {
  ctx.save();
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = r * 0.12;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.beginPath();
  if (glyph === "paper") {
    const w = r * 0.9, h = r * 1.15, f = r * 0.32, l = x - w / 2, t = y - h / 2;
    ctx.moveTo(l, t);
    ctx.lineTo(l + w - f, t);
    ctx.lineTo(l + w, t + f);
    ctx.lineTo(l + w, t + h);
    ctx.lineTo(l, t + h);
    ctx.closePath();
    for (let i = 0; i < 3; i++) {
      ctx.moveTo(l + r * 0.2, t + h * (0.42 + i * 0.18));
      ctx.lineTo(l + w - r * 0.2, t + h * (0.42 + i * 0.18));
    }
    ctx.stroke();
  } else if (glyph === "sparkle") {
    // a four-point sparkle: the mark AI assistants use
    const k = r * 0.62, w = r * 0.16;
    ctx.moveTo(x, y - k);
    ctx.quadraticCurveTo(x + w, y - w, x + k, y);
    ctx.quadraticCurveTo(x + w, y + w, x, y + k);
    ctx.quadraticCurveTo(x - w, y + w, x - k, y);
    ctx.quadraticCurveTo(x - w, y - w, x, y - k);
    ctx.fill();
  } else if (glyph === "mail") {
    const w = r * 1.1, h = r * 0.78, l = x - w / 2, t = y - h / 2;
    ctx.rect(l, t, w, h);
    ctx.moveTo(l, t);
    ctx.lineTo(x, y + h * 0.08);
    ctx.lineTo(l + w, t);
    ctx.stroke();
  } else if (glyph === "play") {
    ctx.moveTo(x - r * 0.28, y - r * 0.42);
    ctx.lineTo(x + r * 0.45, y);
    ctx.lineTo(x - r * 0.28, y + r * 0.42);
    ctx.closePath();
    ctx.fill();
  } else if (glyph === "book") {
    ctx.moveTo(x, y - r * 0.32);
    ctx.quadraticCurveTo(x - r * 0.3, y - r * 0.45, x - r * 0.58, y - r * 0.32);
    ctx.lineTo(x - r * 0.58, y + r * 0.42);
    ctx.quadraticCurveTo(x - r * 0.3, y + r * 0.3, x, y + r * 0.42);
    ctx.quadraticCurveTo(x + r * 0.3, y + r * 0.3, x + r * 0.58, y + r * 0.42);
    ctx.lineTo(x + r * 0.58, y - r * 0.32);
    ctx.quadraticCurveTo(x + r * 0.3, y - r * 0.45, x, y - r * 0.32);
    ctx.lineTo(x, y + r * 0.42);
    ctx.stroke();
  } else if (glyph === "clip") {
    // scissors: two finger loops and crossed blades
    ctx.arc(x - r * 0.3, y + r * 0.35, r * 0.17, 0, 2 * Math.PI);
    ctx.moveTo(x + r * 0.47, y + r * 0.35);
    ctx.arc(x + r * 0.3, y + r * 0.35, r * 0.17, 0, 2 * Math.PI);
    ctx.moveTo(x - r * 0.2, y + r * 0.2);
    ctx.lineTo(x + r * 0.35, y - r * 0.5);
    ctx.moveTo(x + r * 0.2, y + r * 0.2);
    ctx.lineTo(x - r * 0.35, y - r * 0.5);
    ctx.stroke();
  } else if (glyph === "slides") {
    // a screen on a stand
    ctx.rect(x - r * 0.55, y - r * 0.45, r * 1.1, r * 0.7);
    ctx.moveTo(x, y + r * 0.25);
    ctx.lineTo(x, y + r * 0.5);
    ctx.moveTo(x - r * 0.25, y + r * 0.5);
    ctx.lineTo(x + r * 0.25, y + r * 0.5);
    ctx.stroke();
  } else if (glyph === "image") {
    // a frame with a hill
    ctx.rect(x - r * 0.55, y - r * 0.45, r * 1.1, r * 0.9);
    ctx.moveTo(x - r * 0.55, y + r * 0.3);
    ctx.lineTo(x - r * 0.15, y - r * 0.05);
    ctx.lineTo(x + r * 0.1, y + r * 0.2);
    ctx.lineTo(x + r * 0.25, y + r * 0.05);
    ctx.lineTo(x + r * 0.55, y + r * 0.3);
    ctx.stroke();
  } else if (glyph === "handwritten") {
    // a pen stroke over a wavy line
    ctx.moveTo(x - r * 0.35, y + r * 0.2);
    ctx.lineTo(x + r * 0.35, y - r * 0.5);
    ctx.moveTo(x - r * 0.55, y + r * 0.45);
    ctx.quadraticCurveTo(x - r * 0.3, y + r * 0.25, x - r * 0.05, y + r * 0.45);
    ctx.quadraticCurveTo(x + r * 0.2, y + r * 0.62, x + r * 0.5, y + r * 0.42);
    ctx.stroke();
  } else {
    // article, blog post and the rest: lines of text
    for (let i = -1; i <= 1; i++) {
      ctx.moveTo(x - r * 0.45, y + i * r * 0.3);
      ctx.lineTo(x + (i === 1 ? r * 0.12 : r * 0.45), y + i * r * 0.3);
    }
    ctx.stroke();
  }
  ctx.restore();
}

/** Draw a node's mark of radius r at (x, y) in `col`; `bg` fills the hollow ones, `text` is a person's initials. */
export function drawMark(ctx: CanvasRenderingContext2D, mark: NodeMark, x: number, y: number, r: number, col: string, bg: string, font: string, text = ""): void {
  const sw = r * G.ringStroke;
  const ring = (rr: number) => {
    ctx.beginPath();
    ctx.arc(x, y, rr, 0, 2 * Math.PI);
    ctx.fillStyle = bg;
    ctx.fill();
    ctx.strokeStyle = col;
    ctx.lineWidth = sw;
    ctx.stroke();
  };
  const label = (s: string, px: number, color: string) => {
    ctx.fillStyle = color;
    ctx.font = `700 ${px}px ${font}`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(s, x, y + r * G.textDy);
  };
  if (mark === "question") {
    ring(r);
    label("?", r * G.questionText, col);
  } else if (mark === "idea") {
    ring(r);
    ctx.beginPath();
    ctx.arc(x, y, r * G.ideaDot, 0, 2 * Math.PI);
    ctx.fillStyle = col;
    ctx.fill();
  } else if (mark === "topic") {
    ring(r);
    ctx.beginPath();
    for (let i = -1; i <= 1; i++) {
      ctx.moveTo(x - r * G.topicLineHalf, y + i * r * G.topicLineGap);
      ctx.lineTo(x + r * G.topicLineHalf, y + i * r * G.topicLineGap);
    }
    ctx.strokeStyle = col;
    ctx.lineWidth = r * G.topicLineStroke;
    ctx.lineCap = "round";
    ctx.stroke();
    ctx.lineCap = "butt";
  } else if (mark === "collection") {
    ctx.beginPath();
    ctx.arc(x, y, r * G.collectionOuter, 0, 2 * Math.PI);
    ctx.strokeStyle = col;
    ctx.lineWidth = r * G.collectionOuterStroke;
    ctx.stroke();
    ring(r);
  } else {
    ctx.beginPath();
    ctx.arc(x, y, r, 0, 2 * Math.PI);
    ctx.fillStyle = col;
    ctx.fill();
    if (mark === "person" && text) label(text, r * (text.length > 2 ? G.initials3 : G.initials2), "#fff");
  }
}

/**
 * The state ring under a mark of radius r (graph units at zoom `scale`; pass 1 for screen px): the selection, focus
 * and drawn-source rings sit `STATE.gap` px outside it; the hovered page gets a soft glow in its own colour instead.
 */
export function drawNodeState(ctx: CanvasRenderingContext2D, state: NodeState, x: number, y: number, r: number, col: string, ring: string, scale = 1): void {
  if (!state) return;
  if (state === "hover") {
    const g = ctx.createRadialGradient(x, y, r, x, y, r + STATE.glow / scale);
    g.addColorStop(0, withAlpha(col, STATE.glowAlpha));
    g.addColorStop(1, withAlpha(col, 0));
    ctx.beginPath();
    ctx.arc(x, y, r + STATE.glow / scale, 0, 2 * Math.PI);
    ctx.fillStyle = g;
    ctx.fill();
    return;
  }
  const s = STATE[state];
  ctx.beginPath();
  ctx.arc(x, y, r + STATE.gap / scale, 0, 2 * Math.PI);
  ctx.strokeStyle = withAlpha(ring, s.alpha);
  ctx.lineWidth = s.width / scale;
  ctx.stroke();
}

export interface NodeDraw {
  x: number;
  y: number;
  /** radius in the context's units */
  r: number;
  /** the surface's colour channel for this page */
  color: string;
  /** the canvas background (fills hollow marks) and the label font */
  background: string;
  font: string;
  /** the selection colour (`--primary`) */
  ring: string;
  /** a person's initials (`personInitials`) */
  initials?: string;
  state?: NodeState;
  /** opacity of the mark (dimming); the state ring is always drawn in full */
  alpha?: number;
  /** a source shows its type glyph (big enough on screen, or hovered) */
  glyph?: boolean;
  /** the zoom: px values (state rings) are divided by it; 1 when drawing in screen px */
  scale?: number;
}

/** One page as a node, the same on every surface: its state ring, then its type's mark (and a source's glyph). */
export function drawNode(ctx: CanvasRenderingContext2D, type: string, d: NodeDraw): void {
  drawNodeState(ctx, d.state ?? null, d.x, d.y, d.r, d.color, d.ring, d.scale ?? 1);
  ctx.globalAlpha = d.alpha ?? 1;
  const mark = markOf(type);
  drawMark(ctx, mark, d.x, d.y, d.r, d.color, d.background, d.font, d.initials);
  if (mark === "source" && d.glyph) drawSourceGlyph(ctx, type, d.x, d.y, d.r);
  ctx.globalAlpha = 1;
}
