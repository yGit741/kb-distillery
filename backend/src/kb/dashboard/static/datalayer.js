/* Data layer UI: per-format drawer (table + preview + actions) and the citation view.
   Driven by graph.js events (datalayer:pile / datalayer:toggle) and the inspector's Sources list.
   Absent on the shared static site (graph.js hides the toggle when window.KB_STATIC is set). */
(function () {
  "use strict";
  if (window.KB_STATIC) return;

  const ROW_CAP = 400;
  let CHIPS = [];             // corpus dispositions, from /api/schema (backend/src/kb/core/schema.py DISPOSITIONS)
  fetch("/api/schema").then((r) => r.json())
    .then((s) => { CHIPS = (s.dispositions || []).filter((d) => d !== "sidecar"); }).catch(() => {});
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  let fmt = null;
  let data = null;            // {columns, rows}
  let sort = { key: null, dir: 1 };
  let text = "";
  let active = new Set();     // disposition chips; empty = all
  let selected = null;
  let citeGraph = null;
  let citeOn = false;
  let drawer = null;

  function build() {
    if (drawer) return;
    drawer = document.createElement("section");
    drawer.className = "dl-drawer";
    drawer.id = "dl-drawer";
    drawer.setAttribute("aria-label", "Raw data table");
    drawer.innerHTML = `<div class="dl-grip" id="dl-grip" title="Drag to resize"></div>
      <header class="dl-head"><h2 id="dl-title"></h2><span class="dl-count" id="dl-count"></span>
        <input type="search" id="dl-filter" placeholder="Filter rows…" autocomplete="off">
        <span id="dl-chips"></span>
        <button type="button" class="dl-btn" id="dl-cite-toggle" hidden>Citation view</button>
        <button type="button" class="dl-x" id="dl-close" aria-label="Close (Esc)">×</button></header>
      <div class="dl-body"><div class="dl-tablewrap" id="dl-tablewrap"></div>
        <div class="dl-cite" id="dl-cite" hidden></div>
        <aside class="dl-side" id="dl-side" hidden></aside></div>`;
    document.body.appendChild(drawer);
    const $ = (id) => drawer.querySelector("#" + id);
    $("dl-close").addEventListener("click", close);
    $("dl-filter").addEventListener("input", (e) => { text = e.target.value.toLowerCase(); renderTable(); });
    $("dl-chips").addEventListener("click", (e) => {
      const b = e.target.closest("[data-chip]");
      if (!b) return;
      const c = b.dataset.chip;
      active.has(c) ? active.delete(c) : active.add(c);
      b.classList.toggle("on", active.has(c));
      renderTable();
    });
    $("dl-cite-toggle").addEventListener("click", () => setCite(!citeOn));
    $("dl-tablewrap").addEventListener("click", (e) => {
      const th = e.target.closest("th[data-key]");
      if (th) {
        sort = { key: th.dataset.key, dir: sort.key === th.dataset.key ? -sort.dir : 1 };
        renderTable();
        return;
      }
      const tr = e.target.closest("tr[data-path]");
      if (tr) select(tr.dataset.path);
    });
    const grip = $("dl-grip");
    grip.addEventListener("pointerdown", (e) => {
      grip.setPointerCapture(e.pointerId);
      const move = (ev) => {
        const h = Math.min(window.innerHeight * 0.9, Math.max(160, window.innerHeight - ev.clientY));
        drawer.style.setProperty("--dl-h", h + "px");
      };
      grip.addEventListener("pointermove", move);
      grip.addEventListener("pointerup", () => grip.removeEventListener("pointermove", move), { once: true });
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && drawer.classList.contains("open")) close();
    });
  }

  const q = (id) => drawer.querySelector("#" + id);

  async function open(format, path) {
    build();
    fmt = format;
    sort = { key: null, dir: 1 };
    text = "";
    active = new Set();
    selected = null;
    q("dl-filter").value = "";
    q("dl-title").textContent = format;
    q("dl-count").textContent = "loading…";
    q("dl-chips").innerHTML = CHIPS.map((c) => `<button type="button" class="dl-chip" data-chip="${c}">${c}</button>`).join(" ");
    q("dl-cite-toggle").hidden = format !== "printed-docs";
    q("dl-side").hidden = true;
    setCite(false);
    drawer.classList.add("open");
    await load();
    if (path) select(path, true);
  }

  function close() {
    if (!drawer) return;
    drawer.classList.remove("open");
  }

  async function load() {
    try {
      const res = await fetch("/api/corpus?format=" + encodeURIComponent(fmt));
      data = await res.json();
      if (!res.ok) throw new Error(data.error || res.status);
    } catch (e) {
      q("dl-tablewrap").innerHTML = `<p class="dl-more">Could not load the table: ${esc(e.message)}</p>`;
      return;
    }
    renderTable();
  }

  function cell(row, key) {
    const v = row[key];
    if (Array.isArray(v)) return v.join(", ");
    if (key === "path") return v.split("/").slice(2).join("/");
    return v === null || v === undefined ? "" : String(v);
  }

  function renderTable() {
    if (!data) return;
    let rows = data.rows.filter((r) => (!active.size || active.has(r.disposition)) &&
      (!text || JSON.stringify(Object.values(r)).toLowerCase().includes(text)));
    if (sort.key) {
      const k = sort.key;
      rows = [...rows].sort((a, b) => {
        const x = a[k], y = b[k];
        if (x === y) return 0;
        if (x === null || x === undefined || x === "") return 1;
        if (y === null || y === undefined || y === "") return -1;
        return (typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y))) * sort.dir;
      });
    }
    q("dl-count").textContent = `${rows.length} / ${data.rows.length} rows`;
    const head = data.columns.map((c) => `<th data-key="${c.key}">${esc(c.label)}${sort.key === c.key ? (sort.dir > 0 ? " ▲" : " ▼") : ""}</th>`).join("");
    const body = rows.slice(0, ROW_CAP).map((r) => {
      const cls = (r.disposition === "queued" ? "dl-undigested" : r.disposition === "source" ? "dl-done" : "") + (r.path === selected ? " sel" : "");
      return `<tr class="${cls}" data-path="${esc(r.path)}">${data.columns.map((c) => `<td title="${esc(cell(r, c.key))}">${esc(cell(r, c.key))}</td>`).join("")}</tr>`;
    }).join("");
    q("dl-tablewrap").innerHTML = `<table class="dl-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>` +
      (rows.length > ROW_CAP ? `<p class="dl-more">Showing the first ${ROW_CAP} — filter to narrow.</p>` : "");
  }

  async function select(path, scroll) {
    selected = path;
    renderTable();
    if (scroll) {
      const tr = [...drawer.querySelectorAll("tr[data-path]")].find((t) => t.dataset.path === path);
      if (tr) tr.scrollIntoView({ block: "center" });
    }
    const side = q("dl-side");
    side.hidden = false;
    side.innerHTML = `<p class="dl-more">Loading preview…</p>`;
    const row = data && data.rows.find((r) => r.path === path);
    let meta = {};
    try {
      const res = await fetch("/api/raw-preview?path=" + encodeURIComponent(path));
      meta = await res.json();
      if (!res.ok) throw new Error(meta.error || res.status);
    } catch (e) {
      side.innerHTML = `<p class="dl-more">Preview failed: ${esc(e.message)}</p>`;
      return;
    }
    const undigested = row && row.disposition === "queued";
    const slug = (row && row.slug) || meta.slug;
    const dl = [["disposition", row ? row.disposition : meta.disposition], ["page", slug], ["collection", (row ? row.collection : meta.collection || []).join(", ")],
      ["year", row && row.year], ["sha1", row && row.sha1]].filter(([, v]) => v);
    const cmd = (tier) => `python3 -m kb.ingest ${tier}-digest ${path}`;
    side.innerHTML = `<h3>${esc(path.split("/").slice(2).join("/"))}</h3>
      <dl>${dl.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join("")}</dl>
      <div class="dl-actions">
        ${meta.exists ? `<a class="dl-btn" href="${esc(meta.file_url)}" target="_blank" rel="noopener noreferrer">open file</a>` : `<span class="dl-note">file not on disk here</span>`}
        ${slug ? `<button type="button" class="dl-btn" data-act="show">show in graph</button>` : ""}
        ${window.ScopeDraft ? `<button type="button" class="dl-btn" data-act="basket">add to scope</button>` : ""}
        <button type="button" class="dl-btn primary" data-act="easy" ${row && row.disposition === "source" ? "disabled" : ""}>easy-digest</button>
      </div>
      ${["full", "deep"].map((t) => `<div class="dl-cmd"><strong>${t}</strong><code>${esc(cmd(t))}</code>
        <button type="button" class="dl-btn" data-copy="${esc(cmd(t))}">copy</button>
        <a class="dl-btn" href="/chat?prefill=${encodeURIComponent(t + "-digest " + path)}">prefill chat</a></div>`).join("")}
      <pre id="dl-out" hidden></pre>
      ${undigested ? `<p class="dl-note">Not digested yet.</p>` : ""}
      <pre>${esc(meta.text || (meta.error ? meta.error : "(no text excerpt)"))}</pre>`;
    side.onclick = async (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      if (b.dataset.copy) {
        try { await navigator.clipboard.writeText(b.dataset.copy); b.textContent = "copied"; } catch (_) { b.textContent = "copy failed"; }
      } else if (b.dataset.act === "show") {
        if (window.WikiGraph) window.WikiGraph.focus(slug);
      } else if (b.dataset.act === "basket") {
        const added = window.ScopeDraft.addRows([{ path, format: fmt, disposition: row ? row.disposition : "queued", slug: slug || "",
          page_type: "", digestion: row ? (row.digestion || "") : "", collection: row ? row.collection : [], year: row ? row.year : null }]);
        b.textContent = added ? "in scope draft" : "already in draft";
      } else if (b.dataset.act === "easy") {
        const out = side.querySelector("#dl-out");
        out.hidden = false;
        out.textContent = "running easy-digest…";
        b.disabled = true;
        try {
          const res = await fetch("/api/raw-action", { method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: "easy-digest", path }) });
          const r = await res.json();
          out.textContent = res.ok ? `exit ${r.exit}\n${r.stdout}${r.stderr}` : `error: ${r.error}`;
          if (res.ok && r.exit === 0) { await load(); if (window.WikiGraph) window.WikiGraph.reload(); }
        } catch (err) {
          out.textContent = "request failed: " + err.message;
        }
        b.disabled = false;
      }
    };
  }

  // ---- citation view ----
  // `focus` (a paper slug) narrows it to that paper's genealogy: what it cites and what cites it,
  // up to GENEALOGY_HOPS steps each way. Without it, every cataloged paper is drawn.
  const GENEALOGY_HOPS = 2;
  const CITE_COLOR = { all: "#ff6b7a", focus: "#f5b942", cited: "#7aa2ff", citing: "#ff6b7a" };

  function genealogy(c, focus, hops) {
    const refs = new Map(), citers = new Map();
    for (const l of c.links) {
      if (!refs.has(l.source)) refs.set(l.source, []);
      refs.get(l.source).push(l.target);
      if (!citers.has(l.target)) citers.set(l.target, []);
      citers.get(l.target).push(l.source);
    }
    const walk = (adj) => {
      const seen = new Set([focus]);
      let front = [focus];
      for (let h = 0; h < hops && front.length; h++) {
        const next = [];
        for (const id of front) for (const m of adj.get(id) || []) if (!seen.has(m)) { seen.add(m); next.push(m); }
        front = next;
      }
      seen.delete(focus);
      return seen;
    };
    const cited = walk(refs), citing = walk(citers);
    const keep = new Set([focus, ...cited, ...citing]);
    const role = (id) => (id === focus ? "focus" : citing.has(id) ? "citing" : "cited");
    return {
      nodes: c.nodes.filter((n) => keep.has(n.id)).map((n) => ({ ...n, role: role(n.id) })),
      links: c.links.filter((l) => keep.has(l.source) && keep.has(l.target)).map((l) => ({ ...l })),
      cited: cited.size, citing: citing.size,
    };
  }

  async function setCite(on, { focus = null } = {}) {
    citeOn = on;
    q("dl-cite-toggle").classList.toggle("on", on);
    q("dl-cite").hidden = !on;
    q("dl-tablewrap").hidden = on;
    if (!on) { q("dl-side").hidden = !selected; return; }
    q("dl-side").hidden = true;
    const box = q("dl-cite");
    box.innerHTML = `<p class="dl-note">Loading citations…</p>`;
    let c;
    try { c = await (await fetch("/api/citations")).json(); } catch (e) { c = { missing: true, nodes: [], links: [] }; }
    if (c.missing || !c.nodes.length) {
      box.innerHTML = `<p class="dl-note">${c.missing ? "No citation data yet — run <code>python3 -m kb.search.citations fetch</code>." : "No cataloged papers have citation data."}</p>`;
      return;
    }
    const title = (id) => { const n = window.WikiGraph && window.WikiGraph.node(id); return (n && n.title) || id; };
    if (focus && !c.nodes.some((n) => n.id === focus)) {
      box.innerHTML = `<p class="dl-note">No citation data for “${esc(title(focus))}” yet — run <code>python3 -m kb.search.citations fetch</code>. <button type="button" class="dl-btn" data-cite-all>Show all citations</button></p>`;
      box.querySelector("[data-cite-all]").addEventListener("click", () => setCite(true));
      return;
    }
    box.innerHTML = "";
    if (typeof ForceGraph !== "function") { box.innerHTML = `<p class="dl-note">Graph library not loaded.</p>`; return; }
    const w = box.clientWidth || 600, h = box.clientHeight || 300;
    const g = focus ? genealogy(c, focus, GENEALOGY_HOPS) : { nodes: c.nodes.map((n) => ({ ...n, role: "all" })), links: c.links.map((l) => ({ ...l })) };
    citeGraph = ForceGraph()(box).width(w).height(h).backgroundColor("rgba(0,0,0,0)")
      .graphData({ nodes: g.nodes, links: g.links }).nodeId("id")
      .nodeVal((n) => (n.role === "focus" ? 6 : 0) + 2 + Math.log2(1 + (n.citationCount || 0)) ** 2 / 4)
      .nodeLabel((n) => `${n.title} (${n.year || "?"}) · ${n.citationCount || 0} citations`)
      .nodeColor((n) => CITE_COLOR[n.role] || CITE_COLOR.all)
      .linkDirectionalArrowLength(4).linkDirectionalArrowRelPos(0.9)
      .linkColor(() => "rgba(160,175,210,0.5)")
      .onNodeClick((n) => { if (window.WikiGraph) window.WikiGraph.focus(n.id); });
    if (focus) {
      citeGraph.cooldownTicks(80).onEngineStop(() => citeGraph.zoomToFit(400, 40));
      const bar = document.createElement("div");
      bar.className = "dl-cite-bar";
      bar.innerHTML = `<span>Genealogy of <b>${esc(title(focus))}</b> · ${GENEALOGY_HOPS} hops</span>
        <span><i style="background:${CITE_COLOR.cited}"></i>it cites ${g.cited}</span>
        <span><i style="background:${CITE_COLOR.citing}"></i>cite it ${g.citing}</span>
        <button type="button" class="dl-btn" data-cite-all>Show all citations</button>`;
      bar.querySelector("[data-cite-all]").addEventListener("click", () => setCite(true));
      box.appendChild(bar);
    }
    box.dataset.focus = focus || "";
  }

  document.addEventListener("datalayer:pile", (e) => open(e.detail.format));
  document.addEventListener("datalayer:toggle", (e) => { if (!e.detail.on) close(); });
  document.addEventListener("click", (e) => {
    const li = e.target.closest("#gs-inspect [data-raw]");
    if (li) open(li.dataset.format, li.dataset.raw);
  });
  // The citation view lives in the printed-docs drawer; this opens it straight away
  // (`focus`: one paper's genealogy instead of every paper).
  async function openCitations({ focus = null } = {}) {
    await open("printed-docs");
    setCite(true, { focus });
  }
  window.DataLayer = { open, close, openCitations,
    citeIds: () => (citeOn && citeGraph ? citeGraph.graphData().nodes.map((n) => n.id) : []) };
})();
