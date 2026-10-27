/**
 * Guided tour engine: dims the app, spotlights one element per step and explains it in a card next to it.
 * The Back / Next / Skip controls sit in a fixed dock at the bottom centre, so they never move under the
 * mouse while the explainer follows the spotlight. Framework-free: works on the real app and on mockups.
 */
/**
 * What a mark means. One colour per meaning, the app's own status tokens, always with a numbered badge and a
 * label so colour is never the only cue: look here (accent), new (ok), changed (warn), problem (bad).
 */
export type MarkKind = "focus" | "new" | "changed" | "issue";

/** A second (third…) element lit and ringed in the same step, numbered so the card's text can say "①". */
export interface Mark {
  target: string;
  kind?: MarkKind;
  /** short tag next to the badge, e.g. "new button" */
  label?: string;
}

/**
 * A scripted action, run (in order, after `before`) when the step shows: the tour acts the feature out instead
 * of only pointing at it. A dot glides to the element first, so the viewer sees what is about to be pressed.
 */
export type TourAction =
  | { click: string }
  | { hover: string }
  | { type: string; text: string }
  | { press: string }
  | { wait: number };

export interface TourStep {
  /** CSS selector of the element to spotlight; waited for up to `wait` ms (panels open after a click). Omit for a centred card. */
  target?: string;
  title: string;
  body: string;
  place?: "right" | "left" | "top" | "bottom";
  pad?: number;
  /** runs before the step shows, e.g. click a toolbar button to open its panel */
  before?: () => void | Promise<void>;
  /** ms to await the target (default 2000) — a screen that computes before it renders needs more */
  wait?: number;
  /**
   * app path + search this step (and the ones after it, until the next `go`) is shown on, e.g.
   * `/graph?view=thesis`; navigated through `window.kbGo` when the location differs, forward and back
   */
  go?: string;
  /** colour of the main spotlight ring (default "focus") */
  kind?: MarkKind;
  /** more elements to light and number in this step */
  marks?: Mark[];
  /** actions to perform when the step shows (see TourAction) */
  do?: TourAction[];
  /** how dark the rest of the screen gets, 0 (none) … 0.85 (default 0.55) */
  dim?: number;
}

/** why a tour ended: the user finished it, skipped it, or another tour replaced it */
export type TourEndReason = "done" | "skip" | "replaced";

/** set on <body> while a tour runs, so screens can move chrome out from under the dock */
export const ACTIVE_CLASS = "gt-active";

