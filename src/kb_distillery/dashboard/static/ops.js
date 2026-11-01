(function () {
  let data = null;
  let filter = "attention";
  let selectedRun = null;

  const GLYPH = { ok: "✓", warn: "!", error: "✗", info: "i" };
  const el = (id) => document.getElementById(id);

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function empty(msg) {
    return `<p class="empty-state">${esc(msg)}</p>`;
  }

  function age(hours) {
    if (hours === null || hours === undefined) return "?";
    if (hours < 1) return `${Math.max(1, Math.round(hours * 60))}m`;
    if (hours < 48) return `${Math.floor(hours)}h`;
    return `${Math.floor(hours / 24)}d`;
  }

  function ago(iso) {
    if (!iso) return "";
    const h = (Date.now() - new Date(iso).getTime()) / 3600000;
    return Number.isFinite(h) ? `${age(h)} ago` : "";
  }

  // "cmd   # or: other" → command pill + muted hint, with a copy button for the command
  function command(text) {
    if (!text) return "";
    const i = text.indexOf("   # ");
    const cmd = i >= 0 ? text.slice(0, i).trim() : text.trim();
    const hint = i >= 0 ? text.slice(i + 5).trim() : "";
    return `<div class="ops-cmd"><code>$ ${esc(cmd)}</code><button type="button" class="ops-copy" data-copy="${esc(cmd)}">Copy</button></div>`
      + (hint ? `<div class="ops-hint">${esc(hint)}</div>` : "");
  }

  function section(id) {
    return (data.doc.sections || []).find((s) => s.id === id);
  }

  function renderBanner() {
    const head = data.doc.sections[0];
    const banner = head.blocks.find((b) => b.kind === "banner");
    el("banner").innerHTML = banner
      ? `<div class="ops-banner is-${esc(banner.status)}"><div class="ops-banner-title">${esc(GLYPH[banner.status] || "")} ${esc(banner.title)}</div>`
        + `<div class="ops-banner-sub">${esc(banner.subtitle)}</div></div>`
      : "";
    const threads = data.threads;
    const stale = threads.filter((t) => t.state !== "active").length;
    const prs = threads.filter((t) => t.kind === "pr");
    const h = data.hygiene;
    const last = data.runs[0];
    const cards = [
      ["Open PRs", prs.length, prs.some((t) => t.state === "stale") ? "warn" : ""],
      ["Threads", threads.length, ""],
      ["Stale / blocked", stale, stale ? "warn" : ""],
      ["Errors", h.errors, h.errors ? "bad" : ""],
      ["Warnings", h.warnings, h.warnings ? "warn" : ""],
      ["Last nightly", last ? ago(last.started) : (data.nightly && data.nightly.last_run ? ago(data.nightly.last_run) : "never"),
        (last && last.status === "error") || (data.nightly && !data.nightly.loaded) ? "bad" : ""],
    ];
    el("summary-cards").innerHTML = cards
      .map(([label, value, cls]) => `<div class="summary-card ${cls ? "is-" + cls : ""}"><div class="label">${esc(label)}</div><div class="value">${esc(value)}</div></div>`)
      .join("");
  }

  const FILTERS = [
    ["attention", "Needs attention", (t) => t.state !== "active"],
    ["active", "Active", (t) => t.state === "active"],
    ["pr", "PRs", (t) => t.kind === "pr"],
    ["all", "All", () => true],
  ];

  function threadCard(t, card) {
    const facts = (card && card.facts) || [];
    const notes = (card && card.notes) || t.notes || [];
    const status = (card && card.status) || t.status;
    const title = t.link ? `<a href="${esc(t.link)}" target="_blank" rel="noopener">${esc(t.title)}</a>` : esc(t.title);
    return `<article class="ops-thread is-${esc(status)}">
      <header><h3>${title}</h3><span class="ops-chip is-${esc(status)}">${esc(t.state)}</span></header>
      <div class="ops-facts">${facts.map(([k, v]) => `<span><em>${esc(k)}</em> ${esc(v)}</span>`).join("")}</div>
      ${notes.length ? `<ul class="ops-notes">${notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>` : ""}
      ${command(t.next)}
    </article>`;
  }

  function renderThreads() {
    const cards = {};
    const sec = section("threads");
    if (sec) for (const b of sec.blocks) for (const c of b.items || []) cards[c.id] = c;
    el("thread-filters").innerHTML = FILTERS.map(([key, label, fn]) => {
      const n = data.threads.filter(fn).length;
      return `<button type="button" class="ops-filter${filter === key ? " active" : ""}" data-filter="${key}">${esc(label)} <b>${n}</b></button>`;
    }).join("");
    const fn = FILTERS.find(([key]) => key === filter)[2];
    const shown = data.threads.filter(fn);
    el("threads").innerHTML = shown.length
      ? shown.map((t) => threadCard(t, cards[t.id])).join("")
      : empty(filter === "attention" ? "Nothing stale or blocked." : "No threads here.");
  }

  function findingList(items, emptyMsg) {
    if (!items.length) return empty(emptyMsg);
    return items.map((f) => `<div class="ops-finding is-${esc(f.status || f.severity)}">
      <div><b>${esc(GLYPH[f.status || f.severity] || "")} ${esc(f.label || f.kind)}</b> — ${esc(f.detail)}</div>
      ${command(f.fix)}
      ${f.more ? `<details><summary>full output</summary><pre>${esc(f.more)}</pre></details>` : ""}
    </div>`).join("");
  }

  function renderNeeds() {
    const sec = section("needs");
    const items = sec ? sec.blocks.flatMap((b) => b.items || []) : [];
    el("needs").innerHTML = findingList(items, "Nothing outside the threads needs you.");
  }

  function renderRuns() {
    const runs = data.runs.slice().reverse();
    if (!runs.length) {
      el("runs").innerHTML = empty("No nightly run logged yet — the first one after this change starts the history.");
      el("run-detail").innerHTML = "";
      return;
    }
    el("runs").innerHTML = runs.map((r, i) => {
      const when = new Date(r.started);
      const label = `${when.toLocaleString()} · ${r.status} · ${r.errors} error(s), ${r.warnings} warning(s) · mail ${r.notify || "?"}`;
      return `<button type="button" class="ops-run is-${esc(r.status)}${selectedRun === r.started ? " active" : ""}" data-run="${esc(r.started)}" title="${esc(label)}" aria-label="${esc(label)}"></button>`;
    }).join("");
    const run = data.runs.find((r) => r.started === selectedRun) || data.runs[0];
    const sync = run.sync || {};
    if (run.source === "log") {
      el("run-detail").innerHTML = `<div class="ops-facts ops-run-facts"><span><em>started</em> ${esc(new Date(run.started).toLocaleString())}</span>`
        + `<span><em>errors</em> ${esc(run.errors)}</span><span><em>warnings</em> ${esc(run.warnings)}</span><span><em>mail</em> ${esc(run.notify || "?")}</span></div>`
        + `<p class="subtle">From the launchd transcript (before the structured run log) — see the nightly log below.</p>`;
      return;
    }
    const facts = [
      ["started", new Date(run.started).toLocaleString()],
      ["took", `${run.duration ?? "?"} s`],
      ["sync", sync.failed ? "failed" : sync.skipped ? "skipped" : sync.pushed === false ? "not pushed" : "ok"],
      ["commits", sync.commits ?? "?"],
      ["threads", run.threads],
      ["mail", run.notify || "?"],
      ["deploy", (run.deploy && run.deploy.state) || "?"],
    ];
    el("run-detail").innerHTML = `<div class="ops-facts ops-run-facts">${facts.map(([k, v]) => `<span><em>${esc(k)}</em> ${esc(v)}</span>`).join("")}</div>`
      + `<div class="ops-steps">${(run.steps || []).map((s) => `<span class="ops-chip is-${esc(s.status)}">${esc(s.name)}${s.outcome ? " · " + esc(s.outcome) : ""}</span>`).join("")}</div>`
      + findingList((run.findings || []).map((f) => ({ ...f, status: f.severity })), "That run was clean.");
  }

  function renderRecent() {
    const sec = section("recent");
    if (!sec) return;
    el("recent").innerHTML = sec.blocks.map((b) => {
      if (b.kind === "text") return `<p class="subtle">${esc(b.text)}</p>`;
      if (b.kind === "table") {
        return `<table class="data-table"><thead><tr>${b.columns.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead>`
          + `<tbody>${b.rows.map((r) => `<tr>${r.map((v, i) => `<td${i === 0 ? ' class="nowrap"' : ""}>${i === 0 ? `<code>${esc(v)}</code>` : esc(v)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
      }
      return "";
    }).join("");
  }

  function renderVault() {
    const sec = section("vault");
    const stats = sec ? sec.blocks.flatMap((b) => b.items || []) : [];
    el("vault").innerHTML = `<div class="ops-vault">${stats.map((s) => `<div><div class="label">${esc(s.label)}</div><div class="value${s.status ? " is-" + esc(s.status) : ""}">${esc(s.value)}</div>${s.hint ? `<div class="subtle">${esc(s.hint)}</div>` : ""}</div>`).join("")}</div>`;
  }

  function render() {
    el("status-line").textContent = `${data.subject} · checked ${ago(data.generated_at) || "just now"} · ${data.hygiene.checks.length} checks in ${data.hygiene.elapsed}s`;
    renderBanner();
    renderThreads();
    renderNeeds();
    renderRuns();
    renderRecent();
    renderVault();
    el("log").textContent = data.log || "No nightly log yet.";
    el("log").scrollTop = el("log").scrollHeight;
  }

  async function load(refresh) {
    el("status-line").textContent = refresh ? "Re-running the checks…" : "Running the checks…";
    el("btn-refresh").disabled = true;
    try {
      const res = await fetch(`/api/ops${refresh ? "?refresh=1" : ""}`);
      const body = await res.json();
      if (!res.ok) throw new Error(body.error || res.statusText);
      data = body;
      render();
    } catch (err) {
      el("status-line").textContent = `Could not load: ${err.message}`;
    } finally {
      el("btn-refresh").disabled = false;
    }
  }

  document.addEventListener("click", async (e) => {
    const f = e.target.closest("[data-filter]");
    if (f) {
      filter = f.dataset.filter;
      renderThreads();
      return;
    }
    const r = e.target.closest("[data-run]");
    if (r) {
      selectedRun = r.dataset.run;
      renderRuns();
      return;
    }
    const c = e.target.closest("[data-copy]");
    if (c) {
      try {
        await navigator.clipboard.writeText(c.dataset.copy);
        c.textContent = "Copied";
        setTimeout(() => (c.textContent = "Copy"), 1200);
      } catch (_) {
        c.textContent = "Select it";
      }
    }
  });
  el("btn-refresh").addEventListener("click", () => load(true));
  load(false);
})();
