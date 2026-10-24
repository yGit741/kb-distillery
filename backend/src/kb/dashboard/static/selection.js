/* Scopes on the graph: a selection layer (click / cmd-click / shift-path; box + lasso are in graph-mouse.js), a floating action bar,
   scope drafts (raw files collected from the selection, persisted in localStorage) and the Scope filter.
   graph.js owns the canvas; this file talks to it through window.WikiGraph and the graph:* events. */
(function () {
  "use strict";
  const DRAFTS_KEY = "thesis-wiki-scope-drafts";
  const OLD_KEY = "thesis-wiki-scope-basket";   // legacy single basket, migrated once into a draft
  const STATIC = !!window.KB_STATIC;
  const isSource = (n) => !!n && n.layer === "source";     // graph nodes carry their schema layer
  const esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const byId = (id) => document.getElementById(id);
  const G = () => window.WikiGraph;

  // ---------------------------------------------------------------- draft store
  let store = { active: "", drafts: {} };   // drafts[key] = {slug, title, isNew, rows}
  let rows = [];                         // rows of the active draft [{path, format, disposition, slug, page_type, digestion, collection, year}]
  let highlight = false;
  let projection = null;                 // Set of node ids kept bright while highlight is on

  const kebab = (t) => String(t || "").toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  const slugOf = (title) => { const k = kebab(title); return k ? (k.startsWith("scope-") ? k : "scope-" + k) : ""; };
  const draft = () => store.drafts[store.active] || null;
  function syncRows() { const d = draft(); rows = d ? d.rows : []; }
  function loadDrafts() {
    try {
      const raw = localStorage.getItem(DRAFTS_KEY);
      const d = raw ? JSON.parse(raw) : null;
      if (d && d.drafts && typeof d.drafts === "object") store = { active: d.active || "", drafts: d.drafts };
    } catch (_) { store = { active: "", drafts: {} }; }
    try {
      const old = localStorage.getItem(OLD_KEY);
      if (old !== null) {
        const o = JSON.parse(old);
        const list = o && Array.isArray(o.rows) ? o.rows : [];
        if (list.length && !store.drafts["scope-untitled-scope"]) {
          store.drafts["scope-untitled-scope"] = { slug: "scope-untitled-scope", title: "Untitled scope", isNew: true, rows: list };
          if (!store.active) store.active = "scope-untitled-scope";
        }
        localStorage.removeItem(OLD_KEY);
        saveDrafts();
      }
    } catch (_) { /* ignore */ }
    if (store.active && !store.drafts[store.active]) store.active = "";
    syncRows();
  }
  function saveDrafts() {
    try { localStorage.setItem(DRAFTS_KEY, JSON.stringify(store)); } catch (_) { /* storage unavailable */ }
  }
  function changed() {
    saveDrafts();
    syncRows();
    projection = null;
    renderBasket();
    if (G()) G().redraw();
  }
  function ensureDraft() {
    if (!draft()) {
      const key = "scope-untitled-scope";
      if (!store.drafts[key]) store.drafts[key] = { slug: key, title: "Untitled scope", isNew: true, rows: [] };
      store.active = key;
      syncRows();
    }
    return draft();
  }
  function pushRows(d, list) {
    const have = new Set(d.rows.map((r) => r.path));
    let added = 0;
    for (const r of list || []) {
      if (!r || !r.path || have.has(r.path)) continue;
      have.add(r.path);
      d.rows.push(r);
      added += 1;
    }
    return added;
  }
  function addRows(list) {
    const added = pushRows(ensureDraft(), list);
    changed();
    return added;
  }
  // Target an existing scope (loading its rows) or a new one, make it active, then add rows.
  async function addToTarget(target, list) {
    let d = store.drafts[target.slug];
    if (!d) {
      d = { slug: target.slug, title: target.title, isNew: !!target.isNew, rows: [] };
      if (!target.isNew) {
        const res = await fetch("/api/scope?slug=" + encodeURIComponent(target.slug));
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || res.status);
        d.rows = data.rows || [];
      }
      store.drafts[target.slug] = d;
    }
    store.active = target.slug;
    const added = pushRows(d, list);
    changed();
    return { added, draft: d };
  }
  function removePath(path) { const d = draft(); if (d) d.rows = d.rows.filter((r) => r.path !== path); changed(); }
  function discardDraft() { if (store.active) delete store.drafts[store.active]; store.active = ""; changed(); }
  function clearBasket() { discardDraft(); }

  function toast(msg) {
    let t = byId("sel-toast");
    if (!t) { t = document.createElement("div"); t.id = "sel-toast"; t.className = "sel-toast"; document.body.appendChild(t); }
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => t.classList.remove("show"), 3200);
  }

  async function resolve(ids) {
    const res = await fetch("/api/scope/resolve", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nodes: ids }) });
    let data = {};
    try { data = await res.json(); } catch (_) { /* non-JSON */ }
    if (!res.ok) throw new Error(data.error || "resolve failed (" + res.status + ")");
    return data.rows || [];
  }

  // ---------------------------------------------------------------- draft projection (client side)
  function computeProjection() {
    const g = G();
    const set = new Set();
    if (!g || !rows.length) return set;
    const paths = new Set(rows.map((r) => r.path));
    for (const r of rows) {
      if (r.slug) set.add(r.slug);
      const col = Array.isArray(r.collection) ? r.collection : String(r.collection || "").split(",");
      col.map((c) => c.trim()).filter(Boolean).forEach((c) => set.add(c));
    }
    for (const n of g.nodes()) {
      const raw = n.properties && n.properties.raw;
      const list = Array.isArray(raw) ? raw : raw ? [raw] : [];
      if (list.some((p) => paths.has(p))) set.add(n.id);
    }
    const snap = g.rawSnapshot();
    for (const l of (snap && snap.raw_links) || []) {
      if (l.kind === "source" && paths.has(String(l.source).replace(/^raw:/, ""))) set.add(l.target);
    }
    return set;
  }
  window.Selection = {
    dims(node) {
      if (!highlight || !rows.length) return false;
      if (!projection) projection = computeProjection();
      return !projection.has(node.id);
    },
    onNodeClick,
  };

  // ---------------------------------------------------------------- selection helpers
  let anchor = null;
  function selIds() { return G() ? G().selectedIds().filter((i) => !String(i).startsWith("pile:")) : []; }
  function adjacency() {
    const adj = new Map();
    for (const l of G().visibleLinks()) {
      if (String(l.kind || "").startsWith("pile")) continue;
      if (!adj.has(l.source)) adj.set(l.source, new Set());
      if (!adj.has(l.target)) adj.set(l.target, new Set());
      adj.get(l.source).add(l.target);
      adj.get(l.target).add(l.source);
    }
    return adj;
  }
  function shortestPath(from, to) {
    const adj = adjacency();
    const prev = new Map([[from, null]]);
    const queue = [from];
    while (queue.length) {
      const cur = queue.shift();
      if (cur === to) break;
      for (const nx of adj.get(cur) || []) if (!prev.has(nx)) { prev.set(nx, cur); queue.push(nx); }
    }
    if (!prev.has(to)) return [];
    const path = [];
    for (let c = to; c !== null; c = prev.get(c)) path.push(c);
    return path;
  }
  function onNodeClick(node, ev) {
    const g = G();
    if (ev.shiftKey && anchor && anchor !== node.id && g.node(anchor)) {
      const path = shortestPath(anchor, node.id);
      if (path.length) { g.select(path, { additive: true }); toast("Added a path of " + path.length + " nodes"); }
      else { g.select([node.id], { additive: true }); toast("No path in the visible graph"); }
      anchor = node.id;
      return true;
    }
    if (ev.ctrlKey || ev.metaKey) {
      const cur = new Set(g.selectedIds());
      if (cur.has(node.id)) { cur.delete(node.id); g.select([...cur], { additive: false }); }
      else g.select([node.id], { additive: true });
      anchor = node.id;
      return true;
    }
    if (ev.shiftKey) { g.select([node.id], { additive: true }); anchor = node.id; return true; }
    anchor = node.id;
    return false;                                           // plain click: graph.js selects it and opens the panel
  }
  function addIds(ids) { if (ids.length) G().select(ids, { additive: true }); }
  function neighbours(ids, filterFn) {
    const adj = adjacency();
    const out = new Set();
    for (const id of ids) for (const nx of adj.get(id) || []) if (!ids.includes(nx) && (!filterFn || filterFn(G().node(nx)))) out.add(nx);
    return [...out];
  }

  // ---------------------------------------------------------------- floating bar
  let bar = null;
  const BTN = (id, label, title, cls) => `<button type="button" class="sel-btn ${cls || ""}" id="${id}" title="${esc(title)}">${label}</button>`;
  function buildBar() {
    bar = document.createElement("div");
    bar.className = "sel-bar hidden";
    bar.id = "sel-bar";
    bar.innerHTML = `<span class="sel-count" id="sel-count">0 selected</span>
      ${BTN("sel-nb", "+ neighbours", "Add everything one hop away over the visible links (repeatable)")}
      ${BTN("sel-mem", "+ members", "For hubs, themes and concepts: add the pages linked to them")}
      ${STATIC ? "" : BTN("sel-src", "+ sources", "Preview the raw files under the selection")}
      ${BTN("sel-cite", "+ citations", "Add papers that cite or are cited by the selection")}
      <select class="sel-select" id="sel-type" title="Keep only one type"><option value="">only type…</option></select>
      ${BTN("sel-clear", "clear", "Clear selection (Esc)")}
      ${STATIC ? "" : BTN("sel-add", "Add to scope ▾", "Resolve the selection to raw files and add them to a scope", "primary")}
      <div class="sel-pop hidden" id="sel-pop"></div>`;
    document.body.appendChild(bar);
    byId("sel-nb").onclick = () => { addIds(neighbours(selIds())); };
    byId("sel-mem").onclick = () => {
      const ids = selIds();
      const hubs = ids.filter((i) => { const n = G().node(i); return n && !isSource(n); });
      addIds(neighbours(hubs, isSource));
    };
    byId("sel-cite").onclick = addCitations;
    byId("sel-type").onchange = (e) => {
      const t = e.target.value;
      if (!t) return;
      G().select(selIds().filter((i) => { const n = G().node(i); return n && n.type === t; }), { additive: false });
    };
    byId("sel-clear").onclick = () => G().clear();
    if (!STATIC) {
      byId("sel-add").onclick = openTargetMenu;
      byId("sel-src").onclick = previewSources;
    }
  }
  function updateBar() {
    if (!bar) return;
    const ids = selIds();
    bar.classList.toggle("hidden", !ids.length);
    byId("sel-count").textContent = ids.length + " selected";
    const types = [...new Set(ids.map((i) => (G().node(i) || {}).type).filter(Boolean))];
    const sel = byId("sel-type");
    sel.innerHTML = `<option value="">only type…</option>` + (types.length > 1 ? types.map((t) => `<option>${esc(t)}</option>`).join("") : "");
    sel.disabled = types.length < 2;
    if (!ids.length) hidePop();
  }
  function hidePop() { const p = byId("sel-pop"); if (p) p.classList.add("hidden"); }

  let citations;
  async function addCitations() {
    if (citations === undefined) {
      try { citations = await (await fetch("/api/citations")).json(); } catch (_) { citations = { missing: true }; }
    }
    if (!citations || citations.missing || !citations.links) { toast("No citation data yet"); return; }
    const ids = new Set(selIds());
    const out = new Set();
    for (const l of citations.links) {
      const s = l.source.id || l.source, t = l.target.id || l.target;
      if (ids.has(s) && G().node(t)) out.add(t);
      if (ids.has(t) && G().node(s)) out.add(s);
    }
    if (!out.size) toast("No citation neighbours on the canvas");
    addIds([...out]);
  }

  async function openTargetMenu() {
    const ids = selIds();
    if (!ids.length) return;
    const pop = byId("sel-pop");
    if (!pop.classList.contains("hidden") && pop.dataset.kind === "target") { hidePop(); return; }
    pop.dataset.kind = "target";
    pop.classList.remove("hidden");
    let list = [];
    try { const res = await fetch("/api/scopes"); if (res.ok) list = (await res.json()).scopes || []; } catch (_) { /* none */ }
    const known = new Set(list.map((s) => s.slug));
    const drafts = Object.values(store.drafts).filter((d) => d.isNew && !known.has(d.slug));
    const item = (slug, title, extra) => `<li><button type="button" class="sel-menu-item" data-slug="${esc(slug)}" data-title="${esc(title)}">${esc(title)} <span class="sel-note">${extra}</span></button></li>`;
    pop.innerHTML = `<p class="sel-note">Add ${ids.length} node${ids.length === 1 ? "" : "s"} to…</p>
      <ul class="sel-menu">${drafts.map((d) => item(d.slug, d.title, "draft").replace("<li>", `<li data-new="1">`)).join("")}${list.map((s) => item(s.slug, s.title || s.slug, (s.files ?? 0) + " files")).join("")}
      <li><button type="button" class="sel-menu-item" id="sel-new-scope">New scope…</button></li></ul>
      <form class="sel-newform hidden" id="sel-newform"><input type="text" id="sel-new-name" placeholder="Scope name" autocomplete="off" aria-label="Scope name">
        <button type="submit" class="sel-btn primary">Create</button></form>`;
    const run = async (target) => {
      try {
        const rowsList = await resolve(ids);
        const { added, draft: d } = await addToTarget(target, rowsList);
        toast(`${d.title}: ${added} new file${added === 1 ? "" : "s"} (${rowsList.length} resolved)`);
        hidePop();
        openBasket(true);
      } catch (e) { toast("Could not add: " + e.message); }
    };
    pop.querySelectorAll("[data-slug]").forEach((b) => {
      b.onclick = () => run({ slug: b.dataset.slug, title: b.dataset.title, isNew: !!b.closest("[data-new]") });
    });
    const form = byId("sel-newform");
    byId("sel-new-scope").onclick = () => { form.classList.remove("hidden"); byId("sel-new-name").focus(); };
    form.onsubmit = (e) => {
      e.preventDefault();
      const title = byId("sel-new-name").value.trim();
      const slug = slugOf(title);
      if (!slug) { toast("Give the scope a name"); return; }
      const existing = list.find((s) => s.slug === slug);
      run({ slug, title: existing ? existing.title || slug : title, isNew: !existing });
    };
  }
  async function previewSources() {
    const ids = selIds();
    const pop = byId("sel-pop");
    pop.dataset.kind = "sources";
    pop.classList.remove("hidden");
    pop.innerHTML = `<p class="sel-note">Resolving…</p>`;
    try {
      const list = await resolve(ids);
      const fresh = list.filter((r) => !rows.some((b) => b.path === r.path));
      pop.innerHTML = `<p class="sel-note"><strong>${list.length}</strong> raw files under the selection · ${list.filter((r) => r.disposition === "queued").length} undigested · ${fresh.length} not in the draft</p>
        <ul class="sel-list">${list.slice(0, 14).map((r) => `<li><span class="sel-badge ${esc(r.disposition)}">${esc(r.disposition)}</span> ${esc(r.path.split("/").slice(2).join("/"))}</li>`).join("")}${list.length > 14 ? `<li class="sel-note">…and ${list.length - 14} more</li>` : ""}</ul>
        <button type="button" class="sel-btn primary" id="sel-pop-add">Add ${fresh.length} to scope draft</button>`;
      byId("sel-pop-add").onclick = () => { addRows(list); hidePop(); openBasket(true); };
    } catch (e) { pop.innerHTML = `<p class="sel-note">Could not resolve: ${esc(e.message)}</p>`; }
  }

  // ---------------------------------------------------------------- scope draft panel
  let bkChip = null, bkPanel = null;
  function buildBasket() {
    if (STATIC) return;
    bkChip = document.createElement("button");
    bkChip.type = "button"; bkChip.id = "bk-chip"; bkChip.className = "bk-chip";
    bkChip.addEventListener("click", () => openBasket(bkPanel.classList.contains("hidden")));
    bkPanel = document.createElement("aside");
    bkPanel.id = "bk-panel"; bkPanel.className = "bk-panel hidden"; bkPanel.setAttribute("aria-label", "Scope draft");
    document.body.append(bkChip, bkPanel);
    bkPanel.addEventListener("click", (e) => {
      const rm = e.target.closest("[data-rm]");
      if (rm) { removePath(rm.dataset.rm); return; }
      const pg = e.target.closest("[data-page]");
      if (pg && G()) { e.preventDefault(); G().focus(pg.dataset.page); return; }
      const act = e.target.closest("[data-act]");
      if (!act) return;
      if (act.dataset.act === "save") location.href = "/scopes?draft=" + encodeURIComponent(store.active);
      else if (act.dataset.act === "clear") clearBasket();
      else if (act.dataset.act === "close") openBasket(false);
    });
    bkPanel.addEventListener("change", (e) => {
      if (e.target.id === "bk-hl") { highlight = e.target.checked; projection = null; if (G()) G().redraw(); }
    });
    window.addEventListener("storage", (e) => { if (e.key === DRAFTS_KEY) { loadDrafts(); projection = null; renderBasket(); } });
    renderBasket();
  }
  function openBasket(open) {
    if (!bkPanel) return;
    bkPanel.classList.toggle("hidden", !open);
    renderBasket();
  }
  function stats(list) {
    const dig = list.filter((r) => r.disposition === "source").length;
    return { n: list.length, dig, pct: list.length ? Math.round((100 * dig) / list.length) : 0 };
  }
  function rowHtml(r) {
    return `<li class="${r.disposition === "queued" ? "undigested" : ""}">
          <span class="sel-badge ${esc(r.disposition)}">${esc(r.disposition)}</span>
          <span class="bk-name" title="${esc(r.path.split("/").slice(2).join("/"))}">${esc(r.path.split("/").slice(2).join("/"))}</span>
          ${r.slug ? `<a href="#" data-page="${esc(r.slug)}" title="Focus the page">${esc(r.slug)}</a>` : ""}
          <button type="button" class="sel-x" data-rm="${esc(r.path)}" aria-label="Remove">×</button></li>`;
  }
  function renderBasket() {
    if (!bkChip) return;
    const st = stats(rows);
    const d = draft();
    const nm = d ? (d.title.length > 18 ? d.title.slice(0, 17) + "…" : d.title) : "Scope draft";
    bkChip.textContent = nm + " · " + st.n;
    bkChip.title = d ? "Scope: " + d.title + " (unsaved)" : "No scope draft yet";
    bkChip.classList.toggle("has", st.n > 0);
    if (bkPanel.classList.contains("hidden")) return;
    const groups = new Map();
    rows.forEach((r) => { const k = r.format || "other"; if (!groups.has(k)) groups.set(k, []); groups.get(k).push(r); });
    const body = st.n
      ? [...groups].map(([f, list]) => `<details open><summary>${esc(f)} <span class="sel-note">${list.length}</span></summary><ul class="sel-list">${list.map(rowHtml).join("")}</ul></details>`).join("")
      : `<p class="sel-note">Empty. Select nodes on the canvas and press Add to scope.</p>`;
    bkPanel.innerHTML = `<header><strong class="bk-title" title="${esc(d ? d.title : "")}">${d ? "Scope: " + esc(d.title) : "Scope draft"}</strong>${d ? `<span class="bk-tag">unsaved</span>` : ""}
        <span class="sel-note">${st.n} files · ${st.dig} digested · ${st.pct}%</span>
        <button type="button" class="sel-x" data-act="close" aria-label="Close panel">×</button></header>
      <label class="sel-check"><input type="checkbox" id="bk-hl" ${highlight ? "checked" : ""}> highlight scope on canvas</label>
      <div class="bk-body">${body}</div>
      <footer><button type="button" class="sel-btn primary" data-act="save" ${st.n ? "" : "disabled"}>Save scope…</button>
        <button type="button" class="sel-btn" data-act="clear" ${d ? "" : "disabled"}>Discard draft</button></footer>`;
  }
  window.ScopeDraft = window.ScopeBasket = { addRows, paths: () => rows.map((r) => r.path), rows: () => rows.slice(), clear: discardDraft, open: openBasket };

  // ---------------------------------------------------------------- scope filter + search helpers
  async function buildScopeFilter() {
    const search = byId("search-nodes");
    if (!search || STATIC || byId("scope-filter")) return;
    let list = [];
    try {
      const res = await fetch("/api/scopes");
      if (res.ok) list = (await res.json()).scopes || [];
    } catch (_) { /* backend without scopes */ }
    const wrap = document.createElement("label");
    wrap.className = "field sel-scope-field";
    wrap.innerHTML = `<span>Scope</span><select id="scope-filter"><option value="">All</option>${list.map((s) => `<option value="${esc(s.slug)}">${esc(s.title || s.slug)} (${s.files ?? 0})</option>`).join("")}</select>`;
    search.parentNode.insertBefore(wrap, search);
    const btn = document.createElement("button");
    btn.type = "button"; btn.className = "ghost-btn"; btn.id = "btn-select-results"; btn.textContent = "Select all results";
    search.insertAdjacentElement("afterend", btn);
    btn.addEventListener("click", () => {
      const q = search.value.trim().toLowerCase();
      const hits = G().visibleNodes().filter((n) => !q || (n.id + " " + (n.title || "")).toLowerCase().includes(q)).map((n) => n.id);
      G().select(hits, { additive: false });
      toast(hits.length + " nodes selected");
    });
    const sel = byId("scope-filter");
    sel.addEventListener("change", () => applyScope(sel.value));
    const want = new URLSearchParams(location.search).get("scope");
    if (want) {
      if (!list.some((s) => s.slug === want)) sel.insertAdjacentHTML("beforeend", `<option value="${esc(want)}">${esc(want)}</option>`);
      sel.value = want;
      applyScope(want);
    }
  }
  async function applyScope(slug) {
    if (!slug) { G().setExternalFilter(null); return; }
    try {
      const res = await fetch("/api/scope?slug=" + encodeURIComponent(slug));
      const d = await res.json();
      if (!res.ok) throw new Error(d.error || res.status);
      const p = d.projection || {};
      G().setExternalFilter(new Set([slug, ...(p.hop0 || []), ...(p.hop1 || [])]));
      toast("Scope " + slug + ": " + (p.hop0 || []).length + " pages + " + (p.hop1 || []).length + " neighbours");
    } catch (e) { toast("Could not load scope: " + e.message); }
  }

  // ---------------------------------------------------------------- boot
  function boot() {
    loadDrafts();
    buildBar();
    buildBasket();
    document.addEventListener("graph:selection", updateBar);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") hidePop(); });
    document.addEventListener("graph:ready", buildScopeFilter);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
