/* The right mouse button on the graph: drag a box to select (Shift adds), Cmd/Ctrl+drag a freeform
   lasso (adds), a plain right-click on a node opens its menu. Left button, wheel and double-click
   live in graph.js; this file talks to it through window.WikiGraph. */
(function () {
  "use strict";
  const G = () => window.WikiGraph;
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const DRAG_PX = 4;
  const UI = ".graph-toolbar, .hud, .hud-shell, .inspector-shell, .ui-edge-tab";

  // The node menu. `when(node)` offers an entry at all, `enabled(node)` greys it out with `why`.
  // A new action is one more entry here.
  const ITEMS = [
    { id: "reader", label: "Open in side reader", hint: "double-click",
      when: () => !!window.SideReader, run: (n) => window.SideReader.open(n.id) },
    { id: "details", label: "Show details", hint: "links · sources",
      when: () => !!window.GraphDetails,
      run: (n) => { if (!G().selectedIds().includes(n.id)) G().select([n.id], { additive: false }); window.GraphDetails.open(); } },
    { id: "explore", label: "Open in Explore", hint: "E",
      run: (n) => { location.href = G().exploreUrl(n.id); } },
    { id: "genealogy", label: "Open in citation genealogy",
      when: () => !!window.DataLayer && !window.KB_STATIC,
      enabled: (n) => n.type === "paper", why: "papers only",
      run: (n) => window.DataLayer.openCitations({ focus: n.id }) },
  ];

  // ---------------------------------------------------------------- menu
  let menu = null;
  function closeMenu() {
    if (menu) menu.remove();
    menu = null;
  }
  function openMenu(node, x, y) {
    closeMenu();
    const items = ITEMS.filter((it) => !it.when || it.when(node));
    menu = document.createElement("div");
    menu.className = "gm-menu";
    menu.setAttribute("role", "menu");
    menu.innerHTML = `<div class="gm-head"><i class="gs-dot" style="background:${G().colorFor(node)}"></i><span>${esc(node.title || node.id)}</span></div>` +
      items.map((it) => {
        const on = !it.enabled || it.enabled(node);
        return `<button type="button" role="menuitem" class="gm-item" data-id="${it.id}"${on ? "" : " disabled"}><span>${esc(it.label)}</span><small>${esc(on ? it.hint || "" : it.why || "")}</small></button>`;
      }).join("");
    document.body.appendChild(menu);
    const r = menu.getBoundingClientRect();
    menu.style.left = `${Math.max(8, Math.min(x, window.innerWidth - r.width - 8))}px`;
    menu.style.top = `${Math.max(8, Math.min(y, window.innerHeight - r.height - 8))}px`;
    const target = node;
    menu.addEventListener("click", (e) => {
      const b = e.target.closest(".gm-item");
      if (!b || b.disabled) return;
      const it = ITEMS.find((i) => i.id === b.dataset.id);
      closeMenu();
      if (it) it.run(target);
    });
    const first = menu.querySelector(".gm-item:not([disabled])");
    if (first) first.focus({ preventScroll: true });
  }

  function closePanels() {
    if (window.SideReader) window.SideReader.close();
    if (window.GraphDetails) window.GraphDetails.close();
  }

  // ---------------------------------------------------------------- box + lasso
  let drag = null;   // {x, y, lasso, additive, node, moved, pts, canvas, id}

  function inPoly(x, y, poly) {
    let inside = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const [xi, yi] = poly[i], [xj, yj] = poly[j];
      if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
  }

  function startOverlay(d) {
    if (!d.lasso) { $("box-select-rect").classList.remove("hidden"); return; }
    const c = document.createElement("canvas");
    c.className = "sel-lasso";
    c.style.pointerEvents = "none";   // draw only: the release must reach force-graph's canvas
    c.width = window.innerWidth; c.height = window.innerHeight;
    document.body.appendChild(c);
    d.canvas = c;
  }

  function drawOverlay(d, x, y) {
    if (!d.lasso) {
      const rect = $("box-select-rect");
      rect.style.left = `${Math.min(d.x, x)}px`;
      rect.style.top = `${Math.min(d.y, y)}px`;
      rect.style.width = `${Math.abs(x - d.x)}px`;
      rect.style.height = `${Math.abs(y - d.y)}px`;
      return;
    }
    d.pts.push([x, y]);
    const ctx = d.canvas.getContext("2d");
    ctx.clearRect(0, 0, d.canvas.width, d.canvas.height);
    ctx.beginPath();
    d.pts.forEach(([px, py], i) => (i ? ctx.lineTo(px, py) : ctx.moveTo(px, py)));
    ctx.closePath();
    ctx.fillStyle = "rgba(122,162,255,0.14)"; ctx.fill();
    ctx.strokeStyle = "rgba(122,162,255,0.95)"; ctx.setLineDash([6, 4]); ctx.lineWidth = 1.5; ctx.stroke();
  }

  function endOverlay(d) {
    $("box-select-rect").classList.add("hidden");
    if (d.canvas) d.canvas.remove();
  }

  function pickInside(d, x, y) {
    const x1 = Math.min(d.x, x), x2 = Math.max(d.x, x), y1 = Math.min(d.y, y), y2 = Math.max(d.y, y);
    const inside = d.lasso
      ? (p) => inPoly(p.x, p.y, d.pts)
      : (p) => p.x >= x1 && p.x <= x2 && p.y >= y1 && p.y <= y2;
    return G().visibleNodes().filter((n) => Number.isFinite(n.x) && inside(G().screenOf(n))).map((n) => n.id);
  }

  function bind() {
    const root = $("graph-root");
    root.addEventListener("contextmenu", (e) => e.preventDefault());
    root.addEventListener("pointerdown", (e) => {
      if (e.button !== 2 || !G() || e.target.closest(UI)) return;
      closeMenu();
      drag = { x: e.clientX, y: e.clientY, lasso: e.metaKey || e.ctrlKey, additive: e.shiftKey,
        node: G().hovered(), moved: false, pts: [[e.clientX, e.clientY]], canvas: null, id: e.pointerId };
    }, true);
    // Followed on window, not with pointer capture: capturing would retarget the pointerup away from
    // force-graph's canvas, which then believes the button is still down and stops reporting hovers.
    window.addEventListener("pointermove", (e) => {
      if (!drag || e.pointerId !== drag.id) return;
      if (!drag.moved) {
        if (Math.hypot(e.clientX - drag.x, e.clientY - drag.y) < DRAG_PX) return;
        drag.moved = true;
        startOverlay(drag);
      }
      drawOverlay(drag, e.clientX, e.clientY);
    }, true);
    const end = (e) => {
      if (!drag || e.pointerId !== drag.id) return;
      const d = drag;
      drag = null;
      if (e.type === "pointercancel") { endOverlay(d); return; }
      if (!d.moved) {
        if (d.node && !d.node.pile) openMenu(d.node, e.clientX, e.clientY);
        else { closePanels(); G().clear(); }   // right-click on empty space: close the reader and details, drop the selection
        return;
      }
      const ids = pickInside(d, e.clientX, e.clientY);
      endOverlay(d);
      if (d.lasso) { if (ids.length && d.pts.length > 3) G().select(ids, { additive: true }); return; }
      if (ids.length) G().select(ids, { additive: d.additive });
      else if (!d.additive) G().clear();
    };
    window.addEventListener("pointerup", end, true);
    window.addEventListener("pointercancel", end, true);

    document.addEventListener("pointerdown", (e) => { if (menu && !menu.contains(e.target)) closeMenu(); }, true);
    document.addEventListener("keydown", (e) => {
      if (!menu) return;
      if (e.key === "Escape") { e.stopPropagation(); closeMenu(); return; }
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      e.preventDefault();
      const all = [...menu.querySelectorAll(".gm-item:not([disabled])")];
      const i = all.indexOf(document.activeElement);
      const next = all[(i + (e.key === "ArrowDown" ? 1 : -1) + all.length) % all.length];
      if (next) next.focus();
    }, true);
    root.addEventListener("wheel", closeMenu, { passive: true });
    window.addEventListener("blur", closeMenu);
  }

  window.GraphMenu = { items: ITEMS, open: openMenu, close: closeMenu, isOpen: () => !!menu };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bind); else bind();
})();
