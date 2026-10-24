/* Magnetic pointer (experiment): the hovered node is the nearest one, not only the one under the pointer.
   How far the pull reaches follows the spacing around that node on screen (so density and zoom both count),
   the current target is sticky so dense areas don't flicker, and a soft bubble joins the pointer to it.
   graph.js still draws the graph; this file picks the hovered node and paints the bubble on an overlay. */
(function () {
  "use strict";
  const G = () => window.WikiGraph;
  const $ = (id) => document.getElementById(id);
  const KEYS = { "magnet-pointer": "thesis-wiki-graph-magnet", "declutter-labels": "thesis-wiki-graph-declutter", "magnet-variant": "thesis-wiki-graph-magnet-variant" };
  const REACH_MIN = 12, REACH_MAX = 90, REACH_SHARE = 0.6, STICKY = 1.2, GAPS_EVERY_MS = 1000;
  const FIXED_REACH = 80;        // the "crisp" variant: the first take, one reach for every node
  // Two variants to compare on real data: "soft" = blurred bubble + density-adaptive, sticky reach;
  // "crisp" = outlined bubble + a fixed 80 px reach, no stickiness.
  const variant = () => ($("magnet-variant") && $("magnet-variant").value) || "soft";
  const UI = ".graph-toolbar, .hud, .hud-shell, .inspector-shell, .ui-edge-tab";

  let canvas = null, ctx = null, dpr = 1;
  let pointer = null;           // {x, y} in client coordinates while over the graph
  let pressed = false;
  let target = null;
  let raf = 0;
  let lastRecheck = 0;
  const soft = { r: 0, a: 0 };   // eased bubble radius and strength
  const gaps = new Map();        // node id → gap to its closest visible neighbour, graph units
  let gapsAt = 0, gapsCount = -1;

  const on = () => !!$("magnet-pointer")?.checked;
  const live = () => (G() ? G().visibleNodes().filter((n) => Number.isFinite(n.x)) : []);

  const radii = new Map();       // node id → base radius, graph units (cached with the gaps)

  // Rim-to-rim gap to the nearest neighbour for every node: sort by x and sweep outwards, stopping once the
  // x distance alone exceeds the best gap — close to O(n log n), a few ms for a couple of thousand nodes.
  function refreshGaps(list) {
    const now = performance.now();
    if (list.length === gapsCount && now - gapsAt < GAPS_EVERY_MS) return;
    gapsAt = now; gapsCount = list.length; gaps.clear(); radii.clear();
    let rMax = 0;
    for (const n of list) { const r = G().radiusOf(n); radii.set(n.id, r); if (r > rMax) rMax = r; }
    const xs = [...list].sort((a, b) => a.x - b.x);
    for (let i = 0; i < xs.length; i++) {
      const a = xs[i], ra = radii.get(a.id);
      let best = Infinity;
      for (const dir of [-1, 1]) {
        for (let j = i + dir; j >= 0 && j < xs.length; j += dir) {
          const b = xs[j], dx = Math.abs(b.x - a.x);
          if (dx - ra - rMax > best) break;
          const d = Math.hypot(b.x - a.x, b.y - a.y) - ra - radii.get(b.id);
          if (d < best) best = d;
        }
      }
      gaps.set(a.id, Math.max(0, best));
    }
  }

  const reachOf = (n, k) => (variant() === "crisp" ? FIXED_REACH
    : Math.min(REACH_MAX, Math.max(REACH_MIN, (gaps.get(n.id) ?? 40) * k * REACH_SHARE)));
  const radiusOf = (n) => radii.get(n.id) ?? G().radiusOf(n);

  function rim(n, px, py, k) {
    const s = G().screenOf(n);
    return Math.hypot(s.x - px, s.y - py) - radiusOf(n) * k;
  }

  function pick(px, py) {
    const list = live();
    if (!list.length) return null;
    refreshGaps(list);
    const k = G().view().k;
    let best = null, bd = Infinity;
    for (const n of list) {
      const d = rim(n, px, py, k);
      if (d < bd) { bd = d; best = n; }
    }
    if (variant() === "soft" && target && target !== best && list.includes(target)) {   // sticky: switch only when clearly closer
      const td = rim(target, px, py, k);
      if (td <= reachOf(target, k) && td < bd * STICKY + 3) return target;
    }
    return bd <= reachOf(best, k) ? best : null;
  }

  // ---------------------------------------------------------------- overlay
  function size() {
    const root = $("graph-root");
    if (!canvas || !root) return;
    const r = root.getBoundingClientRect();
    dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(r.width * dpr); canvas.height = Math.round(r.height * dpr);
    canvas.style.width = `${r.width}px`; canvas.style.height = `${r.height}px`;
  }

  function rgbOf(color) {
    const m = String(color).match(/\d+(\.\d+)?/g);
    if (color.startsWith("#") && color.length === 7) return [1, 3, 5].map((o) => parseInt(color.slice(o, o + 2), 16)).join(",");
    return m && m.length >= 3 ? m.slice(0, 3).join(",") : "122,162,255";
  }

  function frame() {
    raf = 0;
    if (!canvas || !G()) return;
    const root = $("graph-root").getBoundingClientRect();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, canvas.width / dpr, canvas.height / dpr);
    const aim = on() && pointer && !pressed;
    const k = G().view().k;
    // the layout can drift under a pointer that holds still: re-check the target a few times a second
    const now = performance.now();
    if (aim && target && now - lastRecheck > 150) {
      lastRecheck = now;
      const next = pick(pointer.x, pointer.y);
      if (next !== target) { target = next; G().setHover(target); }
    }
    let tx = 0, ty = 0, tr = 0, want = 0, strength = 0;
    if (aim && target && Number.isFinite(target.x)) {
      const s = G().screenOf(target);
      tx = s.x - root.left; ty = s.y - root.top; tr = radiusOf(target) * k;
      want = Math.hypot(tx - (pointer.x - root.left), ty - (pointer.y - root.top)) + tr + 10;
      strength = 1 - 0.55 * Math.min(1, Math.max(0, rim(target, pointer.x, pointer.y, k)) / reachOf(target, k));
    }
    const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
    soft.r = still ? want : soft.r + (want - soft.r) * 0.3;
    soft.a = still ? strength : soft.a + (strength - soft.a) * 0.2;
    if (variant() === "crisp" && aim && target && tr) {
      // the first take: an outlined bubble that just reaches the target, no easing
      const rgb = rgbOf(getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#7aa2ff");
      const px = pointer.x - root.left, py = pointer.y - root.top;
      const rr = Math.hypot(tx - px, ty - py) + tr + 4;
      ctx.beginPath(); ctx.arc(px, py, rr, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${rgb},0.07)`; ctx.fill();
      ctx.strokeStyle = `rgba(${rgb},0.45)`; ctx.lineWidth = 1.2; ctx.stroke();
      soft.r = 0; soft.a = 0;
    } else if (pointer && soft.a > 0.02 && soft.r > 2) {
      const rgb = rgbOf(getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#7aa2ff");
      const px = pointer.x - root.left, py = pointer.y - root.top;
      const g = ctx.createRadialGradient(px, py, 0, px, py, soft.r * 1.12);
      g.addColorStop(0, `rgba(${rgb},${0.17 * soft.a})`);
      g.addColorStop(0.6, `rgba(${rgb},${0.11 * soft.a})`);
      g.addColorStop(1, `rgba(${rgb},0)`);
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(px, py, soft.r * 1.12, 0, Math.PI * 2); ctx.fill();
      if (tr) {                                    // a soft glow on the target, so pointer and node read as one shape
        const g2 = ctx.createRadialGradient(tx, ty, tr * 0.6, tx, ty, tr + 16);
        g2.addColorStop(0, `rgba(${rgb},${0.3 * soft.a})`);
        g2.addColorStop(1, `rgba(${rgb},0)`);
        ctx.fillStyle = g2;
        ctx.beginPath(); ctx.arc(tx, ty, tr + 16, 0, Math.PI * 2); ctx.fill();
      }
    }
    // keep animating while the bubble is fading or the target can still drift with the layout
    if ((aim && target) || soft.a > 0.02) raf = requestAnimationFrame(frame);
  }
  const kick = () => { if (!raf) raf = requestAnimationFrame(frame); };

  function retarget() {
    if (!G()) return;
    if (pressed) { kick(); return; }   // the target stays put while a button is down: a drag starting on it must keep it
    const next = on() && pointer ? pick(pointer.x, pointer.y) : null;
    if (next !== target) {
      target = next;
      if (on()) G().setHover(target);
    }
    kick();
  }

  // The quiet arrow, drawn as SVG and handed to CSS as a blob URL:
  // the shared site is a single inlined page that must not carry embedded images.
  function setCursors(root) {
    const svg = (inner) => `<svg xmlns='http://www.w3.org/2000/svg' width='32' height='32' viewBox='0 0 32 32'>${inner}</svg>`;
    const arrow = "<path d='M7 4 L7 24.5 L12.4 19.4 L16 27.2 L19.4 25.7 L15.9 18 L23.2 18 Z' fill='#15171c' stroke='#fff' stroke-width='1.8' stroke-linejoin='round'/>";
    const url = (inner) => URL.createObjectURL(new Blob([svg(inner)], { type: "image/svg+xml" }));
    try {
      root.style.setProperty("--magnet-cursor", `url("${url(arrow)}") 7 4, default`);
    } catch { /* no blob URLs: the CSS falls back to the system cursors */ }
  }

  // ---------------------------------------------------------------- wiring
  function bind() {
    const root = $("graph-root");
    if (!root) return;
    // a sibling laid over #graph-root, not a child: force-graph empties its container when it starts
    canvas = document.createElement("canvas");
    canvas.className = "gm-magnet";
    canvas.setAttribute("aria-hidden", "true");
    root.insertAdjacentElement("afterend", canvas);
    ctx = canvas.getContext("2d");
    size();
    window.addEventListener("resize", size);

    let queued = false;
    root.addEventListener("pointermove", (e) => {
      if (e.target.closest && e.target.closest(UI)) { pointer = null; retarget(); return; }
      pointer = { x: e.clientX, y: e.clientY };
      if (queued) return;
      queued = true;
      requestAnimationFrame(() => { queued = false; retarget(); });
    }, { passive: true });
    root.addEventListener("pointerdown", (e) => { if (e.button === 0) { pressed = true; kick(); } }, true);
    // after force-graph has seen the release: re-setting its props inside the event breaks its pan/drag bookkeeping
    window.addEventListener("pointerup", () => { if (pressed) { pressed = false; requestAnimationFrame(retarget); } });
    root.addEventListener("pointerleave", () => { pointer = null; retarget(); });
    root.addEventListener("wheel", () => requestAnimationFrame(retarget), { passive: true });   // the view moved under the pointer
    root.classList.toggle("magnet", on());
    setCursors(root);

    // the two experiment switches remember their state per browser
    Object.entries(KEYS).forEach(([id, key]) => {
      const box = $(id);
      if (!box) return;
      const isBox = box.type === "checkbox";
      try {
        const v = localStorage.getItem(key);
        if (v !== null) { if (isBox) box.checked = v === "1"; else box.value = v; }
      } catch { /* defaults */ }
      box.addEventListener("change", () => {
        try { localStorage.setItem(key, isBox ? (box.checked ? "1" : "0") : box.value); } catch { /* ignore */ }
        root.classList.toggle("magnet", on());
        if (!on()) { target = null; G() && G().setHover(null); }
        if (G()) G().redraw();
        retarget();
      });
    });
    if (G()) G().redraw();
  }

  window.GraphMagnet = {
    target: () => target, reachOf: (n) => reachOf(n, G().view().k), gap: (id) => gaps.get(id),
    timeGaps: () => { gapsCount = -1; const t0 = performance.now(); refreshGaps(live()); return performance.now() - t0; },
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bind); else bind();
})();