const CSS = `
.gt-veil{position:fixed;inset:0;z-index:9997;width:100vw;height:100vh;pointer-events:none}
.gt-ring{position:fixed;z-index:9998;border-radius:10px;pointer-events:none;border:1.5px solid var(--gt-c);box-shadow:0 0 0 3px color-mix(in srgb,var(--gt-c) 16%,transparent);transition:all .28s ease}
.gt-chip{position:absolute;left:-1.5px;bottom:calc(100% + 6px);display:flex;align-items:center;gap:6px;padding:3px 9px 3px 3px;border-radius:999px;background:var(--card,#fff);color:var(--foreground,#18202b);border:1px solid color-mix(in srgb,var(--gt-c) 40%,var(--border,#e4e4e7));box-shadow:0 4px 14px rgba(0,0,0,.14);font:500 12px/16px system-ui,sans-serif;white-space:nowrap}
.gt-chip.gt-below{bottom:auto;top:calc(100% + 6px)}
.gt-chip:not(:has(span)){padding:3px}
.gt-n{display:inline-grid;place-items:center;width:16px;height:16px;border-radius:999px;background:var(--gt-c);color:#fff;font:600 10.5px/1 system-ui,sans-serif;font-variant-numeric:tabular-nums}
.gt-k-focus{--gt-c:var(--primary,#2563eb)}.gt-k-new{--gt-c:var(--ok,#16a34a)}.gt-k-changed{--gt-c:var(--warn,#ca8a04)}.gt-k-issue{--gt-c:var(--bad,#dc2626)}
.gt-dot{position:fixed;z-index:10000;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:999px;background:color-mix(in srgb,var(--primary,#2563eb) 35%,transparent);border:2px solid var(--primary,#2563eb);pointer-events:none;transition:left .45s ease,top .45s ease,transform .15s}
.gt-dot.gt-press{transform:scale(.6)}
.gt-card{position:fixed;z-index:9999;width:min(320px,calc(100vw - 32px));background:var(--card,#fff);color:var(--foreground,#18202b);border:1px solid var(--border,#dde2ea);border-left:4px solid var(--gt-c,var(--primary,#2563eb));border-radius:10px;padding:12px 14px;box-shadow:0 12px 32px rgba(0,0,0,.28);font:14px/1.5 system-ui,sans-serif;transition:top .28s,left .28s;pointer-events:none}
.gt-card h4{margin:0 0 4px;font-size:15px;font-weight:600}.gt-card p{margin:0;color:var(--muted-foreground,#5b6676)}
.gt-card strong{color:var(--foreground,#18202b);font-weight:600}
.gt-card .gt-n{vertical-align:1px}
.gt-dock{position:fixed;z-index:9999;left:50%;bottom:calc(20px + env(safe-area-inset-bottom,0px));transform:translateX(-50%);display:flex;align-items:center;gap:10px;background:var(--card,#fff);color:var(--foreground,#18202b);border:1px solid var(--border,#dde2ea);border-radius:999px;padding:6px 8px 6px 14px;box-shadow:0 8px 24px rgba(0,0,0,.25);font:13px system-ui,sans-serif;pointer-events:auto}
.gt-dock button{font:inherit;border:0;border-radius:999px;padding:6px 14px;cursor:pointer;background:transparent;color:inherit}
.gt-dock button:disabled{opacity:.35;cursor:default}
.gt-dock .gt-next{background:var(--primary,#2f6fde);color:var(--primary-foreground,#fff);min-width:72px}
.gt-dock .gt-skip{color:var(--muted-foreground,#5b6676)}
.gt-dock button:focus-visible{outline:2px solid var(--primary,#2f6fde);outline-offset:2px}
.gt-count{font-variant-numeric:tabular-nums;color:var(--muted-foreground,#5b6676);min-width:3.5em;text-align:center}
@media (prefers-reduced-motion:reduce){.gt-ring,.gt-card,.gt-dot{transition:none}}`;

async function waitFor(sel: string, ms = 2000): Promise<Element | null> {
  const t0 = performance.now();
  for (;;) {
    const el = document.querySelector(sel);
    if (el || performance.now() - t0 > ms) return el;
    await new Promise((r) => setTimeout(r, 50));
  }
}

/** The app is served under a base path (vite `base`); step paths are written without it. */
const BASE = (import.meta.env.BASE_URL as string).replace(/\/$/, "");

/** True when the window is already at `go`: same path, and every param it names has that value. */
export function atLocation(go: string, loc: { pathname: string; search: string } = window.location): boolean {
  const [path = "/", qs = ""] = go.split("?");
  const here = loc.pathname.startsWith(BASE) ? loc.pathname.slice(BASE.length) : loc.pathname;
  if ((here.replace(/\/$/, "") || "/") !== (path.replace(/\/$/, "") || "/")) return false;
  const cur = new URLSearchParams(loc.search);
  return [...new URLSearchParams(qs)].every(([k, v]) => cur.get(k) === v);
}

/** Where each step is shown: its own `go`, else the previous step's route; the first steps are at Home. */
export const routesOf = (steps: readonly TourStep[]): string[] => {
  const out: string[] = [];
  for (const [i, s] of steps.entries()) out.push(s.go ?? out[i - 1] ?? "/");
  return out;
};

/** keys typed into a field belong to the field, not to the tour */
const inField = (t: EventTarget | null) =>
  t instanceof HTMLElement && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable);

/**
 * Card text: plain text with `**bold**` and `[1]`-style references to the step's numbered marks. A reference
 * wears its mark's colour (`kinds[n-1]`), so ③ is the same red in the text as on the screen.
 */
export function richText(text: string, kinds: readonly MarkKind[] = []): string {
  const esc = text.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);
  return esc
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\[(\d)\]/g, (_, n: string) => `<span class="gt-n gt-k-${kinds[Number(n) - 1] ?? "focus"}">${n}</span>`);
}

const SVG = "http://www.w3.org/2000/svg";

