/**
 * Any CSS colour the browser can paint (oklch, color-mix, a name, hex), as an rgba() string with the given alpha.
 * Painted once into a 1px canvas and read back; cached per colour. Null where there is no canvas (jsdom) or the
 * browser cannot parse it, so callers keep their own fallback.
 */
const RESOLVED = new Map<string, readonly [number, number, number] | null>();
let probe: CanvasRenderingContext2D | null | undefined;
const SENTINEL = "#010203";

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

export function rgbaOf(color: string, alpha: number): string | null {
  const px = resolveRgb(color);
  return px ? `rgba(${px[0]}, ${px[1]}, ${px[2]}, ${alpha})` : null;
}
