// Snapshots tab of the private site (inlined by backend/src/kb/share/build.py, private profile only).
//
// Talks to the Worker's admin API (share/admin.js) with the session cookie plus the
// `X-KB-Admin: 1` CSRF header: GET snapshots, DELETE snapshots/<worker> (type-the-name confirm),
// POST prune (dry run → orphan banner). Creating or updating a snapshot stays a CLI step: the
// "New snapshot" box only builds the `pixi run share -- snapshot <name> <version>` command from the
// knowledge versions embedded at build time (<script id="kb-versions">); a row's "Update…" fills it
// with that snapshot's name in replace mode (same Worker, same link, `--replace`). Static code; no
// data but that list.
(function () {
  "use strict";
  const API = "/admin/api/";
  const NAME_RE = /^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/;
  const root = document.getElementById("kb-panel");
  if (!root) return;
  let versions = [];
  try { versions = JSON.parse(document.getElementById("kb-versions").textContent) || []; } catch (_e) { versions = []; }
  let built = false;

  // ---------- tiny DOM helpers (textContent only — API data is never parsed as HTML) ----------
  function el(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === "class") n.className = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat()) if (kid != null) n.append(kid instanceof Node ? kid : String(kid));
    return n;
  }
  const $ = (id) => document.getElementById(id);

  async function api(method, path, body) {
    const init = { method, credentials: "same-origin", headers: { "X-KB-Admin": "1", Accept: "application/json" } };
    if (body !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(body); }
    const res = await fetch(API + path, init);
    let data = null;
    try { data = await res.json(); } catch (_e) { data = null; }
    return { status: res.status, data: data || {} };
  }

  function copy(text, btn) {
    const done = () => { const t = btn.textContent; btn.textContent = "Copied"; setTimeout(() => { btn.textContent = t; }, 1200); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, () => window.prompt("Copy:", text));
    } else {
      window.prompt("Copy:", text);
    }
  }

  // Names of the snapshots in the last listing (the box warns before an accidental duplicate).
  const knownNames = new Set();
  let refreshBox = () => {};

  // ---------- skeleton ----------
  function skeleton() {
    root.append(
      el("div", { class: "kbp-head" },
        el("h2", {}, "Snapshots"),
        el("span", { class: "kbp-muted", id: "kbp-main" }),
        el("span", { class: "kb-spacer" }),
        el("button", { type: "button", class: "kbp-btn", onclick: load }, "Refresh")),
      el("p", { class: "kbp-muted" }, "Public, forwardable copies of a knowledge version — anyone with the link can open one."),
      el("div", { id: "kbp-status", role: "status" }),
      el("div", { id: "kbp-banner" }),
      el("div", { id: "kbp-table" }),
      el("ul", { id: "kbp-notes", class: "kbp-notes" }),
      newBox(),
      confirmDialog());
  }

  function newBox() {
    const select = el("select", { id: "kbp-ver", "aria-label": "Knowledge version" },
      versions.map((v, i) => el("option", { value: "kb-" + v.version, selected: i === 0 },
        `kb-${v.version} · ${v.date}${v.subject ? " · " + v.subject.slice(0, 60) : ""}`)));
    const name = el("input", { id: "kbp-name", type: "text", placeholder: "name (e.g. cohen)", autocomplete: "off",
                                spellcheck: "false", maxlength: "40", "aria-label": "Snapshot name" });
    const cmd = el("code", { id: "kbp-cmd" });
    const btn = el("button", { type: "button", class: "kbp-btn", id: "kbp-copy-cmd" }, "Copy");
    const hint = el("span", { class: "kbp-muted", id: "kbp-name-hint" });
    const replace = el("input", { id: "kbp-replace", type: "checkbox" });
    const title = el("h3", { id: "kbp-box-title" }, "New snapshot");
    const note = el("p", { class: "kbp-muted", id: "kbp-box-note" });
    function update() {
      const n = name.value.trim().toLowerCase();
      const ok = NAME_RE.test(n) && n !== "kb";
      const existing = knownNames.has(n);
      hint.textContent = n && !ok ? "lowercase letters, digits and inner hyphens; not “kb”"
        : existing && !replace.checked ? "a snapshot with this name exists — tick “update in place” to replace it" : "";
      cmd.textContent = `pixi run share -- snapshot ${ok ? n : "<name>"} ${select.value || "<version>"}${replace.checked ? " --replace" : ""}`;
      btn.disabled = !ok || !select.value || (existing && !replace.checked);
      title.textContent = replace.checked ? "Update snapshot" : "New snapshot";
      note.textContent = replace.checked
        ? "Same Worker, same link: whoever has the URL sees the chosen version from now on (the footer shows kb version "
          + "and build date). The audit runs again, an older version is refused without --force, and every earlier version "
          + "stays on Cloudflare — `pixi run share -- history <name>` lists them, `rollback --worker <worker>` brings one back."
        : "Run it in the repo on the Mac: it audits the public build, then deploys snapshot-<date>-<name>.";
    }
    name.addEventListener("input", update);
    select.addEventListener("change", update);
    replace.addEventListener("change", update);
    btn.addEventListener("click", () => copy(cmd.textContent, btn));
    update();
    refreshBox = update;
    return el("section", { class: "kbp-box", id: "kbp-box" },
      title,
      versions.length ? null : el("p", { class: "kbp-muted" }, "No knowledge versions were embedded in this build."),
      el("div", { class: "kbp-row" }, select, name, hint),
      el("div", { class: "kbp-row" }, el("label", { class: "kbp-check" }, replace, " update in place (keep the link)")),
      el("div", { class: "kbp-row" }, cmd, btn),
      note);
  }

  // "Update…" on a row: the box in replace mode with that snapshot's name, current version preselected.
  function askUpdate(s) {
    $("kbp-name").value = s.name;
    $("kbp-replace").checked = true;
    const select = $("kbp-ver");
    if (select.options.length) select.selectedIndex = 0;   // newest knowledge version: the usual reason to update
    refreshBox();
    $("kbp-box").scrollIntoView({ behavior: "smooth", block: "nearest" });
    $("kbp-name").focus();
  }

  function confirmDialog() {
    const input = el("input", { id: "kbp-confirm-input", type: "text", autocomplete: "off", spellcheck: "false" });
    const go = el("button", { type: "button", class: "kbp-btn kbp-danger", id: "kbp-confirm-go", disabled: true }, "Delete");
    const dlg = el("dialog", { id: "kbp-confirm", class: "kbp-dialog" },
      el("h3", {}, "Delete snapshot"),
      el("p", {}, "This removes the Worker and its link for everyone. Type ", el("code", { id: "kbp-confirm-name" }), " to confirm."),
      input,
      el("p", { id: "kbp-confirm-msg", class: "kbp-muted" }),
      el("div", { class: "kbp-row" },
        el("button", { type: "button", class: "kbp-btn", onclick: () => dlg.close() }, "Cancel"), go));
    input.addEventListener("input", () => { go.disabled = input.value !== dlg.dataset.worker; });
    go.addEventListener("click", async () => {
      const worker = dlg.dataset.worker;
      go.disabled = true;
      $("kbp-confirm-msg").textContent = "Deleting…";
      const r = await api("DELETE", "snapshots/" + encodeURIComponent(worker), { confirm: input.value });
      if (r.status === 200) { dlg.close(); setStatus(`Deleted ${worker}.`); load(); }
      else { $("kbp-confirm-msg").textContent = r.data.error || `failed (HTTP ${r.status})`; go.disabled = false; }
    });
    return dlg;
  }

  function askDelete(worker) {
    const dlg = $("kbp-confirm");
    dlg.dataset.worker = worker;
    $("kbp-confirm-name").textContent = worker;
    $("kbp-confirm-input").value = "";
    $("kbp-confirm-go").disabled = true;
    $("kbp-confirm-msg").textContent = "";
    if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", "");
    $("kbp-confirm-input").focus();
  }

  function setStatus(text, cls) {
    const s = $("kbp-status");
    s.replaceChildren();
    if (text) s.append(el("p", { class: "kbp-msg " + (cls || "") }, text));
  }

  function setupHint(error) {
    $("kbp-status").replaceChildren(el("div", { class: "kbp-msg kbp-warn" },
      el("strong", {}, error || "panel not configured"),
      el("p", {}, "One-time setup: create a Cloudflare API token with Account → Workers Scripts → Edit and "
        + "Account → Account Analytics → Read, copy it, then in the repo run:"),
      el("pre", {}, "pbpaste | npx wrangler@4.151.3 secret put CF_API_TOKEN --name kb && pbcopy < /dev/null"),
      el("p", {}, "Then reload this tab. See the share-kb skill for details.")));
  }

  // ---------- table ----------
  function onlineCell(v) {
    const [cls, label] = v === true ? ["ok", "online"] : v === false ? ["down", "down"] : ["unk", "unknown"];
    return el("span", { class: "kbp-dot kbp-" + cls, title: label }, label);
  }
  function behindCell(n) {
    if (n == null) return el("span", { class: "kbp-badge", title: "different schema version or unknown" }, "?");
    return el("span", { class: "kbp-badge " + (n === 0 ? "kbp-fresh" : "kbp-stale") }, n === 0 ? "up to date" : `${n} behind`);
  }

  function table(rows) {
    if (!rows.length) return el("p", { class: "kbp-muted" }, "No snapshots yet.");
    return el("div", { class: "kbp-scroll" }, el("table", { class: "kbp-table" },
      el("thead", {}, el("tr", {}, ["Name", "kb version", "Behind main", "Views 7d", "Built", "Online", ""].map((h) => el("th", {}, h)))),
      el("tbody", {}, rows.map((s) => el("tr", {},
        el("td", { title: s.worker }, el("strong", {}, s.name), el("div", { class: "kbp-muted kbp-mono" }, s.worker)),
        el("td", { class: "kbp-mono" }, s.kb_version ? "kb-" + s.kb_version : "—",
          s.content_sha ? el("div", { class: "kbp-muted" }, s.content_sha.slice(0, 7)) : null),
        el("td", {}, behindCell(s.behind_main)),
        el("td", { class: "kbp-num" }, String(s.views_7d)),
        el("td", { class: "kbp-mono" }, s.built_at ? s.built_at.slice(0, 10) : "—"),
        el("td", {}, onlineCell(s.online)),
        el("td", { class: "kbp-actions" },
          el("a", { class: "kbp-btn", href: s.url, target: "_blank", rel: "noopener" }, "Open"),
          el("button", { type: "button", class: "kbp-btn", onclick: (e) => copy(s.url, e.currentTarget) }, "Copy link"),
          el("button", { type: "button", class: "kbp-btn", title: "Serve another knowledge version at this same link",
                         onclick: () => askUpdate(s) }, "Update…"),
          el("button", { type: "button", class: "kbp-btn kbp-danger", onclick: () => askDelete(s.worker) }, "Delete")))))));
  }

  function banner(plan) {
    const b = $("kbp-banner");
    b.replaceChildren();
    const parts = [];
    if (plan.orphans && plan.orphans.length) {
      parts.push(el("p", {}, el("strong", {}, "Orphans: "), plan.orphans.join(", "),
        " — snapshot Workers with no reachable manifest. Remove with ", el("code", {}, "pixi run share -- prune --apply"), " or Delete above."));
    }
    if (plan.unknown && plan.unknown.length) {
      parts.push(el("p", {}, el("strong", {}, "Not answering: "), plan.unknown.join(", "), " (manifest timed out — left alone)."));
    }
    if (plan.foreign && plan.foreign.length) {
      parts.push(el("p", {}, el("strong", {}, "Not ours: "), plan.foreign.join(", "), " — other Workers in the account, never touched."));
    }
    if (parts.length) b.append(el("div", { class: "kbp-msg kbp-warn" }, parts));
  }

  async function load() {
    if (location.protocol === "file:") {
      setStatus("The Snapshots panel works on the deployed private site only (it needs the sign-in Worker).", "kbp-warn");
      return;
    }
    setStatus("Loading…");
    let r;
    try { r = await api("GET", "snapshots"); } catch (e) { setStatus("Could not reach the panel API: " + e.message, "kbp-err"); return; }
    if (r.status === 503) { setupHint(r.data.error); $("kbp-table").replaceChildren(); return; }
    if (r.status === 401) { setStatus("Signed out — reload the page to sign in again.", "kbp-err"); return; }
    if (r.status === 403) { setStatus("This account cannot manage snapshots (" + (r.data.error || "forbidden") + ").", "kbp-err"); return; }
    if (r.status !== 200) { setStatus(r.data.error || `Panel API failed (HTTP ${r.status}).`, "kbp-err"); return; }
    setStatus("");
    $("kbp-main").textContent = r.data.main && r.data.main.kb_version ? `main is kb-${r.data.main.kb_version}` : "";
    knownNames.clear();
    (r.data.snapshots || []).forEach((s) => knownNames.add(s.name));
    $("kbp-table").replaceChildren(table(r.data.snapshots || []));
    refreshBox();
    $("kbp-notes").replaceChildren(...(r.data.notes || []).map((n) => el("li", {}, n)));
    try {
      const p = await api("POST", "prune");
      if (p.status === 200) banner(p.data);
    } catch (_e) { /* the banner is best-effort */ }
  }

  // The shell opens extra tabs through this registry (see SHELL_JS in build.py).
  window.KB_EXTRA_TABS = Object.assign(window.KB_EXTRA_TABS || {}, {
    snapshots() {
      if (built) return;
      built = true;
      skeleton();
      load();
    },
  });
})();
