/**
 * Guided tour engine: dims the app, spotlights one element per step and explains it in a card next to it.
 * The Back / Next / Skip controls sit in a fixed dock at the bottom centre, so they never move under the
 * mouse while the explainer follows the spotlight. Framework-free: works on the real app and on mockups.
 */
export interface TourStep {
  /** CSS selector of the element to spotlight; waited for up to 2 s (panels open after a click) */
  target: string;
  title: string;
  body: string;
  place?: "right" | "left" | "top" | "bottom";
  pad?: number;
  /** runs before the step shows, e.g. click a toolbar button to open its panel */
  before?: () => void | Promise<void>;
}

const CSS = `
.gt-hole{position:fixed;z-index:9998;border-radius:10px;box-shadow:0 0 0 9999px rgba(10,14,20,.6);transition:all .28s ease;pointer-events:none}
.gt-card{position:fixed;z-index:9999;width:min(300px,calc(100vw - 32px));background:var(--card,#fff);color:var(--foreground,#18202b);border:1px solid var(--border,#dde2ea);border-radius:10px;padding:12px 14px;box-shadow:0 12px 32px rgba(0,0,0,.28);font:14px/1.5 system-ui,sans-serif;transition:top .28s,left .28s;pointer-events:none}
.gt-card h4{margin:0 0 4px;font-size:15px;font-weight:600}.gt-card p{margin:0;color:var(--muted-foreground,#5b6676)}
.gt-dock{position:fixed;z-index:9999;left:50%;bottom:calc(20px + env(safe-area-inset-bottom,0px));transform:translateX(-50%);display:flex;align-items:center;gap:10px;background:var(--card,#fff);color:var(--foreground,#18202b);border:1px solid var(--border,#dde2ea);border-radius:999px;padding:6px 8px 6px 14px;box-shadow:0 8px 24px rgba(0,0,0,.25);font:13px system-ui,sans-serif}
.gt-dock button{font:inherit;border:0;border-radius:999px;padding:6px 14px;cursor:pointer;background:transparent;color:inherit}
.gt-dock button:disabled{opacity:.35;cursor:default}
.gt-dock .gt-next{background:var(--primary,#2f6fde);color:var(--primary-foreground,#fff);min-width:72px}
.gt-dock .gt-skip{color:var(--muted-foreground,#5b6676)}
.gt-dock button:focus-visible{outline:2px solid var(--primary,#2f6fde);outline-offset:2px}
.gt-count{font-variant-numeric:tabular-nums;color:var(--muted-foreground,#5b6676);min-width:3.5em;text-align:center}
@media (prefers-reduced-motion:reduce){.gt-hole,.gt-card{transition:none}}`;

async function waitFor(sel: string, ms = 2000): Promise<Element | null> {
  const t0 = performance.now();
  for (;;) {
    const el = document.querySelector(sel);
    if (el || performance.now() - t0 > ms) return el;
    await new Promise((r) => setTimeout(r, 50));
  }
}

let stop: (() => void) | null = null;

export function startTour(steps: TourStep[], opts: { onEnd?: () => void } = {}): void {
  stop?.();
  if (!document.getElementById("gt-style")) {
    const st = document.createElement("style");
    st.id = "gt-style";
    st.textContent = CSS;
    document.head.appendChild(st);
  }
  let i = 0;
  let target: Element | null = null;
  const hole = Object.assign(document.createElement("div"), { className: "gt-hole" });
  const card = Object.assign(document.createElement("div"), { className: "gt-card" });
  const dock = Object.assign(document.createElement("div"), { className: "gt-dock" });
  dock.setAttribute("role", "dialog");
  dock.setAttribute("aria-label", "Guided tour");
  dock.innerHTML = `<button class="gt-skip">Skip</button><button class="gt-back" aria-label="Back">‹ Back</button><span class="gt-count"></span><button class="gt-next"></button>`;
  const q = (s: string) => dock.querySelector(s) as HTMLButtonElement;
  const skipB = q(".gt-skip"), backB = q(".gt-back"), count = q(".gt-count"), nextB = q(".gt-next");
  card.setAttribute("aria-live", "polite");
  document.body.append(hole, card, dock);

  function place() {
    const s = steps[i]!;
    if (!target) {
      Object.assign(hole.style, { top: "50%", left: "50%", width: "0px", height: "0px" });
      card.style.left = `${(innerWidth - card.offsetWidth) / 2}px`;
      card.style.top = `${innerHeight / 3}px`;
      return;
    }
    const r = target.getBoundingClientRect();
    const pad = s.pad ?? 6;
    Object.assign(hole.style, { top: `${r.top - pad}px`, left: `${r.left - pad}px`, width: `${r.width + pad * 2}px`, height: `${r.height + pad * 2}px` });
    const cw = card.offsetWidth, ch = card.offsetHeight, W = innerWidth, H = innerHeight - 80, g = 16;
    let p = s.place ?? "right";
    if (p === "right" && r.right + g + cw > W) p = "left";
    if (p === "left" && r.left - g - cw < 0) p = "bottom";
    if (p === "bottom" && r.bottom + g + ch > H) p = "top";
    const x = p === "right" ? r.right + g : p === "left" ? r.left - g - cw : r.left;
    const y = p === "bottom" ? r.bottom + g : p === "top" ? r.top - g - ch : r.top;
    card.style.left = `${Math.max(16, Math.min(x, W - cw - 16))}px`;
    card.style.top = `${Math.max(16, Math.min(y, H - ch - 16))}px`;
  }

  async function show() {
    const s = steps[i]!;
    await s.before?.();
    target = await waitFor(s.target);
    target?.scrollIntoView({ block: "nearest" });
    card.innerHTML = `<h4></h4><p></p>`;
    card.querySelector("h4")!.textContent = s.title;
    card.querySelector("p")!.textContent = s.body;
    count.textContent = `${i + 1} / ${steps.length}`;
    backB.disabled = i === 0;
    nextB.textContent = i === steps.length - 1 ? "Done" : "Next ›";
    requestAnimationFrame(place);
    nextB.focus({ preventScroll: true });
  }
  const next = () => (i < steps.length - 1 ? (i++, void show()) : end());
  const back = () => i > 0 && (i--, void show());
  const key = (e: KeyboardEvent) => {
    if (e.key === "ArrowRight" || e.key === "Enter") { e.preventDefault(); e.stopPropagation(); next(); }
    else if (e.key === "ArrowLeft") { e.stopPropagation(); back(); }
    else if (e.key === "Escape") { e.stopPropagation(); end(); }
  };
  function end() {
    hole.remove(); card.remove(); dock.remove();
    removeEventListener("keydown", key, true);
    removeEventListener("resize", place);
    removeEventListener("scroll", place, true);
    stop = null;
    opts.onEnd?.();
  }
  nextB.onclick = next;
  backB.onclick = back;
  skipB.onclick = end;
  addEventListener("keydown", key, true);
  addEventListener("resize", place);
  addEventListener("scroll", place, true);
  stop = end;
  void show();
}
