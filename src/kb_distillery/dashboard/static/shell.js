(function () {
  const STORAGE_KEY = "dashboard-theme";

  function systemTheme() {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function getTheme() {
    return localStorage.getItem(STORAGE_KEY) || systemTheme();
  }

  function applyTheme(theme, persist) {
    document.documentElement.setAttribute("data-theme", theme);
    if (persist !== false) {
      localStorage.setItem(STORAGE_KEY, theme);
    }
    document.dispatchEvent(new CustomEvent("themechange", { detail: { theme } }));
  }

  applyTheme(getTheme(), false);

  window.DashboardTheme = {
    get: getTheme,
    set: applyTheme,
    toggle() {
      applyTheme(getTheme() === "dark" ? "light" : "dark");
    },
  };

  function wireToggle() {
    const btn = document.getElementById("theme-toggle");
    if (!btn || btn.dataset.wired) return;
    btn.dataset.wired = "1";
    btn.addEventListener("click", () => window.DashboardTheme.toggle());
  }

  // Share deploy status chip: /api/share/status → {chip: {label, cls, title, href} | null}
  function renderChip(chip) {
    const el = document.getElementById("share-chip");
    if (!el) return;
    if (!chip) { el.hidden = true; return; }
    el.hidden = false;
    el.textContent = chip.label;
    el.className = "share-chip " + (chip.cls || "");
    el.title = chip.title || "";
    el.href = chip.href || "/share-log";
    if (/^https?:/.test(el.href)) el.target = "_blank"; else el.removeAttribute("target");
  }

  function pollChip() {
    fetch("/api/share/status", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => renderChip(data && data.chip))
      .catch(() => {});
  }

  function init() {
    wireToggle();
    pollChip();
    setInterval(pollChip, 30000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
