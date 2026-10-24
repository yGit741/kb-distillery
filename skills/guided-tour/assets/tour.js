/* Guided tour engine: dims the page, spotlights one element per step, Next / Back / Skip.
   Usage: Tour.start([{ target: "#css-selector", title: "…", body: "…", place: "right|left|top|bottom", before: () => {} }]) */
(function () {
  const css = `
  .gt-hole{position:fixed;z-index:9998;border-radius:10px;box-shadow:0 0 0 9999px rgba(10,14,20,.62);transition:all .28s ease;pointer-events:none}
  .gt-card{position:fixed;z-index:9999;width:min(300px,calc(100vw - 32px));background:var(--gt-bg,#fff);color:var(--gt-fg,#18202b);border-radius:10px;padding:14px 16px;box-shadow:0 12px 32px rgba(0,0,0,.28);font:14px/1.5 system-ui,sans-serif;transition:top .28s,left .28s}
  .gt-card h4{margin:0 0 4px;font-size:15px}.gt-card p{margin:0 0 12px;color:var(--gt-muted,#5b6676)}
  .gt-row{display:flex;align-items:center;gap:8px}.gt-dots{flex:1;display:flex;gap:4px}
  .gt-dots i{width:6px;height:6px;border-radius:3px;background:var(--gt-muted,#5b6676);opacity:.35}.gt-dots i.on{opacity:1;width:14px;background:var(--gt-accent,#2f6fde)}
  .gt-card button{font:inherit;border:0;border-radius:6px;padding:5px 12px;cursor:pointer}
  .gt-next{background:var(--gt-accent,#2f6fde);color:#fff}.gt-back,.gt-skip{background:transparent;color:var(--gt-muted,#5b6676)}
  .gt-card button:focus-visible{outline:2px solid var(--gt-accent,#2f6fde);outline-offset:2px}
  @media (prefers-reduced-motion:reduce){.gt-hole,.gt-card{transition:none}}`;
  let steps = [], i = 0, hole, card, onEnd;
  function el(tag, cls) { const e = document.createElement(tag); if (cls) e.className = cls; return e; }
  function place() {
    const s = steps[i], t = document.querySelector(s.target);
    if (!t) return;
    const r = t.getBoundingClientRect(), pad = s.pad ?? 6;
    Object.assign(hole.style, { top: r.top - pad + "px", left: r.left - pad + "px", width: r.width + pad * 2 + "px", height: r.height + pad * 2 + "px" });
    const cw = card.offsetWidth, ch = card.offsetHeight, W = innerWidth, H = innerHeight, g = 14;
    let p = s.place || "right", x, y;
    if (p === "right" && r.right + g + cw > W) p = "bottom";
    if (p === "left" && r.left - g - cw < 0) p = "bottom";
    if (p === "bottom" && r.bottom + g + ch > H) p = "top";
    if (p === "right") { x = r.right + g; y = r.top; } else if (p === "left") { x = r.left - g - cw; y = r.top; }
    else if (p === "top") { x = r.left; y = r.top - g - ch; } else { x = r.left; y = r.bottom + g; }
    card.style.left = Math.max(16, Math.min(x, W - cw - 16)) + "px";
    card.style.top = Math.max(16, Math.min(y, H - ch - 16)) + "px";
  }
  function show() {
    const s = steps[i];
    if (s.before) s.before();
    const t = document.querySelector(s.target);
    if (t) t.scrollIntoView({ block: "nearest" });
    card.innerHTML = `<h4>${s.title}</h4><p>${s.body}</p><div class="gt-row"><button class="gt-skip">Skip</button><span class="gt-dots">${steps.map((_, k) => `<i class="${k === i ? "on" : ""}"></i>`).join("")}</span>${i ? '<button class="gt-back">Back</button>' : ""}<button class="gt-next">${i === steps.length - 1 ? "Done" : "Next"}</button></div>`;
    card.querySelector(".gt-next").onclick = next;
    card.querySelector(".gt-skip").onclick = end;
    const b = card.querySelector(".gt-back");
    if (b) b.onclick = back;
    requestAnimationFrame(place);
    card.querySelector(".gt-next").focus({ preventScroll: true });
  }
  function next() { if (i < steps.length - 1) { i++; show(); } else end(); }
  function back() { if (i) { i--; show(); } }
  function key(e) {
    if (e.key === "ArrowRight" || e.key === "Enter") { e.preventDefault(); next(); }
    else if (e.key === "ArrowLeft") back();
    else if (e.key === "Escape") end();
  }
  function end() { hole.remove(); card.remove(); removeEventListener("keydown", key); removeEventListener("resize", place); if (onEnd) onEnd(); }
  window.Tour = {
    start(list, opts = {}) {
      if (!document.getElementById("gt-style")) { const st = el("style"); st.id = "gt-style"; st.textContent = css; document.head.appendChild(st); }
      steps = list; i = opts.from || 0; onEnd = opts.onEnd;
      hole = el("div", "gt-hole"); card = el("div", "gt-card"); card.setAttribute("role", "dialog");
      document.body.append(hole, card);
      addEventListener("keydown", key); addEventListener("resize", place);
      show();
    },
  };
})();
