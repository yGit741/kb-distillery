(function () {
  "use strict";

  // Type tables and the depth ladder come from /api/schema (src/kb_distillery/core/schema.py); nothing is listed here.
  const TYPE_COLORS = { unknown: "#6c7086" };
  const TYPE_LABEL = { unknown: "Other" };
  const TYPE_LAYER = {};
  const TYPE_ORDER = [];
  const DEPTH_RANK = {};
  function applySchema(schema) {
    (schema.types || []).forEach((t) => {
      TYPE_COLORS[t.id] = t.color; TYPE_LABEL[t.id] = t.label; TYPE_LAYER[t.id] = t.layer; TYPE_ORDER.push(t.id);
    });
    TYPE_ORDER.push("unknown");
    (schema.depth || []).forEach((d, i) => { DEPTH_RANK[d] = i; });   // listed 0 · easy 1 · full 2 · deep 3
  }
  const TRAIL_KEY = "explore-trail";
  const PINS_KEY = "explore-pins";
  const TRAIL_MAX = 14;
  const RING_MAX = 26;

  const $ = (id) => document.getElementById(id);
  const main = $("ex-main");
  const rail = $("ex-rail");

  // chat visualizations report their height (serve.py injects the reporter)
  window.addEventListener("message", (e) => {
    if (!e.data || !e.data.vizHeight) return;
    document.querySelectorAll("iframe.ex-viz-frame").forEach((f) => {
      if (f.contentWindow === e.source) f.style.height = `${e.data.vizHeight + 4}px`;
    });
  });

  // in-page jumps (chat pages: #viz-n, #lost-n, #branch-n) — open every enclosing
  // fold, then scroll; never let them reach the hash router
  document.addEventListener("click", (e) => {
    const a = e.target.closest('a[href^="#viz-"], a[href^="#lost-"], a[href^="#branch-"], a[href^="#main-after-"]');
    if (!a) return;
    e.preventDefault();
    const el = document.getElementById(a.getAttribute("href").slice(1));
    if (!el) return;
    for (let p = el.parentElement; p; p = p.parentElement) if (p.tagName === "DETAILS") p.open = true;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  let pages = new Map();
  let outAdj = new Map();
  let inAdj = new Map();
  let indexData = null;
  let currentSlug = null;

  // ---------- storage (per-viewer convenience only) ----------
  function loadList(key) {
    try {
      const v = JSON.parse(localStorage.getItem(key) || "[]");
      return Array.isArray(v) ? v : [];
    } catch (_e) {
      return [];
    }
  }
  function saveList(key, list) {
    try { localStorage.setItem(key, JSON.stringify(list)); } catch (_e) { /* ignore */ }
  }

  // ---------- helpers ----------
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function titleOf(slug) {
    const p = pages.get(slug);
    return p ? p.title : slug;
  }
  function typeOf(slug) {
    const p = pages.get(slug);
    return p ? p.type : "unknown";
  }
  function color(type) {
    return TYPE_COLORS[type] || TYPE_COLORS.unknown;
  }
  function dot(type) {
    return `<span class="ex-dot" style="background:${color(type)}" title="${esc(TYPE_LABEL[type] || type)}"></span>`;
  }
  function pageHref(slug) {
    return `#/p/${encodeURIComponent(slug)}`;
  }
  function pageLink(slug, label) {
    if (!pages.has(slug)) return `<span class="wl-missing" title="No page yet: ${esc(slug)}">${esc(label || slug)}</span>`;
    return `<a class="wl" data-slug="${esc(slug)}" href="${pageHref(slug)}">${esc(label || titleOf(slug))}</a>`;
  }
  function ago(ts) {
    if (!ts) return "";
    const d = Math.floor((Date.now() / 1000 - ts) / 86400);
    if (d <= 0) return "today";
    if (d === 1) return "yesterday";
    if (d < 30) return `${d}d ago`;
    if (d < 365) return `${Math.floor(d / 30)}mo ago`;
    return `${Math.floor(d / 365)}y ago`;
  }
  function neighbours(slug) {
    const s = new Set(outAdj.get(slug) || []);
    (inAdj.get(slug) || []).forEach((x) => s.add(x));
    return s;
  }
  async function getJSON(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`${res.status} ${url}`);
    return res.json();
  }

  // ---------- markdown ----------
  function renderMath(src, display) {
    try {
      return window.katex.renderToString(src, { displayMode: display, throwOnError: false, strict: "ignore" });
    } catch (_e) {
      return `<code>${esc(src)}</code>`;
    }
  }

  function renderMarkdown(md) {
    const stash = [];
    const hold = (html) => {
      stash.push(html);
      return `XSTASHX${stash.length - 1}XENDX`;
    };
    const codeStash = [];
    const holdCode = (raw) => {
      codeStash.push(raw);
      return `XCODEX${codeStash.length - 1}XENDX`;
    };

    let s = md;
    // Obsidian comments
    s = s.replace(/<!--[\s\S]*?-->/g, "");
    // chat visualizations: the Obsidian dataviewjs iframe block → a live sandboxed frame
    s = s.replace(/```dataviewjs\n[\s\S]*?const path = "([^"]+)";[\s\S]*?```/g, (_m, p) =>
      hold(`<div class="ex-viz" data-src="${esc(p)}"></div>`));
    // protect code so math/wikilink passes leave it alone
    s = s.replace(/```[\s\S]*?```/g, holdCode);
    s = s.replace(/`[^`\n]+`/g, holdCode);
    // math
    s = s.replace(/\$\$([\s\S]+?)\$\$/g, (_m, tex) => hold(renderMath(tex.trim(), true)));
    s = s.replace(/(^|[^\\$])\$(?!\s)([^$\n]+?)\$(?!\d)/g, (_m, pre, tex) => pre + hold(renderMath(tex, false)));
    // embeds + wikilinks (table cells escape the pipe as \|)
    s = s.replace(/!\[\[([^\]|]+)(?:\\?\|[^\]]*)?\]\]/g, (_m, name) =>
      hold(`<img class="ex-embed" alt="${esc(name)}" src="/vault-asset?name=${encodeURIComponent(name.trim())}">`));
    s = s.replace(/\[\[([^\]|#]+)(#[^\]|]+)?(?:\s*\\?\|\s*([^\]]+))?\]\]/g, (_m, slug, _h, label) =>
      hold(pageLink(slug.trim(), label ? label.trim() : "")));
    s = s.replace(/XCODEX(\d+)XENDX/g, (_m, i) => codeStash[Number(i)]);

    let html = window.marked.parse(s, { gfm: true, breaks: false });
    html = html.replace(/XSTASHX(\d+)XENDX/g, (_m, i) => stash[Number(i)]);

    const tpl = document.createElement("template");
    tpl.innerHTML = html;
    const root = tpl.content;
    root.querySelectorAll("script, iframe, object, embed, style").forEach((n) => n.remove());
    root.querySelectorAll(".ex-viz").forEach((box) => {
      const frame = document.createElement("iframe");
      frame.setAttribute("sandbox", "allow-scripts");  // no same-origin: can't touch the dashboard
      frame.src = `/chat-asset?path=${encodeURIComponent(box.dataset.src)}`;
      frame.className = "ex-viz-frame";
      box.appendChild(frame);
    });
    // page links: [Title](slug.md) and [label](slug.md#heading) route to the page like a wikilink did
    root.querySelectorAll("a[href]").forEach((a) => {
      const m = /^([^/:#?]+)\.md(?:#.*)?$/.exec(a.getAttribute("href"));
      if (!m) return;
      const slug = decodeURIComponent(m[1]);
      const holder = document.createElement("template");
      holder.innerHTML = pageLink(slug, a.textContent);
      a.replaceWith(holder.content);
    });
    root.querySelectorAll("a[href]").forEach((a) => {
      if (/^https?:/i.test(a.getAttribute("href"))) {
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.classList.add("ext");
      }
    });
    root.querySelectorAll("table").forEach((t) => {
      const wrap = document.createElement("div");
      wrap.className = "ex-table-wrap";
      t.replaceWith(wrap);
      wrap.appendChild(t);
    });
    // Obsidian callouts: > [!kind]- Title
    root.querySelectorAll("blockquote").forEach((bq) => {
      const first = bq.querySelector("p");
      if (!first) return;
      const m = /^\s*\[!(\w+)\][+-]?\s*(.*)/.exec(first.innerHTML.split("\n")[0]);
      if (!m) return;
      const rest = first.innerHTML.split("\n").slice(1).join("\n");
      const box = document.createElement("details");
      box.className = `ex-callout ex-callout-${m[1].toLowerCase()}`;
      box.open = !/\]-/.test(first.innerHTML.split("\n")[0]);
      const sum = document.createElement("summary");
      sum.innerHTML = m[2] || m[1];
      box.appendChild(sum);
      if (rest.trim()) first.innerHTML = rest; else first.remove();
      while (bq.firstChild) box.appendChild(bq.firstChild);
      bq.replaceWith(box);
    });
    // heading anchors; drop the H1 (shown in the page header)
    const toc = [];
    const h1 = root.querySelector("h1");
    if (h1) h1.remove();
    root.querySelectorAll("h2, h3").forEach((h, i) => {
      h.id = `sec-${i}`;
      toc.push({ id: h.id, text: h.textContent, level: h.tagName === "H2" ? 2 : 3 });
    });
    return { fragment: root, toc };
  }

  // ---------- sidebar ----------
  function renderSideLists() {
    const pins = loadList(PINS_KEY).filter((s) => pages.has(s));
    const trail = loadList(TRAIL_KEY).filter((s) => pages.has(s));
    const row = (s) => `<li${s === currentSlug ? ' class="current"' : ""}>${dot(typeOf(s))}${pageLink(s)}</li>`;
    $("sec-pins").classList.toggle("hidden", !pins.length);
    $("ex-pins").innerHTML = pins.map(row).join("");
    $("sec-trail").classList.toggle("hidden", !trail.length);
    $("ex-trail").innerHTML = trail.map(row).join("");
  }
  function pushTrail(slug) {
    const trail = loadList(TRAIL_KEY).filter((s) => s !== slug);
    trail.unshift(slug);
    saveList(TRAIL_KEY, trail.slice(0, TRAIL_MAX));
  }
  function togglePin(slug) {
    if (!slug) return;
    let pins = loadList(PINS_KEY);
    pins = pins.includes(slug) ? pins.filter((s) => s !== slug) : [slug, ...pins];
    saveList(PINS_KEY, pins);
    renderSideLists();
    const btn = $("btn-pin");
    if (btn) btn.textContent = pins.includes(slug) ? "★ Pinned" : "☆ Pin";
  }
  function renderToc(toc) {
    const sec = $("sec-toc");
    const items = (toc || []).filter((t) => t.level === 2);
    sec.classList.toggle("hidden", items.length < 2);
    $("ex-toc").innerHTML = items.map((t) => `<li><a href="#" data-anchor="${t.id}">${esc(t.text)}</a></li>`).join("");
  }

  // ---------- cards ----------
  function card(p, extra) {
    const meta = [];
    if (p.year) meta.push(p.year);
    if (p.depth) meta.push(p.depth);
    else if (p.maturity) meta.push(p.maturity);
    meta.push(`${p.in}↘ ${p.out}↗`);
    return `<a class="ex-card" data-slug="${esc(p.id)}" href="${pageHref(p.id)}">
      <span class="ex-card-head">${dot(p.type)}<span class="ex-card-title">${esc(p.title)}</span></span>
      ${extra ? `<span class="ex-card-extra">${extra}</span>` : ""}
      <span class="ex-card-preview">${esc(p.preview || "")}</span>
      <span class="ex-card-meta">${esc(meta.join(" · "))}</span>
    </a>`;
  }
  function row(p, right) {
    return `<li>${dot(p.type)}${pageLink(p.id)}<span class="ex-row-right">${right || ""}</span></li>`;
  }
  function section(title, hint, body, cls) {
    return `<section class="ex-section ${cls || ""}"><h2>${esc(title)}</h2>${hint ? `<p class="ex-hint">${hint}</p>` : ""}${body}</section>`;
  }

  // ---------- home ----------
  function renderHome() {
    currentSlug = null;
    document.title = "Thesis Wiki — Explore";
    const all = [...pages.values()];
    const by = (t) => all.filter((p) => p.type === t);
    const count = {};
    all.forEach((p) => { count[p.type] = (count[p.type] || 0) + 1; });

    const themes = by("topic").filter((p) => p.out > 0).sort((a, b) => b.out + b.in - (a.out + a.in));
    const people = by("person").sort((a, b) => b.in - a.in);
    const questions = by("question").filter((p) => p.maturity !== "resolved").sort((a, b) => b.in + b.out - (a.in + a.out));
    const deep = all.filter((p) => (p.type === "paper" || p.type === "part") && DEPTH_RANK[p.depth] >= 2)
      .sort((a, b) => DEPTH_RANK[b.depth] - DEPTH_RANK[a.depth] || b.words - a.words);
    const recent = [...all].sort((a, b) => b.mtime - a.mtime).slice(0, 10);
    const hubs = all.filter((p) => p.type !== "topic" && p.type !== "person").sort((a, b) => b.in - a.in).slice(0, 10);
    const thin = all.filter((p) => (p.type === "paper" || p.type === "part") && p.in >= 3 && (DEPTH_RANK[p.depth] || 0) < 2 && p.words < 450)
      .sort((a, b) => b.in - a.in).slice(0, 10);
    const orphans = all.filter((p) => p.in === 0 && p.type !== "topic");

    const chips = TYPE_ORDER.filter((t) => count[t]).map((t) =>
      `<a class="ex-chip" href="#/browse/${t}">${dot(t)}${esc(TYPE_LABEL[t])} <b>${count[t]}</b></a>`).join("");

    main.innerHTML = `
      <header class="ex-hero">
        <h1>Explore the vault</h1>
        <p class="subtle">${all.length} pages · ${indexData.links.length} links · ${questions.length} open questions · ${deep.length} real digests</p>
        <div class="ex-chips">${chips}</div>
      </header>
      ${section("Start from a theme", "Each theme page is a map into one research direction.",
        `<div class="ex-grid">${themes.slice(0, 9).map((p) => card(p)).join("")}</div>${themes.length > 9 ? `<p class="ex-more"><a href="#/browse/theme">All ${themes.length} themes →</a></p>` : ""}`)}
      ${section("Open questions", "The live threads — what the vault is actually trying to decide.",
        `<div class="ex-grid">${questions.slice(0, 9).map((p) => card(p)).join("")}</div>`)}
      ${section("People", "", `<div class="ex-grid ex-grid-tight">${people.map((p) => card(p)).join("")}</div>`)}
      <div class="ex-two">
        ${section("Read in depth", "Papers with a real write-up, deepest first.",
          `<ul class="ex-rows">${deep.slice(0, 12).map((p) => row(p, `<span class="ex-badge ex-depth-${p.depth}">${p.depth}</span>`)).join("")}</ul>`)}
        ${section("Recently touched", "", `<ul class="ex-rows">${recent.map((p) => row(p, ago(p.mtime))).join("")}</ul>`)}
      </div>
      <div class="ex-two">
        ${section("Most cited, thinnest notes", "Heavily linked papers that are still stubs — the best candidates to digest next.",
          `<ul class="ex-rows">${thin.map((p) => row(p, `${p.in} links · ${p.words}w`)).join("") || "<li class='subtle'>None — nice.</li>"}</ul>`)}
        ${section("Hubs", "Non-theme pages with the most inbound links.",
          `<ul class="ex-rows">${hubs.map((p) => row(p, `${p.in}↘`)).join("")}</ul>`)}
      </div>
      <div class="ex-two">
        ${section(`Wanted pages (${indexData.wanted_total})`, "Linked to, but not written yet. Count = how many pages ask for it.",
          `<ul class="ex-rows">${indexData.wanted.slice(0, 10).map((w) =>
            `<li><span class="wl-missing">${esc(w.id)}</span><span class="ex-row-right">${w.count}× · from ${w.from.slice(0, 2).map((s) => pageLink(s)).join(", ")}</span></li>`).join("")}</ul>`)}
        ${section(`Orphans (${orphans.length})`, "Nothing links here. Chats and mail are excluded.",
          `<ul class="ex-rows">${orphans.slice(0, 10).map((p) => row(p, TYPE_LABEL[p.type] || p.type)).join("")}</ul>`)}
      </div>`;
    rail.innerHTML = "";
    renderToc([]);
    renderSideLists();
  }

  // ---------- browse ----------
  function renderBrowse(type, sort) {
    currentSlug = null;
    sort = sort || "links";
    const list = [...pages.values()].filter((p) => p.type === type);
    const sorters = {
      links: (a, b) => b.in + b.out - (a.in + a.out),
      recent: (a, b) => b.mtime - a.mtime,
      title: (a, b) => a.title.localeCompare(b.title),
      year: (a, b) => (b.year || 0) - (a.year || 0),
      length: (a, b) => b.words - a.words,
    };
    list.sort(sorters[sort] || sorters.links);
    const tabs = Object.keys(sorters).map((k) =>
      `<a class="ex-tab${k === sort ? " active" : ""}" href="#/browse/${type}/${k}">${k}</a>`).join("");
    main.innerHTML = `<header class="ex-hero"><p class="ex-crumb"><a href="#/">Explore</a> / browse</p>
      <h1>${dot(type)} ${esc(TYPE_LABEL[type] || type)} <span class="subtle">${list.length}</span></h1>
      <div class="ex-tabs">sort: ${tabs}</div></header>
      <div class="ex-grid">${list.map((p) => card(p)).join("")}</div>`;
    rail.innerHTML = "";
    renderToc([]);
    renderSideLists();
  }

  // ---------- local graph ----------
  function localGraph(slug) {
    const outs = outAdj.get(slug) || new Set();
    const ins = inAdj.get(slug) || new Set();
    let ring = [...neighbours(slug)];
    const total = ring.length;
    if (!total) return `<p class="subtle">No links yet.</p>`;
    const deg = (s) => neighbours(s).size;
    ring.sort((a, b) => deg(b) - deg(a));
    ring = ring.slice(0, RING_MAX);
    ring.sort((a, b) => TYPE_ORDER.indexOf(typeOf(a)) - TYPE_ORDER.indexOf(typeOf(b)) || a.localeCompare(b));

    const W = 320, C = W / 2, R = 122;
    const pos = new Map();
    ring.forEach((s, i) => {
      const ang = (2 * Math.PI * i) / ring.length - Math.PI / 2;
      pos.set(s, [C + R * Math.cos(ang), C + R * Math.sin(ang), ang]);
    });
    const inRing = new Set(ring);
    let cross = "";
    ring.forEach((s) => {
      (outAdj.get(s) || []).forEach((t) => {
        if (t !== slug && inRing.has(t)) {
          const [x1, y1] = pos.get(s), [x2, y2] = pos.get(t);
          cross += `<path class="lg-cross" d="M${x1.toFixed(1)},${y1.toFixed(1)} Q${C},${C} ${x2.toFixed(1)},${y2.toFixed(1)}"/>`;
        }
      });
    });
    let spokes = "", nodes = "";
    const labelled = ring.length <= 20;
    ring.forEach((s) => {
      const [x, y, ang] = pos.get(s);
      const both = outs.has(s) && ins.has(s);
      const cls = both ? "lg-both" : outs.has(s) ? "lg-out" : "lg-in";
      spokes += `<line class="lg-spoke ${cls}" x1="${C}" y1="${C}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}"/>`;
      const r = Math.min(9, 4 + Math.sqrt(deg(s)) * 0.9);
      let label = "";
      if (labelled) {
        const right = Math.cos(ang) >= 0;
        const lx = x + (right ? r + 3 : -r - 3);
        const t = titleOf(s);
        label = `<text class="lg-label" x="${lx.toFixed(1)}" y="${(y + 3).toFixed(1)}" text-anchor="${right ? "start" : "end"}">${esc(t.length > 15 ? t.slice(0, 14) + "…" : t)}</text>`;
      }
      nodes += `<a href="${pageHref(s)}" class="lg-node wl" data-slug="${esc(s)}"><circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r.toFixed(1)}" fill="${color(typeOf(s))}"/>${label}</a>`;
    });
    const pad = labelled ? 72 : 12;
    return `<svg class="ex-lg" viewBox="${-pad} -6 ${W + pad * 2} ${W + 12}" role="img" aria-label="Local link graph">
      ${cross}${spokes}
      <circle class="lg-centre" cx="${C}" cy="${C}" r="11" fill="${color(typeOf(slug))}"/>
      ${nodes}</svg>
      <p class="ex-lg-legend"><span class="lg-key lg-key-out"></span>links to <span class="lg-key lg-key-in"></span>linked from <span class="lg-key lg-key-both"></span>both${total > ring.length ? ` · showing ${ring.length} of ${total}` : ""}</p>`;
  }

  // ---------- page ----------
  function metaChips(data) {
    const fm = data.frontmatter, c = data.card, out = [];
    out.push(`<a class="ex-chip" href="#/browse/${esc(c.type)}">${dot(c.type)}${esc(TYPE_LABEL[c.type] || c.type)}</a>`);
    if (fm.book && c.type === "part") out.push(`<a class="ex-chip" href="${pageHref(fm.book)}" title="the book this part belongs to">${dot("book")}book · pp. ${esc(String(fm.section_pages || "").replace("-", "–"))}</a>`);
    if (c.depth) out.push(`<span class="ex-badge ex-depth-${esc(c.depth)}" title="digestion depth">${esc(c.depth)}</span>`);
    if (c.maturity) out.push(`<span class="ex-badge">${esc(c.maturity)}</span>`);
    if (c.year) out.push(`<span class="ex-badge">${c.year}</span>`);
    (c.areas || []).forEach((a) => {
      const theme = `theme-${a}`;
      out.push(pages.has(theme) ? `<a class="ex-chip" href="${pageHref(theme)}">#${esc(a)}</a>` : `<span class="ex-chip ex-chip-flat">#${esc(a)}</span>`);
    });
    const authors = fm.authors;
    const line2 = [];
    if (authors) line2.push(esc(Array.isArray(authors) ? authors.join(", ") : authors));
    if (fm.affiliation) line2.push(esc(fm.affiliation));
    if (fm.url && /^https?:/i.test(fm.url)) line2.push(`<a class="ext" href="${esc(fm.url)}" target="_blank" rel="noopener noreferrer">source ↗</a>`);
    if (fm.scholar) line2.push(`<a class="ext" href="${esc(fm.scholar)}" target="_blank" rel="noopener noreferrer">scholar ↗</a>`);
    if (fm.raw && fm.raw !== "none") line2.push(`<code class="ex-raw" title="click to copy" data-copy="${esc(fm.raw)}">${esc(fm.raw)}</code>`);
    return `<div class="ex-chips">${out.join("")}</div>${line2.length ? `<p class="ex-byline">${line2.join(" · ")}</p>` : ""}`;
  }

  function railList(title, items, empty) {
    return `<section class="ex-rail-sec"><h3>${title}</h3>${items.length ? `<ul class="ex-rail-list">${items.join("")}</ul>` : `<p class="subtle">${empty}</p>`}</section>`;
  }

  async function renderPage(slug) {
    if (!pages.has(slug)) {
      main.innerHTML = `<header class="ex-hero"><h1>No page “${esc(slug)}”</h1><p class="subtle">It may be a wanted page — linked to but not written yet.</p><p><a href="#/">Back to Explore</a></p></header>`;
      rail.innerHTML = "";
      return;
    }
    const data = await getJSON(`/api/explore/page?slug=${encodeURIComponent(slug)}`);
    if (decodeURIComponent((location.hash.split("/")[2] || "")) !== slug) return; // navigated away meanwhile
    currentSlug = slug;
    pushTrail(slug);
    const c = data.card;
    document.title = `${c.title} — Explore`;
    const pinned = loadList(PINS_KEY).includes(slug);
    const { fragment, toc } = renderMarkdown(data.markdown);
    // A concept's (or collection's) source pages: its source-layer neighbours, folded until asked for.
    const srcIds = TYPE_LAYER[c.type] === "source" ? []
      : [...new Set([...(outAdj.get(slug) || []), ...(inAdj.get(slug) || [])])]
        .filter((id) => TYPE_LAYER[typeOf(id)] === "source").sort();

    main.innerHTML = `<header class="ex-page-head">
        <p class="ex-crumb"><a href="#/">Explore</a> / <a href="#/browse/${esc(c.type)}">${esc(TYPE_LABEL[c.type] || c.type)}</a></p>
        <h1>${esc(c.title)}</h1>
        ${metaChips(data)}
        <div class="ex-actions">
          <button type="button" class="ex-btn" id="btn-pin">${pinned ? "★ Pinned" : "☆ Pin"}</button>
          <a class="ex-btn" href="/graph?focus=${encodeURIComponent(slug)}">Show in graph</a>
          ${srcIds.length ? `<button type="button" class="ex-btn" id="btn-see-sources" aria-expanded="false">See sources (${srcIds.length})</button>` : ""}
          <a class="ex-btn" href="obsidian://open?file=${encodeURIComponent(data.path)}">Open in Obsidian</a>
          <span class="subtle">${c.words} words · edited ${ago(c.mtime)}</span>
        </div>
      </header>
      <article class="ex-article" id="ex-article"></article>`;
    $("ex-article").appendChild(fragment);
    if (data.broken.length) {
      $("ex-article").insertAdjacentHTML("beforeend",
        `<p class="ex-broken"><b>${data.broken.length} wanted link${data.broken.length > 1 ? "s" : ""}:</b> ${data.broken.map((b) => `<span class="wl-missing">${esc(b)}</span>`).join(" ")}</p>`);
    }

    const back = data.backlinks.map((b) =>
      `<li>${dot(typeOf(b.id))}${pageLink(b.id)}${b.context ? `<span class="ex-ctx">${esc(b.context)}</span>` : ""}</li>`);
    const sugg = data.suggested.map((s) =>
      `<li>${dot(typeOf(s.id))}${pageLink(s.id)}<span class="ex-ctx">${s.shared} shared neighbours — via ${s.via.map((v) => pageLink(v)).join(", ")}</span></li>`);
    const outs = data.outbound.map((s) => `<li>${dot(typeOf(s))}${pageLink(s)}</li>`);

    rail.innerHTML = `
      <section class="ex-rail-sec"><h3>Neighbourhood <span class="subtle">${c.in}↘ ${c.out}↗</span></h3>${localGraph(slug)}</section>
      ${srcIds.length ? `<div id="ex-sources" hidden>${railList(`Sources <span class="subtle">${srcIds.length}</span>`,
        srcIds.map((id) => `<li>${dot(typeOf(id))}${pageLink(id)}</li>`), "")}</div>` : ""}
      <section class="ex-rail-sec"><h3>Connect to…</h3>
        <form id="connect-form" class="ex-connect"><input list="ex-all-pages" id="connect-to" placeholder="another page" autocomplete="off"><button type="submit" class="ex-btn">Find path</button></form>
      </section>
      ${railList(`Linked from <span class="subtle">${back.length}</span>`, back, "Nothing links here yet.")}
      ${railList(`Related but unlinked`, sugg, "No strong candidates.")}
      ${railList(`Links to <span class="subtle">${outs.length}</span>`, outs, "No outgoing links.")}`;
    const seeBtn = $("btn-see-sources");
    if (seeBtn) seeBtn.addEventListener("click", () => {
      const box = $("ex-sources");
      box.hidden = !box.hidden;
      seeBtn.setAttribute("aria-expanded", String(!box.hidden));
      seeBtn.textContent = `${box.hidden ? "See" : "Hide"} sources (${srcIds.length})`;
      if (!box.hidden) box.scrollIntoView({ block: "nearest" });
    });
    renderToc(toc);
    renderSideLists();
    main.scrollTop = 0;
    window.scrollTo(0, 0);
  }

  // ---------- search ----------
  async function renderSearch(q) {
    currentSlug = null;
    main.innerHTML = `<header class="ex-hero"><p class="ex-crumb"><a href="#/">Explore</a> / search</p><h1>“${esc(q)}”</h1><p class="subtle">Searching…</p></header>`;
    rail.innerHTML = "";
    renderToc([]);
    const data = await getJSON(`/api/explore/search?q=${encodeURIComponent(q)}`);
    const mark = (text) => {
      let h = esc(text);
      q.toLowerCase().split(/\s+/).filter((t) => t.length > 1).forEach((t) => {
        h = h.replace(new RegExp(`(${t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "ig"), "<mark>$1</mark>");
      });
      return h;
    };
    main.innerHTML = `<header class="ex-hero"><p class="ex-crumb"><a href="#/">Explore</a> / search</p>
      <h1>“${esc(q)}”</h1><p class="subtle">${data.total} page${data.total === 1 ? "" : "s"}${data.total > data.hits.length ? ` · showing ${data.hits.length}` : ""}</p>
      ${data.total ? `<p><a class="ex-btn" href="/graph?search=${encodeURIComponent(q)}">Visualize in graph</a></p>` : ""}</header>
      <ul class="ex-results">${data.hits.map((h) =>
        `<li><a class="ex-result wl" data-slug="${esc(h.id)}" href="${pageHref(h.id)}">${dot(h.type)}<span class="ex-result-title">${mark(h.title)}</span><span class="ex-result-snip">${mark(h.snippet)}</span></a></li>`).join("")
        || "<li class='subtle'>No matches.</li>"}</ul>`;
    renderSideLists();
  }

  // ---------- path ----------
  async function renderPath(a, b) {
    currentSlug = null;
    renderToc([]);
    rail.innerHTML = "";
    const form = `<form id="path-form" class="ex-pathform">
        <input list="ex-all-pages" id="path-a" placeholder="from page" value="${esc(a || "")}" autocomplete="off">
        <span>→</span>
        <input list="ex-all-pages" id="path-b" placeholder="to page" value="${esc(b || "")}" autocomplete="off">
        <button type="submit" class="ex-btn">Find path</button>
      </form>
      <p class="ex-hint">Try: ${[["gil-kalai", "nadav-cohen"], ["gal-vardi", "theme-quantum"], ["entropy", "tensor-rank"]]
        .filter(([x, y]) => pages.has(x) && pages.has(y))
        .map(([x, y]) => `<a href="#/path/${x}/${y}">${esc(titleOf(x))} → ${esc(titleOf(y))}</a>`).join(" · ")}</p>`;
    const head = `<header class="ex-hero"><p class="ex-crumb"><a href="#/">Explore</a> / connect</p><h1>How are two pages connected?</h1>
      <p class="subtle">Shortest chain of links in either direction, with the sentence that makes each link.</p>${form}</header>`;
    if (!a || !b) { main.innerHTML = head; renderSideLists(); return; }
    main.innerHTML = head + `<p class="subtle">Searching…</p>`;
    let data;
    try {
      data = await getJSON(`/api/explore/path?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);
    } catch (_e) {
      main.innerHTML = head + `<p class="ex-broken">One of those pages does not exist. Pick from the suggestions while typing.</p>`;
      return;
    }
    let body;
    if (data.distance == null) {
      body = `<p class="ex-broken">No chain of links connects these two pages — they sit in separate islands of the graph.</p>`;
    } else if (data.distance === 0) {
      body = `<p class="subtle">Same page.</p>`;
    } else {
      body = `<p class="subtle">${data.distance} hop${data.distance > 1 ? "s" : ""} · ${data.paths.length} shortest route${data.paths.length > 1 ? "s shown" : ""}</p>` +
        data.paths.map((p, i) => `<section class="ex-path"><h2>Route ${i + 1}</h2><ol class="ex-hops">
          <li class="ex-hop-node">${dot(typeOf(p.nodes[0]))}${pageLink(p.nodes[0])}</li>
          ${p.hops.map((h) => `<li class="ex-hop-edge"><span class="ex-hop-arrow">${h.dir === "forward" ? "↓ links to" : "↑ is linked from"}</span>${h.context ? `<span class="ex-ctx">${esc(h.context)}</span>` : ""}</li>
            <li class="ex-hop-node">${dot(typeOf(h.to))}${pageLink(h.to)}</li>`).join("")}
        </ol></section>`).join("");
    }
    main.innerHTML = head + body;
    renderSideLists();
  }

  // ---------- search box ----------
  let suggestItems = [];
  let suggestIdx = -1;
  function scoreTitle(p, q) {
    const t = p.title.toLowerCase(), s = p.id.toLowerCase();
    if (t === q) return 100;
    if (t.startsWith(q)) return 80;
    if (t.includes(` ${q}`)) return 60;
    if (t.includes(q)) return 50;
    if (s.includes(q.replace(/\s+/g, "-"))) return 40;
    const terms = q.split(/\s+/);
    return terms.length > 1 && terms.every((x) => t.includes(x) || s.includes(x)) ? 30 : 0;
  }
  function updateSuggest() {
    const box = $("ex-suggest");
    const q = $("ex-search").value.trim().toLowerCase();
    if (!q) { box.classList.add("hidden"); suggestItems = []; return; }
    const hits = [...pages.values()].map((p) => [scoreTitle(p, q) + Math.min(p.in, 20) / 10, p])
      .filter(([sc]) => sc >= 30).sort((x, y) => y[0] - x[0]).slice(0, 8).map(([, p]) => p);
    suggestItems = hits.map((p) => ({ href: pageHref(p.id) }));
    suggestItems.push({ href: `#/search/${encodeURIComponent(q)}` });
    suggestItems.push({ href: `/graph?search=${encodeURIComponent(q)}`, page: true });
    suggestIdx = hits.length ? 0 : suggestItems.length - 1;
    box.innerHTML = hits.map((p, i) =>
      `<a role="option" class="ex-sg${i === suggestIdx ? " active" : ""}" href="${pageHref(p.id)}">${dot(p.type)}<span>${esc(p.title)}</span><small>${esc(TYPE_LABEL[p.type] || p.type)}</small></a>`).join("") +
      `<a role="option" class="ex-sg ex-sg-full${suggestIdx === hits.length ? " active" : ""}" href="#/search/${encodeURIComponent(q)}">Search inside all pages for “${esc(q)}” ↵</a>` +
      `<a role="option" class="ex-sg ex-sg-full${suggestIdx === hits.length + 1 ? " active" : ""}" href="/graph?search=${encodeURIComponent(q)}">Visualize “${esc(q)}” in graph</a>`;
    box.classList.remove("hidden");
  }
  function moveSuggest(d) {
    if (!suggestItems.length) return;
    suggestIdx = (suggestIdx + d + suggestItems.length) % suggestItems.length;
    [...$("ex-suggest").children].forEach((n, i) => n.classList.toggle("active", i === suggestIdx));
  }
  function closeSuggest() {
    $("ex-suggest").classList.add("hidden");
  }

  // ---------- hover preview ----------
  let hoverTimer = null;
  function showHover(a) {
    const p = pages.get(a.dataset.slug);
    if (!p || a.dataset.slug === currentSlug) return;
    const box = $("ex-hover");
    box.innerHTML = `<div class="ex-hover-head">${dot(p.type)}<b>${esc(p.title)}</b></div>
      <p>${esc(p.preview || "(no summary yet)")}</p>
      <small>${esc(TYPE_LABEL[p.type] || p.type)}${p.depth ? ` · ${esc(p.depth)}` : p.maturity ? ` · ${esc(p.maturity)}` : ""} · ${p.in}↘ ${p.out}↗ · ${p.words}w</small>`;
    box.classList.remove("hidden");
    const r = a.getBoundingClientRect();
    const w = 340;
    let left = Math.min(Math.max(8, r.left), window.innerWidth - w - 8);
    let top = r.bottom + 8;
    if (top + box.offsetHeight > window.innerHeight - 8) top = Math.max(8, r.top - box.offsetHeight - 8);
    box.style.left = `${left}px`;
    box.style.top = `${top}px`;
  }
  function hideHover() {
    clearTimeout(hoverTimer);
    $("ex-hover").classList.add("hidden");
  }

  // ---------- routing ----------
  async function route() {
    hideHover();
    closeSuggest();
    const parts = location.hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent);
    try {
      if (parts[0] === "p" && parts[1]) await renderPage(parts[1]);
      else if (parts[0] === "search" && parts[1]) await renderSearch(parts[1]);
      else if (parts[0] === "path") await renderPath(parts[1], parts[2]);
      else if (parts[0] === "browse" && parts[1]) renderBrowse(parts[1], parts[2]);
      else renderHome();
    } catch (err) {
      main.innerHTML = `<p class="ex-broken">Could not load: ${esc(err.message)}</p>`;
    }
  }

  function randomPage() {
    const pool = [...pages.values()].filter((p) => p.words > 150 && !p.id.startsWith("source-chat-") && !p.id.startsWith("source-mail-"));
    const p = pool[Math.floor(Math.random() * pool.length)];
    if (p) location.hash = pageHref(p.id);
  }

  function resolveInput(v) {
    v = (v || "").trim();
    if (pages.has(v)) return v;
    const low = v.toLowerCase();
    const hit = [...pages.values()].find((p) => p.title.toLowerCase() === low);
    return hit ? hit.id : v;
  }

  function bind() {
    const search = $("ex-search");
    search.addEventListener("input", updateSuggest);
    search.addEventListener("focus", updateSuggest);
    search.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); moveSuggest(1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); moveSuggest(-1); }
      else if (e.key === "Enter" && suggestItems[suggestIdx]) {
        e.preventDefault();
        const it = suggestItems[suggestIdx];
        if (it.page) { location.href = it.href; return; }
        location.hash = it.href;
        search.value = "";
        search.blur();
      } else if (e.key === "Escape") { search.blur(); closeSuggest(); }
    });
    document.addEventListener("click", (e) => {
      if (!e.target.closest(".ex-search")) closeSuggest();
      if (e.target.closest(".ex-sg")) { search.value = ""; closeSuggest(); }
      const anchor = e.target.closest("[data-anchor]");
      if (anchor) {
        e.preventDefault();
        const t = document.getElementById(anchor.dataset.anchor);
        if (t) t.scrollIntoView({ behavior: "smooth", block: "start" });
      }
      const copy = e.target.closest("[data-copy]");
      if (copy && navigator.clipboard) {
        navigator.clipboard.writeText(copy.dataset.copy).then(() => {
          copy.classList.add("copied");
          setTimeout(() => copy.classList.remove("copied"), 900);
        }).catch(() => {});
      }
      if (e.target.id === "btn-pin") togglePin(currentSlug);
    });
    document.addEventListener("submit", (e) => {
      if (e.target.id === "path-form") {
        e.preventDefault();
        location.hash = `#/path/${encodeURIComponent(resolveInput($("path-a").value))}/${encodeURIComponent(resolveInput($("path-b").value))}`;
      } else if (e.target.id === "connect-form") {
        e.preventDefault();
        const to = resolveInput($("connect-to").value);
        if (to && currentSlug) location.hash = `#/path/${encodeURIComponent(currentSlug)}/${encodeURIComponent(to)}`;
      }
    });
    $("btn-random").addEventListener("click", randomPage);
    $("btn-clear-trail").addEventListener("click", () => { saveList(TRAIL_KEY, []); renderSideLists(); });

    document.addEventListener("mouseover", (e) => {
      const a = e.target.closest("a.wl[data-slug]");
      if (!a) return;
      clearTimeout(hoverTimer);
      hoverTimer = setTimeout(() => showHover(a), 320);
    });
    document.addEventListener("mouseout", (e) => {
      if (e.target.closest("a.wl[data-slug]")) hideHover();
    });
    window.addEventListener("scroll", hideHover, true);

    document.addEventListener("keydown", (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey) {
        if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); search.focus(); search.select(); }
        return;
      }
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) return;
      if (e.key === "/") { e.preventDefault(); search.focus(); search.select(); }
      else if (e.key === "r") randomPage();
      else if (e.key === "h") location.hash = "#/";
      else if (e.key === "p") togglePin(currentSlug);
      else if (e.key === "g" && currentSlug) location.href = `/graph?focus=${encodeURIComponent(currentSlug)}`;
    });
    window.addEventListener("hashchange", route);
  }

  async function boot() {
    bind();
    try {
      applySchema(await getJSON("/api/schema"));
      indexData = await getJSON("/api/explore/index");
    } catch (err) {
      main.innerHTML = `<p class="ex-broken">Could not load the vault index: ${esc(err.message)}</p>`;
      return;
    }
    indexData.pages.forEach((p) => { pages.set(p.id, p); outAdj.set(p.id, new Set()); inAdj.set(p.id, new Set()); });
    indexData.links.forEach(([s, t]) => { outAdj.get(s).add(t); inAdj.get(t).add(s); });
    const dl = document.createElement("datalist");
    dl.id = "ex-all-pages";
    dl.innerHTML = indexData.pages.map((p) => `<option value="${esc(p.id)}">${esc(p.title)}</option>`).join("");
    document.body.appendChild(dl);
    route();
  }

  document.addEventListener("DOMContentLoaded", boot);
})();