/** An element's box; a `display: contents` wrapper has none, so it is the union of its children's. */
export function rectOf(el: Element): DOMRect {
  const r = el.getBoundingClientRect();
  if (r.width || r.height || !el.children.length) return r;
  const rs = [...el.children].map(rectOf).filter((c) => c.width || c.height);
  if (!rs.length) return r;
  const left = Math.min(...rs.map((c) => c.left)), top = Math.min(...rs.map((c) => c.top));
  return new DOMRect(left, top, Math.max(...rs.map((c) => c.right)) - left, Math.max(...rs.map((c) => c.bottom)) - top);
}
/** true while a scripted `press` is dispatched: that key belongs to the app, not to the tour */
let scripted = false;
const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/** Perform one scripted action; a glide-and-press dot shows where it happens. */
async function act(a: TourAction, dot: HTMLElement, stale: () => boolean): Promise<void> {
  if ("wait" in a) return void (await sleep(a.wait));
  if ("press" in a) {
    const f = document.activeElement;
    const t = f && !f.closest(".gt-dock") ? f : document.body;   // never the dock's own Next button
    scripted = true;
    for (const type of ["keydown", "keyup"]) t.dispatchEvent(new KeyboardEvent(type, { key: a.press, bubbles: true }));
    scripted = false;
    return void (await sleep(150));
  }
  const sel = "click" in a ? a.click : "hover" in a ? a.hover : a.type;
  const el = (await waitFor(sel)) as HTMLElement | null;
  if (!el) return;
  el.scrollIntoView({ block: "nearest" });
  const r = el.getBoundingClientRect();
  dot.style.display = "block";
  dot.style.left = `${r.left + r.width / 2}px`;
  dot.style.top = `${r.top + r.height / 2}px`;
  await sleep(480);
  if (stale()) return;
  if ("hover" in a) {
    for (const type of ["pointerover", "pointerenter", "mouseover", "mouseenter"]) el.dispatchEvent(new MouseEvent(type, { bubbles: true }));
    return void (await sleep(250));
  }
  dot.classList.add("gt-press");
  await sleep(140);
  dot.classList.remove("gt-press");
  if (stale()) return;
  if ("click" in a) el.click();
  else {
    el.focus();
    // React tracks the value through the native setter; assigning .value alone would be swallowed
    const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    for (let n = 1; n <= a.text.length && !stale(); n++) {
      Object.getOwnPropertyDescriptor(proto, "value")?.set?.call(el, a.text.slice(0, n));
      el.dispatchEvent(new Event("input", { bubbles: true }));
      await sleep(35);
    }
  }
  await sleep(250);
}

let stop: ((reason: TourEndReason) => void) | null = null;

export interface TourOptions {
  onEnd?: (reason: TourEndReason) => void;
  /** advance by itself every `autoplay` ms from step 2 on (step 1 always waits for Next); keys and buttons still work */
  autoplay?: number;
}

