(function () {
  const snapEl = document.getElementById("snapshot");
  if (!snapEl) return;
  const snapshot = JSON.parse(snapEl.textContent);

  // ? popovers
  let openPopover = null;
  document.querySelectorAll(".help-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (openPopover && openPopover.btn === btn) {
        closePopover();
        return;
      }
      closePopover();
      const pop = document.createElement("div");
      pop.className = "help-popover";
      pop.textContent = btn.dataset.help;
      btn.setAttribute("aria-expanded", "true");
      btn.closest(".metric-row").appendChild(pop);
      openPopover = { btn, pop };
    });
  });

  function closePopover() {
    if (!openPopover) return;
    openPopover.btn.removeAttribute("aria-expanded");
    openPopover.pop.remove();
    openPopover = null;
  }

  document.addEventListener("click", closePopover);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closePopover();
  });

  const gridColor = getComputedStyle(document.documentElement)
    .getPropertyValue("--border")
    .trim() || "#e4e4e7";
  const textColor = getComputedStyle(document.documentElement)
    .getPropertyValue("--muted")
    .trim() || "#71717a";

  const chartDefaults = {
    responsive: true,
    maintainAspectRatio: true,
    plugins: { legend: { labels: { color: textColor } } },
    scales: {
      x: { ticks: { color: textColor }, grid: { color: gridColor } },
      y: { ticks: { color: textColor }, grid: { color: gridColor } },
    },
  };

  const indegree = snapshot.graphs.in_degree;
  new Chart(document.getElementById("chart-indegree"), {
    type: "bar",
    data: {
      labels: ["0 inbound", "1 inbound", "2+ inbound"],
      datasets: [{
        label: "Pages",
        data: [indegree["0"], indegree["1"], indegree["2+"]],
        backgroundColor: ["#dc2626", "#ca8a04", "#16a34a"],
        borderRadius: 6,
      }],
    },
    options: { ...chartDefaults, plugins: { legend: { display: false } } },
  });

  const phases = snapshot.graphs.lint_phases_ms;
  new Chart(document.getElementById("chart-lint"), {
    type: "bar",
    data: {
      labels: ["SHA1", "Wiki", "Links"],
      datasets: [{
        label: "ms",
        data: [phases.sha1, phases.wiki, phases.links],
        backgroundColor: ["#2563eb", "#7c3aed", "#0891b2"],
        borderRadius: 6,
      }],
    },
    options: {
      indexAxis: "y",
      ...chartDefaults,
      plugins: { legend: { display: false } },
    },
  });

  const coherence = snapshot.graphs.coherence_by_kind;
  new Chart(document.getElementById("chart-coherence"), {
    type: "doughnut",
    data: {
      labels: ["Internal", "External", "Cosmetic"],
      datasets: [{
        data: [coherence.internal, coherence.external, coherence.cosmetic],
        backgroundColor: ["#dc2626", "#ca8a04", "#71717a"],
        borderWidth: 0,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: { legend: { position: "bottom", labels: { color: textColor } } },
    },
  });

  const lintByCat = snapshot.graphs.lint_by_category;
  const categories = ["coherence", "wiki", "raw", "inbox", "corpus", "root", "other"]
    .filter((cat) => lintByCat.errors[cat] > 0 || lintByCat.warnings[cat] > 0);
  new Chart(document.getElementById("chart-lint-issues"), {
    type: "bar",
    data: {
      labels: categories,
      datasets: [
        {
          label: "Errors",
          data: categories.map((cat) => lintByCat.errors[cat]),
          backgroundColor: "#dc2626",
          borderRadius: 4,
        },
        {
          label: "Warnings",
          data: categories.map((cat) => lintByCat.warnings[cat]),
          backgroundColor: "#ca8a04",
          borderRadius: 4,
        },
      ],
    },
    options: { ...chartDefaults },
  });
})();
