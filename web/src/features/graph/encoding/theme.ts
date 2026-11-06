export interface CanvasColors {
  text: string;
  background: string;
  link: string;
  ring: string;
  muted: string;
  /** the --warn status token: experiment halos */
  warn: string;
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
  // any other CSS colour (oklch, color-mix, a name): paint it once and read the pixel back, so the alpha is never lost
  const px = resolveRgb(c);
  return px ? `rgba(${px[0]}, ${px[1]}, ${px[2]}, ${a})` : c;
}

const RESOLVED = new Map<string, readonly [number, number, number] | null>();
let probe: CanvasRenderingContext2D | null | undefined;
const SENTINEL = "#010203";

/** The sRGB value of any CSS colour the browser can paint; null where there is no canvas (tests) or it cannot. */
export function resolveRgb(color: string): readonly [number, number, number] | null {
  const hit = RESOLVED.get(color);
  if (hit !== undefined) return hit;
  let out: readonly [number, number, number] | null = null;
  try {
    if (probe === undefined) {
      // jsdom has no canvas (and logs when asked for one): tests keep the colour as it is
      const real = typeof document !== "undefined" && !/jsdom/i.test(navigator.userAgent);
      const el = real ? document.createElement("canvas") : null;
      if (el) el.width = el.height = 1;
      probe = el?.getContext("2d", { willReadFrequently: true }) ?? null;
    }
    if (probe) {
      probe.clearRect(0, 0, 1, 1);
      probe.fillStyle = SENTINEL;
      probe.fillStyle = color;
      // a colour the browser cannot parse leaves the sentinel in place: no guess
      if (probe.fillStyle === SENTINEL) throw new Error("unparsed");
      probe.fillRect(0, 0, 1, 1);
      const d = probe.getImageData(0, 0, 1, 1).data;
      if (d[3]) out = [d[0]!, d[1]!, d[2]!];
    }
  } catch {
    out = null;
  }
  RESOLVED.set(color, out);
  return out;
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
      font: getComputedStyle(document.body).fontFamily || FALLBACK.font,
    };
  } catch {
    return FALLBACK;
  }
}