export function startTour(steps: TourStep[], opts: TourOptions = {}): void {
  stop?.("replaced");
  if (!document.getElementById("gt-style")) {
    const st = document.createElement("style");
    st.id = "gt-style";
    st.textContent = CSS;
    document.head.appendChild(st);
  }
  const routes = routesOf(steps);
  let i = 0;
  let lit: { el: Element; kind: MarkKind; label?: string; n?: number }[] = [];
  let ended = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const div = (className: string) => Object.assign(document.createElement("div"), { className });
  const veil = document.createElementNS(SVG, "svg");
  veil.setAttribute("class", "gt-veil");
  veil.setAttribute("aria-hidden", "true");
  veil.innerHTML = `<defs><mask id="gt-mask"><rect width="100%" height="100%" fill="#fff"/></mask></defs><rect class="gt-shade" width="100%" height="100%" fill="rgb(10,14,20)" mask="url(#gt-mask)"/>`;
  const mask = veil.querySelector("mask")!;
  const shade = veil.querySelector(".gt-shade")!;
  const rings = div("gt-rings");
  const dot = div("gt-dot");
  dot.style.display = "none";
  const card = div("gt-card");
  const dock = div("gt-dock");
  dock.setAttribute("role", "dialog");
  dock.setAttribute("aria-label", "Guided tour");
  dock.innerHTML = `<button class="gt-skip">Skip</button><button class="gt-back" aria-label="Back">‹ Back</button><span class="gt-count"></span><button class="gt-next"></button>`;
  const q = (s: string) => dock.querySelector(s) as HTMLButtonElement;
  const skipB = q(".gt-skip"), backB = q(".gt-back"), count = q(".gt-count"), nextB = q(".gt-next");
  card.setAttribute("aria-live", "polite");
  document.body.append(veil, rings, card, dot, dock);
  document.body.classList.add(ACTIVE_CLASS);

  function place() {
    const s = steps[i]!;
    const pad = s.pad ?? 6;
    shade.setAttribute("fill-opacity", String(Math.min(0.85, Math.max(0, s.dim ?? 0.55))));
    const boxes = lit.map((l) => rectOf(l.el));
    // one cut per lit element (kept in order, so the mask animates between steps), extras removed
    const cuts = [...mask.querySelectorAll("rect.gt-cut")];
    boxes.forEach((r, k) => {
      let c = cuts[k];
      if (!c) { c = document.createElementNS(SVG, "rect"); c.setAttribute("class", "gt-cut"); c.setAttribute("fill", "#000"); c.setAttribute("rx", "10"); mask.append(c); }
      // attributes, not CSS x/y/width/height: WebKit has no CSS geometry for SVG rects (the ring animates instead)
      c.setAttribute("x", String(r.left - pad)); c.setAttribute("y", String(r.top - pad));
      c.setAttribute("width", String(r.width + pad * 2)); c.setAttribute("height", String(r.height + pad * 2));
    });
    cuts.slice(boxes.length).forEach((c) => c.remove());
    const ringEls = [...rings.children] as HTMLElement[];
    lit.forEach((l, k) => {
      const r = boxes[k]!;
      let ring = ringEls[k];
      if (!ring) { ring = div("gt-ring"); rings.append(ring); }
      ring.className = `gt-ring gt-k-${l.kind}`;
      // one chip per mark: number + label, above the ring, or below it when the ring hugs the top edge
      ring.innerHTML = l.n ? `<div class="gt-chip${r.top - pad < 40 ? " gt-below" : ""}"><b class="gt-n">${l.n}</b>${l.label ? "<span></span>" : ""}</div>` : "";
      if (l.label && l.n) ring.querySelector(".gt-chip span")!.textContent = l.label;
      Object.assign(ring.style, { top: `${r.top - pad}px`, left: `${r.left - pad}px`, width: `${r.width + pad * 2}px`, height: `${r.height + pad * 2}px` });
    });
    ringEls.slice(lit.length).forEach((r) => r.remove());
    // a chip that lands on an earlier one moves to the other side of its ring; boxes come from the targets,
    // not the rings, which are still gliding into place
    const placed: number[][] = [];
    lit.forEach((_, k) => {
      const chip = rings.children[k]?.querySelector<HTMLElement>(".gt-chip");
      if (!chip) return;
      const r = boxes[k]!, w = chip.offsetWidth, h = chip.offsetHeight, x = r.left - pad;
      const at = (below: boolean) => [x, below ? r.bottom + pad + 6 : r.top - pad - 6 - h, x + w, below ? r.bottom + pad + 6 + h : r.top - pad - 6];
      const hits = (b: number[]) => placed.some((p) => b[0]! < p[2]! && p[0]! < b[2]! && b[1]! < p[3]! + 4 && p[1]! < b[3]! + 4);
      let below = chip.classList.contains("gt-below");
      if (hits(at(below))) chip.classList.toggle("gt-below", (below = !below));
      placed.push(at(below));
    });

    const main = lit[0]?.n ? null : boxes[0];   // a step with no target has only numbered marks
    card.className = `gt-card gt-k-${s.kind ?? "focus"}`;
    const cw = card.offsetWidth, ch = card.offsetHeight, W = innerWidth, H = innerHeight - 80, g = 16;
    if (!main) {
      // no spotlight: centred when nothing is marked, else the candidate spot that covers the marks least
      const spots = [[(W - cw) / 2, innerHeight / 3], [(W - cw) / 2, H - ch - 16], [(W - cw) / 2, 72], [16, H - ch - 16], [W - cw - 16, H - ch - 16], [16, 72], [W - cw - 16, 72]];
      const cover = ([x, y]: number[]) => boxes.reduce((a, b) => a + Math.max(0, Math.min(x! + cw, b.right + g) - Math.max(x!, b.left - g)) * Math.max(0, Math.min(y! + ch, b.bottom + g) - Math.max(y!, b.top - g)), 0);
      const [x, y] = spots.reduce((best, s) => (cover(s) < cover(best) ? s : best));
      card.style.left = `${x}px`;
      card.style.top = `${y}px`;
      return;
    }
    const r = main;
    let p = s.place ?? "right";
    if (p === "right" && r.right + g + cw > W) p = "left";
    if (p === "left" && r.left - g - cw < 0) p = "bottom";
    if (p === "bottom" && r.bottom + g + ch > H) p = "top";
    const x = p === "right" ? r.right + g : p === "left" ? r.left - g - cw : r.left;
    const y = p === "bottom" ? r.bottom + g : p === "top" ? r.top - g - ch : r.top;
    card.style.left = `${Math.max(16, Math.min(x, W - cw - 16))}px`;
    card.style.top = `${Math.max(16, Math.min(y, H - ch - 16))}px`;
  }

  let showing = 0;
  async function show() {
    const s = steps[i]!;
    const token = ++showing;
    clearTimeout(timer);
    const stale = () => ended || token !== showing; // the user moved on, or the tour ended, while we waited
    if (stale()) return;
    if (!atLocation(routes[i]!)) window.kbGo?.(routes[i]!);
    await s.before?.();
    if (stale()) return;
    dot.style.display = "none";
    for (const a of s.do ?? []) {
      await act(a, dot, stale);
      if (stale()) return;
    }
    dot.style.display = "none";
    const target = s.target ? await waitFor(s.target, s.wait) : null;
    if (stale()) return;
    target?.scrollIntoView({ block: "nearest" });
    const marks = await Promise.all((s.marks ?? []).map(async (m, k) => ({ el: await waitFor(m.target, s.wait), kind: m.kind ?? "focus", label: m.label, n: k + 1 })));
    if (stale()) return;
    lit = [...(target ? [{ el: target, kind: s.kind ?? "focus" }] : []), ...marks.filter((m) => m.el)] as typeof lit;
    card.innerHTML = `<h4></h4><p></p>`;
    card.querySelector("h4")!.textContent = s.title;
    card.querySelector("p")!.innerHTML = richText(s.body, (s.marks ?? []).map((m) => m.kind ?? "focus"));
    count.textContent = `${i + 1} / ${steps.length}`;
    backB.disabled = i === 0;
    nextB.textContent = i === steps.length - 1 ? "Done" : "Next ›";
    requestAnimationFrame(place);
    nextB.focus({ preventScroll: true });
    // autoplay starts only after a person has pressed Next once: a link alone never acts without a gesture
    if (opts.autoplay && i > 0 && i < steps.length - 1) timer = setTimeout(next, opts.autoplay);
  }
  const next = () => (i < steps.length - 1 ? (i++, void show()) : end("done"));
  const back = () => i > 0 && (i--, void show());
  const key = (e: KeyboardEvent) => {
    if (scripted) return;
    if (inField(e.target)) return;
    if (e.key === "ArrowRight" || e.key === "Enter") { e.preventDefault(); e.stopPropagation(); next(); }
    else if (e.key === "ArrowLeft") { e.stopPropagation(); back(); }
    else if (e.key === "Escape") { e.stopPropagation(); end("skip"); }
  };
  function end(reason: TourEndReason) {
    if (ended) return;
    ended = true;
    clearTimeout(timer);
    veil.remove(); rings.remove(); card.remove(); dot.remove(); dock.remove();
    document.body.classList.remove(ACTIVE_CLASS);
    removeEventListener("keydown", key, true);
    removeEventListener("resize", place);
    removeEventListener("scroll", place, true);
    stop = null;
    opts.onEnd?.(reason);
  }
  nextB.onclick = next;
  backB.onclick = back;
  skipB.onclick = () => end("skip");
  addEventListener("keydown", key, true);
  addEventListener("resize", place);
  addEventListener("scroll", place, true);
  stop = end;
  void show();
}
