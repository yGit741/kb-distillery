/**
 * Calm hover: what the pointer is on (`pointed`) follows it at once — cursor, clicks, drags, the magnet
 * bubble — while the focus (dimmed graph, hover labels) commits only once the pointer settles. A sweep
 * across the graph therefore changes nothing, and moving between close pages cross-fades instead of
 * blinking back to the unfocused graph. Timings after hoverIntent (7 px / 100 ms), Material and Atlassian
 * motion (fade out about half the fade in) and a short leave grace.
 */

export const HOVER_TUNING = {
  /** ms the pointer rests on a page before it takes the focus */
  dwell: 150,
  /** ms when the focus moves straight from one page to another */
  switchDwell: 80,
  /** ms a page keeps the focus after the pointer leaves it */
  grace: 200,
  /** px per 100 ms: faster than this is a sweep, not an aim */
  speed: 7,
  /** ms the rest of the graph takes to dim, and to come back */
  fadeIn: 180,
  fadeOut: 100,
};

/** Pointer speed in px per 100 ms from the latest moves; 0 once the pointer has rested 100 ms. */
export function createSpeedMeter() {
  let x = 0;
  let y = 0;
  let t = -Infinity;
  let v = 0;
  return {
    note(nx: number, ny: number, now: number) {
      const dt = now - t;
      // coalesced events a few ms apart would read as huge speeds: average over at least 16 ms
      v = dt > 0 && dt < 200 ? (Math.hypot(nx - x, ny - y) / Math.max(dt, 16)) * 100 : 0;
      x = nx;
      y = ny;
      t = now;
    },
    speed: (now: number) => (now - t > 100 ? 0 : v),
  };
}

export interface HoverIntentOptions {
  /** Apply the focus to this page (or none). */
  commit: (id: string | null) => void;
  /** The page the focus shows now. */
  committed: () => string | null;
  /** Pointer speed in px per 100 ms. */
  speed: () => number;
  /** false = commit at once (calm hover off). */
  enabled: () => boolean;
  tuning?: typeof HOVER_TUNING;
}

export function createHoverIntent(o: HoverIntentOptions) {
  const tune = o.tuning ?? HOVER_TUNING;
  let pointed: string | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  const clear = () => {
    if (timer) clearTimeout(timer);
    timer = null;
  };
  const commit = () => {
    clear();
    if (pointed !== o.committed()) o.commit(pointed);
  };
  const settle = () => {
    if (pointed && o.speed() > tune.speed) {
      timer = setTimeout(settle, 40);
      return;
    }
    commit();
  };
  return {
    pointed: () => pointed,
    request(id: string | null) {
      pointed = id;
      if (!o.enabled()) return commit();
      clear();
      const now = o.committed();
      if (id === now) return;
      timer = setTimeout(settle, !id ? tune.grace : now ? tune.switchDwell : tune.dwell);
    },
    /** Apply what the pointer is on now, skipping the wait (calm hover switched off). */
    flush: commit,
    cancel: clear,
  };
}
