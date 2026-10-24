(function () {
  let snapshot = null;
  let filter = "all";
  let query = "";

  function el(id) {
    return document.getElementById(id);
  }

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function empty(msg) {
    return `<p class="empty-state">${escapeHtml(msg)}</p>`;
  }

  function copyButton(text) {
    return `<button type="button" class="lc-copy" data-copy="${escapeHtml(text)}">Copy</button>`;
  }

  // A snapshot captured for the shared site carries no working-tree state (`working`, `nightly`,
  // `stale_worktrees`, `infra_branches` are absent): those parts render as "not in this snapshot".
  function renderSummary(s) {
    const w = s.working;
    const cards = [
      ["Knowledge version", s.version ? `kb-${s.version}` : "none yet"],
      ["Next step", `kb-${s.next_version}`],
      ["Schema", s.schema.version],
      ["Snapshots", s.snapshots.length ? s.snapshots[0].tag : "none"],
    ];
    if (w) {
      const sessions = w.sessions.ingest.length + w.sessions.distill.length + w.sessions.researcher.length + (w.sessions.ops ? 1 : 0);
      cards.push(
        ["Unpushed", w.unpushed ?? "?"],
        ["Open sessions", sessions],
        ["Uncommitted", `${w.lanes.knowledge} kb · ${w.lanes.tooling} tool`],
      );
    }
    el("summary-cards").innerHTML = cards
      .map(([label, value]) =>
        `<div class="summary-card"><div class="label">${escapeHtml(label)}</div><div class="value">${escapeHtml(value)}</div></div>`)
      .join("");
  }

  function renderAlerts(s) {
    const alerts = [];
    if (s.branch !== "main") alerts.push(`This checkout is on <code>${escapeHtml(s.branch || "detached HEAD")}</code> — knowledge commits only happen on main.`);
    if (s.policy.hooks_installed === false) alerts.push("Git hooks are not installed — run <code>pixi run install-hooks</code> so commit messages and pushes are checked.");
    if (s.schema.pending.length) alerts.push(`Pending schema migrations: ${s.schema.pending.map(escapeHtml).join(", ")}.`);
    if (s.working && s.working.think_dirty) alerts.push(`${s.working.think_dirty} think/ file(s) changed — they will be committed as <code>kb(think)</code> before the next operation or tonight.`);
    if (s.nightly && s.nightly.hint) alerts.push(`Nightly sync ${escapeHtml(s.nightly.summary)} — run <code>${escapeHtml(s.nightly.hint)}</code>.`);
    const stale = s.stale_worktrees || [];
    const merged = stale.filter((w) => w.merged);
    const session = stale.filter((w) => !w.merged);
    if (merged.length) alerts.push(`${merged.length} merged worktree(s) left behind (${merged.map((w) => escapeHtml(w.branch)).join(", ")}) — <code>pixi run ship -- prune --apply</code> removes the clean ones.`);
    if (session.length) alerts.push(`${session.length} session worktree(s) on <code>worktree-*</code> branches (${session.map((w) => `${escapeHtml(w.branch)}: ${w.ahead} commits, ${w.dirty} uncommitted`).join("; ")}) — turn into a PR with <code>pixi run ship -- start &lt;feature&gt;</code> inside it, or <code>ship -- prune --drop</code>.`);
    el("alerts").innerHTML = alerts.map((a) => `<div class="lc-alert">${a}</div>`).join("");
  }

  function chipFor(r) {
    if (r.kind === "kb") return `<span class="lc-chip kb">kb-${escapeHtml(r.kb_version)}</span>`;
    if (r.kind === "pr-merge") {
      const label = r.pr ? `#${r.pr}` : "retro";
      const cls = r.type === "schema" || r.type === "paradigm" ? "schema" : "pr";
      const link = r.pr && snapshot.github ? `${snapshot.github}/pull/${r.pr}` : null;
      const chip = `<span class="lc-chip ${cls}">${escapeHtml(label)}${r.kb_version ? " → kb-" + escapeHtml(r.kb_version) : ""}</span>`;
      return link ? `<a href="${link}" target="_blank" rel="noopener noreferrer">${chip}</a>` : chip;
    }
    return `<span class="lc-chip other">${escapeHtml(r.kind === "infra" ? r.type || "infra" : "legacy")}</span>`;
  }

  function matches(r) {
    if (filter === "kb" && r.kind !== "kb") return false;
    if (filter === "infra" && r.kind === "kb") return false;
    if (filter === "schema" && !(r.type === "schema" || r.type === "paradigm")) return false;
    if (query) {
      const hay = `${r.subject} ${r.op || ""} ${r.target || ""} ${r.short}`.toLowerCase();
      if (!query.split(/\s+/).every((t) => hay.includes(t))) return false;
    }
    return true;
  }

  function renderTimeline() {
    const rows = snapshot.timeline.filter(matches);
    if (!rows.length) {
      el("timeline").innerHTML = empty(snapshot.timeline.length ? "No commits match." : "No history yet.");
      return;
    }
    el("timeline").innerHTML = rows.map((r) => {
      const extra = [];
      if (r.op && r.kind === "kb") extra.push(`op ${escapeHtml(r.op)} · ${escapeHtml(r.target || "")}`);
      if (r.reverts) extra.push(`reverts ${escapeHtml(r.reverts.slice(0, 9))}`);
      if (r.reverted_by) extra.push(`undone by ${escapeHtml(r.reverted_by.slice(0, 9))}`);
      if (r.kind === "kb" && !r.reverted_by && r.op && !["think", "import", "undo"].includes(r.op)) {
        extra.push(`undo: <code>pixi run ops -- undo ${escapeHtml(r.short)}</code>`);
      }
      const snap = r.snapshot_tag ? ` <span class="lc-chip snap">${escapeHtml(r.snapshot_tag)}</span>` : "";
      return `<div class="lc-row${r.reverted_by ? " undone" : ""}">
        ${chipFor(r)}
        <span class="lc-date">${escapeHtml(r.date.slice(0, 10))}</span>
        <span class="lc-subj">${escapeHtml(r.subject)}${snap}${extra.length ? `<small>${extra.join(" · ")}</small>` : ""}</span>
        <span class="lc-sha">${escapeHtml(r.short)}</span>
      </div>`;
    }).join("");
  }

  function renderSnapshots(list) {
    if (!list.length) {
      el("snapshots").innerHTML = empty("No snapshots yet — pixi run ops -- snapshot \"label\"");
      return;
    }
    const rows = list.map((s) => {
      const cmd = `pixi run ops -- restore ${s.tag}`;
      return `<tr><td><code>${escapeHtml(s.tag)}</code></td><td>${escapeHtml(s.date)}</td><td>${escapeHtml(s.label)}</td><td>${copyButton(cmd)}</td></tr>`;
    }).join("");
    el("snapshots").innerHTML = `<table class="data-table"><thead><tr><th>Tag</th><th>Date</th><th>Label</th><th>Restore</th></tr></thead><tbody>${rows}</tbody></table>`;
  }

  function renderWorking(s) {
    const w = s.working;
    if (!w) {
      el("working").innerHTML = `<dl class="lc-kv">
        <dt>Commit</dt><dd><code>${escapeHtml(s.branch || "detached")}</code> @ ${escapeHtml(s.head)}</dd>
        <dt>Policy</dt><dd>mode ${escapeHtml(s.policy.mode)} · guard ${s.policy.strict ? "strict" : "warn"}</dd>
        <dt>Migrations</dt><dd>applied ${s.schema.applied.length} · pending ${s.schema.pending.length}</dd>
      </dl>${empty("Working tree, sessions and the nightly job are not part of this snapshot.")}`;
      return;
    }
    const sess = [];
    w.sessions.ingest.forEach((x) => sess.push(`ingest ${escapeHtml(x.sha1)} (${escapeHtml(x.raw)})`));
    w.sessions.distill.forEach((x) => sess.push(`distill ${escapeHtml(x.think)} (${escapeHtml(x.mode)})`));
    w.sessions.researcher.forEach((x) => sess.push(`researcher ${escapeHtml(x)}`));
    if (w.sessions.ops) sess.push(`ops ${escapeHtml(w.sessions.ops.op)} ${escapeHtml(w.sessions.ops.target)}`);
    el("working").innerHTML = `<dl class="lc-kv">
      <dt>Branch</dt><dd><code>${escapeHtml(s.branch || "detached")}</code> @ ${escapeHtml(s.head)}</dd>
      <dt>Policy</dt><dd>hooks ${s.policy.hooks_installed ? "installed" : "not installed"} · mode ${escapeHtml(s.policy.mode)} · guard ${s.policy.strict ? "strict" : "warn"}</dd>
      <dt>Sessions</dt><dd>${sess.join("<br>") || "none"}</dd>
      <dt>Knowledge</dt><dd>${w.lanes.knowledge} uncommitted${w.knowledge.length ? "<br><small>" + w.knowledge.slice(0, 8).map(escapeHtml).join("<br>") + "</small>" : ""}</dd>
      <dt>Tooling</dt><dd>${w.lanes.tooling} uncommitted — ships through an infra PR</dd>
      <dt>Migrations</dt><dd>applied ${s.schema.applied.length} · pending ${s.schema.pending.length}</dd>
      <dt>Nightly</dt><dd>${escapeHtml(s.nightly.summary || (s.nightly.plist_installed ? "installed (22:00)" : "not installed — pixi run install-sync"))} · backstop only: each kb step pushes right away · log <code>${escapeHtml(s.nightly.log)}</code></dd>
    </dl>`;
  }

  function renderBranches(list) {
    if (!list) {                       // branches are not fixed by a commit: absent from snapshots
      el("section-branches").hidden = true;
      return;
    }
    if (!list.length) {
      el("branches").innerHTML = empty("No infra branches — start one with pixi run ship -- start <feature> --worktree");
      return;
    }
    const rows = list.map((b) =>
      `<tr><td><code>${escapeHtml(b.name)}</code></td><td>${b.ahead} ahead · ${b.behind} behind</td><td>${escapeHtml(b.last)}</td><td>${escapeHtml((b.date || "").slice(0, 10))}</td></tr>`).join("");
    el("branches").innerHTML = `<table class="data-table"><thead><tr><th>Branch</th><th>vs main</th><th>Last commit</th><th>Date</th></tr></thead><tbody>${rows}</tbody></table>`;
  }

  function render() {
    const s = snapshot;
    el("status-line").textContent =
      `${s.version ? "kb-" + s.version : "no version yet"} · ${s.stats.kb_steps} knowledge steps · ${s.stats.pr_merges} PR merges · generated ${s.generated_at}`;
    renderSummary(s);
    renderAlerts(s);
    renderTimeline();
    renderSnapshots(s.snapshots);
    renderWorking(s);
    renderBranches(s.infra_branches);
  }

  async function load() {
    el("status-line").textContent = "Loading…";
    try {
      const res = await fetch("/api/lifecycle", { cache: "no-store" });
      snapshot = await res.json();
      render();
    } catch (e) {
      el("status-line").textContent = `Could not load /api/lifecycle: ${e}`;
    }
  }

  document.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-copy]");
    if (btn) {
      try {
        await navigator.clipboard.writeText(btn.dataset.copy);
        btn.textContent = "Copied";
      } catch (_) {
        btn.textContent = btn.dataset.copy;
      }
      setTimeout(() => { btn.textContent = "Copy"; }, 1500);
      return;
    }
    const tab = e.target.closest("#timeline-filters .filter-tab");
    if (tab) {
      filter = tab.dataset.kind;
      document.querySelectorAll("#timeline-filters .filter-tab").forEach((t) => t.classList.toggle("active", t === tab));
      renderTimeline();
    }
  });
  document.addEventListener("input", (e) => {
    if (e.target.id === "timeline-search") {
      query = e.target.value.toLowerCase().trim();
      if (snapshot) renderTimeline();
    }
  });
  document.addEventListener("DOMContentLoaded", () => {
    el("btn-refresh").addEventListener("click", load);
    load();
  });
})();
