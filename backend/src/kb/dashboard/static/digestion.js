(function () {
  // One sentence per term. Panels, tooltips and the glossary all read from here.
  const STAGE_TIP = {
    inbox: "In raw/inbox/, waiting to be cataloged.",
    failed: "Cataloging tried and stopped — the reason is shown on the file.",
    uncataloged: "Already in a raw/ format folder but never cataloged: no record, no collection, no note.",
    cataloged: "Filed in its format folder with a record (collection, catalog stub or course row).",
    "not-digested": "Cataloged, but no wiki note has been written from it yet — the real backlog.",
    partial: "A book or notebook with only some page-range parts written up.",
    digested: "Has a wiki note.",
    easy: "Digested by a skim: Problem and Main result written from the abstract (~2–4k tokens).",
    full: "Digested by a proper read: method, results and key equations, linked into the graph (~8–12k tokens).",
    deep: "Digested by a close, thesis-critical read with proofs and neighbouring papers (~25–40k+ tokens).",
    skipped: "Deliberately not worth a note — a decision, not neglect.",
  };
  const TERM_TIP = {
    "ink overlay": "A reMarkable file holding only your pen strokes for another PDF — shown with that PDF, never on its own.",
    duplicate: "A byte-identical copy of another file — shown with the original.",
    figure: "An image downloaded with a web clip (scrap-wordpress) — part of that clip, never a backlog item.",
    attachment: "A file attached to an email thread — part of the thread.",
    transcription: "parsed.md: an agent transcription of an email thread — part of the thread.",
    collection: "The course, series, book or researcher a file belongs to (corpus.tsv `collection`).",
    modified: "When the file last changed on disk — not when you read it.",
    last_op: "Newest first, by the last operation on each file — cataloged, or its wiki page committed (digest, refine…). Files nothing has touched yet fall back to when they changed on disk. One row per file; local time.",
    internal: "A wiki page may be wrong or stale against its own source — fix the page.",
    external: "Two digested papers seem to disagree — note the tension on both.",
    cosmetic: "Graph hygiene: near-duplicate one-liners, one-way links to themes.",
  };
  const FORMAT_TIP = {
    inbox: "The single unsorted drop zone.",
    "printed-docs": "Typed documents: papers, books, course books, typed notes, blog posts.",
    handwritten: "Your own handwriting: reMarkable notebooks, recaps and summaries.",
    presentations: "Lecture decks and slides.",
    "llm-chats": "Exported conversations with LLMs.",
    emails: "Email threads — one item per thread, attachments folded in.",
    "web-clips": "Web pages saved with the Web Clipper.",
    images: "Screenshots and figures.",
  };
  const STAGES = ["inbox", "failed", "uncataloged", "not-digested", "partial", "easy", "full", "deep", "digested", "skipped"];
  const STAGE_LABEL = { "not-digested": "not digested" };
  const DIGESTED = new Set(["easy", "full", "deep", "digested"]);
  const CATALOGED = new Set(["not-digested", "partial", "easy", "full", "deep", "digested", "skipped"]);
  const KIND_ORDER = ["inbox", "printed-docs", "handwritten", "presentations", "llm-chats", "emails", "web-clips", "images"];
  const RELATION = { ink: "ink overlay", dupe: "duplicate", asset: "figure", sidecar: "transcription" };
  const VIEWS = ["list", "board", "chron"];
  const GROUP_BY = ["none", "format", "collection", "stage", "depth"];
  const PAGE_SIZE = 300, CARD_CAP = 30, CELL_CAP = 8;

  let snapshot = null, units = [], byKey = new Map(), titles = {};
  let coherenceFilter = "all", collFilter = "open", digestOpen = false;
  const state = { view: "list", group: "none", rows: "none", status: "", q: "", kind: "", coll: "", sort: "stage", asc: true, item: "" };
  let shown = PAGE_SIZE, order = [], cursor = -1;
  const selected = new Set(), collapsedGroups = new Set(), expandedCells = new Set();

  const el = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const label = (s) => STAGE_LABEL[s] || s;
  const obsidianUri = (path) => `obsidian://open?file=${encodeURIComponent(path)}`;
  const hostOf = (url) => { try { return new URL(url).hostname.replace(/^www\./, ""); } catch (_e) { return url; } };
  const rawUrl = (path) => `/raw-file?path=${encodeURIComponent(path)}`;
  const thumbUrl = (path, w = 360) => `/raw-thumb?path=${encodeURIComponent(path)}&w=${w}`;
  const newTab = (path, text, cls = "") => `<a class="${cls}" href="${rawUrl(path)}" target="_blank" rel="noopener noreferrer" title="Open in a new tab">${esc(text || path)}</a>`;
  const slugLink = (slug, text) => `<a href="${obsidianUri(`wiki/${slug}.md`)}" title="Open the note in Obsidian">${esc(text || slug)}</a>`;
  const empty = (msg) => `<p class="empty-state">${esc(msg)}</p>`;
  const collName = (slug) => titles[slug] || slug;
  const pill = (s, filter = true) => `<span class="status-pill s-${esc(s)}${filter ? " js-filter" : ""}"${filter ? ` data-f-status="${esc(s)}"` : ""} title="${esc(STAGE_TIP[s] || "")}">${esc(label(s))}</span>`;
  const kindChip = (k) => `<span class="kind-chip js-filter" data-f-kind="${esc(k)}" title="${esc(FORMAT_TIP[k] || "")} — click to filter">${esc(k)}</span>`;
  const collChip = (c) => `<span class="coll-chip js-filter" data-f-coll="${esc(c)}" title="${esc(c)} — click to filter">${esc(collName(c))}</span>`;
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
  };
  const fmtSize = (kb) => (kb >= 1024 ? `${(kb / 1024).toFixed(1)} MB` : `${Math.round(kb)} KB`);
  function fmtAge(days) {
    if (days == null || !isFinite(days)) return "—";
    if (days < 1) return "today";
    if (days < 60) return `${Math.round(days)}d`;
    if (days < 730) return `${Math.round(days / 30)}mo`;
    return `${(days / 365).toFixed(1)}y`;
  }
  const OP_TIP = {
    catalog: "Moved from the inbox into raw/ (meta/.catalog/events.jsonl).",
    digest: "Its wiki page was written or re-digested (kb(digest) commit).",
    refine: "Its wiki page was edited (kb(refine) commit).",
    distill: "Its wiki page was patched by a distill apply (kb(distill) commit).",
    edit: "Its wiki page changed in a commit that is not a kb(op) step.",
    modified: "No recorded operation — this is when the file last changed on disk.",
  };
  // "YYYY-MM-DD HH:MM" in the browser's local time zone
  function localStamp(d) {
    const p = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  }
  const byOrder = (list) => (a, b) => {
    const ia = list.indexOf(a), ib = list.indexOf(b);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || String(a).localeCompare(String(b));
  };

  /* ---------- items: one per file or email thread; companions fold into their parent ---------- */

  function stageOf(f) {
    if (f.ingestion !== "cataloged") return f.ingestion;
    if (f.digestion === "digested") return f.depth || "digested";
    return f.digestion === "not digested" ? "not-digested" : f.digestion;
  }

  function relationOf(f) {
    if (RELATION[f.status]) return RELATION[f.status];
    return f.companion_of ? "attachment" : "";
  }

  function buildUnits(items) {
    const map = new Map();
    for (const it of items) {
      if (!map.has(it.unit)) map.set(it.unit, []);
      map.get(it.unit).push(it);
    }
    const now = Date.now(), out = [];
    for (const [key, files] of map) {
      const primary = files.find((f) => !f.companion_of) || files[0];
      const companions = files.filter((f) => f !== primary);
      const isThread = primary.name === "thread.md";
      const colls = [...new Set(files.flatMap((f) => f.collections))];
      const age = Math.min(...files.map((f) => f.age_days ?? Infinity));
      const last = files.reduce((m, f) => ((f.last_op_at || "") > (m.last_op_at || "") ? f : m), files[0]);
      out.push({
        last_op: last.last_op || "",
        last_op_at: last.last_op_at || "",
        last_at: last.last_op_at ? new Date(last.last_op_at) : null,
        key, files, primary, companions, isThread, colls,
        kind: primary.kind,
        name: isThread ? key.split("/").pop() : primary.name,
        stage: stageOf(primary),
        slug: primary.slug || "",
        size_kb: files.reduce((n, f) => n + (f.size_kb || 0), 0),
        age_days: age,
        mtime: isFinite(age) ? new Date(now - age * 86400000) : null,
        next: primary.next,
        failure: primary.failure,
        search: files.map((f) => `${f.path} ${f.slug}`).concat(colls, colls.map(collName)).join(" ").toLowerCase(),
      });
    }
    return out;
  }

  /* ---------- dimensions: group-by (list groups, board columns) and board rows ---------- */

  function groupKey(u, dim = state.group) {
    switch (dim) {
      case "format": return u.kind;
      case "collection": return u.colls[0] || "";
      case "stage": return u.stage;
      case "depth": return DIGESTED.has(u.stage) ? u.stage : "not read";
      default: return "";
    }
  }
  const groupLabel = (k, dim = state.group) => (dim === "collection" ? (k ? collName(k) : "(no collection)") : dim === "stage" ? label(k) : k || "—");
  function groupTip(k, dim = state.group) {
    if (dim === "format") return FORMAT_TIP[k] || "";
    if (dim === "stage" || dim === "depth") return STAGE_TIP[k] || "Not digested yet.";
    if (dim === "collection") return k ? `${k} — click to filter` : "Files that belong to no course, series, book or researcher.";
    return "";
  }
  function groupSort(a, b, dim = state.group) {
    if (dim === "format") return byOrder(KIND_ORDER)(a, b);
    if (dim === "stage") return byOrder(STAGES)(a, b);
    if (dim === "depth") return byOrder(["deep", "full", "easy", "digested", "not read"])(a, b);
    if (dim === "collection") return (a ? 0 : 1) - (b ? 0 : 1) || groupLabel(a, dim).localeCompare(groupLabel(b, dim));
    return 0;
  }
  function groupName(k, dim = state.group) {
    return dim === "collection" && k
      ? `<span class="js-filter" data-f-coll="${esc(k)}" title="${esc(groupTip(k, dim))}">${esc(groupLabel(k, dim))}</span>`
      : `<span class="term" title="${esc(groupTip(k, dim))}">${esc(groupLabel(k, dim))}</span>`;
  }
  function grouped(list, dim = state.group) {
    const map = new Map();
    for (const u of list) {
      const k = groupKey(u, dim);
      if (!map.has(k)) map.set(k, []);
      map.get(k).push(u);
    }
    return [...map.entries()].sort((a, b) => groupSort(a[0], b[0], dim));
  }
  const stageCls = (dim, k) => (["stage", "depth", "none"].includes(dim) ? ` s-${esc(k === "not read" ? "not-digested" : k)}` : "");

  function stackBar(list, cls = "") {
    const counts = {};
    for (const u of list) counts[u.stage] = (counts[u.stage] || 0) + 1;
    if (!list.length) return `<div class="stack ${cls}"></div>`;
    return `<div class="stack ${cls}">${STAGES.filter((s) => counts[s]).map((s) =>
      `<span class="s-${s}" style="width:${(100 * counts[s] / list.length).toFixed(2)}%" title="${esc(label(s))}: ${counts[s]}"></span>`).join("")}</div>`;
  }

  /* ---------- URL state ---------- */

  let writingHash = false;
  function readHash() {
    const p = new URLSearchParams(location.hash.slice(1));
    state.view = VIEWS.includes(p.get("view")) ? p.get("view") : store.get("pipeline-view", "list");
    state.group = GROUP_BY.includes(p.get("group")) ? p.get("group") : store.get("pipeline-group", "none");
    state.rows = GROUP_BY.includes(p.get("rows")) ? p.get("rows") : store.get("pipeline-rows", "none");
    for (const k of ["status", "q", "kind", "coll", "item"]) state[k] = p.get(k) || "";
    state.sort = p.get("sort") || "stage";
    state.asc = p.get("dir") !== "desc";
  }
  function writeHash(push = true) {
    const p = new URLSearchParams();
    if (state.view !== "list") p.set("view", state.view);
    if (state.group !== "none") p.set("group", state.group);
    if (state.rows !== "none") p.set("rows", state.rows);
    for (const k of ["status", "q", "kind", "coll", "item"]) if (state[k]) p.set(k, state[k]);
    if (state.sort !== "stage") p.set("sort", state.sort);
    if (!state.asc) p.set("dir", "desc");
    const next = p.toString() ? `#${p}` : location.pathname;
    if (next !== location.hash && !(!p.toString() && !location.hash)) {
      writingHash = true;
      history[push ? "pushState" : "replaceState"](null, "", next);
      writingHash = false;
    }
    store.set("pipeline-view", state.view);
    store.set("pipeline-group", state.group);
    store.set("pipeline-rows", state.rows);
  }

  /* ---------- status panels ---------- */

  function segment(key, count, total, active, extra = "") {
    const weight = Math.max(count, total * 0.07);
    const bare = key.replace(/^@/, "");
    return `<button type="button" class="seg-btn s-${bare}${active ? " active" : ""}${count ? "" : " zero"}" data-status="${esc(key)}" ` +
      `style="flex-grow:${weight.toFixed(1)}" title="${esc(STAGE_TIP[bare] || "")}">` +
      `<span class="seg-count">${count}</span><span class="seg-label">${esc(label(bare))}${extra}</span></button>`;
  }

  function renderPanels() {
    const count = (pred) => units.filter(pred).length;
    const total = units.length;
    const cat = count((u) => CATALOGED.has(u.stage));
    el("funnel-ingestion").innerHTML =
      ["inbox", "failed", "uncataloged"].map((s) => segment(s, count((u) => u.stage === s), total, state.status === s)).join("") +
      segment("@cataloged", cat, total, state.status === "@cataloged");

    const dig = count((u) => DIGESTED.has(u.stage));
    const depthSegs = ["easy", "full", "deep", "digested"].map((s) => [s, count((u) => u.stage === s)]).filter(([s, n]) => n || s !== "digested");
    el("funnel-digestion").innerHTML =
      segment("not-digested", count((u) => u.stage === "not-digested"), cat, state.status === "not-digested") +
      segment("partial", count((u) => u.stage === "partial"), cat, state.status === "partial") +
      (digestOpen
        ? `<div class="seg-group" style="flex-grow:${Math.max(dig, cat * 0.07 * depthSegs.length).toFixed(1)}">` +
          `<button type="button" class="seg-collapse" id="digest-toggle" title="Fold back into one 'digested' segment">▾ digested · ${dig}</button>` +
          `<div class="seg-row">${depthSegs.map(([s, n]) => segment(s, n, cat, state.status === s)).join("")}</div></div>`
        : segment("@digested", dig, cat, state.status === "@digested", ` <span class="chev" id="digest-toggle" role="button" title="Split by read depth: easy · full · deep">▸</span>`)) +
      segment("skipped", count((u) => u.stage === "skipped"), cat, state.status === "skipped");

    const failures = snapshot.failures || [], recent = snapshot.recent || [];
    el("ingestion-foot").innerHTML =
      (failures.length ? `<div class="fail-list"><b>Failed to catalog</b>${failures.slice(0, 5).map((f) =>
        `<div class="fail-row">${newTab(f.path, f.path.split("/").pop())} <span class="subtle">— ${esc(f.reason)}</span></div>`).join("")}</div>` : "") +
      `<details><summary>Recently cataloged (${recent.length})</summary>${recent.length
        ? `<ul class="recent">${recent.map((e) => `<li><span class="subtle cdate" title="${esc(e.ts || "")} (UTC)">${esc(e.ts ? localStamp(new Date(e.ts)) : "")}</span> ${e.dest ? newTab(e.dest, e.dest.split("/").pop()) : esc(e.path)}${e.collection ? ` → ${esc(collName(e.collection))}` : ""}</li>`).join("")}</ul>`
        : `<p class="subtle">Nothing logged yet — the log starts with the next <code>catalog</code> run.</p>`}</details>`;
  }

  /* ---------- by-format matrix (inside the Digestion panel) ---------- */

  function renderMatrix() {
    const kinds = [...new Set(units.map((u) => u.kind))].sort(byOrder(KIND_ORDER));
    const present = new Set(units.map((u) => u.stage));
    const cols = STAGES.filter((s) => present.has(s));
    const grid = {}, totals = {};
    for (const u of units) {
      (grid[u.kind] = grid[u.kind] || {})[u.stage] = (grid[u.kind][u.stage] || 0) + 1;
      totals[u.stage] = (totals[u.stage] || 0) + 1;
    }
    const cell = (kind, s, n) => (n ? `<button type="button" class="cnt" data-kind="${esc(kind)}" data-status="${esc(s)}">${n}</button>` : `<span class="zero">·</span>`);
    const row = (kind, counts, name, cls = "") => `<tr class="${cls}"><th scope="row">${name}</th>${cols.map((s) => `<td>${cell(kind, s, counts[s])}</td>`).join("")}` +
      `<td class="tot">${cell(kind, "", Object.values(counts).reduce((a, b) => a + b, 0))}</td></tr>`;
    el("matrix").innerHTML = `<table class="matrix"><thead><tr><th>Format</th>${cols.map((s) => `<th>${pill(s, false)}</th>`).join("")}<th>Total</th></tr></thead><tbody>` +
      kinds.map((k) => row(k, grid[k], `<button type="button" class="kind-btn" data-kind="${esc(k)}" title="${esc(FORMAT_TIP[k] || "")}">${esc(k)}</button>`)).join("") +
      row("", totals, "All", "total") + `</tbody></table>`;
  }

  /* ---------- browser: breadcrumbs, filters, views ---------- */

  function crumbLabel() {
    const s = state.status;
    if (!s) return null;
    if (s === "@cataloged") return ["Ingestion", "cataloged"];
    if (s === "@digested") return ["Digestion", "digested"];
    if (["inbox", "failed", "uncataloged"].includes(s)) return ["Ingestion", label(s)];
    if (["easy", "full", "deep"].includes(s)) return ["Digestion", "digested", s];
    return ["Digestion", label(s)];
  }

  function renderCrumbs(n) {
    const chips = [];
    const st = crumbLabel();
    if (st) chips.push(`<span class="crumb s-${esc(state.status.replace(/^@/, ""))}"><b>${st.map(esc).join(" › ")}</b><button type="button" data-clear="status" aria-label="Remove">×</button></span>`);
    if (state.kind) chips.push(`<span class="crumb">format <b>${esc(state.kind)}</b><button type="button" data-clear="kind" aria-label="Remove">×</button></span>`);
    if (state.coll) chips.push(`<span class="crumb">collection <b>${esc(state.coll === "@none" ? "none" : collName(state.coll))}</b><button type="button" data-clear="coll" aria-label="Remove">×</button></span>`);
    if (state.q) chips.push(`<span class="crumb">search <b>“${esc(state.q)}”</b><button type="button" data-clear="q" aria-label="Remove">×</button></span>`);
    el("crumbs").innerHTML = chips.length ? chips.join("") + (chips.length > 1 ? `<button type="button" class="crumb-clear" data-clear="all">clear all</button>` : "")
      : `<span class="crumb-all">All files</span> <span class="subtle">— pick a segment above to narrow down</span>`;
    el("files-count").textContent = `${n} item${n === 1 ? "" : "s"}`;
  }

  function fillSelect(id, options, current) {
    el(id).innerHTML = options.map(([v, t]) => `<option value="${esc(v)}"${v === current ? " selected" : ""}>${esc(t)}</option>`).join("");
  }
  function refreshToolbar() {
    fillSelect("f-kind", [["", "All formats"], ...[...new Set(units.map((u) => u.kind))].sort(byOrder(KIND_ORDER)).map((k) => [k, k])], state.kind);
    const colls = [...new Set(units.flatMap((u) => u.colls))].sort((a, b) => collName(a).localeCompare(collName(b)));
    fillSelect("f-coll", [["", "All collections"], ["@none", "(no collection)"], ...colls.map((c) => [c, collName(c)])], state.coll);
    el("f-group").value = state.group;
    el("f-rows").value = state.rows;
    el("f-q").value = state.q;
    el("rows-by").hidden = state.view !== "board";
    el("group-label").textContent = state.view === "board" ? "Columns" : "Group by";
    el("view-tabs").querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.view === state.view));
  }

  function setFilter(next, scroll = false) {
    Object.assign(state, next);
    shown = PAGE_SIZE;
    cursor = -1;
    writeHash();
    refreshToolbar();
    renderPanels();
    renderView();
    if (scroll) {
      el("browser").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
      el("browser").classList.remove("flash");
      void el("browser").offsetWidth;
      el("browser").classList.add("flash");
    }
  }

  function matchStatus(u) {
    if (!state.status) return true;
    if (state.status === "@cataloged") return CATALOGED.has(u.stage);
    if (state.status === "@digested") return DIGESTED.has(u.stage);
    return u.stage === state.status;
  }
  function filteredUnits() {
    const q = state.q.trim().toLowerCase();
    const list = units.filter((u) => (!state.kind || u.kind === state.kind) && matchStatus(u) &&
      (!state.coll || (state.coll === "@none" ? !u.colls.length : u.colls.includes(state.coll))) && (!q || u.search.includes(q)));
    const dir = state.asc ? 1 : -1;
    list.sort((a, b) => {
      let r;
      switch (state.sort) {
        case "stage": r = byOrder(STAGES)(a.stage, b.stage); break;
        case "kind": r = byOrder(KIND_ORDER)(a.kind, b.kind); break;
        case "coll": r = collName(a.colls[0] || "~").localeCompare(collName(b.colls[0] || "~")); break;
        case "size_kb": case "age_days": r = (a[state.sort] ?? 0) - (b[state.sort] ?? 0); break;
        default: r = String(a[state.sort] || "").localeCompare(String(b[state.sort] || ""));
      }
      return dir * r || a.name.localeCompare(b.name);
    });
    return list;
  }

  const sliced = (dim) => state.group === dim || (state.view === "board" && state.rows === dim);

  function nameCell(u) {
    const extra = [u.isThread ? `${u.files.length} file${u.files.length === 1 ? "" : "s"}` : "",
      !u.isThread && u.companions.length ? `+${u.companions.length} ${relationOf(u.companions[0])}` : ""].filter(Boolean).join(" · ");
    return `<button type="button" class="fname" data-open="${esc(u.key)}" data-preview="${esc(u.key)}" title="Preview">${esc(u.name)}</button>` +
      (extra ? ` <span class="subtle nowrap">· ${esc(extra)}</span>` : "") +
      (u.failure ? `<div class="fail-reason" title="${esc(u.failure)}">⚠ ${esc(u.failure)}</div>` : "");
  }

  function listRow(u) {
    return `<tr class="row${state.item === u.key ? " selected" : ""}${selected.has(u.key) ? " checked" : ""}" data-key="${esc(u.key)}">` +
      `<td class="sel"><input type="checkbox" class="sel-one" data-key="${esc(u.key)}" ${selected.has(u.key) ? "checked" : ""}></td>` +
      `<td class="name">${nameCell(u)}</td><td>${kindChip(u.kind)}</td>` +
      `<td>${u.colls.length ? u.colls.map(collChip).join(" ") : `<span class="subtle">—</span>`}</td><td>${pill(u.stage)}</td>` +
      `<td class="slug">${u.slug ? slugLink(u.slug) : "—"}</td><td class="num">${fmtSize(u.size_kb)}</td>` +
      `<td class="num" title="${esc(u.mtime ? u.mtime.toISOString().slice(0, 10) : "")}">${fmtAge(u.age_days)}</td></tr>`;
  }

  function renderList(list) {
    const cols = [["sel", ""], ["name", "Name"], ["kind", "Format"], ["coll", "Collection"], ["stage", "Status"], ["slug", "Wiki note"], ["size_kb", "Size"], ["age_days", "Modified"]];
    const head = cols.map(([k, t]) => (k === "sel" ? `<th class="sel"><input type="checkbox" id="sel-all" title="Select all shown"></th>`
      : `<th data-key="${k}" class="sortable${state.sort === k ? ` sorted${state.asc ? " asc" : ""}` : ""}"${k === "age_days" ? ` title="${esc(TERM_TIP.modified)}"` : ""}>${t}</th>`)).join("");
    let body = "", n = 0;
    order = [];
    for (const [k, members] of state.group === "none" ? [["", list]] : grouped(list)) {
      if (state.group !== "none") {
        const id = `list|${state.group}|${k}`, closed = collapsedGroups.has(id);
        body += `<tr class="grp${closed ? " closed" : ""}"><td class="sel"><input type="checkbox" class="sel-group" data-grp="${esc(k)}" ${members.every((u) => selected.has(u.key)) ? "checked" : ""}></td>` +
          `<td colspan="${cols.length - 1}"><button type="button" class="grp-toggle" data-grp="${esc(id)}">${closed ? "▸" : "▾"}</button> ${groupName(k)} <span class="subtle">${members.length}</span>${stackBar(members, "mini")}</td></tr>`;
        if (closed) continue;
      }
      for (const u of members) {
        if (n >= shown) break;
        body += listRow(u);
        order.push(u.key);
        n += 1;
      }
    }
    const more = list.length > shown ? `<tr class="more-row"><td colspan="${cols.length}"><button type="button" class="filter-tab" id="btn-more">Show ${Math.min(PAGE_SIZE, list.length - shown)} more of ${list.length - shown}</button></td></tr>` : "";
    el("files-view").innerHTML = `<div class="files-wrap"><table class="data-table list"><thead><tr>${head}</tr></thead><tbody>${body}${more}</tbody></table></div>`;
    el("files-view").querySelectorAll("th.sortable").forEach((th) => th.addEventListener("click", () => {
      if (state.sort === th.dataset.key) state.asc = !state.asc; else { state.sort = th.dataset.key; state.asc = true; }
      writeHash(false);
      renderView();
    }));
    el("btn-more")?.addEventListener("click", () => { shown += PAGE_SIZE; renderView(); });
    el("sel-all")?.addEventListener("change", (e) => {
      for (const u of list.slice(0, shown)) e.target.checked ? selected.add(u.key) : selected.delete(u.key);
      renderView();
    });
  }

  function card(u) {
    return `<div class="bcard${state.item === u.key ? " selected" : ""}${selected.has(u.key) ? " checked" : ""}" data-key="${esc(u.key)}">` +
      `<div class="bcard-top"><input type="checkbox" class="sel-one" data-key="${esc(u.key)}" ${selected.has(u.key) ? "checked" : ""}>${nameCell(u)}</div>` +
      `<div class="bcard-meta">${state.kind || sliced("format") ? "" : kindChip(u.kind)} ${state.coll || sliced("collection") ? "" : u.colls.slice(0, 1).map(collChip).join("")}</div>` +
      `<div class="bcard-foot subtle">${state.group === "none" || sliced("stage") ? "" : `${pill(u.stage)} `}${fmtSize(u.size_kb)} · ${fmtAge(u.age_days)}</div></div>`;
  }

  const colKey = (u) => (state.group === "none" ? u.stage : groupKey(u));
  function boardColumns(list) {
    return state.group === "none" ? STAGES.map((s) => [s, list.filter((u) => u.stage === s)]).filter(([, m]) => m.length) : grouped(list);
  }
  function colMeta(k) {
    const id = `board|${state.group}|${k}`;
    const dim = state.group === "none" ? "stage" : state.group;
    return { id, closed: collapsedGroups.has(id), text: groupLabel(k, dim), nameHtml: groupName(k, dim), cls: stageCls(dim, k) };
  }
  const byStage = (a, b) => byOrder(STAGES)(a.stage, b.stage) || a.name.localeCompare(b.name);

  function renderBoard(list) {
    order = [];
    if (state.rows !== "none" && state.rows !== state.group) { renderBoardGrid(list); return; }
    el("files-view").innerHTML = `<div class="board">${boardColumns(list).map(([k, members]) => {
      const { id, closed, text, nameHtml, cls } = colMeta(k);
      if (closed) return `<div class="bcol folded${cls}"><button type="button" class="grp-toggle" data-grp="${esc(id)}" title="Expand">▸</button><div class="bcol-vlabel">${esc(text)} <span class="subtle">${members.length}</span></div></div>`;
      const cap = expandedCells.has(id) ? members.length : CARD_CAP;
      const sorted = [...members].sort(byStage);
      sorted.slice(0, cap).forEach((u) => order.push(u.key));
      return `<div class="bcol${cls}"><div class="bcol-head"><button type="button" class="grp-toggle" data-grp="${esc(id)}" title="Collapse column">▾</button><span class="dot"></span>${nameHtml} <span class="subtle">${members.length}</span></div>` +
        `${state.group === "none" ? "" : stackBar(members, "mini")}<div class="bcol-body">${sorted.slice(0, cap).map(card).join("")}` +
        `${members.length > cap ? `<button type="button" class="filter-tab cell-more" data-cell="${esc(id)}">+${members.length - cap} more</button>` : ""}</div></div>`;
    }).join("")}</div>`;
  }

  function renderBoardGrid(list) {
    const columns = boardColumns(list).map(([k, members]) => ({ k, members, ...colMeta(k) }));
    const widths = columns.map((c) => (c.closed ? "44px" : "240px")).join(" ");
    const head = `<div class="bg-corner subtle">${esc(state.rows === "stage" ? "status" : state.rows)} ↓ · ${esc(state.group === "none" || state.group === "stage" ? "status" : state.group)} →</div>` +
      columns.map((c) => (c.closed ? `<div class="bg-colhead folded${c.cls}"><button type="button" class="grp-toggle" data-grp="${esc(c.id)}" title="Expand ${esc(c.text)}">▸</button></div>`
        : `<div class="bg-colhead${c.cls}"><button type="button" class="grp-toggle" data-grp="${esc(c.id)}">▾</button><span class="dot"></span>${c.nameHtml} <span class="subtle">${c.members.length}</span>${state.group === "none" ? "" : stackBar(c.members, "mini")}</div>`)).join("");
    const body = grouped(list, state.rows).map(([rk, rm]) => {
      const rid = `boardrow|${state.rows}|${rk}`, rclosed = collapsedGroups.has(rid);
      const cells = columns.map((c) => {
        const inCell = rm.filter((u) => colKey(u) === c.k).sort(byStage);
        if (c.closed || rclosed) return `<div class="bg-cell compact">${inCell.length ? `<span class="subtle">${inCell.length}</span>` : ""}</div>`;
        const cid = `${rid}|${c.k}`, cap = expandedCells.has(cid) ? inCell.length : CELL_CAP;
        inCell.slice(0, cap).forEach((u) => order.push(u.key));
        return `<div class="bg-cell${inCell.length ? "" : " empty"}">${inCell.slice(0, cap).map(card).join("")}${inCell.length > cap ? `<button type="button" class="filter-tab cell-more" data-cell="${esc(cid)}">+${inCell.length - cap} more</button>` : ""}</div>`;
      }).join("");
      return `<div class="bg-rowhead${stageCls(state.rows, rk)}${rclosed ? " closed" : ""}"><button type="button" class="grp-toggle" data-grp="${esc(rid)}">${rclosed ? "▸" : "▾"}</button><span class="dot"></span>${groupName(rk, state.rows)} <span class="subtle">${rm.length}</span>${stackBar(rm, "mini")}</div>${cells}`;
    }).join("");
    el("files-view").innerHTML = `<div class="board-grid" style="grid-template-columns: 170px ${widths}">${head}${body}</div>`;
  }

  function renderChron(list) {
    const months = new Map();
    for (const u of [...list].sort((a, b) => (b.last_op_at || "").localeCompare(a.last_op_at || ""))) {
      const k = u.last_at ? localStamp(u.last_at).slice(0, 7) : "unknown";
      if (!months.has(k)) months.set(k, []);
      months.get(k).push(u);
    }
    order = [];
    let html = `<p class="subtle chron-note">${esc(TERM_TIP.last_op)}</p>`;
    for (const [m, members] of months) {
      const id = `chron|${m}`, closed = collapsedGroups.has(id);
      const title = m === "unknown" ? "Unknown date" : new Date(`${m}-01T00:00:00`).toLocaleDateString(undefined, { month: "long", year: "numeric" });
      html += `<div class="chron-month${closed ? " closed" : ""}"><div class="chron-head"><button type="button" class="grp-toggle" data-grp="${esc(id)}">${closed ? "▸" : "▾"}</button> <b>${esc(title)}</b> <span class="subtle">${members.length}</span>${stackBar(members, "mini")}</div>`;
      if (!closed) {
        for (const [k, ms] of state.group === "none" ? [["", members]] : grouped(members)) {
          if (state.group !== "none") html += `<div class="chron-sub">${groupName(k)} <span class="subtle">${ms.length}</span></div>`;
          html += `<ul class="chron-list">${ms.map((u) => {
            order.push(u.key);
            return `<li class="crow${state.item === u.key ? " selected" : ""}${selected.has(u.key) ? " checked" : ""}" data-key="${esc(u.key)}"><input type="checkbox" class="sel-one" data-key="${esc(u.key)}" ${selected.has(u.key) ? "checked" : ""}>` +
              `<span class="cdate" title="${esc(u.last_op_at)} (UTC)">${esc(u.last_at ? localStamp(u.last_at).slice(5) : "")}</span><span class="cop cop-${esc(u.last_op || "none")}" title="${esc(OP_TIP[u.last_op] || "")}">${esc(u.last_op || "")}</span>${pill(u.stage)} ${nameCell(u)} ${kindChip(u.kind)} ${u.colls.slice(0, 1).map(collChip).join("")}</li>`;
          }).join("")}</ul>`;
        }
      }
      html += `</div>`;
    }
    el("files-view").innerHTML = html;
  }

  function renderView() {
    const list = filteredUnits();
    renderCrumbs(list.length);
    el("rows-by").hidden = state.view !== "board";
    el("group-label").textContent = state.view === "board" ? "Columns" : "Group by";
    el("view-tabs").querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.view === state.view));
    if (!list.length) { el("files-view").innerHTML = empty("Nothing matches — remove a filter above."); order = []; }
    else if (state.view === "board") renderBoard(list);
    else if (state.view === "chron") renderChron(list);
    else renderList(list);
    renderBulk();
    if (state.item && byKey.has(state.item) && el("modal").hidden) openPreview(state.item, false);
  }

  /* ---------- preview modal ---------- */

  const textCache = new Map();
  async function fetchText(path, limit = 40000) {
    if (!textCache.has(path)) textCache.set(path, fetch(rawUrl(path)).then((r) => (r.ok ? r.text() : `(${r.status})`)).catch((e) => `Preview failed: ${e}`));
    const t = await textCache.get(path);
    return t.length > limit ? { text: t.slice(0, limit), truncated: true } : { text: t, truncated: false };
  }

  /* ---------- markdown rendering (raw .md clips, notes, chats) ---------- */

  const MODE_KEY = "pipeline.previewMode";
  const TEXT_EXTS = [".md", ".txt", ".html", ".json", ".eml"];
  let previewMode = "rendered";
  try { if (localStorage.getItem(MODE_KEY) === "source") previewMode = "source"; } catch (_e) { /* private mode */ }

  function splitFrontmatter(md) {
    const m = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(md);
    if (!m) return { fm: [], body: md };
    const fm = [];
    m[1].split(/\r?\n/).forEach((line) => {
      const kv = /^([A-Za-z0-9_-]+):\s*(.*)$/.exec(line);
      if (kv) fm.push([kv[1], kv[2]]);
      else if (fm.length && /^\s+\S/.test(line)) fm[fm.length - 1][1] += ` ${line.trim()}`;
    });
    return { fm, body: md.slice(m[0].length) };
  }

  function renderMath(src, display) {
    if (!window.katex) return `<code>${esc(src)}</code>`;
    try {
      return window.katex.renderToString(src, { displayMode: display, throwOnError: false, strict: "ignore" });
    } catch (_e) {
      return `<code>${esc(src)}</code>`;
    }
  }

  // relative links inside raw/ (../images/x.jpg from raw/web-clips/) → the raw-file route
  function resolveRaw(href, baseDir) {
    if (/^(?:[a-z]+:|\/|#)/i.test(href)) return href;
    const parts = baseDir.split("/");
    href.split("/").forEach((seg) => {
      if (seg === "..") parts.pop();
      else if (seg && seg !== ".") parts.push(seg);
    });
    const path = parts.join("/");
    return path.startsWith("raw/") ? rawUrl(decodeURIComponent(path)) : href;
  }

  function renderMarkdown(md, baseDir) {
    const stash = [];
    const hold = (html) => { stash.push(html); return `XSTASHX${stash.length - 1}XENDX`; };
    const codeStash = [];
    const holdCode = (raw) => { codeStash.push(raw); return `XCODEX${codeStash.length - 1}XENDX`; };
    let s = md.replace(/<!--[\s\S]*?-->/g, "");
    s = s.replace(/```[\s\S]*?```/g, holdCode);
    s = s.replace(/`[^`\n]+`/g, holdCode);
    s = s.replace(/\$\$([\s\S]+?)\$\$/g, (_m, tex) => hold(renderMath(tex.trim(), true)));
    s = s.replace(/(^|[^\\$])\$(?!\s)([^$\n]+?)\$(?!\d)/g, (_m, pre, tex) => pre + hold(renderMath(tex, false)));
    s = s.replace(/!\[\[([^\]|]+)(?:\\?\|[^\]]*)?\]\]/g, (_m, name) => hold(`<img alt="${esc(name)}" src="${esc(resolveRaw(name.trim(), baseDir))}">`));
    s = s.replace(/\[\[([^\]|#]+)(#[^\]|]+)?(?:\s*\\?\|\s*([^\]]+))?\]\]/g, (_m, slug, _h, label) =>
      hold(`<a class="wl" href="/explore#/p/${encodeURIComponent(slug.trim())}" title="Open in Explore">${esc((label || slug).trim())}</a>`));
    s = s.replace(/XCODEX(\d+)XENDX/g, (_m, i) => codeStash[Number(i)]);
    let html = window.marked ? window.marked.parse(s, { gfm: true, breaks: false }) : `<pre>${esc(s)}</pre>`;
    html = html.replace(/XSTASHX(\d+)XENDX/g, (_m, i) => stash[Number(i)]);
    const tpl = document.createElement("template");
    tpl.innerHTML = html;
    const root = tpl.content;
    root.querySelectorAll("script, iframe, object, embed, style, link, meta").forEach((n) => n.remove());
    root.querySelectorAll("*").forEach((n) => [...n.attributes].forEach((a) => { if (/^on/i.test(a.name)) n.removeAttribute(a.name); }));
    root.querySelectorAll("img[src]").forEach((img) => {
      img.src = resolveRaw(img.getAttribute("src"), baseDir);
      img.loading = "lazy";
      img.addEventListener("error", () => {
        const miss = document.createElement("span");
        miss.className = "md-img-missing";
        miss.textContent = `[image not found: ${img.getAttribute("alt") || img.getAttribute("src")}]`;
        img.replaceWith(miss);
      }, { once: true });
    });
    root.querySelectorAll("a[href]").forEach((a) => {
      const href = a.getAttribute("href");
      if (/^javascript:/i.test(href)) { a.removeAttribute("href"); return; }
      if (/^https?:/i.test(href)) { a.target = "_blank"; a.rel = "noopener noreferrer"; a.classList.add("ext"); }
      else if (!a.classList.contains("wl")) a.setAttribute("href", resolveRaw(href, baseDir));
    });
    root.querySelectorAll("table").forEach((t) => {
      const wrap = document.createElement("div");
      wrap.className = "md-table-wrap";
      t.replaceWith(wrap);
      wrap.appendChild(t);
    });
    return root;
  }

  function frontmatterBlock(fm) {
    if (!fm.length) return "";
    const title = fm.find(([k]) => k === "title");
    return `<details class="md-fm"><summary>Frontmatter · <b>${fm.length} field${fm.length === 1 ? "" : "s"}</b>${title ? ` · ${esc(title[1])}` : ""}</summary>` +
      `<dl>${fm.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl></details>`;
  }

  function setPreviewMode(mode, rerender = true) {
    previewMode = mode === "source" ? "source" : "rendered";
    try { localStorage.setItem(MODE_KEY, previewMode); } catch (_e) { /* private mode */ }
    el("preview-mode").querySelectorAll("[data-mode]").forEach((b) => b.classList.toggle("active", b.dataset.mode === previewMode));
    if (rerender && previewFile) renderPreview(previewFile);
  }

  let previewFor = "";
  let previewFile = null;
  async function renderPreview(file) {
    const box = el("modal-preview");
    previewFor = file.path;
    previewFile = file;
    el("preview-open").href = rawUrl(file.path);
    const isImg = [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"].includes(file.ext);
    const canRender = file.ext === ".md";
    el("preview-bar").hidden = !TEXT_EXTS.includes(file.ext) && !isImg && file.ext !== ".pdf";
    el("preview-mode").hidden = !canRender;
    el("preview-mode").querySelectorAll("[data-mode]").forEach((b) => b.classList.toggle("active", b.dataset.mode === previewMode));
    const openImg = (src, alt) => `<a class="preview-img" href="${rawUrl(file.path)}" target="_blank" rel="noopener noreferrer" title="Open the full file in a new tab"><img src="${src}" alt="${esc(alt)}"></a>`;
    if (file.ext === ".pdf") box.innerHTML = openImg(thumbUrl(file.path, 1000), `First page of ${file.name}`);
    else if (isImg) box.innerHTML = openImg(rawUrl(file.path), file.name);
    else if (TEXT_EXTS.includes(file.ext)) {
      box.innerHTML = `<pre>Loading…</pre>`;
      const rendered = canRender && previewMode === "rendered";
      const { text, truncated } = await fetchText(file.path, rendered ? 400000 : 40000);
      if (previewFor !== file.path) return;
      const tail = truncated ? "\n\n… (open the file for the rest)" : "";
      if (!rendered) { box.querySelector("pre").textContent = text + tail; return; }
      const { fm, body } = splitFrontmatter(text);
      const doc = document.createElement("article");
      doc.className = "md-doc";
      doc.innerHTML = frontmatterBlock(fm);
      doc.appendChild(renderMarkdown(body, file.path.split("/").slice(0, -1).join("/")));
      if (truncated) doc.insertAdjacentHTML("beforeend", `<p class="md-truncated">… truncated — open the file for the rest.</p>`);
      box.replaceChildren(doc);
    } else box.innerHTML = `<div class="no-preview">No preview for ${esc(file.ext || "this file")} — <a href="${rawUrl(file.path)}" target="_blank" rel="noopener noreferrer">open it</a>.</div>`;
    el("modal-info").querySelectorAll("[data-show]").forEach((b) => b.classList.toggle("on", b.dataset.show === file.path));
  }

  function cmdBlock(cmd) {
    return `<div class="cmd"><code>${esc(cmd)}</code><button type="button" class="btn-copy" data-cmd="${esc(cmd)}">Copy</button></div>`;
  }

  function openPreview(key, push = true) {
    const u = byKey.get(key);
    if (!u) return;
    state.item = key;
    if (push) writeHash(false);
    markCursor();
    const f = u.primary;
    const ing = CATALOGED.has(u.stage) ? "cataloged" : u.stage;
    const dig = CATALOGED.has(u.stage) ? u.stage : "";
    const rows = [
      ["Ingestion", pill(ing, false)],
      ["Digestion", dig ? (DIGESTED.has(dig) && dig !== "digested" ? `${pill("digested", false)} › ${pill(dig, false)}` : pill(dig, false)) : `<span class="subtle">— not cataloged yet</span>`],
      ["Format", `${kindChip(u.kind)} <span class="subtle">${esc(FORMAT_TIP[u.kind] || "")}</span>`],
      ["Collection", u.colls.length ? u.colls.map((c) => `${collChip(c)} ${slugLink(c, "page ↗")}`).join("<br>") + (f.hub_row ? ` <span class="subtle">· row ${f.hub_row}</span>` : "") : "—"],
      ["Wiki note", u.slug ? slugLink(u.slug) : `<span class="subtle">none yet</span>`],
      ...(f.url ? [["Source", `<a href="${esc(f.url)}" target="_blank" rel="noopener noreferrer" class="src-link" title="${esc(f.url)}">${esc(hostOf(f.url))} ↗</a>`]] : []),
      ["Size", `${fmtSize(u.size_kb)} · modified ${fmtAge(u.age_days)}`],
      ["Last operation", u.last_at ? `${u.last_op} · ${localStamp(u.last_at)}` : "—"],
    ];
    const files = [f, ...u.companions];
    const companions = u.companions.length
      ? `<div class="mi-block"><h4>${u.isThread ? "Thread files" : "Belongs with it"}</h4><div class="comp-list">${files.map((x) =>
          `<button type="button" data-show="${esc(x.path)}" title="${esc(TERM_TIP[relationOf(x)] || "")}">${esc(x.name)} <span class="subtle">${esc(x === f ? "main" : relationOf(x))} · ${fmtSize(x.size_kb)}</span></button>`).join("")}</div></div>` : "";
    const next = u.next ? `<div class="mi-block"><h4>Next step</h4>${cmdBlock(u.next)}</div>`
      : u.stage === "uncataloged" ? `<div class="mi-block"><h4>Next step</h4><p class="subtle">Give it a collection (corpus.tsv <code>collection</code>) or mark it <code>skip</code>.</p></div>` : "";
    const fail = u.failure ? `<div class="mi-block fail-box"><h4>Why cataloging failed</h4><p>${esc(u.failure)}</p></div>` : "";
    el("modal-title").innerHTML = `${pill(u.stage, false)} <span>${esc(u.name)}</span>`;
    el("modal-info").innerHTML = fail + `<dl class="kv">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>` + next + companions +
      `<div class="mi-block mi-actions"><a class="primary-btn" href="${rawUrl(f.path)}" target="_blank" rel="noopener noreferrer">Open file ↗</a><a class="ghost-btn" href="${obsidianUri(f.path)}">Obsidian</a>${f.url ? `<a class="ghost-btn" href="${esc(f.url)}" target="_blank" rel="noopener noreferrer">Original page ↗</a>` : ""}</div>` +
      `<p class="subtle mi-path">${esc(f.path)}</p>`;
    el("modal-info").querySelectorAll("[data-show]").forEach((b) => b.addEventListener("click", () => renderPreview(files.find((x) => x.path === b.dataset.show))));
    const i = order.indexOf(key);
    el("modal-prev").disabled = i <= 0;
    el("modal-next").disabled = i < 0 || i >= order.length - 1;
    if (el("modal").hidden) {
      el("modal").hidden = false;
      document.body.classList.add("modal-open");
      requestAnimationFrame(() => el("modal").classList.add("in"));
      el("modal-close").focus({ preventScroll: true });
    }
    renderPreview(f);
  }

  function closePreview() {
    el("modal").classList.remove("in");
    el("modal").hidden = true;
    document.body.classList.remove("modal-open");
    state.item = "";
    writeHash(false);
    markCursor();
  }

  function step(delta) {
    const j = order.indexOf(state.item) + delta;
    if (j < 0 || j >= order.length || order.indexOf(state.item) < 0) return;
    cursor = j;
    openPreview(order[j]);
  }

  function markCursor() {
    el("files-view").querySelectorAll("[data-key].row, .bcard, .crow").forEach((n) =>
      n.classList.toggle("selected", n.dataset.key === state.item || (cursor >= 0 && n.dataset.key === order[cursor])));
  }

  /* ---------- hover preview ---------- */

  let hoverTimer = null, hoverKey = "";
  function hideHover() { clearTimeout(hoverTimer); hoverKey = ""; el("hover-card").hidden = true; }
  async function showHover(anchor, key) {
    const u = byKey.get(key);
    if (!u || !el("modal").hidden) return;
    hoverKey = key;
    const f = u.primary;
    const isImg = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"].includes(f.ext);
    const visual = f.ext === ".pdf" || isImg ? `<img class="hc-thumb" src="${thumbUrl(f.path)}" alt="">`
      : [".md", ".txt", ".html", ".json"].includes(f.ext) ? `<pre class="hc-text">Loading…</pre>` : "";
    const hc = el("hover-card");
    hc.innerHTML = `<div class="hc-head">${pill(u.stage, false)} <b>${esc(u.name)}</b></div><div class="hc-meta">${esc(u.kind)}${u.colls.length ? ` · ${esc(u.colls.map(collName).join(", "))}` : ""} · ${fmtSize(u.size_kb)}</div>${visual}<div class="hc-foot subtle">click to preview</div>`;
    const r = anchor.getBoundingClientRect();
    hc.style.left = `${Math.min(window.innerWidth - 392, Math.max(12, r.left))}px`;
    hc.style.top = `${r.bottom + 8 + window.scrollY}px`;
    hc.hidden = false;
    const pre = hc.querySelector(".hc-text");
    if (pre) { const t = await fetchText(f.path, 3000); if (hoverKey === key) pre.textContent = t.split("\n").slice(0, 30).join("\n"); }
    hc.querySelector(".hc-thumb")?.addEventListener("error", (e) => e.target.remove());
  }

  /* ---------- bulk ---------- */

  function renderBulk() {
    const n = selected.size;
    el("bulk-bar").hidden = !n;
    if (!n) return;
    const withCmd = [...selected].filter((k) => byKey.get(k)?.next).length;
    el("bulk-count").textContent = `${n} selected`;
    el("bulk-cmds").textContent = `Copy ${withCmd} next-step command${withCmd === 1 ? "" : "s"}`;
    el("bulk-cmds").disabled = !withCmd;
  }
  function copy(text, note) {
    navigator.clipboard?.writeText(text);
    el("bulk-note").textContent = note;
    setTimeout(() => { el("bulk-note").textContent = ""; }, 2500);
  }
  function toggleSel(key, on) {
    (on ?? !selected.has(key)) ? selected.add(key) : selected.delete(key);
    el("files-view").querySelectorAll(`[data-key="${CSS.escape(key)}"]`).forEach((n) => {
      if (n.matches("input")) n.checked = selected.has(key); else n.classList.toggle("checked", selected.has(key));
    });
    renderBulk();
  }

  /* ---------- "More" ---------- */

  function rowClass(status) {
    if (["easy", "full", "deep"].includes(status)) return status;
    if (status === "skip") return "skipped";
    if (status === "partial") return "partial";
    return "not-digested";
  }
  function renderCollections(list) {
    const counts = { open: 0, all: list.length };
    for (const c of list) { counts[c.type] = (counts[c.type] || 0) + 1; if (c.total && c.covered < c.total) counts.open += 1; }
    el("coll-filters").innerHTML = [["open", "Unfinished"], ["all", "All"], ["course", "Courses"], ["series", "Series"], ["book", "Books"], ["notebook", "Notebooks"]]
      .filter(([k]) => counts[k] || k === "open" || k === "all")
      .map(([k, t]) => `<button type="button" class="filter-tab${collFilter === k ? " active" : ""}" data-k="${k}">${t} (${counts[k] || 0})</button>`).join("");
    el("coll-filters").querySelectorAll(".filter-tab").forEach((b) => b.addEventListener("click", () => { collFilter = b.dataset.k; renderCollections(list); }));
    const showList = list.filter((c) => collFilter === "all" || (collFilter === "open" ? c.total && c.covered < c.total : c.type === collFilter));
    el("collections").innerHTML = showList.length ? showList.map((c) => {
      const w = (r) => (r.pages ? Math.max(1, r.pages[1] - r.pages[0] + 1) : 1);
      const tot = c.rows.reduce((n, r) => n + w(r), 0) || 1;
      const rows = c.rows.map((r, i) => {
        const where = r.pages ? (c.raw ? newTab(c.raw, `pp. ${r.pages[0] ?? "?"}–${r.pages[1] ?? "?"}`) : "") : r.raws.map((p) => newTab(p, p.split("/").pop())).join("<br>");
        const cmd = rowClass(r.status) === "not-digested" ? (c.unit === "items" ? `python3 -m kb.ingest full-digest ${c.slug} --row ${i + 1}` : c.raw && r.pages ? `python3 -m kb.ingest full-digest ${c.raw} --pages ${r.pages[0]}-${r.pages[1]}` : "") : "";
        return `<tr><td class="num">${i + 1}</td><td>${esc(r.title)}</td><td class="where">${where}</td><td>${pill(rowClass(r.status), false)}</td><td>${r.slug ? slugLink(r.slug) : cmd ? cmdBlock(cmd) : ""}</td></tr>`;
      }).join("");
      return `<div class="book"><div class="book-head"><span><span class="type-tag">${esc(c.type)}</span> ${slugLink(c.slug, c.title)} <button type="button" class="filter-tab mini js-filter" data-f-coll="${esc(c.slug)}">browse files ↑</button></span><span class="meta">${c.covered}/${c.total} ${c.unit} · ${c.pct}%</span></div>` +
        `<div class="stack">${c.rows.map((r) => `<span class="s-${rowClass(r.status)}" style="width:${(100 * w(r) / tot).toFixed(2)}%" title="${esc(r.title)}"></span>`).join("")}</div>` +
        `<details><summary>Contents (${c.rows.length})</summary><div class="scroll-box"><table class="data-table"><thead><tr><th>#</th><th>Item</th><th>${c.unit === "pp" ? "Pages" : "Raw"}</th><th>Status</th><th>Note / next step</th></tr></thead><tbody>${rows}</tbody></table></div></details></div>`;
    }).join("") : empty("Nothing in this view.");
  }

  function renderSide() {
    const s = snapshot;
    const active = s.active_ingest || [];       // absent from a shared snapshot (local sessions)
    el("ingest-table").innerHTML = active.length ? `<table class="data-table"><tbody>${active.map((x) =>
      `<tr><td>${newTab(x.raw, x.raw.split("/").pop())}</td><td><span class="stage-pill">${esc(x.stage)}</span></td><td>${pill(x.digestion_status, false)}</td></tr>`).join("")}</tbody></table>` : empty("No open sessions.");
    el("distill-table").innerHTML = s.distill_review.length ? `<table class="data-table"><tbody>${s.distill_review.map((x) =>
      `<tr><td>${slugLink(x.slug)}</td><td>${x.proposals} proposals</td></tr>`).join("")}</tbody></table>` : empty("Nothing waiting.");
    el("shallow-table").innerHTML = s.shallow_papers.length ? `<div class="scroll-box"><table class="data-table"><tbody>${s.shallow_papers.map((x) => `<tr><td>${slugLink(x.slug)}</td></tr>`).join("")}</tbody></table></div>` : empty("None.");
    const counts = { all: s.coherence.length };
    for (const it of s.coherence) counts[it.kind] = (counts[it.kind] || 0) + 1;
    el("coherence-filters").innerHTML = ["all", "internal", "external", "cosmetic"].map((k) =>
      `<button type="button" class="filter-tab${coherenceFilter === k ? " active" : ""}" data-kind="${k}" title="${esc(TERM_TIP[k] || "")}">${k} (${counts[k] || 0})</button>`).join("");
    el("coherence-filters").querySelectorAll(".filter-tab").forEach((b) => b.addEventListener("click", () => { coherenceFilter = b.dataset.kind; renderSide(); }));
    const rows = s.coherence.filter((x) => coherenceFilter === "all" || x.kind === coherenceFilter);
    el("coherence-table").innerHTML = rows.length ? `<div class="scroll-box"><table class="data-table"><tbody>${rows.map((x) =>
      `<tr><td><code>${esc(x.id)}</code> <button type="button" class="btn-copy mini" data-cmd="python3 -m kb.core.coherence dismiss ${esc(x.id)}">dismiss cmd</button></td><td><span class="kind-pill ${esc(x.kind)}">${esc(x.kind)}</span></td><td>${x.score}</td><td>${x.slugs.split(",").filter(Boolean).map((sl) => slugLink(sl)).join("<br>")}</td><td>${esc(x.summary)}</td></tr>`).join("")}</tbody></table></div>` : empty("No open warnings.");
    const gl = (title, entries, isStage) => `<div class="gl-group"><h3>${esc(title)}</h3><dl>${entries.map(([k, v]) => `<dt>${isStage ? pill(k, false) : `<code>${esc(k)}</code>`}</dt><dd>${esc(v)}</dd>`).join("")}</dl></div>`;
    el("glossary-body").innerHTML =
      gl("Ingestion status", ["inbox", "failed", "uncataloged", "cataloged"].map((k) => [k, STAGE_TIP[k]]), true) +
      gl("Digestion status", ["not-digested", "partial", "digested", "easy", "full", "deep", "skipped"].map((k) => [k, STAGE_TIP[k]]), true) +
      gl("Companion files (folded into their parent)", ["ink overlay", "duplicate", "figure", "attachment", "transcription"].map((k) => [k, TERM_TIP[k]])) +
      gl("Formats", KIND_ORDER.map((k) => [k, FORMAT_TIP[k]]));
  }

  /* ---------- load ---------- */

  function renderAll() {
    titles = snapshot.titles || {};
    units = buildUnits(snapshot.items);
    byKey = new Map(units.map((u) => [u.key, u]));
    const server = snapshot.server;
    el("stale-banner").hidden = !(server && server.stale);
    if (server && server.stale) el("stale-banner").innerHTML = `⚠ The server is running older code than what's on disk — restart with <code>pixi run launch</code>.`;
    renderPanels();
    renderMatrix();
    refreshToolbar();
    renderView();
    renderCollections(snapshot.collections || []);
    renderSide();
    const errs = snapshot.summary.errors ? ` · ⚠ ${snapshot.summary.errors} lint errors` : "";
    el("status-line").textContent = `${units.length} items from ${snapshot.summary.files} raw files · updated ${snapshot.generated_at}${errs}`;
  }

  async function load() {
    el("status-line").textContent = "Loading…";
    try {
      snapshot = await (await fetch("/api/pipeline")).json();
      renderAll();
    } catch (e) {
      el("status-line").textContent = `Failed to load /api/pipeline: ${e}`;
    }
  }

  /* ---------- wiring ---------- */

  readHash();
  digestOpen = store.get("pipeline-digest-open", false) || ["easy", "full", "deep"].includes(state.status);
  let qTimer = null;
  el("f-q").addEventListener("input", (e) => { clearTimeout(qTimer); qTimer = setTimeout(() => { state.q = e.target.value; shown = PAGE_SIZE; writeHash(false); renderView(); }, 150); });
  el("f-kind").addEventListener("change", (e) => setFilter({ kind: e.target.value }));
  el("f-coll").addEventListener("change", (e) => setFilter({ coll: e.target.value }));
  el("f-group").addEventListener("change", (e) => setFilter({ group: e.target.value }));
  el("f-rows").addEventListener("change", (e) => setFilter({ rows: e.target.value }));
  el("view-tabs").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => setFilter({ view: b.dataset.view })));
  el("modal-close").addEventListener("click", closePreview);
  el("preview-mode").addEventListener("click", (e) => { const b = e.target.closest("[data-mode]"); if (b) setPreviewMode(b.dataset.mode); });
  el("modal-prev").addEventListener("click", () => step(-1));
  el("modal-next").addEventListener("click", () => step(1));
  el("modal").addEventListener("click", (e) => { if (e.target === el("modal")) closePreview(); });
  el("btn-refresh").addEventListener("click", load);
  el("btn-help").addEventListener("click", () => { el("help-panel").hidden = !el("help-panel").hidden; });
  el("bulk-clear").addEventListener("click", () => { selected.clear(); renderView(); });
  el("bulk-cmds").addEventListener("click", () => { const c = [...selected].map((k) => byKey.get(k)?.next).filter(Boolean); copy(c.join("\n"), `copied ${c.length}`); });
  el("bulk-paths").addEventListener("click", () => { const p = [...selected].map((k) => byKey.get(k)?.primary.path).filter(Boolean); copy(p.join("\n"), `copied ${p.length}`); });
  window.addEventListener("popstate", () => {
    if (writingHash) return;
    readHash();
    refreshToolbar();
    renderPanels();
    if (!state.item && !el("modal").hidden) { el("modal").hidden = true; document.body.classList.remove("modal-open"); }
    renderView();
  });

  document.addEventListener("click", (e) => {
    const t = e.target;
    if (t.closest("#digest-toggle")) {
      e.stopPropagation();
      digestOpen = !digestOpen;
      store.set("pipeline-digest-open", digestOpen);
      renderPanels();
      return;
    }
    const seg = t.closest(".seg-btn");
    if (seg) { setFilter({ status: state.status === seg.dataset.status ? "" : seg.dataset.status }, true); return; }
    const cnt = t.closest(".cnt, .kind-btn");
    if (cnt) { setFilter({ kind: cnt.dataset.kind || "", status: cnt.dataset.status || "" }, true); return; }
    const clr = t.closest("[data-clear]");
    if (clr) { setFilter(clr.dataset.clear === "all" ? { status: "", kind: "", coll: "", q: "" } : { [clr.dataset.clear]: "" }); return; }
    const copyBtn = t.closest(".btn-copy");
    if (copyBtn) { navigator.clipboard?.writeText(copyBtn.dataset.cmd); const old = copyBtn.textContent; copyBtn.textContent = "Copied"; setTimeout(() => { copyBtn.textContent = old; }, 1200); return; }
    const f = t.closest(".js-filter");
    if (f) {
      e.preventDefault();
      if (!el("modal").hidden) closePreview();
      if (f.dataset.fStatus) setFilter({ status: f.dataset.fStatus }, true);
      else if (f.dataset.fKind) setFilter({ kind: f.dataset.fKind }, true);
      else if (f.dataset.fColl) setFilter({ coll: f.dataset.fColl }, true);
      return;
    }
    const tog = t.closest(".grp-toggle") || t.closest(".bcol.folded")?.querySelector(".grp-toggle");
    if (tog) { collapsedGroups.has(tog.dataset.grp) ? collapsedGroups.delete(tog.dataset.grp) : collapsedGroups.add(tog.dataset.grp); renderView(); return; }
    const more = t.closest(".cell-more");
    if (more) { expandedCells.add(more.dataset.cell); renderView(); return; }
    if (t.matches(".sel-group")) {
      for (const u of filteredUnits().filter((x) => groupKey(x) === t.dataset.grp)) t.checked ? selected.add(u.key) : selected.delete(u.key);
      renderView();
      return;
    }
    if (t.matches(".sel-one")) { toggleSel(t.dataset.key, t.checked); return; }
    const open = t.closest("[data-open]");
    if (open) { hideHover(); cursor = order.indexOf(open.dataset.open); openPreview(open.dataset.open); return; }
    if (t.closest("a, button, input, select, summary")) return;
    const row = t.closest("#files-view [data-key]");
    if (row) { hideHover(); cursor = order.indexOf(row.dataset.key); openPreview(row.dataset.key); }
  });

  document.addEventListener("mouseover", (e) => {
    const a = e.target.closest("[data-preview]");
    if (!a || a.dataset.preview === hoverKey) return;
    clearTimeout(hoverTimer);
    hoverTimer = setTimeout(() => showHover(a, a.dataset.preview), 450);
  });
  document.addEventListener("mouseout", (e) => { const a = e.target.closest("[data-preview]"); if (a && !a.contains(e.relatedTarget)) hideHover(); });

  document.addEventListener("keydown", (e) => {
    const typing = e.target instanceof Element && e.target.closest("input, select, textarea");
    const modalOpen = !el("modal").hidden;
    if (e.key === "Escape") {
      if (typing) { e.target.blur(); return; }
      if (!el("help-panel").hidden) el("help-panel").hidden = true;
      else if (modalOpen) closePreview();
      else if (selected.size) { selected.clear(); renderView(); }
      return;
    }
    if (typing || e.metaKey || e.ctrlKey || e.altKey) return;
    const k = e.key;
    if (modalOpen && (k === "ArrowLeft" || k === "ArrowRight")) { e.preventDefault(); step(k === "ArrowLeft" ? -1 : 1); return; }
    if (k === "/") { e.preventDefault(); el("f-q").focus(); }
    else if (k === "j" || k === "k") {
      if (!order.length) return;
      cursor = Math.max(0, Math.min(order.length - 1, (cursor < 0 ? (k === "j" ? -1 : order.length) : cursor) + (k === "j" ? 1 : -1)));
      markCursor();
      el("files-view").querySelector(`[data-key="${CSS.escape(order[cursor])}"]`)?.scrollIntoView({ block: "nearest" });
      if (modalOpen) openPreview(order[cursor]);
    } else if (k === "Enter" && cursor >= 0) openPreview(order[cursor]);
    else if (k === "v" && !el("modal").hidden && previewFile && previewFile.ext === ".md") setPreviewMode(previewMode === "rendered" ? "source" : "rendered");
    else if (k === "o" && (state.item || cursor >= 0)) window.open(rawUrl(byKey.get(state.item || order[cursor]).primary.path), "_blank", "noopener");
    else if (k === "x" && cursor >= 0) toggleSel(order[cursor]);
    else if (k === "?") el("help-panel").hidden = !el("help-panel").hidden;
    else if ("lbc".includes(k.toLowerCase()) && k.length === 1) setFilter({ view: { l: "list", b: "board", c: "chron" }[k.toLowerCase()] });
  });

  load();
})();
