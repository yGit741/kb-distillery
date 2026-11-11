import { rgbaOf } from "@/theme/resolveColor";

export interface CanvasColors {
  text: string;
  background: string;
  link: string;
  ring: string;
  muted: string;
  /** the --warn status token: experiment halos */
  warn: string;
  /** the --ok / --bad status tokens: the citation map's fetched-to-deep ramp */
  ok?: string;
  bad?: string;
  font: string;
}

const FALLBACK: CanvasColors = {
  text: "#18181b",
  background: "#ffffff",
  link: "#71717a",
  ring: "#2563eb",
  muted: "#71717a",
  warn: "#ca8a04",
  font: "system-ui, sans-serif",
};

/** `#rrggbb` / `#rgb` / `rgb(a)(...)` plus an alpha -> an `rgba()` string the canvas understands. */
export function withAlpha(color: string, alpha: number): string {
  const a = Math.max(0, Math.min(1, alpha));
  const c = color.trim();
  let m = /^#([0-9a-f]{6})$/i.exec(c);
  if (m?.[1]) {
    const n = parseInt(m[1], 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
  }
  m = /^#([0-9a-f]{3})$/i.exec(c);
  if (m?.[1]) {
    const [r, g, b] = m[1].split("").map((h) => parseInt(h + h, 16));
    return `rgba(${r}, ${g}, ${b}, ${a})`;
  }
  const rgb = /^rgba?\(\s*([\d.]+)[ ,]+([\d.]+)[ ,]+([\d.]+)/i.exec(c);
  if (rgb) return `rgba(${rgb[1]}, ${rgb[2]}, ${rgb[3]}, ${a})`;
  // any other CSS colour (oklch, color-mix, a name): resolved by the browser, so the alpha is never lost
  return rgbaOf(c, a) ?? c;
}

/** The chrome tokens the canvas draws with, read from the active theme (the canvas cannot use CSS vars). */
export function readCanvasColors(root: HTMLElement = document.documentElement): CanvasColors {
  try {
    const cs = getComputedStyle(root);
    const v = (name: string, fb: string) => cs.getPropertyValue(name).trim() || fb;
    return {
      text: v("--foreground", FALLBACK.text),
      background: v("--card", FALLBACK.background),
      link: v("--muted-foreground", FALLBACK.link),
      ring: v("--primary", FALLBACK.ring),
      muted: v("--muted-foreground", FALLBACK.muted),
      warn: v("--warn", FALLBACK.warn),
      ok: v("--ok", FALLBACK.muted),   // the app always defines the status tokens; muted only in a bare test DOM
      bad: v("--bad", FALLBACK.warn),
      font: getComputedStyle(document.body).fontFamily || FALLBACK.font,
    };
  } catch {
    return FALLBACK;
  }
}
