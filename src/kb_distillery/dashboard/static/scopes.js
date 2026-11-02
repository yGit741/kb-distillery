/* Scopes screen: list of saved scopes, and an editor with easy pruning of the raw files. */
(function () {
  "use strict";
  const DRAFTS_KEY = "thesis-wiki-scope-drafts";
  const STATIC = !!window.KB_STATIC;
  const FORMATS = ["printed-docs", "handwritten", "presentations", "llm-chats", "emails", "web-clips", "images"];
  const esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const byId = (id) => document.getElementById(id);
  if (STATIC) document.body.classList.add("sc-static");

  let scopes = [];
  let ed = null;            // editor state, null when nothing is open
  let corpus = null;        // lazily loaded rows from every format, for "Add files"
  let msg = { kind: "", text: "" };

  const nameOf = (p) => String(p).split("/").slice(2).join("/");
  const colOf = (r) => (Array.isArray(r.collection) ? r.collection : String(r.collection || "").split(",")).map((c) => c.trim()).filter(Boolean);
  const snapshot = () => JSON.stringify({ t: ed.title, w: ed.why, p: ed.rows.map((r) => r.path).sort() });
  const dirty = () => !!ed && !STATIC && snapshot() !== ed.baseline;

  function normSlug(raw) {
    let s = String(raw || "").toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
    if (s && !s.startsWith("scope-")) s = "scope-" + s;
    return s;
  }
  function readDrafts() {
    try { const d = JSON.parse(localStorage.getItem(DRAFTS_KEY) || "null"); return d && d.drafts ? d : { active: "", drafts: {} }; }
    catch (_) { return { active: "", drafts: {} }; }
  }
  function getDraft(key) { const s = readDrafts(); return s.drafts[key || s.active] || null; }
  function dropDraft(key) {
    try { const s = readDrafts(); delete s.drafts[key]; if (s.active === key) s.active = ""; localStorage.setItem(DRAFTS_KEY, JSON.stringify(s)); } catch (_) { /* ignore */ }
  }

  async function getJson(url) {
    const res = await fetch(url);
    let d = {};
    try { d = await res.json(); } catch (_) { /* non-JSON */ }
    if (!res.ok) throw new Error(d.error || ("HTTP " + res.status));
    return d;
  }
  async function postJson(url, body) {
    const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    let d = {};
    try { d = await res.json(); } catch (_) { /* non-JSON */ }
    if (!res.ok || d.error) {
      const e = new Error(d.error || ("HTTP " + res.status));
      e.status = res.status;
      throw e;
    }
    return d;
  }

  // ---------------------------------------------------------------- list
  async function loadList() {
    const note = byId("sc-list-note");
    try {
      scopes = (await getJson("/api/scopes")).scopes || [];
      note.textContent = scopes.length ? scopes.length + " scope" + (scopes.length === 1 ? "" : "s") : "No scopes yet.";
    } catch (e) { scopes = []; note.textContent = "Could not load scopes: " + e.message; }
    renderList();
  }
  function renderList() {
    const cur = ed && !ed.isNew ? ed.slug : null;
    byId("sc-list").innerHTML = scopes.map((s) => {
      const pct = Math.round(100 * (s.coverage || 0));
      return `<li class="sc-item ${s.slug === cur ? "active" : ""}" data-slug="${esc(s.slug)}">
        <h3>${esc(s.title || s.slug)}</h3>
        <div class="sc-meta"><span>${s.files ?? 0} files</span><span class="sc-bar" title="${pct}% digested"><i style="width:${pct}%"></i></span><span>${pct}%</span></div>
        <div class="sc-meta"><span>${esc(s.updated || "")}</span><a href="/graph?scope=${encodeURIComponent(s.slug)}">open in graph</a></div></li>`;
    }).join("");
  }

  // ---------------------------------------------------------------- editor
  function openEditor(state) {
    ed = state;
    ed.sel = new Set();
    ed.f = { undig: false, formats: new Set(), hubs: new Set(), text: "" };
    ed.baseline = ed.isNew ? "" : snapshot();
    msg = { kind: "", text: "" };
    renderList();
    const w = STATIC ? "" : "sc-write";
    byId("sc-editor").innerHTML = `
      <div class="sc-editor-head"><h2 id="sc-h">${ed.isNew ? "New scope" : esc(ed.title || ed.slug)}</h2><span class="sc-dirty" id="sc-dirty" hidden>unsaved changes</span></div>
      ${ed.isNew ? `<label class="sc-field"><span>Slug <span class="sc-hint">(kebab-case, scope- is added)</span></span><input id="sc-slug" value="${esc(ed.slug)}" placeholder="scope-my-topic" autocomplete="off"></label>` : `<p class="sc-note">${esc(ed.slug)}${ed.maturity ? " · " + esc(ed.maturity) : ""}</p>`}
      <label class="sc-field"><span>Title</span><input id="sc-title" value="${esc(ed.title)}" autocomplete="off" ${STATIC ? "readonly" : ""}></label>
      <label class="sc-field"><span>Why <span class="sc-hint">required; link a theme or question, e.g. [[theme-info-theory]]</span></span><textarea id="sc-why" ${STATIC ? "readonly" : ""}>${esc(ed.why)}</textarea></label>
      <div class="sc-projection" id="sc-proj"></div>
      <div class="sc-stats" id="sc-stats"></div>
      <div class="sc-toolbar" id="sc-tools"></div>
      <div class="sc-tablewrap" id="sc-table"></div>
      <div class="sc-add ${w}"><label class="sc-field"><span>Add files <span class="sc-hint">search the whole corpus by name, page or hub</span></span><input id="sc-add-q" class="sc-input" placeholder="Search raw files…" autocomplete="off"></label>
        <ul class="sc-results" id="sc-results"></ul></div>
      <div class="sc-footer" id="sc-footer"></div>`;
    byId("sc-title").addEventListener("input", (e) => { ed.title = e.target.value; refresh(); });
    byId("sc-why").addEventListener("input", (e) => { ed.why = e.target.value; refresh(); });
    const sl = byId("sc-slug");
    if (sl) sl.addEventListener("input", (e) => { ed.slug = e.target.value; });
    byId("sc-add-q").addEventListener("input", (e) => searchCorpus(e.target.value));
    byId("sc-tools").addEventListener("click", onToolsClick);
    byId("sc-tools").addEventListener("input", (e) => { if (e.target.id === "sc-text") { ed.f.text = e.target.value.toLowerCase(); renderTable(); } });
    byId("sc-table").addEventListener("click", onTableClick);
    byId("sc-table").addEventListener("change", onTableChange);
    byId("sc-results").addEventListener("click", onResultClick);
    byId("sc-footer").addEventListener("click", onFooterClick);
    renderProjection();
    refresh();
  }
  function refresh() { renderStats(); renderTools(); renderTable(); renderFooter(); const d = byId("sc-dirty"); if (d) d.hidden = !dirty(); }

  function renderProjection() {
    const el = byId("sc-proj");
    const p = ed.projection;
    if (!p || !el) { if (el) el.textContent = ""; return; }
    const n = (a) => (Array.isArray(a) ? a.length : 0);
    el.textContent = "Knowledge: " + n(p.hop0) + " pages cite these files, " + n(p.hop1) + " one hop away, " + n(p.hubs) + " hubs, " + n(p.themes) + " themes · " + n(p.uncovered) + " files uncovered";
  }
  function renderStats() {
    const n = ed.rows.length;
    const dig = ed.rows.filter((r) => r.disposition === "source").length;
    byId("sc-stats").textContent = n + " files · " + dig + " digested · " + (n ? Math.round((100 * dig) / n) : 0) + "%";
  }
  function formatsOf() { return [...new Set(ed.rows.map((r) => r.format).filter(Boolean))].sort(); }
  function hubsOf() { return [...new Set(ed.rows.flatMap(colOf))].sort(); }
  function renderTools() {
    const chip = (kind, val, label, on) => `<button type="button" class="sc-chip ${on ? "on" : ""}" data-kind="${kind}" data-val="${esc(val)}">${esc(label)}</button>`;
    const keep = byId("sc-text");
    const focused = keep && document.activeElement === keep;
    byId("sc-tools").innerHTML = chip("undig", "", "only undigested", ed.f.undig) +
      formatsOf().map((f) => chip("fmt", f, f, ed.f.formats.has(f))).join("") +
      hubsOf().slice(0, 12).map((h) => chip("hub", h, h, ed.f.hubs.has(h))).join("") +
      `<input id="sc-text" class="sc-input" placeholder="Filter rows…" value="${esc(ed.f.text)}" autocomplete="off">` +
      (STATIC ? "" : `<button type="button" class="sc-btn danger sc-write" data-kind="removesel" ${ed.sel.size ? "" : "disabled"}>Remove selected (${ed.sel.size})</button>`);
    if (focused) { const t = byId("sc-text"); t.focus(); t.setSelectionRange(t.value.length, t.value.length); }
  }
  function onToolsClick(e) {
    const b = e.target.closest("[data-kind]");
    if (!b) return;
    const k = b.dataset.kind, v = b.dataset.val;
    if (k === "undig") ed.f.undig = !ed.f.undig;
    else if (k === "fmt") ed.f.formats.has(v) ? ed.f.formats.delete(v) : ed.f.formats.add(v);
    else if (k === "hub") ed.f.hubs.has(v) ? ed.f.hubs.delete(v) : ed.f.hubs.add(v);
    else if (k === "removesel") { removePaths([...ed.sel]); return; }
    renderTools(); renderTable();
  }
  function visibleRows() {
    const f = ed.f;
    return ed.rows.filter((r) => (!f.undig || r.disposition === "queued") &&
      (!f.formats.size || f.formats.has(r.format)) &&
      (!f.hubs.size || colOf(r).some((c) => f.hubs.has(c))) &&
      (!f.text || (r.path + " " + (r.slug || "") + " " + colOf(r).join(" ")).toLowerCase().includes(f.text)));
  }
  function renderTable() {
    const rows = visibleRows();
    const allOn = rows.length > 0 && rows.every((r) => ed.sel.has(r.path));
    const body = rows.slice(0, 600).map((r) => `<tr class="${r.disposition === "queued" ? "undigested" : ""}">
        <td><input type="checkbox" data-path="${esc(r.path)}" ${ed.sel.has(r.path) ? "checked" : ""} aria-label="Select row"></td>
        <td title="${esc(r.path)}">${esc(nameOf(r.path))}</td><td>${esc(r.format || "")}</td>
        <td><span class="sc-badge ${esc(r.disposition)}">${esc(r.disposition)}</span></td>
        <td>${r.slug ? `<a href="/graph?focus=${encodeURIComponent(r.slug)}">${esc(r.slug)}</a>` : ""}</td>
        <td>${esc(colOf(r).join(", "))}</td>
        <td>${STATIC ? "" : `<button type="button" class="sc-x" data-rm="${esc(r.path)}" aria-label="Remove file" title="Remove">×</button>`}</td></tr>`).join("");
    byId("sc-table").innerHTML = ed.rows.length
      ? `<table class="sc-table"><thead><tr><th><input type="checkbox" id="sc-all" ${allOn ? "checked" : ""} aria-label="Select all shown"></th><th>File</th><th>Format</th><th>State</th><th>Page</th><th>Hub</th><th></th></tr></thead><tbody>${body}</tbody></table>` +
        (rows.length > 600 ? `<p class="sc-note">Showing the first 600 of ${rows.length}.</p>` : "")
      : `<p class="sc-note" style="padding:0.8rem">No files yet. Add some below, or build the set on the Graph with Add to scope.</p>`;
  }
  function onTableClick(e) {
    const rm = e.target.closest("[data-rm]");
    if (rm) removePaths([rm.dataset.rm]);
  }
  function onTableChange(e) {
    const t = e.target;
    if (t.id === "sc-all") {
      visibleRows().forEach((r) => (t.checked ? ed.sel.add(r.path) : ed.sel.delete(r.path)));
      renderTools(); renderTable();
    } else if (t.dataset.path) {
      t.checked ? ed.sel.add(t.dataset.path) : ed.sel.delete(t.dataset.path);
      renderTools();
      const all = byId("sc-all");
      if (all) all.checked = visibleRows().every((r) => ed.sel.has(r.path));
    }
  }
  function removePaths(paths) {
    const gone = new Set(paths);
    ed.rows = ed.rows.filter((r) => !gone.has(r.path));
    paths.forEach((p) => ed.sel.delete(p));
    refresh();
  }

  // ---------------------------------------------------------------- add files (search the corpus)
  async function loadCorpus() {
    if (corpus) return corpus;
    const all = [];
    await Promise.all(FORMATS.map(async (f) => {
      try { ((await getJson("/api/corpus?format=" + f)).rows || []).forEach((r) => all.push({ ...r, format: f })); } catch (_) { /* format unavailable */ }
    }));
    corpus = all;
    return corpus;
  }
  let searchSeq = 0;
  async function searchCorpus(q) {
    const box = byId("sc-results");
    q = q.trim().toLowerCase();
    if (!q) { box.innerHTML = ""; return; }
    const seq = ++searchSeq;
    box.innerHTML = `<li class="sc-note">Searching…</li>`;
    const rows = await loadCorpus();
    if (seq !== searchSeq) return;
    const have = new Set(ed.rows.map((r) => r.path));
    const hits = rows.filter((r) => !have.has(r.path) && (r.path + " " + (r.slug || "") + " " + colOf(r).join(" ")).toLowerCase().includes(q)).slice(0, 30);
    box.innerHTML = hits.length
      ? hits.map((r) => `<li><span class="sc-badge ${esc(r.disposition)}">${esc(r.disposition)}</span><span class="sc-path" title="${esc(r.path)}">${esc(r.format + " / " + nameOf(r.path))}</span><button type="button" class="sc-btn" data-add="${esc(r.path)}">+ add</button></li>`).join("")
      : `<li class="sc-note">No matching files outside this scope.</li>`;
  }
  function onResultClick(e) {
    const b = e.target.closest("[data-add]");
    if (!b || !corpus) return;
    const r = corpus.find((x) => x.path === b.dataset.add);
    if (!r) return;
    ed.rows.push({ path: r.path, format: r.format, disposition: r.disposition, slug: r.slug || "", page_type: "", digestion: "", collection: r.collection || [], year: r.year || null });
    b.closest("li").remove();
    refresh();
  }

  // ---------------------------------------------------------------- footer actions
  function setMsg(kind, text) { msg = { kind, text }; const m = byId("sc-msg"); if (m) { m.className = "sc-msg " + kind; m.textContent = text; } }
  function renderFooter() {
    const slug = ed.isNew ? normSlug(ed.slug) : ed.slug;
    const chat = "/chat?scope=" + encodeURIComponent(slug || "");
    let inline = "";
    if (ed.panel === "dup") inline = `<div class="sc-inline"><input id="sc-dup-slug" class="sc-input" placeholder="new slug, e.g. scope-copy" value="${esc(ed.dupSlug || "")}"><input id="sc-dup-title" class="sc-input" placeholder="title" value="${esc(ed.dupTitle || "")}"><button type="button" class="sc-btn primary" data-act="dup-go">Duplicate</button><button type="button" class="sc-btn" data-act="cancel">Cancel</button></div>`;
    if (ed.panel === "del") inline = `<div class="sc-inline"><span>Delete ${esc(slug)} for good? The raw files stay.</span><button type="button" class="sc-btn danger" data-act="del-go">Yes, delete</button><button type="button" class="sc-btn" data-act="cancel">Cancel</button></div>`;
    byId("sc-footer").innerHTML = `
      <button type="button" class="sc-btn primary sc-write" data-act="save">Save</button>
      ${ed.isNew ? "" : `<button type="button" class="sc-btn sc-write" data-act="dup">Duplicate</button><button type="button" class="sc-btn danger sc-write" data-act="del">Delete</button>`}
      <a class="sc-btn" href="${chat}">Ask in chat</a>
      ${ed.isNew ? "" : `<a class="sc-btn" href="/graph?scope=${encodeURIComponent(slug)}">Open in graph</a>`}
      ${inline}<div class="sc-msg ${msg.kind}" id="sc-msg">${esc(msg.text)}</div>`;
    const ds = byId("sc-dup-slug"), dt = byId("sc-dup-title");
    if (ds) ds.addEventListener("input", (e) => { ed.dupSlug = e.target.value; });
    if (dt) dt.addEventListener("input", (e) => { ed.dupTitle = e.target.value; });
  }
  async function onFooterClick(e) {
    const b = e.target.closest("[data-act]");
    if (!b) return;
    const act = b.dataset.act;
    if (act === "cancel") { ed.panel = null; renderFooter(); }
    else if (act === "dup") { ed.panel = "dup"; ed.dupSlug = ed.slug + "-copy"; ed.dupTitle = (ed.title || ed.slug) + " (copy)"; renderFooter(); }
    else if (act === "del") { ed.panel = "del"; renderFooter(); }
    else if (act === "save") await save();
    else if (act === "dup-go") await duplicate();
    else if (act === "del-go") await remove();
  }
  async function save() {
    const slug = ed.isNew ? normSlug(ed.slug) : ed.slug;
    if (!slug) return setMsg("err", "Give the scope a slug.");
    if (!ed.title.trim()) return setMsg("err", "Give the scope a title.");
    if (!ed.why.trim()) return setMsg("err", "Why is required: say what question this scope serves.");
    setMsg("", "Saving…");
    try {
      const r = await postJson("/api/scope/save", { slug, title: ed.title.trim(), why: ed.why, paths: ed.rows.map((x) => x.path), create: ed.isNew });
      if (ed.draftKey) dropDraft(ed.draftKey);
      ed.isNew = false; ed.slug = slug; ed.draftKey = "";
      ed.baseline = snapshot();
      try { history.replaceState(null, "", "/scopes?scope=" + encodeURIComponent(slug)); } catch (_) { /* ignore */ }
      await loadList();
      await reloadOpen(slug);
      setMsg("ok", "Saved" + (r.version ? " as " + r.version : "") + (r.sha ? " (" + String(r.sha).slice(0, 8) + ")" : "") + ".");
    } catch (err) {
      setMsg("err", err.status === 409 ? "Another ops session is open: " + err.message : "Save failed: " + err.message);
    }
  }
  async function reloadOpen(slug) {
    try { await openScope(slug, true); } catch (_) { /* keep the editor as is */ }
  }
  async function duplicate() {
    const ns = normSlug(ed.dupSlug);
    if (!ns) return setMsg("err", "Give the copy a slug.");
    try {
      await postJson("/api/scope/duplicate", { slug: ed.slug, new_slug: ns, title: (ed.dupTitle || "").trim() || ns });
      await loadList();
      await openScope(ns);
      setMsg("ok", "Duplicated as " + ns + ".");
    } catch (err) { setMsg("err", err.status === 409 ? "Another ops session is open: " + err.message : "Duplicate failed: " + err.message); }
  }
  async function remove() {
    const slug = ed.slug;
    try {
      await postJson("/api/scope/delete", { slug });
      ed = null;
      byId("sc-editor").innerHTML = `<p class="sc-note sc-empty">Deleted ${esc(slug)}.</p>`;
      try { history.replaceState(null, "", "/scopes"); } catch (_) { /* ignore */ }
      await loadList();
    } catch (err) { ed.panel = null; renderFooter(); setMsg("err", err.status === 409 ? "Another ops session is open: " + err.message : "Delete failed: " + err.message); }
  }

  // ---------------------------------------------------------------- open + boot
  async function openScope(slug, keepMsg) {
    const d = await getJson("/api/scope?slug=" + encodeURIComponent(slug));
    const keep = keepMsg ? msg : null;
    openEditor({ isNew: false, slug: d.slug || slug, title: d.title || "", why: d.why || "", maturity: d.maturity || "", rows: d.rows || [], projection: d.projection || null });
    if (keep) { msg = keep; renderFooter(); }
  }
  async function openDraft(key) {
    const d = getDraft(key);
    if (!d) { openEditor({ isNew: true, slug: "", title: "", why: "", rows: [] }); ed.baseline = ""; setMsg("", "That draft no longer exists. Add files below, or select nodes on the Graph."); return; }
    if (d.isNew) {
      openEditor({ isNew: true, slug: d.slug || "", title: d.title || "", why: "", rows: (d.rows || []).slice(), draftKey: d.slug });
      ed.baseline = "";
    } else {
      await openScope(d.slug);
      const have = new Set(ed.rows.map((r) => r.path));
      (d.rows || []).forEach((r) => { if (!have.has(r.path)) ed.rows.push(r); });
      ed.draftKey = d.slug;
      renderTable && renderTable();
      setMsg("", "Unsaved: rows added from the Graph are merged in. Press Save to keep them.");
    }
  }
  function newBlank() {
    // "New scope" always starts empty; a Graph draft arrives only through ?draft=<key> ("Save scope…").
    openEditor({ isNew: true, slug: "", title: "", why: "", rows: [] });
    setMsg("", "Add files below, or select nodes on the Graph and press Add to scope.");
    ed.baseline = "";
  }
  async function boot() {
    byId("sc-list").addEventListener("click", async (e) => {
      if (e.target.closest("a")) return;
      const li = e.target.closest("[data-slug]");
      if (!li) return;
      try { await openScope(li.dataset.slug); history.replaceState(null, "", "/scopes?scope=" + encodeURIComponent(li.dataset.slug)); } catch (err) { byId("sc-list-note").textContent = "Could not open: " + err.message; }
    });
    byId("sc-new").addEventListener("click", () => { clearParam(); newBlank(); });
    await loadList();
    const q = new URLSearchParams(location.search);
    if (q.get("draft") && !STATIC) await openDraft(q.get("draft"));
    else if (q.get("new") && !STATIC) newBlank();
    else if (q.get("scope")) { try { await openScope(q.get("scope")); } catch (err) { byId("sc-list-note").textContent = "Could not open " + q.get("scope") + ": " + err.message; } }
  }
  function clearParam() { try { history.replaceState(null, "", "/scopes?new=1"); } catch (_) { /* ignore */ } }
  boot();
})();
