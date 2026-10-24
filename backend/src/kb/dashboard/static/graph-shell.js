/* Unified graph shell: search bar · dock flyouts · legend · right-hand inspector · side reader.
   Drives the existing controls (same element ids) so graph.js stays the single source of behaviour. */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const G = () => window.WikiGraph;
  const NB_MAX = 40;

  const FLYOUTS = {
    filter: { title: "Filter nodes", panels: ["nodes"] },
    labels: { title: "Labels", panels: ["labels"] },
    look: { title: "Colour & size", panels: ["groups", "display"] },
    layout: { title: "Layout & sync", panels: ["forces", "sync"] },
    presets: { title: "Saved views", panels: ["presets"] },
    help: { title: "Shortcuts", extra: "help" },
  };

  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // ---------- drive legacy controls ----------
  function setControl(id, value) {
    const c = $(id);
    if (!c) return;
    if (c.type === "checkbox") {
      if (value === undefined || c.checked !== value) c.click();
      return;
    }
    c.value = value;
    c.dispatchEvent(new Event("input", { bubbles: true }));
    c.dispatchEvent(new Event("change", { bubbles: true }));
  }
  const click = (id) => { const b = $(id); if (b) b.click(); };

  // ---------- flyouts ----------
  let openFly = null;
  function park() {
    const body = $("gs-fly-body");
    while (body.firstChild) {
      const n = body.firstChild;
      if (n.dataset && n.dataset.keep) $("gs-park").appendChild(n);
      else n.remove();
    }
  }
  function closeFly() {
    park();
    openFly = null;
    $("gs-fly").classList.add("hidden");
    document.querySelectorAll(".gs-dock-btn[data-fly]").forEach((b) => b.classList.remove("active"));
  }
  function showFly(name) {
    if (openFly === name) { closeFly(); return; }
    const def = FLYOUTS[name];
    if (!def) return;
    park();
    openFly = name;
    $("gs-fly-title").textContent = def.title;
    const body = $("gs-fly-body");
    (def.panels || []).forEach((p) => {
      const panel = document.querySelector(`details.fold-panel[data-panel="${p}"]`);
      if (panel) { panel.open = true; body.appendChild(panel); }
    });
    if (def.extra === "help") body.appendChild($("shortcuts-panel"));
    $("gs-fly").classList.remove("hidden");
    document.querySelectorAll(".gs-dock-btn[data-fly]").forEach((b) => b.classList.toggle("active", b.dataset.fly === name));
    const first = body.querySelector("input[type=search], select");
    if (name === "filter" && first) first.focus();
  }

  function adoptLegacy() {
    document.querySelectorAll("details.fold-panel").forEach((p) => { p.dataset.keep = "1"; p.open = true; $("gs-park").appendChild(p); });
    const help = $("shortcuts-panel");
    help.dataset.keep = "1";
    $("gs-park").appendChild(help);

    const corner = $("gs-corner");
    corner.appendChild($("selection-pill"));
    corner.appendChild(document.querySelector(".zoom-group"));
  }

  // ---------- legend ----------
  function renderLegend() {
    if (!G()) return;
    const { by, rows } = G().legend();
    const names = { type: "Type", status: "Status", area: "Area", degree: "Links", none: "Colour" };
    const active = by === "type" ? G().activeLabelTypes() : new Set();
    const status = $("status-line");
    // Colour by type: a row click shows/hides the type (hidden rows stay, dimmed); "Aa" toggles its labels.
    const html = (by === "type" ? rows : rows.slice(0, 10)).map((r) => by === "type"
      ? `<div class="gs-legend-row gs-legend-type${r.hidden ? " off" : ""}${active.has(r.type) && !r.hidden ? " active" : ""}" data-type="${esc(r.type)}"><button type="button" class="gs-legend-vis" data-vis title="${r.hidden ? "Show" : "Hide"} every ${esc(r.label)}"><i class="gs-dot" style="background:${r.color}"></i><span>${esc(r.label)}</span><small>${r.count}</small></button><button type="button" class="gs-legend-aa" data-aa title="Labels for every ${esc(r.label)}"${r.hidden ? " disabled" : ""}>Aa</button></div>`
      : `<div class="gs-legend-row"><i class="gs-dot" style="background:${r.color}"></i><span>${esc(r.label)}</span><small>${r.count}</small></div>`).join("");
    const legend = $("gs-legend");
    if (status && status.parentElement !== legend) status.dataset.keepStatus = "1";
    const typeActions = by === "type"
      ? `<button type="button" id="gs-legend-overview" title="The concept layer: topics, ideas and questions (people one chip away)">concepts</button><button type="button" id="gs-legend-all" title="Show every type">all</button>`
      : "";
    legend.innerHTML = `<div class="gs-legend-head"><span>${names[by] || by}</span><span class="gs-legend-actions">${typeActions}<button type="button" id="gs-legend-change">change</button></span></div>${html}<div class="gs-legend-foot" id="gs-legend-foot"></div>`;
    if (status) $("gs-legend-foot").appendChild(status);
    const shown = rows.filter((r) => !r.hidden).reduce((s, r) => s + r.count, 0);
    const filtered = G().nodes().length && (G().typesFiltered() || shown < G().nodes().length);
    document.querySelector('.gs-dock-btn[data-fly="filter"]').classList.toggle("has-badge", !!filtered);
    document.querySelector('.gs-dock-btn[data-fly="labels"]').classList.toggle("has-badge", active.size > 0);
  }

  // ---------- inspector ----------
  function nodeRow(id) {
    const n = G().node(id);
    if (!n) return "";
    return `<li data-go="${esc(id)}"><i class="gs-dot" style="background:${G().colorFor(n)}"></i><span>${esc(n.title || id)}</span><a href="${G().exploreUrl(id)}" title="Read in Explore">read →</a></li>`;
  }
  function propValue(k, v) {
    const s = String(v);
    return /^https?:\/\//i.test(s) ? `<a href="${esc(s)}" target="_blank" rel="noopener noreferrer">${esc(s)}</a>` : esc(s);
  }
  // A book hub shows its partition: coverage bar + parts (digested ones focus their node).
  // A part shows the book it hangs off.
  function bookBlock(n) {
    if (n.part && n.part.book && G().node(n.part.book)) {
      return `<h3><span>Part of</span><span>pp. ${esc(n.part.pages.replace("-", "–"))}</span></h3><ul class="gs-nb">${nodeRow(n.part.book)}</ul>`;
    }
    const b = n.book;
    if (!b) return "";
    const pct = b.content ? Math.round((100 * b.done) / b.content) : 0;
    const rows = b.parts.filter((p) => p.status !== "skip").map((p) => {
      const pages = `p.${p.start}–${p.end}`;
      if (p.slug && G().node(p.slug)) {
        return `<li data-go="${esc(p.slug)}"><i class="gs-dot" style="background:${G().colorFor(G().node(p.slug))}"></i><span>${esc(p.title)}</span><small>${pages} · ${esc(p.status)}</small></li>`;
      }
      return `<li class="gs-part-todo" style="cursor:default;opacity:.55"><i class="gs-dot" style="background:transparent;border:1px solid var(--muted)"></i><span>${esc(p.title)}</span><small>${pages}</small></li>`;
    }).join("");
    return `<h3><span>Partition</span><span>${b.done}/${b.content} pp · ${pct}%</span></h3>
      <div class="gs-cover" style="height:6px;border-radius:3px;background:var(--line, rgba(127,127,127,.25));overflow:hidden;margin:4px 0 8px"><div style="height:100%;width:${pct}%;background:${G().colorFor(n)}"></div></div>
      <ul class="gs-nb">${rows}</ul>`;
  }

  // "See sources (N)": a concept's source pages (a collection's members) drawn on top of the
  // concept view; a second click hides them again.
  function seeSourcesButton(n) {
    if (!G().sourcesOf || G().layerOf(n) === "source") return "";
    const k = G().sourcesOf(n.id).length;
    if (!k) return "";
    const on = G().sourcesRevealed(n.id);
    return `<button type="button" class="gs-btn" data-see-sources="${esc(n.id)}" aria-pressed="${on}">${on ? "Hide" : "See"} sources (${k})</button>`;
  }

  // Raw files feeding this page (data layer on): each opens the table drawer at that row.
  function sourcesBlock(n) {
    const src = G().sources ? G().sources(n.id) : [];
    if (!src.length) return "";
    return `<h3><span>Raw files</span><span>${src.length}</span></h3><ul class="gs-nb">${src.slice(0, NB_MAX).map((r) =>
      `<li data-raw="${esc(r.path)}" data-format="${esc(r.format)}"><i class="gs-dot" style="background:var(--muted)"></i><span>${esc(r.path.split("/").slice(2).join("/"))}</span><small>${esc(r.disposition)}</small></li>`).join("")}</ul>`;
  }

  // The details panel shows the selection but opens only on request (node menu "Show details");
  // a click selects and nothing more. A right-click on empty space or Esc closes it.
  let detailsOpen = false;
  let lastNodes = [];
  function renderInspector(nodes) {
    const panel = $("gs-inspect");
    lastNodes = nodes;
    if (!nodes.length) detailsOpen = false;
    document.body.classList.toggle("gs-inspecting", detailsOpen && nodes.length > 0);
    if (!nodes.length) return;
    if (nodes.length > 1) {
      panel.innerHTML = `<div class="gs-inspect-head"><button type="button" class="gs-x" data-close aria-label="Close">×</button>
          <div class="gs-kicker">Selection</div><h2>${nodes.length} pages selected</h2>
          <div class="gs-actions"><button type="button" class="gs-btn" data-close>Clear selection</button></div></div>
        <div class="gs-inspect-body"><ul class="gs-nb">${nodes.slice(0, NB_MAX).map((n) => nodeRow(n.id)).join("")}</ul>
          ${nodes.length > NB_MAX ? `<p class="gs-more">…and ${nodes.length - NB_MAX} more</p>` : ""}</div>`;
      return;
    }
    const n = nodes[0];
    const nbs = G().neighbors(n.id).map((id) => G().node(id)).filter(Boolean)
      .sort((a, b) => (b.inDegree + b.outDegree) - (a.inDegree + a.outDegree));
    const kicker = [`<i class="gs-dot" style="background:${G().colorFor(n)}"></i>${esc(G().layerOf(n) ? `${G().layerOf(n)} · ${n.type}` : n.type)}`];
    if (n.depth) kicker.push(`<span class="gs-badge gs-badge-${esc(n.depth)}">${esc(n.depth)}</span>`);
    if (n.status) kicker.push(`<span class="gs-badge">${esc(n.status)}</span>`);
    if (n.year) kicker.push(`<span>${n.year}</span>`);
    if (n.part && n.part.pages) kicker.push(`<span>pp. ${esc(n.part.pages.replace("-", "–"))}</span>`);
    (n.areas || []).slice(0, 3).forEach((a) => kicker.push(`<span>#${esc(a)}</span>`));
    const props = Object.entries(n.properties || {}).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${propValue(k, v)}</dd>`).join("");
    panel.innerHTML = `<div class="gs-inspect-head"><button type="button" class="gs-x" data-close aria-label="Close">×</button>
        <div class="gs-kicker">${kicker.join("")}</div>
        <h2>${esc(n.title || n.id)}</h2>
        <div class="gs-actions">
          <button type="button" class="gs-btn gs-btn-primary" data-reader="${esc(n.id)}">Read</button>
          <a class="gs-btn" href="${G().exploreUrl(n.id)}">Explore →</a>
          <button type="button" class="gs-btn" data-centre="${esc(n.id)}">Centre</button>
          ${seeSourcesButton(n)}
          <a class="gs-btn" href="${G().obsidianUri(n.path || `wiki/${n.id}.md`)}">Obsidian</a>
        </div></div>
      <div class="gs-inspect-body">
        <p class="gs-preview${n.preview ? "" : " empty"}">${esc(n.preview || "No summary yet — this page is still a stub.")}</p>
        ${sourcesBlock(n)}
        ${bookBlock(n)}
        <h3><span>Connected pages</span><span>${n.inDegree}↘ ${n.outDegree}↗</span></h3>
        <ul class="gs-nb">${nbs.slice(0, NB_MAX).map((m) => nodeRow(m.id)).join("") || `<li style="cursor:default;color:var(--muted)">No links yet.</li>`}</ul>
        ${nbs.length > NB_MAX ? `<p class="gs-more">…and ${nbs.length - NB_MAX} more — open the page to see all.</p>` : ""}
        <details class="gs-props"><summary>Properties</summary><dl>${props}</dl></details>
        <p class="gs-hint">Double-click reads the page · <kbd>E</kbd> opens Explore · right-click empty space or <kbd>Esc</kbd> closes</p>
      </div>`;
  }

  // ---------- command palette ----------
  let items = [];
  let idx = 0;

  function commands() {
    const list = [];
    const add = (label, hint, run) => list.push({ kind: "cmd", label, hint, run });
    [["type", "type"], ["status", "status"], ["area", "theme / area"], ["degree", "link count"], ["none", "one colour"]]
      .forEach(([v, l]) => add(`Colour by ${l}`, "look", () => setControl("color-by", v)));
    [["connections", "connections"], ["in-degree", "inbound links"], ["out-degree", "outbound links"], ["uniform", "uniform"]]
      .forEach(([v, l]) => add(`Size by ${l}`, "look", () => setControl("size-by", v)));
    [["hover", "hovered node only"], ["visible", "all visible nodes"], ["selected", "selection and neighbours"], ["none", "hidden"]]
      .forEach(([v, l]) => add(`Labels: ${l}`, "labels", () => setControl("label-mode", v)));
    document.querySelectorAll("#label-type-chips .type-chip").forEach((chip) =>
      add(`Label every ${chip.textContent.trim()}`, chip.classList.contains("active") ? "on — toggle off" : "labels", () => chip.click()));
    add("Clear type labels", "labels", () => click("btn-clear-label-types"));
    document.querySelectorAll("#show-type-chips .type-chip").forEach((chip) =>
      add(`${chip.classList.contains("active") ? "Hide" : "Show"} every ${chip.textContent.trim()}`, "types", () => chip.click()));
    add("Show the concept layer (topics, ideas, questions)", "types", () => G().showTypes(G().overviewTypes()));
    add("Show all node types", "types", () => G().showTypes(null));
    if (window.DataLayer) {
      add("Toggle raw-file piles (data layer)", "raw", () => setControl("data-layer"));
      add("Open citation view", "raw", () => window.DataLayer.openCitations());
    }
    add("Toggle directional arrows", "look", () => setControl("show-arrows"));
    add("Toggle neighbourhood highlight on hover", "look", () => setControl("highlight-path"));
    add("Toggle magnetic pointer (experiment)", "look", () => setControl("magnet-pointer"));
    add("Magnetic style: soft edge, adaptive reach", "look", () => { setControl("magnet-pointer", true); setControl("magnet-variant", "soft"); });
    add("Magnetic style: crisp edge, fixed reach", "look", () => { setControl("magnet-pointer", true); setControl("magnet-variant", "crisp"); });
    add("Toggle label declutter (experiment)", "labels", () => setControl("declutter-labels"));
    add("Toggle live sync", "sync", () => setControl("live-sync"));
    add("Refresh graph now", "sync", () => click("btn-refresh"));
    add("Fit graph to view", "F", () => click("btn-fit"));
    add("Reset view", "view", () => click("btn-reset-view"));
    add("Reheat layout", "layout", () => click("btn-reheat"));
    Object.entries(FLYOUTS).forEach(([k, d]) => add(`Open panel: ${d.title}`, "panel", () => { if (openFly !== k) showFly(k); }));
    const presets = $("preset-select");
    if (presets) [...presets.options].forEach((o) => add(`Apply saved view: ${o.textContent}`, "preset", () => { presets.value = o.value; click("btn-apply-preset"); }));
    add("Save current view as preset", "preset", () => click("btn-save-preset"));
    add("Clear selection", "Esc", () => G().clear());
    add("Open Explore home", "go", () => { location.href = "/explore"; });
    return list;
  }

  function scorePage(n, q) {
    const t = (n.title || "").toLowerCase(), s = n.id.toLowerCase();
    if (t === q) return 100;
    if (t.startsWith(q)) return 80;
    if (t.includes(` ${q}`)) return 62;
    if (t.includes(q)) return 50;
    if (s.includes(q.replace(/\s+/g, "-"))) return 40;
    const terms = q.split(/\s+/);
    return terms.length > 1 && terms.every((x) => t.includes(x) || s.includes(x)) ? 30 : 0;
  }

  // Picked pages: a basket filled from the palette (Tab / click ☐ — the input clears for the next
  // name), shown all at once together with their neighbours, past every other filter.
  const picked = new Map();   // id → node, in pick order

  // Full-text hits from /api/explore/search for the current query, fetched after a short pause.
  let textHits = { q: "", hits: [] };
  let textTimer = null;
  let textAbort = null;
  function fetchTextHits(q) {
    clearTimeout(textTimer);
    if (textAbort) textAbort.abort();
    if (q.length < 2) { textHits = { q: "", hits: [] }; return; }
    textTimer = setTimeout(async () => {
      textAbort = new AbortController();
      try {
        const res = await fetch(`/api/explore/search?q=${encodeURIComponent(q)}&limit=12`, { signal: textAbort.signal });
        const data = await res.json();
        if (!res.ok) return;
        textHits = { q, hits: data.hits || [] };
        if ($("gs-cmd-input").value.trim().toLowerCase() === q && !$("gs-palette").classList.contains("hidden")) buildPalette({ refetch: false });
      } catch { /* aborted or offline: titles still match */ }
    }, 150);
  }

  let agentNote = "";
  function buildPalette({ refetch = true } = {}) {
    const raw = $("gs-cmd-input").value.trim();
    if (raw.startsWith("/")) { buildAgent(raw.slice(1).trim()); return; }
    agentNote = "";
    $("gs-cmd").classList.remove("gs-agent");
    const q = raw.toLowerCase();
    const cmds = commands();
    let pages = [];
    let texts = [];
    let matched = cmds;
    if (q) {
      pages = G().nodes().map((n) => [scorePage(n, q) + Math.min(n.inDegree || 0, 20) / 10, n])
        .filter(([s]) => s >= 30).sort((a, b) => b[0] - a[0]).slice(0, 7)
        .map(([, n]) => ({ kind: "page", section: "pages", node: n }));
      if (refetch) fetchTextHits(q);
      if (textHits.q === q) {
        const seen = new Set(pages.map((it) => it.node.id));
        texts = textHits.hits.filter((h) => !seen.has(h.id) && G().node(h.id)).slice(0, 6)
          .map((h) => ({ kind: "page", section: "text", node: G().node(h.id), snippet: h.snippet || "" }));
      }
      const terms = q.split(/\s+/);
      matched = cmds.filter((c) => terms.every((t) => c.label.toLowerCase().includes(t)));
      if (q.length >= 2) matched.push({ kind: "cmd", label: `Visualize pages mentioning “${raw}”`, hint: "+ neighbours", run: () => visualizeSearch(raw) });
      matched.push({ kind: "cmd", label: `Filter graph to “${raw}”`, hint: "filter", run: () => setControl("search-nodes", raw) });
    } else if ($("search-nodes") && $("search-nodes").value) {
      matched = [{ kind: "cmd", label: `Clear text filter “${$("search-nodes").value}”`, hint: "filter", run: () => setControl("search-nodes", "") }, ...cmds];
    }
    if (!q) matched = matched.slice(0, picked.size ? 6 : 9);
    matched = matched.map((c) => ({ ...c, section: q ? "cmds" : "try" }));
    const head = picked.size ? [{ kind: "show", section: "show", label: `Show ${picked.size} picked page${picked.size === 1 ? "" : "s"} on graph` }] : [];
    items = [...head, ...pages, ...texts, ...matched];
    idx = q ? head.length : 0;
    if (idx >= items.length) idx = 0;
    drawPalette();
  }

  // "/…" asks an agent — a placeholder until the agent is wired in.
  function buildAgent(question) {
    $("gs-cmd").classList.add("gs-agent");
    items = [{ kind: "agent", section: "agent", label: question }];
    idx = 0;
    const box = $("gs-palette");
    box.innerHTML = `<h5>Ask an agent</h5>
      <div class="gs-row gs-row-agent active" data-i="0" role="option"><span class="gs-glyph">✦</span><span class="gs-row-label">${question ? `Ask: “${esc(question)}”` : "Type a question after the slash…"}</span><small>coming soon</small></div>
      ${agentNote ? `<div class="gs-empty gs-agent-note">${esc(agentNote)}</div>` : ""}`;
    box.classList.remove("hidden");
  }

  function pickedBar() {
    if (!picked.size) return "";
    return `<div class="gs-picked">${[...picked.values()].map((n) =>
      `<span class="gs-pick-chip"><i class="gs-dot" style="background:${G().colorFor(n)}"></i><span class="gs-pick-name" title="${esc(n.title || n.id)}">${esc(n.title || n.id)}</span><button type="button" data-unpick="${esc(n.id)}" aria-label="Remove">×</button></span>`).join("")}
      <button type="button" class="gs-pick-clear" data-unpick-all>clear</button></div>`;
  }

  const SECTIONS = {
    pages: `Pages <span class="gs-h5-hint">Tab picks · ↵ shows · ⇧↵ reads</span>`,
    text: "Mentioned in the text",
    cmds: "Commands",
    try: "Try a command",
  };

  function drawPalette() {
    const box = $("gs-palette");
    let html = pickedBar();
    if (!items.length) html += `<div class="gs-empty">Nothing matches.</div>`;
    let section = null;
    items.forEach((it, i) => {
      if (it.section !== section) {
        section = it.section;
        if (SECTIONS[section]) html += `<h5>${SECTIONS[section]}</h5>`;
      }
      const act = i === idx ? " active" : "";
      if (it.kind === "show") {
        html += `<div class="gs-row gs-row-show${act}" data-i="${i}" role="option"><span class="gs-glyph">◎</span><span class="gs-row-label">${esc(it.label)}</span><small>↵ + neighbours</small></div>`;
      } else if (it.kind === "page") {
        const on = picked.has(it.node.id);
        const hidden = !G().isVisible(it.node.id);
        const snip = it.snippet ? `<span class="gs-row-snip">${esc(it.snippet)}</span>` : "";
        html += `<div class="gs-row${it.snippet ? " gs-row-text" : ""}${act}" data-i="${i}" role="option"><button type="button" class="gs-pick${on ? " on" : ""}" data-pick="${i}" aria-label="${on ? "Unpick" : "Pick"}" title="Pick (Tab)">${on ? "✓" : ""}</button><i class="gs-dot" style="background:${G().colorFor(it.node)}"></i><span class="gs-row-label">${esc(it.node.title || it.node.id)}${snip}</span>${hidden ? `<small class="gs-hidden-tag" title="Not in the current view — showing it brings it in">hidden</small>` : ""}<small>${esc((it.node.type || "page").replace(/-/g, " "))}</small></div>`;
      } else {
        html += `<div class="gs-row${act}" data-i="${i}" role="option"><span class="gs-glyph">›</span><span class="gs-row-label">${esc(it.label)}</span><small>${esc(it.hint || "")}</small></div>`;
      }
    });
    box.innerHTML = html;
    box.classList.remove("hidden");
  }

  function closePalette({ blur = true } = {}) {
    $("gs-palette").classList.add("hidden");
    $("gs-cmd").classList.remove("gs-agent");
    if (blur) { $("gs-cmd-input").value = ""; $("gs-cmd-input").blur(); }
  }

  function togglePick(node) {
    if (picked.has(node.id)) picked.delete(node.id); else picked.set(node.id, node);
    const input = $("gs-cmd-input");
    input.value = "";
    input.focus();
    buildPalette();
  }

  function showPicked(extra) {
    if (extra) picked.set(extra.id, extra);
    showView({ label: "picked", ids: [...picked.keys()] });
    picked.clear();
  }

  function runItem(it, shift) {
    if (!it) return;
    if (it.kind === "agent") {
      agentNote = it.label ? "The agent isn't wired in yet — this is a placeholder." : "";
      buildAgent(it.label);
      return;
    }
    if (it.kind === "show") {
      showPicked();
    } else if (it.kind === "page") {
      if (shift) { openReader(it.node.id); closePalette(); return; }
      if (picked.size) showPicked(it.node);          // a pick list is open: ↵ adds this page and shows them all
      else if (G().isVisible(it.node.id)) G().focus(it.node.id);
      else showView({ label: "picked", ids: [it.node.id], focus: it.node.id });   // filtered out: bring it in
    } else {
      it.run();
      setTimeout(renderLegend, 60);
    }
    closePalette();
  }

  // ---------- views: a set of pages + their neighbours, shown past every other filter ----------
  let view = null;   // { label: "picked"|"search", q, hits:Set }

  function showView({ label, ids, q = "", focus = null }) {
    const hits = new Set(ids.filter((id) => G().node(id)));
    if (view && label === "picked" && view.label === "picked") view.hits.forEach((id) => hits.add(id));   // picking more extends the view
    const shown = new Set(hits);
    hits.forEach((id) => G().neighbors(id).forEach((n) => shown.add(n)));
    const scope = $("scope-filter");
    if (scope) scope.value = "";
    view = hits.size ? { label, q, hits } : null;
    G().setExternalFilter(hits.size ? shown : null, { force: true });
    G().select([...hits], { additive: false });
    drawViewChip(view, hits.size ? "" : (q ? `No pages mention “${q}”.` : "No pages to show."));
    setTimeout(() => {
      if (focus) G().focus(focus, { zoom: false }); else click("btn-fit");
      renderLegend();
    }, 500);
  }

  async function visualizeSearch(q) {
    q = (q || "").trim();
    if (q.length < 2) return;
    let data;
    try {
      const res = await fetch(`/api/explore/search?q=${encodeURIComponent(q)}&limit=2000`);
      data = await res.json();
      if (!res.ok) throw new Error(data.error || res.status);
    } catch (e) { drawViewChip(null, `Search failed: ${e.message}`); return; }
    showView({ label: "search", q, ids: data.hits.map((h) => h.id) });
  }

  function clearView() {
    view = null;
    G().setExternalFilter(null);
    G().clear();
    drawViewChip(null);
    const u = new URL(location.href);
    if (u.searchParams.has("search") || u.searchParams.has("pages")) {
      u.searchParams.delete("search");
      u.searchParams.delete("pages");
      history.replaceState(null, "", u);
    }
    setTimeout(renderLegend, 60);
  }

  function drawViewChip(v, note = "") {
    let chip = $("gs-search-chip");
    if (!v && !note) { if (chip) chip.remove(); return; }
    if (!chip) {
      chip = document.createElement("div");
      chip.id = "gs-search-chip";
      chip.className = "gs-search-chip";
      $("gs-cmd-input").insertAdjacentElement("afterend", chip);
      chip.addEventListener("click", (e) => {
        if (e.target.closest("[data-clear]")) { if (view) clearView(); else chip.remove(); }
        else if (e.target.closest("[data-more]")) { const i = $("gs-cmd-input"); i.focus(); i.select(); }
      });
    }
    const n = v ? v.hits.size : 0;
    const what = !v ? "" : v.label === "search"
      ? `<b>${n}</b> page${n === 1 ? "" : "s"} mentioning “${esc(v.q)}”`
      : `<b>${n}</b> picked page${n === 1 ? "" : "s"}`;
    chip.innerHTML = v
      ? `<span>${what} <span class="gs-chip-sub">+ neighbours</span></span>${v.label === "picked" ? `<button type="button" class="gs-chip-more" data-more title="Pick more pages to add">+ add</button>` : ""}<button type="button" data-clear aria-label="Clear view">×</button>`
      : `<span>${esc(note)}</span><button type="button" data-clear aria-label="Dismiss">×</button>`;
  }

  function viewFromUrl() {
    const p = new URLSearchParams(location.search);
    if (p.get("search")) visualizeSearch(p.get("search"));
    else if (p.get("pages")) showView({ label: "picked", ids: p.get("pages").split(",").map((s) => s.trim()).filter(Boolean) });
  }

  function move(d) {
    if (!items.length) return;
    idx = (idx + d + items.length) % items.length;
    const rows = $("gs-palette").querySelectorAll(".gs-row");
    rows.forEach((r) => r.classList.toggle("active", Number(r.dataset.i) === idx));
    const cur = $("gs-palette").querySelector(".gs-row.active");
    if (cur) cur.scrollIntoView({ block: "nearest" });
  }

  // ---------- side reader: the Explore page of a node, next to the graph ----------
  const READER_W_KEY = "thesis-wiki-graph-reader-width";
  let reader = null;
  let readerId = null;

  function buildReader() {
    if (reader) return reader;
    reader = document.createElement("aside");
    reader.id = "gs-reader";
    reader.className = "gs-reader hidden";
    reader.setAttribute("aria-label", "Page reader");
    reader.innerHTML = `<div class="gs-reader-grip" title="Drag to resize"></div>
      <header class="gs-reader-head"><span class="gs-reader-title"></span>
        <a class="gs-btn" data-full>Open full page ↗</a>
        <button type="button" class="gs-x" data-close aria-label="Close reader">×</button></header>
      <iframe title="Page reader"></iframe>`;
    document.body.appendChild(reader);
    try {
      const w = Number(localStorage.getItem(READER_W_KEY));
      if (w >= 320) document.body.style.setProperty("--reader-w", `${w}px`);
    } catch { /* no storage: default width */ }
    reader.querySelector("[data-close]").addEventListener("click", closeReader);
    const grip = reader.querySelector(".gs-reader-grip");
    grip.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      grip.setPointerCapture(e.pointerId);
      reader.classList.add("resizing");
      const move = (ev) => {
        const w = Math.max(320, Math.min(window.innerWidth - 160, window.innerWidth - ev.clientX));
        document.body.style.setProperty("--reader-w", `${w}px`);
      };
      const up = () => {
        grip.removeEventListener("pointermove", move);
        reader.classList.remove("resizing");
        try { localStorage.setItem(READER_W_KEY, String(Math.round(reader.getBoundingClientRect().width))); } catch { /* ignore */ }
      };
      grip.addEventListener("pointermove", move);
      grip.addEventListener("pointerup", up, { once: true });
    });
    return reader;
  }

  function openReader(id) {
    const n = G() && G().node(id);
    if (!n) return;
    const r = buildReader();
    const frame = r.querySelector("iframe");
    const hash = `#/p/${encodeURIComponent(id)}`;
    r.querySelector(".gs-reader-title").textContent = n.title || id;
    r.querySelector("[data-full]").href = G().exploreUrl(id);
    let same = false;
    try { same = !!frame.contentWindow && frame.contentWindow.location.pathname === "/explore"; } catch { /* not loaded */ }
    if (same) frame.contentWindow.location.hash = hash;   // already open: navigate without a reload
    else frame.src = `/explore?embed=1${hash}`;
    readerId = id;
    r.classList.remove("hidden");
    document.body.classList.add("gs-reading");
  }

  function closeReader() {
    if (!reader) return;
    reader.classList.add("hidden");
    document.body.classList.remove("gs-reading");
    readerId = null;
  }

  window.SideReader = { open: openReader, close: closeReader, current: () => readerId };
  window.GraphDetails = {
    open: () => { detailsOpen = true; renderInspector(lastNodes); },
    close: () => { detailsOpen = false; document.body.classList.remove("gs-inspecting"); },
    isOpen: () => detailsOpen && document.body.classList.contains("gs-inspecting"),
  };

  // ---------- wiring ----------
  function bind() {
    const input = $("gs-cmd-input");
    input.addEventListener("focus", buildPalette);
    input.addEventListener("input", buildPalette);
    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
      else if (e.key === "Enter") { e.preventDefault(); runItem(items[idx], e.shiftKey); }
      else if (e.key === "Tab" && items[idx] && items[idx].kind === "page") { e.preventDefault(); togglePick(items[idx].node); }
      else if (e.key === "Escape") { e.preventDefault(); closePalette(); }
    });
    $("gs-palette").addEventListener("mousedown", (e) => {
      const un = e.target.closest("[data-unpick], [data-unpick-all]");
      if (un) {
        e.preventDefault();
        if (un.hasAttribute("data-unpick-all")) picked.clear(); else picked.delete(un.dataset.unpick);
        buildPalette();
        return;
      }
      const pick = e.target.closest("[data-pick]");
      if (pick) { e.preventDefault(); togglePick(items[Number(pick.dataset.pick)].node); return; }
      const row = e.target.closest(".gs-row");
      if (!row) return;
      e.preventDefault();
      runItem(items[Number(row.dataset.i)], e.shiftKey);
    });

    $("gs-dock").addEventListener("click", (e) => {
      const b = e.target.closest(".gs-dock-btn");
      if (!b) return;
      if (b.dataset.fly) showFly(b.dataset.fly);
      else if (b.id === "gs-dock-search") { input.value = ""; input.focus(); }
      else if (b.id === "gs-dock-fit") click("btn-fit");
      else if (b.id === "gs-dock-piles") setControl("data-layer");
      else if (b.id === "gs-dock-cite" && window.DataLayer) window.DataLayer.openCitations();
    });
    $("gs-fly-close").addEventListener("click", closeFly);

    $("gs-legend").addEventListener("click", (e) => {
      if (e.target.id === "gs-legend-change") { if (openFly !== "look") showFly("look"); return; }
      if (e.target.id === "gs-legend-all") { G().showTypes(null); return; }
      if (e.target.id === "gs-legend-overview") { G().showTypes(G().overviewTypes()); return; }
      const row = e.target.closest("[data-type]");
      if (!row) return;
      if (e.target.closest("[data-vis]")) { G().toggleType(row.dataset.type); return; }
      if (!e.target.closest("[data-aa]")) return;
      const chip = document.querySelector(`#label-type-chips .type-chip[data-type="${row.dataset.type}"]`);
      if (chip) { chip.click(); setTimeout(renderLegend, 30); }
    });

    $("gs-inspect").addEventListener("click", (e) => {
      if (e.target.closest("a")) return;
      if (e.target.closest("[data-close]")) { window.GraphDetails.close(); return; }
      const rd = e.target.closest("[data-reader]");
      if (rd) { openReader(rd.dataset.reader); return; }
      const c = e.target.closest("[data-centre]");
      if (c) { G().focus(c.dataset.centre); return; }
      const ss = e.target.closest("[data-see-sources]");
      if (ss) {
        const id = ss.dataset.seeSources;
        G().seeSources(id, !G().sourcesRevealed(id));
        const n = G().node(id);
        if (n) renderInspector([n]);
        return;
      }
      const go = e.target.closest("[data-go]");
      if (go) G().focus(go.dataset.go, { zoom: false });
    });

    document.addEventListener("mousedown", (e) => {
      if (!e.target.closest("#gs-cmd")) closePalette({ blur: false });
    });
    // Space opens the search, "/" the ask-an-agent bar; Esc closes the reader, then a flyout.
    document.addEventListener("keydown", (e) => {
      if (e.target.matches("input, textarea, select") || e.metaKey || e.ctrlKey || e.altKey) return;
      const onButton = e.target.matches("button, a, summary");
      if (e.key === " " && !onButton) { e.preventDefault(); input.value = ""; input.focus(); }
      else if (e.key === "/") { e.preventDefault(); input.focus(); input.value = "/"; buildPalette(); }
      else if (e.key === "Escape" && readerId) { e.stopImmediatePropagation(); closeReader(); }
      else if (e.key === "Escape" && detailsOpen) { e.stopImmediatePropagation(); window.GraphDetails.close(); }
      else if (e.key === "Escape" && openFly) closeFly();
    }, true);

    document.addEventListener("graph:selection", (e) => renderInspector(e.detail.nodes || []));
    document.addEventListener("graph:changed", () => setTimeout(renderLegend, 30));
    document.addEventListener("graph:ready", () => { renderLegend(); viewFromUrl(); });
    document.addEventListener("change", (e) => {   // a scope replaces the view's filter
      if (e.target.id === "scope-filter" && view) { view = null; drawViewChip(null); }
    });
    document.addEventListener("themechange", () => setTimeout(renderLegend, 30));
    ["color-by", "search-nodes"].forEach((id) => { const c = $(id); if (c) c.addEventListener("change", () => setTimeout(renderLegend, 60)); });
  }

  // Raw piles + citations are local-only (no raw data on the shared site).
  function syncRawButtons() {
    const box = $("data-layer");
    const local = !!box && !window.KB_STATIC;
    ["gs-dock-piles", "gs-dock-cite"].forEach((id) => { const b = $(id); if (b) b.hidden = !local; });
    const piles = $("gs-dock-piles");
    if (piles && box) { piles.classList.toggle("active", box.checked); piles.setAttribute("aria-pressed", String(box.checked)); }
  }

  document.addEventListener("DOMContentLoaded", () => {
    adoptLegacy();
    bind();
    syncRawButtons();
    const box = $("data-layer");
    if (box) box.addEventListener("change", syncRawButtons);
    if (window.WikiGraph && window.WikiGraph.nodes().length) renderLegend();
  });
})();
