export type StripRect = [number, number, number, number];

const SELECTOR = '[data-corners="types"]';

/**
 * Keeps the page-type strip's box (in the canvas's CSS px, with air around it; null when the strip is not
 * rendered) in a plain field the frame loop reads, so no frame measures the DOM. Re-measured on mount, when the
 * strip or canvas resizes, when the strip comes or goes, when it opens or folds (its own or an ancestor's
 * attributes change), and on window resize.
 */
export function trackTypesStrip(canvas: HTMLElement): { rect: () => StripRect | null; dispose: () => void } {
  const doc = canvas.ownerDocument;
  const win = doc.defaultView;
  let rect: StripRect | null = null;
  let strip: Element | null = null;
  const ro = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => measure());
  const mo = typeof MutationObserver === "undefined" ? null : new MutationObserver(() => measure());
  // the graph's own frame, not the whole page: HUDs and labels elsewhere churn every frame
  const root = canvas.closest('[data-testid="graph-area"]') ?? doc.body;
  // a child-list change only matters when the strip itself came, went or was replaced (a plain lookup, no layout)
  const mo2 = typeof MutationObserver === "undefined" ? null : new MutationObserver(() => doc.querySelector(SELECTOR) !== strip && measure());
  let watched: Element[] = [];

  function measure() {
    const found = doc.querySelector(SELECTOR);
    if (found !== strip) {
      ro?.disconnect();
      mo?.disconnect();
      strip = found;
      ro?.observe(canvas);
      if (strip) ro?.observe(strip);
      watched = [];
      for (let n: Element | null = strip; n; n = n.parentElement) watched.push(n);
      for (const n of watched) mo?.observe(n, { attributes: true, attributeFilter: ["class", "style", "data-open"] });
    }
    if (!strip) {
      rect = null;
      return;
    }
    const s = strip.getBoundingClientRect();
    const c = canvas.getBoundingClientRect();
    rect = s.width === 0 || s.height === 0 ? null : [s.left - c.left - 14, s.top - c.top - 8, s.right - c.left + 14, s.bottom - c.top + 8];
  }

  measure();
  if (!strip) {
    ro?.observe(canvas);
  }
  mo2?.observe(root, { childList: true, subtree: true });
  win?.addEventListener("resize", measure);
  return {
    rect: () => rect,
    dispose: () => {
      ro?.disconnect();
      mo?.disconnect();
      mo2?.disconnect();
      win?.removeEventListener("resize", measure);
    },
  };
}
