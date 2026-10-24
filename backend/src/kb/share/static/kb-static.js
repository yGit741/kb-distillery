/* kb-static.js — runtime shim injected as the FIRST script of each view inside the shared page.
 *
 * The views are the untouched dashboard pages (graph.html / explore.html, and in private builds the
 * Start, Health, Digestion and Lifecycle pages, with their JS and CSS inlined) rendered inside
 * <iframe srcdoc>. They still call the dashboard API; this file answers those calls from the data
 * the shell embedded once (`parent.KB_DATA`), ports the two server-side computations (search,
 * shortest paths) to JS, turns cross-view links into messages to the shell, hides the live-sync /
 * refresh controls and replaces raw/ assets with a placeholder.
 *
 * The only build-time patch to the dashboard code is `location.href = X;` → `KB_STATIC.navigate(X);`
 * (`location` cannot be overridden in JS); see backend/src/kb/share/build.py.
 */
(function () {
  "use strict";
  const MAX_PATHS = 4;
  const PLACEHOLDER = "not included in shared view";
  const ASSET_ROUTES = ["/vault-asset", "/raw-file", "/raw-thumb", "/chat-asset"];
  // Dashboard page → shell view. Pages absent from the build (public profile, or pages that are
  // never shared) fall back to the shell's default tab or a toast.
  const VIEW_ROUTES = [
    [/^\/(?:index\.html)?(?=[#?]|$)/, "health"],
    [/^\/explore(?=[#?/]|$)/, "explore"],
    [/^\/graph(?=[#?/]|$)/, "graph"],
    [/^\/(?:digestion|pipeline)(?=[#?/.]|$)/, "digestion"],
    [/^\/lifecycle(?=[#?/.]|$)/, "lifecycle"],
    [/^\/start(?=[#?/.]|$)/, "start"],
    [/^\/chat(?=[#?/.]|$)/, null],
  ];
  function viewOf(href) {
    for (const [re, view] of VIEW_ROUTES) if (re.test(href)) return { view };
    return null;
  }

  function data() {
    try {
      if (window.KB_DATA) return window.KB_DATA;
      if (window.parent && window.parent !== window && window.parent.KB_DATA) return window.parent.KB_DATA;
    } catch (_e) { /* cross-origin parent: fall through */ }
    return null;
  }

  function jsonResponse(obj, status) {
    const body = JSON.stringify(obj === undefined ? null : obj);
    return new Response(body, { status: status || 200, headers: { "Content-Type": "application/json" } });
  }

  // ---------- ports of backend/src/kb/services/pages.py ----------
  const WIKILINK = /\[\[([^\]|#\\]+)(?:#[^\]|]+)?(?:\\?\|([^\]]+))?\]\]/g;

  function titleOf(d, slug) {
    const p = d.pages[slug];
    return (p && p.card && p.card.title) || slug;
  }

  function plain(d, s) {
    s = s.replace(WIKILINK, (_m, slug, label) => (label || titleOf(d, slug.trim()) || slug).trim());
    s = s.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
    s = s.replace(/[*_`>#]+/g, "");
    return s.replace(/\s+/g, " ").trim();
  }

  function clip(s, centre, width) {
    width = width || 220;
    if (s.length <= width) return s;
    let start = Math.max(0, centre - Math.floor(width / 2));
    const end = Math.min(s.length, start + width);
    start = Math.max(0, end - width);
    let out = s.slice(start, end);
    if (start > 0) out = "…" + out.replace(/^\s+/, "");
    if (end < s.length) out = out.replace(/\s+$/, "") + "…";
    return out;
  }

  function count(hay, needle) {
    if (!needle) return 0;
    let n = 0, i = 0;
    while ((i = hay.indexOf(needle, i)) !== -1) { n += 1; i += needle.length; }
    return n;
  }

  function search(query, limit) {
    limit = limit || 40;
    const d = data();
    const q = (query || "").trim().toLowerCase();
    if (!d || q.length < 2) return { query: query, total: 0, hits: [] };
    const terms = q.split(/\s+/).filter(Boolean);
    const hits = [];
    for (const slug of Object.keys(d.pages)) {
      const page = d.pages[slug];
      const title = page.card.title;
      const body = page.markdown || "";
      const lowTitle = title.toLowerCase(), lowBody = body.toLowerCase(), lowSlug = slug.toLowerCase();
      if (!terms.every((t) => lowTitle.includes(t) || lowBody.includes(t) || lowSlug.includes(t))) continue;
      let score = 0;
      for (const t of terms) {
        if (lowTitle.includes(t) || lowSlug.includes(t)) score += 50;
        score += Math.min(count(lowBody, t), 12);
      }
      if (lowTitle.includes(q)) score += 40;
      let snippet = "";
      for (const line of body.split("\n")) {
        const low = line.toLowerCase();
        if (terms.some((t) => low.includes(t)) && !/^\s*[#|]/.test(line)) {
          const p = plain(d, line);
          const lp = p.toLowerCase();
          const positions = terms.filter((t) => lp.includes(t)).map((t) => lp.indexOf(t));
          snippet = clip(p, positions.length ? Math.min.apply(null, positions) : 0, 240);
          break;
        }
      }
      hits.push({ id: slug, title, type: page.card.type || "unknown", snippet: snippet || page.card.preview || "", score });
    }
    hits.sort((a, b) => (b.score - a.score) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
    return { query: query, total: hits.length, hits: hits.slice(0, limit) };
  }

  function adjacency(d) {
    if (d.__adj) return d.__adj;
    const out = {}, inn = {};
    for (const slug of Object.keys(d.pages)) { out[slug] = new Set(); inn[slug] = new Set(); }
    for (const [s, t] of d.index.links) {
      if (out[s] && inn[t]) { out[s].add(t); inn[t].add(s); }
    }
    d.__adj = { out, inn };
    return d.__adj;
  }

  function linkContext(d, from, to) {
    // explore_data._link_context(from → to) was computed at build time as the backlink entry
    // `from` on page `to`; reuse it so hop contexts match the live dashboard.
    const target = d.pages[to];
    if (target && target.backlinks) {
      for (const b of target.backlinks) if (b.id === from) return b.context || "";
    }
    return "";
  }

  function findPaths(a, b) {
    const d = data();
    if (!d || !d.pages[a] || !d.pages[b]) return null;
    const { out, inn } = adjacency(d);
    const nbrs = (s) => Array.from(new Set([...out[s], ...inn[s]])).sort();
    const dist = { [a]: 0 };
    const parents = { [a]: [] };
    const queue = [a];
    while (queue.length) {
      const cur = queue.shift();
      if (cur === b) break;
      for (const n of nbrs(cur)) {
        if (!(n in dist)) { dist[n] = dist[cur] + 1; parents[n] = [cur]; queue.push(n); }
        else if (dist[n] === dist[cur] + 1) parents[n].push(cur);
      }
    }
    if (!(b in dist)) return { a, b, distance: null, paths: [] };
    const paths = [];
    (function walk(node, tail) {
      if (paths.length >= MAX_PATHS) return;
      if (node === a) { paths.push([a].concat(tail)); return; }
      for (const p of parents[node]) walk(p, [node].concat(tail));
    })(b, []);
    const hop = (s, t) => out[s].has(t)
      ? { from: s, to: t, dir: "forward", context: linkContext(d, s, t) }
      : { from: s, to: t, dir: "back", context: linkContext(d, t, s) };
    return {
      a, b, distance: dist[b],
      paths: paths.map((p) => ({ nodes: p, hops: p.slice(0, -1).map((s, i) => hop(s, p[i + 1])) })),
    };
  }

  // ---------- fetch shim ----------
  function route(url) {
    const u = new URL(String(url), "http://kb.local/");
    const d = data();
    if (u.pathname === "/api/graph") return d ? jsonResponse(d.graph) : jsonResponse({ error: "no data" }, 503);
    if (u.pathname === "/api/schema") return d && d.graph && d.graph.schema ? jsonResponse(d.graph.schema) : jsonResponse({ error: "no data" }, 503);
    if (u.pathname === "/api/explore/index") return d ? jsonResponse(d.index) : jsonResponse({ error: "no data" }, 503);
    if (u.pathname === "/api/explore/page") {
      const slug = u.searchParams.get("slug") || "";
      const page = d && d.pages[slug];
      return page ? jsonResponse(page) : jsonResponse({ error: "not found" }, 404);
    }
    if (u.pathname === "/api/explore/search") return jsonResponse(search(u.searchParams.get("q") || "", Math.min(Number(u.searchParams.get("limit")) || 40, 5000)));
    if (u.pathname === "/api/explore/path") {
      const r = findPaths(u.searchParams.get("a") || "", u.searchParams.get("b") || "");
      return r ? jsonResponse(r) : jsonResponse({ error: "not found" }, 404);
    }
    // Private builds only: the Digestion and Lifecycle snapshots captured at build time.
    if (u.pathname === "/api/pipeline" || u.pathname === "/api/digestion") {
      return d && d.digestion ? jsonResponse(d.digestion) : jsonResponse({ error: "not available in shared view" }, 404);
    }
    if (u.pathname === "/api/lifecycle") {
      return d && d.lifecycle ? jsonResponse(d.lifecycle) : jsonResponse({ error: "not available in shared view" }, 404);
    }
    if (u.pathname.startsWith("/api/")) return jsonResponse({ error: "not available in shared view" }, 404);
    return null;
  }

  const realFetch = window.fetch ? window.fetch.bind(window) : null;
  window.fetch = function (input, init) {
    const url = typeof input === "string" ? input : (input && input.url) || String(input);
    if (url.startsWith("/")) {
      const res = route(url);
      if (res) return Promise.resolve(res);
    }
    return realFetch ? realFetch(input, init) : Promise.reject(new Error("fetch unavailable"));
  };

  // ---------- navigation between views ----------
  function post(msg) {
    try { if (window.parent && window.parent !== window) window.parent.postMessage(msg, "*"); } catch (_e) { /* ignore */ }
  }

  function navigate(href) {
    const s = String(href || "");
    const hit = viewOf(s);
    if (hit && hit.view === "explore") {
      const i = s.indexOf("#");
      post({ type: "kb:nav", view: "explore", hash: i >= 0 ? s.slice(i) : "#/" });
      return true;
    }
    if (hit && hit.view === "graph") {
      const u = new URL(s, "http://kb.local/");
      post({ type: "kb:nav", view: "graph", focus: u.searchParams.get("focus") || "" });
      return true;
    }
    if (hit && hit.view) { post({ type: "kb:nav", view: hit.view }); return true; }
    if (s.startsWith("/")) { toast(PLACEHOLDER); return true; }   // /chat, anything else local
    window.location.href = s;
    return false;
  }

  function toast(text) {
    const t = document.getElementById("toast");
    if (t) {
      t.textContent = text;
      t.hidden = false;
      clearTimeout(toast._timer);
      toast._timer = setTimeout(() => { t.hidden = true; }, 1800);
    }
  }

  document.addEventListener("click", (e) => {
    const a = e.target && e.target.closest ? e.target.closest("a[href]") : null;
    if (!a) return;
    const href = a.getAttribute("href") || "";
    if (viewOf(href) || ASSET_ROUTES.some((r) => href.startsWith(r))) {
      e.preventDefault();
      e.stopPropagation();
      navigate(href);
    }
  }, true);

  function focusWhenReady(id) {
    if (!id) return;
    if (window.WikiGraph && window.WikiGraph.node && window.WikiGraph.node(id)) { window.WikiGraph.focus(id); return; }
    document.addEventListener("graph:ready", () => setTimeout(() => window.WikiGraph && window.WikiGraph.focus(id), 1200), { once: true });
  }

  window.addEventListener("message", (e) => {
    const m = e.data;
    if (!m || typeof m !== "object") return;
    if (m.type === "kb:show") {
      if (m.hash !== undefined && m.hash !== null) {
        if (window.location.hash !== m.hash) window.location.hash = m.hash;
      }
      if (m.focus) focusWhenReady(m.focus);
    } else if (m.type === "kb:theme" && window.DashboardTheme) {
      window.DashboardTheme.set(m.theme);
    }
  });

  window.addEventListener("hashchange", () => post({ type: "kb:hash", hash: window.location.hash }));

  // ---------- assets + live sync ----------
  function placeholder(kind) {
    const box = document.createElement("div");
    box.className = "kb-static-placeholder";
    box.setAttribute("role", "note");
    box.textContent = `${kind}: ${PLACEHOLDER}`;
    return box;
  }

  function isAssetUrl(src) {
    return ASSET_ROUTES.some((r) => (src || "").startsWith(r));
  }

  function scrub(root) {
    if (!root || !root.querySelectorAll) return;
    const sel = ASSET_ROUTES.map((r) => `img[src^="${r}"], iframe[src^="${r}"], a[href^="${r}"]`).join(", ");
    const nodes = root.matches && root.matches(sel) ? [root] : [];
    root.querySelectorAll(sel).forEach((n) => nodes.push(n));
    for (const n of nodes) {
      if (n.tagName === "A") { n.classList.add("kb-static-asset"); n.title = PLACEHOLDER; continue; }
      const kind = n.tagName === "IFRAME" ? "visualization" : (n.getAttribute("alt") || "image");
      n.replaceWith(placeholder(kind));
    }
  }

  const observer = new MutationObserver((muts) => {
    for (const m of muts) {
      m.addedNodes.forEach((n) => { if (n.nodeType === 1) scrub(n); });
      if (m.type === "attributes" && m.target.nodeType === 1 && isAssetUrl(m.target.getAttribute(m.attributeName))) scrub(m.target);
    }
  });

  function onReady() {
    scrub(document.body);
    observer.observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ["src", "href"] });
    const live = document.getElementById("live-sync");
    if (live) {
      live.checked = false;
      const panel = live.closest("details[data-panel]") || live.closest(".field");
      if (panel) panel.hidden = true;
    }
    const refresh = document.getElementById("btn-refresh");
    if (refresh) refresh.hidden = true;
    // Health: lint timings are zeroed at build time — the phase chart and the Performance card
    // would only show zeros. Page footers name the local server/API, meaningless here.
    const lintChart = document.getElementById("chart-lint");
    if (lintChart && lintChart.closest(".chart-card")) lintChart.closest(".chart-card").hidden = true;
    document.querySelectorAll('section.card[data-cluster="performance"], footer.footer').forEach((n) => { n.hidden = true; });
    const style = document.createElement("style");
    style.textContent = ".kb-static-placeholder{margin:.75rem 0;padding:.6rem .8rem;border:1px dashed var(--border,#999);border-radius:8px;color:var(--muted,#777);font-size:.85rem}"
      + ".kb-static-asset{pointer-events:none;opacity:.55}a[href^='obsidian:']{display:none!important}";
    document.head.appendChild(style);
    const prev = document.documentElement.getAttribute("data-theme");
    if (prev) post({ type: "kb:theme-is", theme: prev });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", onReady);
  else onReady();

  window.KB_STATIC = { navigate, search, findPaths, route, data, viewOf, PLACEHOLDER };
})();
