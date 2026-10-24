(function () {
  // "Right now" strip — reuses /api/lifecycle; the rest of the Start page is static.
  function escapeHtml(s) {
    return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  async function load() {
    const el = document.getElementById("now");
    try {
      const s = await (await fetch("/api/lifecycle", { cache: "no-store" })).json();
      const cards = [
        ["Knowledge version", s.version ? `kb-${s.version}` : "none yet"],
        ["Last snapshot", s.snapshots.length ? s.snapshots[0].tag : "none"],
      ];
      const w = s.working;   // absent in the shared (read-only) site: no checkout state there
      if (w) {
        const sessions = w.sessions.ingest.length + w.sessions.distill.length + w.sessions.researcher.length + (w.sessions.ops ? 1 : 0);
        cards.push(["Open sessions", sessions], ["Uncommitted knowledge", w.lanes.knowledge]);
      }
      if (s.infra_branches) cards.push(["Open feature branches", s.infra_branches.length]);
      el.innerHTML = cards.map(([label, value]) =>
        `<div class="summary-card"><div class="label">${escapeHtml(label)}</div><div class="value">${escapeHtml(value)}</div></div>`).join("");
    } catch (e) {
      el.innerHTML = "";
    }
  }

  document.addEventListener("DOMContentLoaded", load);
})();
