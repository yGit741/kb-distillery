(function () {
  const PRESET_KEY = "thesis-wiki-graph-presets-v2";        // v2: schema 1.0 type names
  const UI_FOLD_KEY = "thesis-wiki-graph-ui-fold";
  const OVERVIEW_SEEDED_KEY = "thesis-wiki-graph-overview-seeded-v2";
  // The default view: the concept layer (minus people), everything else one click away in the legend.
  // Filled in place from /api/schema (backend/src/kb/core/schema.py is the only list of types).
  const OVERVIEW_TYPES = [];
  const OVERVIEW_LABEL_TYPES = [];
  const OVERVIEW_PRESET = {
    name: "Overview",
    search: "",
    nodeFilters: [],
    visibleTypes: OVERVIEW_TYPES,
    labelMode: "hover",
    labelField: "title",
    labelTruncate: true,
    labelSizeThreshold: true,
    labelMinSize: 5.5,
    labelFilters: [],
    labelTypes: OVERVIEW_LABEL_TYPES,
    colorBy: "type",
    sizeBy: "connections",
    nodeSize: 5,
    linkOpacity: 0.35,
    showArrows: false,
    highlightPath: true,
    forceCharge: -120,
    forceLink: 70,
    forceCenter: 0.3,
  };
  const DEFAULT_PRESETS = [
    OVERVIEW_PRESET,
    {
      name: "All wiki",
      search: "",
      nodeFilters: [],
      labelMode: "hover",
      labelField: "title",
      labelTruncate: true,
      labelSizeThreshold: true,
      labelMinSize: 5.5,
      labelFilters: [],
      colorBy: "type",
      sizeBy: "connections",
      nodeSize: 5,
      linkOpacity: 0.35,
      showArrows: false,
      highlightPath: true,
      forceCharge: -120,
      forceLink: 70,
      forceCenter: 0.3,
    },
    {
      name: "Papers only",
      search: "",
      nodeFilters: [{ mode: "include", field: "type", op: "is", value: "paper" }],
      labelMode: "visible",
      labelField: "short",
      labelTruncate: true,
      labelSizeThreshold: true,
      labelMinSize: 5.5,
      labelFilters: [],
      colorBy: "area",
      sizeBy: "connections",
      nodeSize: 5.5,
      linkOpacity: 0.4,
      showArrows: true,
      highlightPath: true,
      forceCharge: -100,
      forceLink: 80,
      forceCenter: 0.25,
    },
    {
      name: "Info theory cluster",
      search: "",
      nodeFilters: [{ mode: "include", field: "area", op: "contains", value: "info-theory" }],
      labelMode: "visible",
      labelField: "title",
      labelTruncate: true,
      labelSizeThreshold: true,
      labelMinSize: 5.5,
      labelFilters: [],
      colorBy: "type",
      sizeBy: "connections",
      nodeSize: 6,
      linkOpacity: 0.45,
      showArrows: false,
      highlightPath: true,
      forceCharge: -90,
      forceLink: 65,
      forceCenter: 0.35,
    },
  ];

  // Type tables come from /api/schema (applySchema); only the fallback for unknown types lives here.
  const TYPE_COLORS = { unknown: "#6c7086" };
  const TYPE_DISPLAY = { unknown: "Unknown" };
  const TYPE_LAYER = {};
  const TYPE_CHIP_ORDER = [];
  const LAYERS = [];

  function applySchema(schema) {
    if (!schema || !Array.isArray(schema.types)) return;
    TYPE_CHIP_ORDER.length = 0;
    schema.types.forEach((t) => {
      TYPE_COLORS[t.id] = t.color;
      TYPE_DISPLAY[t.id] = t.label;
      TYPE_LAYER[t.id] = t.layer;
      TYPE_CHIP_ORDER.push(t.id);
    });
    TYPE_CHIP_ORDER.push("unknown");
    LAYERS.length = 0;
    (schema.layers || []).forEach((l) => LAYERS.push(l));
    OVERVIEW_TYPES.length = 0;
    (schema.default_visible || []).forEach((t) => OVERVIEW_TYPES.push(t));
    OVERVIEW_LABEL_TYPES.length = 0;
    (schema.default_visible || []).slice(0, 1).forEach((t) => OVERVIEW_LABEL_TYPES.push(t));
  }

  async function loadSchema() {
    try {
      const res = await fetch("/api/schema");
      if (res.ok) applySchema(await res.json());
    } catch { /* the graph payload carries the schema too */ }
  }

  const STATUS_COLORS = {
    digested: "#9ece6a",
    reading: "#7aa2ff",
    "to-read": "#6c7086",
    open: "#f6c177",
    partial: "#e0af68",
    resolved: "#73daca",
    seed: "#565f89",
    growing: "#7aa2ff",
    solid: "#9ece6a",
    review: "#e0af68",
    applied: "#73daca",
    archived: "#565f89",
  };

  const AREA_COLORS = [
    "#7aa2ff", "#ff6b7a", "#9ece6a", "#f6c177", "#bb9af7",
    "#73daca", "#e0af68", "#ff9e64", "#89ddff", "#c792ea",
  ];

  const FILTER_FIELDS = [
    { id: "type", label: "Type", ops: ["is", "is-not"] },
    { id: "status", label: "Status", ops: ["is", "is-not"] },
    { id: "area", label: "Area", ops: ["contains", "not-contains"] },
    { id: "year", label: "Year", ops: ["is", "gte", "lte"] },
    { id: "slug", label: "Slug", ops: ["contains", "not-contains"] },
    { id: "title", label: "Title", ops: ["contains", "not-contains"] },
    { id: "inDegree", label: "In-links", ops: ["gte", "lte"] },
    { id: "outDegree", label: "Out-links", ops: ["gte", "lte"] },
  ];

  let snapshot = null;
  let graph = null;
  let hoveredNode = null;
  // calm hover state (see requestHover)
  const hoverTuning = { DWELL: 150, SWITCH_DWELL: 80, GRACE: 200, SPEED: 7, FADE_IN: 180, FADE_OUT: 100, HOVER_DIM: 0.35 };
  const calmOn = () => !!el("calm-hover")?.checked;
  let pointedNode = null, intentTimer = 0;
  let prevLabels = new Set();                        // labels drawn before the focus changed: new ones fade in
  const lastMove = { x: 0, y: 0, t: 0, speed: 0 };   // pointer speed in px per 100 ms
  document.addEventListener("pointermove", (e) => notePointer(e), { passive: true });
  let selectedNodeIds = new Set();
  let selectedNodes = new Set();
  let visibleNodeIds = new Set();
  let labeledNodeIds = new Set();
  let activeLabelTypes = new Set();
  let shownTypes = null; // null = every type; otherwise the set of node types drawn at all
  let neighborMap = new Map();
  let pollTimer = null;
  let viewState = null;
  let initialView = null;
  let nodeClickHandled = false;
  let suppressGraphPick = false;
  let needsInitialFit = true;
  let onFirstFit = null;

  const el = (id) => document.getElementById(id);

  // ---- data layer (raw sources bundled into one pile per format; off by default) ----
  const DATA_LAYER_KEY = "thesis-wiki-graph-data-layer";
  const PILE_PAGE_LINK_CAP = 150;      // strongest page links drawn per pile
  const PILE_COLORS = {
    "printed-docs": "#ff6b7a", handwritten: "#c099ff", presentations: "#ffc777", "llm-chats": "#ff9e64",
    emails: "#73daca", "web-clips": "#4fd6be", images: "#7dcfff",
  };
  function dataLayerOn() {
    const box = el("data-layer");
    return !!box && box.checked && !window.KB_STATIC;
  }

  function cssVar(name, fallback = "") {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
  }

  function navHeight() {
    return parseInt(cssVar("--nav-height", "48"), 10) || 48;
  }

  function graphWidth() {
    return window.innerWidth;
  }

  function graphHeight() {
    return Math.max(window.innerHeight - navHeight(), 200);
  }

  function toast(msg) {
    const t = el("toast");
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => { t.hidden = true; }, 2200);
  }

  function loadPresets() {
    try {
      const raw = localStorage.getItem(PRESET_KEY);
      if (!raw) return [...DEFAULT_PRESETS];
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed) || !parsed.length) return [...DEFAULT_PRESETS];
      if (!localStorage.getItem(OVERVIEW_SEEDED_KEY)) {
        localStorage.setItem(OVERVIEW_SEEDED_KEY, "1");
        if (!parsed.some((p) => p.name === OVERVIEW_PRESET.name)) {
          parsed.unshift(OVERVIEW_PRESET);
          localStorage.setItem(PRESET_KEY, JSON.stringify(parsed));
        }
      }
      return parsed.map((p) => {
        const clean = { ...p };
        delete clean.camera;
        if (clean.view && !isValidView(clean.view)) delete clean.view;
        return clean;
      });
    } catch {
      return [...DEFAULT_PRESETS];
    }
  }

  function savePresets(list) {
    localStorage.setItem(PRESET_KEY, JSON.stringify(list));
    refreshPresetSelect();
  }

  function refreshPresetSelect() {
    const select = el("preset-select");
    const presets = loadPresets();
    select.innerHTML = presets.map((p, i) =>
      `<option value="${i}">${escapeHtml(p.name)}</option>`
    ).join("");
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function shortSlug(slug) {
    const parts = slug.split("-");
    if (parts.length <= 4) return slug;
    return parts.slice(0, 3).join("-") + "…";
  }

  function nodeLabel(node, { full = false } = {}) {
    if (full) return node.title || node.id;
    const field = el("label-field").value;
    const truncate = el("label-truncate").checked;
    let text = node.slug || node.id;
    if (field === "title") text = node.title || node.id;
    else if (field === "short") text = shortSlug(node.id);
    else text = node.id;
    if (truncate && text.length > 42) text = text.slice(0, 40) + "…";
    return text;
  }

  function labelTextForNode(node) {
    if (hoveredNode && node.id === hoveredNode.id) return nodeLabel(node, { full: true });
    return nodeLabel(node);
  }

  function isSelected(node) {
    return selectedNodeIds.has(node.id);
  }

  function reconcileSelectedNodes() {
    selectedNodes.clear();
    for (const id of selectedNodeIds) {
      const node = nodeById(id);
      if (node) selectedNodes.add(node);
    }
  }

  function clearSelection() {
    selectedNodeIds.clear();
    selectedNodes.clear();
    updateSelectionUi();
    document.dispatchEvent(new CustomEvent("graph:selection", { detail: { nodes: [] } }));
    hideInspector();
    computeVisibility();
    refreshVisuals();
  }

  function closeInspector() {
    suppressGraphPick = true;
    setTimeout(() => { suppressGraphPick = false; }, 50);
    clearSelection();
  }

  function ensureNeighborMap() {
    if (!snapshot) return;
    neighborMap = buildNeighborMap(snapshot.links.map((l) => ({
      source: l.source,
      target: l.target,
    })));
  }

  function setSelection(nodes, { additive = false } = {}) {
    if (!additive) selectedNodeIds.clear();
    for (const n of nodes) selectedNodeIds.add(n.id);
    reconcileSelectedNodes();
    updateSelectionUi();
    updateInspector();
    ensureNeighborMap();
    computeVisibility();
    refreshVisuals();
  }

  function toggleSelection(node) {
    if (selectedNodeIds.has(node.id)) selectedNodeIds.delete(node.id);
    else selectedNodeIds.add(node.id);
    reconcileSelectedNodes();
    updateSelectionUi();
    updateInspector();
    ensureNeighborMap();
    computeVisibility();
    refreshVisuals();
  }

  function updateSelectionUi() {
    const pill = el("selection-pill");
    const count = selectedNodeIds.size;
    if (count > 0) {
      pill.textContent = `${count} selected`;
      pill.classList.remove("hidden");
    } else {
      pill.classList.add("hidden");
    }
  }

  function readView() {
    if (!graph) return null;
    const c = graph.centerAt();
    return {
      centerX: c?.x ?? 0,
      centerY: c?.y ?? 0,
      k: graph.zoom(),
    };
  }

  function applyView(view) {
    if (!graph || !view) return;
    graph.centerAt(view.centerX, view.centerY, 0);
    graph.zoom(view.k, 0);
    viewState = { ...view };
    updateZoomUi();
  }

  function isValidView(view) {
    return view && Number.isFinite(view.centerX) && Number.isFinite(view.centerY) && Number.isFinite(view.k);
  }

  function updateZoomUi() {
    if (!graph) return;
    const k = viewState?.k ?? graph.zoom();
    el("zoom-level").textContent = `${Math.round(k * 100)}%`;
  }

  // One mouse scheme, no modes: left-drag pans (or moves the node under the pointer), the wheel /
  // two-finger scroll pans, pinch or Cmd/Ctrl+wheel zooms at the pointer. Right-drag box-selects,
  // Cmd+right-drag lassos and a right-click on a node opens its menu (graph-mouse.js).
  function applyInteractionSettings() {
    if (!graph) return;
    graph.enableNodeDrag(true).enablePanInteraction(true).enableZoomInteraction(false);
  }

  function rootOffset() {
    const r = el("graph-root").getBoundingClientRect();
    return { x: r.left, y: r.top };
  }

  function zoomAt(factor, clientX, clientY) {
    const view = readView();
    if (!view) return;
    const k = Math.min(Math.max(view.k * factor, 0.04), 24);
    const o = rootOffset();
    const p = graph.screen2GraphCoords(clientX - o.x, clientY - o.y);
    const f = k / view.k;
    graph.zoom(k, 0);
    graph.centerAt(p.x - (p.x - view.centerX) / f, p.y - (p.y - view.centerY) / f, 0);
    viewState = readView();
    updateZoomUi();
  }

  function panBy(dx, dy) {
    const view = readView();
    if (!view) return;
    graph.centerAt(view.centerX + dx / view.k, view.centerY + dy / view.k, 0);
    viewState = readView();
    updateZoomUi();
  }

  function setupWheel() {
    const root = el("graph-root");
    root.addEventListener("wheel", (ev) => {
      if (!graph) return;
      ev.preventDefault();
      const unit = ev.deltaMode === 1 ? 16 : ev.deltaMode === 2 ? root.clientHeight : 1;
      const dx = ev.deltaX * unit, dy = ev.deltaY * unit;
      if (ev.ctrlKey || ev.metaKey) {
        // a pinch arrives as ctrl+wheel with small deltas, a Cmd+mouse wheel as ±100 steps
        const step = Math.max(-60, Math.min(60, dy));
        zoomAt(Math.exp(-step * (ev.ctrlKey ? 0.012 : 0.004)), ev.clientX, ev.clientY);
      } else if (ev.shiftKey && !dx) {
        panBy(dy, 0);                                   // shift+wheel on a mouse scrolls sideways
      } else {
        panBy(dx, dy);
      }
    }, { passive: false });
    // d3-zoom zooms in on a double-click; here a double-click opens the side reader instead
    root.addEventListener("dblclick", (ev) => ev.stopPropagation(), true);
  }

  function setupKeyboard() {
    window.addEventListener("keydown", (ev) => {
      if (ev.target.matches("input, textarea, select")) return;

      if (ev.key === "Escape") {
        clearSelection();
      }
      if (ev.key === "f" || ev.key === "F") {
        fitToView();
        ev.preventDefault();
      }
      if (ev.key === "+" || ev.key === "=") {
        zoomBy(1.25);
        ev.preventDefault();
      }
      if (ev.key === "-") {
        zoomBy(1 / 1.25);
        ev.preventDefault();
      }
      if ((ev.key === "e" || ev.key === "E") && selectedNodes.size === 1) {
        location.href = exploreUrl([...selectedNodes][0].id);
      }
    });
  }

  function zoomBy(factor) {
    if (!graph) return;
    const view = readView() || { centerX: 0, centerY: 0, k: 1 };
    graph.zoom(view.k * factor, 200);
    setTimeout(() => { viewState = readView(); updateZoomUi(); }, 220);
  }

  function largestComponent() {
    ensureNeighborMap();
    const seen = new Set();
    let best = new Set();
    for (const start of visibleNodeIds) {
      if (seen.has(start)) continue;
      const comp = new Set([start]);
      const stack = [start];
      seen.add(start);
      while (stack.length) {
        for (const nb of neighborMap.get(stack.pop()) || []) {
          if (seen.has(nb) || !visibleNodeIds.has(nb)) continue;
          seen.add(nb);
          comp.add(nb);
          stack.push(nb);
        }
      }
      if (comp.size > best.size) best = comp;
    }
    return best;
  }

  function fitToView() {
    if (!graph) return;
    // Frame the largest connected component: unlinked pages and tiny islands drift far out
    // and would otherwise shrink everything to a speck.
    const core = largestComponent();
    graph.zoomToFit(400, 90, core.size > 1 ? (n) => n.pile || core.has(n.id) : (n) => n.pile || visibleNodeIds.has(n.id));
    setTimeout(() => {
      viewState = readView();
      if (!initialView) initialView = viewState ? { ...viewState } : null;
      updateZoomUi();
      updateStatusLine();
    }, 420);
  }

  function resetView() {
    if (!graph) return;
    if (initialView && isValidView(initialView)) {
      applyView(initialView);
    } else {
      fitToView();
    }
  }

  function snapshotPositions() {
    if (!graph) return new Map();
    const map = new Map();
    for (const n of graph.graphData().nodes) {
      map.set(n.id, { x: n.x, y: n.y, fx: n.fx, fy: n.fy });
    }
    return map;
  }

  function mergePositions(nodes, posMap) {
    return nodes.map((n) => {
      const p = posMap.get(n.id);
      if (!p || p.x == null || p.y == null) return n;
      const merged = { ...n, x: p.x, y: p.y };
      if (p.fx != null) merged.fx = p.fx;
      if (p.fy != null) merged.fy = p.fy;
      return merged;
    });
  }

  function getNodeFilters(containerId) {
    return [...document.querySelectorAll(`#${containerId} .filter-row`)].map((row) => ({
      mode: row.querySelector(".filter-mode").value,
      field: row.querySelector(".filter-field").value,
      op: row.querySelector(".filter-op").value,
      value: row.querySelector(".filter-value").value.trim(),
    }));
  }

  function setNodeFilters(containerId, filters, btnId) {
    const container = el(containerId);
    container.innerHTML = "";
    (filters || []).forEach((f) => addFilterRow(containerId, btnId, f));
    toggleLabelFilterUi();
  }

  function fieldMeta(fieldId) {
    return FILTER_FIELDS.find((f) => f.id === fieldId) || FILTER_FIELDS[0];
  }

  function addFilterRow(containerId, btnId, initial = {}) {
    const container = el(containerId);
    const row = document.createElement("div");
    row.className = "filter-row";
    const field = initial.field || "type";
    row.innerHTML = `
      <select class="filter-mode" aria-label="Include or exclude">
        <option value="include">Include</option>
        <option value="exclude">Exclude</option>
      </select>
      <select class="filter-field" aria-label="Field"></select>
      <select class="filter-op" aria-label="Operator"></select>
      <input class="filter-value text-input" type="text" placeholder="value" aria-label="Value">
      <button type="button" title="Remove filter">×</button>
    `;
    const fieldSel = row.querySelector(".filter-field");
    FILTER_FIELDS.forEach((f) => {
      const opt = document.createElement("option");
      opt.value = f.id;
      opt.textContent = f.label;
      fieldSel.appendChild(opt);
    });
    fieldSel.value = field;
    const modeSel = row.querySelector(".filter-mode");
    modeSel.value = initial.mode || "include";
    const opSel = row.querySelector(".filter-op");
    const valueInput = row.querySelector(".filter-value");

    function refreshOps() {
      const m = fieldMeta(fieldSel.value);
      opSel.innerHTML = m.ops.map((op) => `<option value="${op}">${op}</option>`).join("");
      opSel.value = initial.op && m.ops.includes(initial.op) ? initial.op : m.ops[0];
    }
    refreshOps();
    valueInput.value = initial.value || "";

    fieldSel.addEventListener("change", () => {
      refreshOps();
      applyFilters();
    });
    modeSel.addEventListener("change", applyFilters);
    opSel.addEventListener("change", applyFilters);
    valueInput.addEventListener("input", debounce(applyFilters, 180));

    row.querySelector("button").addEventListener("click", () => {
      row.remove();
      applyFilters();
    });

    container.appendChild(row);
    if (btnId) el(btnId).classList.remove("hidden");
  }

  function debounce(fn, ms) {
    let t;
    return (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...args), ms);
    };
  }

  function matchRule(node, rule) {
    const { field, op, value } = rule;
    if (!value && !["inDegree", "outDegree", "year"].includes(field)) return true;

    let actual;
    if (field === "area") actual = (node.areas || []).join(" ");
    else if (field === "slug") actual = node.id;
    else if (field === "title") actual = node.title || "";
    else if (field === "year") actual = node.year;
    else actual = node[field];

    const val = value.toLowerCase();
    let ok = false;
    switch (op) {
      case "is":
        ok = String(actual ?? "").toLowerCase() === val;
        break;
      case "is-not":
        ok = String(actual ?? "").toLowerCase() !== val;
        break;
      case "contains":
        ok = String(actual ?? "").toLowerCase().includes(val);
        break;
      case "not-contains":
        ok = !String(actual ?? "").toLowerCase().includes(val);
        break;
      case "gte":
        ok = Number(actual ?? 0) >= Number(value);
        break;
      case "lte":
        ok = Number(actual ?? 0) <= Number(value);
        break;
      default:
        ok = true;
    }
    return rule.mode === "exclude" ? !ok : ok;
  }

  let revealedIds = new Set();        // sources revealed by "See sources (N)", shown whatever the type filter says
  let externalFilter = null;           // set by selection.js (scope projection): Set of ids, or null
  let externalForce = false;           // true: ids in externalFilter bypass the other filters (search / picked view)
  function passesFilters(node, filters, search) {
    if (externalFilter && !externalFilter.has(node.id)) return false;
    const q = (search || "").trim().toLowerCase();
    if (q) {
      const hay = `${node.id} ${node.title || ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    if (!filters.length) return true;
    return filters.every((rule) => matchRule(node, rule));
  }

  function addSelectionNeighborLabels() {
    if (!selectedNodeIds.size) return;
    if (el("label-mode").value === "none") return;
    for (const id of selectedNodeIds) {
      labeledNodeIds.add(id);
      (neighborMap.get(id) || []).forEach((nid) => labeledNodeIds.add(nid));
    }
  }

  function applyActiveLabelTypes() {
    if (!activeLabelTypes.size) return;

    const labelMode = el("label-mode").value;
    const hasContext =
      selectedNodeIds.size > 0 ||
      (labelMode === "hover" && hoveredNode) ||
      labelMode === "visible" ||
      labelMode === "custom";

    if (hasContext && labeledNodeIds.size > 0) {
      labeledNodeIds = new Set([...labeledNodeIds].filter((id) => {
        const node = nodeById(id);
        return node && activeLabelTypes.has(node.type);
      }));
      return;
    }

    labeledNodeIds = new Set();
    for (const node of snapshot.nodes) {
      if (!visibleNodeIds.has(node.id)) continue;
      if (activeLabelTypes.has(node.type)) labeledNodeIds.add(node.id);
    }
  }

  function computeVisibility() {
    if (!snapshot) return;
    const search = el("search-nodes").value;
    const nodeFilters = getNodeFilters("node-filters");
    const labelMode = el("label-mode").value;
    const labelFilters = getNodeFilters("label-filters");

    visibleNodeIds = new Set();
    labeledNodeIds = new Set();

    for (const node of snapshot.nodes) {
      if (!isTypeShown(node.type)) continue;
      if (passesFilters(node, nodeFilters, search)) visibleNodeIds.add(node.id);
    }

    revealedIds.forEach((id) => { if (snapshot.nodes.some((n) => n.id === id)) visibleNodeIds.add(id); });
    if (externalForce && externalFilter) externalFilter.forEach((id) => visibleNodeIds.add(id));   // a picked/search view shows its pages whatever else hides them
    if (labelMode === "visible") {
      visibleNodeIds.forEach((id) => labeledNodeIds.add(id));
    } else if (labelMode === "hover" && hoveredNode) {
      labeledNodeIds.add(hoveredNode.id);
      (neighborMap.get(hoveredNode.id) || []).forEach((id) => labeledNodeIds.add(id));
    } else if (labelMode === "custom") {
      for (const node of snapshot.nodes) {
        if (!visibleNodeIds.has(node.id)) continue;
        if (passesFilters(node, labelFilters, "")) labeledNodeIds.add(node.id);
      }
    }

    addSelectionNeighborLabels();

    applyActiveLabelTypes();

    applyLabelSizeThreshold();

    // Past label types, the size cut and the label mode: a selection always labels itself and its
    // neighbours, and the hovered node always shows its own label.
    for (const id of selectedNodeIds) {
      labeledNodeIds.add(id);
      (neighborMap.get(id) || []).forEach((nid) => labeledNodeIds.add(nid));
    }
    if (hoveredNode) labeledNodeIds.add(hoveredNode.id);

    computeFocus();
    el("node-count-pill").textContent = `${visibleNodeIds.size} / ${snapshot.nodes.length}`;
    el("label-count-pill").textContent = String(labeledNodeIds.size);
  }

  function nodeById(id) {
    if (graph) {
      const live = graph.graphData().nodes.find((n) => n.id === id);
      if (live) return live;
    }
    return snapshot?.nodes.find((n) => n.id === id);
  }

  function applyLabelSizeThreshold() {
    if (!el("label-size-threshold")?.checked) return;
    if (el("label-mode").value === "none" && !selectedNodeIds.size) return;
    const minR = Number(el("label-min-size").value);
    const exemptIds = new Set();

    if (selectedNodeIds.size > 0) {
      for (const id of selectedNodeIds) {
        exemptIds.add(id);
        (neighborMap.get(id) || []).forEach((nid) => exemptIds.add(nid));
      }
    } else if (el("label-mode").value === "hover" && hoveredNode) {
      exemptIds.add(hoveredNode.id);
      (neighborMap.get(hoveredNode.id) || []).forEach((id) => exemptIds.add(id));
    }

    if (activeLabelTypes.size > 0) {
      for (const id of labeledNodeIds) {
        const node = nodeById(id);
        if (node && activeLabelTypes.has(node.type)) exemptIds.add(id);
      }
    }

    labeledNodeIds = new Set([...labeledNodeIds].filter((id) => {
      if (exemptIds.has(id)) return true;
      const n = nodeById(id);
      return n && nodeVisualRadius(n) >= minR;
    }));
  }

  function obsidianUri(path) {
    return `obsidian://open?file=${encodeURIComponent(path)}`;
  }

  function renderPropertyValue(key, value) {
    const s = String(value);
    if (key === "url" || key === "scholar" || key === "tau_profile" || /^https?:\/\//i.test(s)) {
      return `<a href="${escapeHtml(s)}" target="_blank" rel="noopener noreferrer">${escapeHtml(s)}</a>`;
    }
    if (key === "slug") {
      return `<a href="${obsidianUri(`wiki/${s}.md`)}" target="_blank" rel="noopener noreferrer">${escapeHtml(s)}</a>`;
    }
    return escapeHtml(s);
  }

  function renderProperties(props) {
    if (!props || !Object.keys(props).length) return "<p class='subtle'>No properties</p>";
    return Object.entries(props)
      .map(([k, v]) => `<dt>${escapeHtml(k)}</dt><dd>${renderPropertyValue(k, v)}</dd>`)
      .join("");
  }

  function colorForNode(node) {
    const by = el("color-by").value;
    if (by === "none") return "#7aa2ff";
    if (by === "type") return TYPE_COLORS[node.type] || TYPE_COLORS.unknown;
    if (by === "status") return STATUS_COLORS[node.status] || "#6c7086";
    if (by === "area") {
      const area = (node.areas && node.areas[0]) || "none";
      let h = 0;
      for (let i = 0; i < area.length; i++) h = (h * 31 + area.charCodeAt(i)) >>> 0;
      return AREA_COLORS[h % AREA_COLORS.length];
    }
    if (by === "degree") {
      const d = (node.inDegree || 0) + (node.outDegree || 0);
      if (d >= 12) return "#ff6b7a";
      if (d >= 6) return "#f6c177";
      if (d >= 2) return "#7aa2ff";
      return "#565f89";
    }
    return "#7aa2ff";
  }

  function buildNeighborMap(links) {
    const map = new Map();
    function add(a, b) {
      if (!map.has(a)) map.set(a, new Set());
      map.get(a).add(b);
    }
    for (const l of links) {
      add(l.source.id || l.source, l.target.id || l.target);
      add(l.target.id || l.target, l.source.id || l.source);
    }
    const out = new Map();
    map.forEach((set, key) => out.set(key, [...set]));
    return out;
  }

  function buildGraphData() {
    const nodes = snapshot.nodes
      .filter((n) => visibleNodeIds.has(n.id))
      .map((n) => ({
        ...n,
        slug: n.id,
        color: colorForNode(n),
      }));
    const nodeSet = new Set(nodes.map((n) => n.id));
    const links = snapshot.links
      .filter((l) => nodeSet.has(l.source) && nodeSet.has(l.target))
      .map((l) => ({ ...l }));
    if (dataLayerOn() && snapshot.piles) addPiles(nodes, links, nodeSet);
    if (!sourcesShown()) addSharedSourceLinks(links, nodeSet);
    return { nodes, links };
  }

  // ---- the source layer behind the concepts ----
  function layerOf(node) {
    return (node && (node.layer || TYPE_LAYER[node.type])) || "";
  }

  // True when any source type is drawn (a type chip on, or sources revealed for a node).
  function sourcesShown() {
    if (revealedIds.size) return true;
    return TYPE_CHIP_ORDER.some((t) => TYPE_LAYER[t] === "source" && isTypeShown(t));
  }

  // Concepts that share sources get a thin dashed edge labelled with the count, so hiding the source
  // layer keeps the structure it carried (graph_data.concept_links).
  function addSharedSourceLinks(links, nodeSet) {
    const linked = new Set(links.map((l) => `${l.source}|${l.target}`));
    for (const c of snapshot.concept_links || []) {
      if (!nodeSet.has(c.source) || !nodeSet.has(c.target)) continue;
      if (linked.has(`${c.source}|${c.target}`) || linked.has(`${c.target}|${c.source}`)) continue;
      links.push({ source: c.source, target: c.target, kind: "shared", shared: c.shared });
    }
  }

  // The source pages behind a node: its source-layer neighbours (for a collection, its members).
  function sourcesOf(id) {
    ensureNeighborMap();
    return (neighborMap.get(id) || []).filter((nid) => {
      const n = snapshot.nodes.find((m) => m.id === nid);
      return n && layerOf(n) === "source";
    });
  }

  function seeSources(id, on = true) {
    const ids = sourcesOf(id);
    if (on) ids.forEach((s) => revealedIds.add(s));
    else ids.forEach((s) => revealedIds.delete(s));
    applyFilters();
    return ids.length;
  }

  function sourcesRevealed(id) {
    const ids = sourcesOf(id);
    return ids.length > 0 && ids.every((s) => revealedIds.has(s));
  }

  function addPiles(nodes, links, nodeSet) {
    const piles = snapshot.piles.filter((p) => p.format !== "inbox" && p.count > 0);
    const have = new Set();
    for (const p of piles) {
      const nonSkip = p.count - p.skip - p.companions;
      nodes.push({
        id: `pile:${p.format}`, pile: true, type: "pile", format: p.format, title: p.format, label: p.format,
        count: p.count, source: p.source, partial: p.partial, queued: p.queued, skip: p.skip,
        companions: p.companions, share: nonSkip > 0 ? (p.source + p.partial) / nonSkip : 0,
        color: PILE_COLORS[p.format] || "#9aa5b1", inDegree: 0, outDegree: 0,
      });
      have.add(p.format);
      Object.entries(p.links_to_pages).filter(([slug]) => nodeSet.has(slug)).slice(0, PILE_PAGE_LINK_CAP)
        .forEach(([slug, n]) => links.push({ source: `pile:${p.format}`, target: slug, kind: "pile-page", count: n }));
    }
    for (const l of snapshot.pile_links || []) {
      if (have.has(l.source) && have.has(l.target) && l.kind !== "page") {
        links.push({ source: `pile:${l.source}`, target: `pile:${l.target}`, kind: "pile-pile", count: l.count, via: l.kind });
      }
    }
  }

  function pileRadius(node) {
    return 7 + Math.sqrt(node.count) * 0.9;
  }

  function drawPile(node, ctx, globalScale) {
    const r = pileRadius(node);
    const gs = globalScale;
    ctx.globalAlpha = 1;
    for (let i = 2; i >= 0; i--) {        // a stack of discs
      ctx.beginPath();
      ctx.arc(node.x + i * r * 0.1, node.y - i * r * 0.1, r, 0, 2 * Math.PI);
      ctx.fillStyle = node.color;
      ctx.globalAlpha = 0.35 + (2 - i) * 0.3;
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    ctx.lineWidth = 3 / gs;                // ring: digested share
    ctx.beginPath();
    ctx.arc(node.x, node.y, r + 3 / gs, 0, 2 * Math.PI);
    ctx.strokeStyle = "rgba(128,128,128,0.35)";
    ctx.stroke();
    if (node.share > 0) {
      ctx.beginPath();
      ctx.arc(node.x, node.y, r + 3 / gs, -Math.PI / 2, -Math.PI / 2 + 2 * Math.PI * node.share);
      ctx.strokeStyle = "#9ece6a";
      ctx.stroke();
    }
    const fontSize = Math.max(11 / gs, 3);
    ctx.font = `600 ${fontSize}px ${getComputedStyle(document.body).fontFamily}`;
    const text = `${node.format} · ${node.count}`;
    const w = ctx.measureText(text).width;
    ctx.fillStyle = cssVar("--graph-label-bg", "rgba(12, 13, 16, 0.72)");
    ctx.fillRect(node.x - w / 2 - 2 / gs, node.y + r + 6 / gs, w + 4 / gs, fontSize + 3 / gs);
    ctx.fillStyle = cssVar("--graph-label-text", "rgba(236, 239, 244, 0.92)");
    ctx.fillText(text, node.x - w / 2, node.y + r + 6 / gs + fontSize);
  }

  function linkWidthFn(link) {
    if (link.kind === "shared") return 0.35 + Math.min(link.shared || 1, 6) * 0.1;
    if (link.kind === "pile-page") return 0.4;
    if (link.kind === "pile-pile") return 1 + Math.log2(1 + link.count) * 0.4;
    return 0.8;
  }

  function linkLabelFn(link) {
    if (link.kind === "shared") return `${link.shared} shared source${link.shared === 1 ? "" : "s"}`;
    if (link.kind === "pile-pile") return `${link.source.format || link.source} ↔ ${link.target.format || link.target}: ${link.count} (${link.via})`;
    if (link.kind === "pile-page") return `${link.count} source file${link.count === 1 ? "" : "s"}`;
    return "";
  }

  // raw rows feeding one page (empty unless the data layer is loaded)
  function rawSources(slug) {
    if (!snapshot || !snapshot.raw_links || !dataLayerOn()) return [];
    if (!snapshot._rawById) snapshot._rawById = new Map(snapshot.raw_nodes.map((n) => [n.id, n]));
    return snapshot.raw_links.filter((l) => l.target === slug && l.kind === "source")
      .map((l) => snapshot._rawById.get(l.source)).filter(Boolean);
  }

  function applyForces() {
    if (!graph) return;
    graph.d3Force("charge").strength(Number(el("force-charge").value));
    graph.d3Force("link").distance(Number(el("force-link").value));
    graph.d3Force("center").strength(Number(el("force-center").value));
    graph.d3ReheatSimulation();
  }

  function drawSharedCount(link, ctx, globalScale) {
    if (link.kind !== "shared" || globalScale < 1.6) return;
    const a = link.source, b = link.target;
    if (!a || !b || a.x == null || b.x == null) return;
    ctx.save();
    ctx.font = `${Math.max(2.5, 9 / globalScale)}px sans-serif`;
    ctx.fillStyle = cssVar("--muted", "#8a93a6");
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(String(link.shared), (a.x + b.x) / 2, (a.y + b.y) / 2);
    ctx.restore();
  }

  function refreshVisuals() {
    if (!graph) return;
    graph.nodeCanvasObject(drawNode);
    graph.linkColor(linkColorFn);
    if (typeof graph.refresh === "function") graph.refresh();
    else if (typeof graph.redraw === "function") graph.redraw();
  }

  function applyFilters() {
    if (!snapshot || !graph) return;
    neighborMap = buildNeighborMap(snapshot.links.map((l) => ({
      source: l.source,
      target: l.target,
    })));
    computeVisibility();

    const savedView = readView();
    const posMap = snapshotPositions();
    const data = buildGraphData();
    data.nodes = mergePositions(data.nodes, posMap);

    graph.graphData(data);
    reconcileSelectedNodes();
    computeVisibility();
    if (savedView) applyView(savedView);

    graph.linkDirectionalArrowLength(el("show-arrows").checked ? 4 : 0);
    graph.linkDirectionalArrowRelPos(0.85);
    refreshVisuals();
    updateZoomUi();
    document.dispatchEvent(new CustomEvent("graph:changed"));
  }

  function nodeRadius() {
    return Number(el("node-size").value);
  }

  function sizeMetric(node) {
    const by = el("size-by").value;
    if (by === "in-degree") return node.inDegree || 0;
    if (by === "out-degree") return node.outDegree || 0;
    if (by === "connections") return (node.inDegree || 0) + (node.outDegree || 0);
    return 0;
  }

  function sizeScale(node) {
    const hub = node.type === "book" ? 1.7 : 1;      // a book is a hub over its parts
    if (el("size-by").value === "uniform") return hub;
    const d = sizeMetric(node);
    return (0.55 + Math.min(d, 24) * 0.04) * hub;
  }

  function nodeBaseRadius(node) {
    if (node.pile) return pileRadius(node);
    return nodeRadius() * sizeScale(node);
  }

  function nodeDrawRadius(node) {
    return nodeBaseRadius(node);
  }

  function nodeVisualRadius(node) {
    return nodeBaseRadius(node);
  }

  function applyNodeSizing() {
    if (!graph) return;
    graph.nodeVal((n) => nodeBaseRadius(n) ** 2);
    graph.nodeRelSize(nodeRadius());
    refreshVisuals();
    graph.d3ReheatSimulation();
  }

  function paintPointerArea(node, color, ctx) {
    const r = nodeDrawRadius(node);
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
    ctx.fill();
  }

  function drawNodeLabel(node, ctx, globalScale) {
    if (!labeledNodeIds.has(node.id)) return;
    const fontSize = Math.max(10 / globalScale, 2.5);
    ctx.font = `${fontSize}px ${getComputedStyle(document.body).fontFamily}`;
    const text = labelTextForNode(node);
    const padding = 2 / globalScale;
    const width = ctx.measureText(text).width;
    const x = node.x - width / 2;
    const y = node.y + (nodeDrawRadius(node) + 2) / globalScale;
    ctx.globalAlpha = labelAlpha(node.id);
    ctx.fillStyle = cssVar("--graph-label-bg", "rgba(12, 13, 16, 0.72)");
    ctx.fillRect(x - padding, y - fontSize, width + padding * 2, fontSize + padding);
    ctx.fillStyle = cssVar("--graph-label-text", "rgba(236, 239, 244, 0.92)");
    ctx.fillText(text, x, y);
    ctx.globalAlpha = 1;
  }

  // The neighbourhood highlight covers the selection and the hovered node together: a selection keeps
  // its look while the pointer moves on (with the magnetic pointer something is nearly always hovered).
  let focusCore = null;   // selected + hovered ids, or null when nothing is highlighted
  let focusLit = null;    // focusCore + their neighbours
  let focusDim = 0.12;    // context opacity: light under a hover alone, strong once something is selected
  // Calm hover: the previous focus is kept so the context cross-fades into the new one (A → B never
  // flashes back to the unfocused graph); the focus itself switches at once, only the context fades.
  let prevFocus = null;   // {core, lit, dim, labels} at the moment the focus changed
  let fadeT = 1, fadeFrom = 0, fadeMs = 0, fadeRaf = 0, focusKey = "";
  const ease = (t) => 1 - (1 - t) * (1 - t);
  function computeFocus() {
    const before = { core: focusCore, lit: focusLit, dim: focusDim, labels: prevLabels };
    focusCore = focusLit = null;
    focusDim = selectedNodeIds.size ? 0.12 : hoverTuning.HOVER_DIM;
    if (el("highlight-path").checked && (hoveredNode || selectedNodeIds.size)) {
      focusCore = new Set(selectedNodeIds);
      if (hoveredNode) focusCore.add(hoveredNode.id);
      focusLit = new Set(focusCore);
      focusCore.forEach((id) => (neighborMap.get(id) || []).forEach((n) => focusLit.add(n)));
    }
    const key = focusCore ? [...focusCore].sort().join("|") + `@${focusDim}` : "";
    if (key === focusKey) return;
    focusKey = key;
    const still = !calmOn() || matchMedia("(prefers-reduced-motion: reduce)").matches;
    fadeMs = still ? 0 : focusCore ? hoverTuning.FADE_IN : hoverTuning.FADE_OUT;
    prevFocus = fadeMs ? before : null;
    fadeT = fadeMs ? 0 : 1;
    fadeFrom = performance.now();
    if (fadeMs && !fadeRaf) fadeRaf = requestAnimationFrame(fadeStep);
  }
  function fadeStep() {
    fadeT = Math.min(1, (performance.now() - fadeFrom) / (fadeMs || 1));
    if (fadeT >= 1) { fadeRaf = 0; prevFocus = null; prevLabels = new Set(labeledNodeIds); }
    else fadeRaf = requestAnimationFrame(fadeStep);
    if (graph && typeof graph.refresh === "function") graph.refresh();
  }
  const labelAlpha = (id) => (fadeT >= 1 || prevLabels.has(id) ? 1 : ease(fadeT));

  function focusOpacity(f, node) {
    if (!f.core || f.core.has(node.id)) return 1;
    return f.lit.has(node.id) ? 0.95 : f.dim;
  }

  function nodeOpacity(node) {
    if (node.pile) return 1;
    if (window.Selection && window.Selection.dims(node)) return 0.12;
    const now = focusOpacity({ core: focusCore, lit: focusLit, dim: focusDim }, node);
    if (!prevFocus || (focusCore && focusLit.has(node.id))) return now;   // the focus shows at once
    const was = focusOpacity(prevFocus, node);
    return was + (now - was) * ease(fadeT);
  }

  function linkOpacity(link) {
    if (link.kind === "pile-page") return Math.min(0.75, 0.06 + 0.1 * Math.log2(1 + link.count));
    if (link.kind === "pile-pile") return 0.55;
    const base = Number(el("link-opacity").value) * (link.kind === "shared" ? 0.6 : 1);
    const s = link.source.id || link.source;
    const t = link.target.id || link.target;
    const of = (core, dim) => {
      if (!core) return base;
      if (core.has(s) || core.has(t)) return Math.min(base + 0.35, 0.95);
      return base * (dim < 0.2 ? 0.15 : 0.4);
    };
    const now = of(focusCore, focusDim);
    if (!prevFocus) return now;
    const was = of(prevFocus.core, prevFocus.dim);
    return was + (now - was) * ease(fadeT);
  }

  function drawNode(node, ctx, globalScale) {
    if (node.pile) { drawPile(node, ctx, globalScale); return; }
    const r = nodeDrawRadius(node);
    const alpha = nodeOpacity(node);
    const selected = isSelected(node);

    const hovered = !selected && hoveredNode && node.id === hoveredNode.id;
    if (selected || hovered) {
      ctx.beginPath();
      ctx.arc(node.x, node.y, r + 3 / globalScale, 0, 2 * Math.PI);
      ctx.strokeStyle = selected ? "rgba(122, 162, 255, 0.9)" : "rgba(122, 162, 255, 0.6)";
      ctx.lineWidth = (selected ? 2 : 1.5) / globalScale;
      ctx.stroke();
    }

    ctx.beginPath();
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
    ctx.fillStyle = node.color || colorForNode(node);
    ctx.globalAlpha = alpha;
    ctx.fill();
    ctx.globalAlpha = alpha * 0.5;
    ctx.strokeStyle = selected
      ? cssVar("--graph-node-stroke-selected", "#ffffff")
      : cssVar("--graph-node-stroke", "rgba(255,255,255,0.7)");
    ctx.lineWidth = (selected ? 1.4 : 0.8) / globalScale;
    ctx.stroke();
    ctx.globalAlpha = 1;

    if (labeledNodeIds.has(node.id) && !declutterOn()) drawNodeLabel(node, ctx, globalScale);
  }

  const magnetOn = () => !!el("magnet-pointer")?.checked;

  // Hover intent (calm hover): `pointedNode` follows the pointer at once (cursor, clicks, drags, the magnet
  // bubble); `hoveredNode` drives the focus and labels and commits only when the pointer settles
  // (dwell + speed gate, after hoverIntent's 7 px / 100 ms), so a sweep across the graph changes nothing.
  // Leaving keeps the focus for a short grace, so moving between close nodes cross-fades instead of blinking.
  function notePointer(e) {
    const now = performance.now(), dt = now - lastMove.t;
    const d = Math.hypot(e.clientX - lastMove.x, e.clientY - lastMove.y);
    lastMove.speed = dt > 0 && dt < 200 ? (d / dt) * 100 : 0;
    Object.assign(lastMove, { x: e.clientX, y: e.clientY, t: now });
  }
  const pointerSpeed = () => (performance.now() - lastMove.t > 100 ? 0 : lastMove.speed);
  const sameNode = (a, b) => (a && a.id) === (b && b.id);
  function commitHover(node) {
    clearTimeout(intentTimer); intentTimer = 0;
    if (sameNode(node, hoveredNode)) return;
    prevLabels = new Set(labeledNodeIds);
    hoveredNode = node || null;
    computeVisibility();
    refreshVisuals();
  }
  function requestHover(node) {
    pointedNode = node || null;
    if (!calmOn()) { commitHover(pointedNode); return; }
    clearTimeout(intentTimer);
    if (sameNode(pointedNode, hoveredNode)) { intentTimer = 0; return; }
    const wait = !pointedNode ? hoverTuning.GRACE : hoveredNode ? hoverTuning.SWITCH_DWELL : hoverTuning.DWELL;
    const settle = () => {
      if (pointedNode && pointerSpeed() > hoverTuning.SPEED) { intentTimer = setTimeout(settle, 40); return; }
      commitHover(pointedNode);
    };
    intentTimer = setTimeout(settle, wait);
  }
  const declutterOn = () => !!el("declutter-labels")?.checked;

  // Declutter (experiment): labels go on after every node, most important first, and a label that
  // would overlap one already placed is skipped, so a dense graph shows fewer names, not a pile-up.
  function labelRank(node, hoverNbs) {
    if (hoveredNode && node.id === hoveredNode.id) return 0;
    if (selectedNodeIds.has(node.id)) return 1;
    if (hoverNbs.has(node.id)) return 2;
    return 3;
  }

  function drawLabelsDecluttered(ctx, globalScale) {
    const hoverNbs = new Set(hoveredNode ? neighborMap.get(hoveredNode.id) || [] : []);
    const list = graph.graphData().nodes.filter((n) => !n.pile && labeledNodeIds.has(n.id) && Number.isFinite(n.x))
      .map((n) => ({ n, rank: labelRank(n, hoverNbs), deg: (n.inDegree || 0) + (n.outDegree || 0) }))
      .sort((a, b) => a.rank - b.rank || b.deg - a.deg);
    const fontSize = Math.max(10 / globalScale, 2.5);
    ctx.font = `${fontSize}px ${getComputedStyle(document.body).fontFamily}`;
    const padding = 2 / globalScale;
    const cell = fontSize * 6;
    const grid = new Map();                              // coarse buckets keep the overlap test cheap
    const keys = (b) => {
      const out = [];
      for (let gx = Math.floor(b[0] / cell); gx <= Math.floor(b[2] / cell); gx++)
        for (let gy = Math.floor(b[1] / cell); gy <= Math.floor(b[3] / cell); gy++) out.push(`${gx},${gy}`);
      return out;
    };
    const bg = cssVar("--graph-label-bg", "rgba(12, 13, 16, 0.72)");
    const fg = cssVar("--graph-label-text", "rgba(236, 239, 244, 0.92)");
    for (const { n, rank } of list) {
      const text = labelTextForNode(n);
      const width = ctx.measureText(text).width;
      const x = n.x - width / 2;
      const y = n.y + (nodeDrawRadius(n) + 2) / globalScale;
      const box = [x - padding, y - fontSize, x + width + padding, y + padding];
      const ks = keys(box);
      const hit = rank > 0 && ks.some((k) => (grid.get(k) || []).some((q) => box[0] < q[2] && box[2] > q[0] && box[1] < q[3] && box[3] > q[1]));
      if (hit) continue;
      ks.forEach((k) => { if (!grid.has(k)) grid.set(k, []); grid.get(k).push(box); });
      ctx.globalAlpha = (nodeOpacity(n) < 0.5 ? 0.35 : 1) * labelAlpha(n.id);
      ctx.fillStyle = bg;
      ctx.fillRect(box[0], box[1], box[2] - box[0], box[3] - box[1]);
      ctx.fillStyle = fg;
      ctx.fillText(text, x, y);
    }
    ctx.globalAlpha = 1;
  }

  function linkColorFn(link) {
    const rgb = cssVar("--graph-link-rgb", "160, 175, 210");
    return `rgba(${rgb}, ${linkOpacity(link)})`;
  }

  function updateInspector() {
    document.dispatchEvent(new CustomEvent("graph:selection", { detail: { nodes: [...selectedNodes] } }));
    const panel = el("node-inspector");
    const link = el("inspector-link");
    const propsEl = el("inspector-props");
    const previewEl = el("inspector-preview");
    const previewSection = el("inspector-preview-section");
    const list = el("inspector-list");
    const nodes = [...selectedNodes];

    if (!nodes.length) {
      hideInspector();
      return;
    }

    showInspector();

    if (nodes.length === 1) {
      const node = nodes[0];
      const title = node.title || node.id;
      link.textContent = title;
      link.href = obsidianUri(node.path || `wiki/${node.id}.md`);
      link.hidden = false;
      propsEl.innerHTML = renderProperties(node.properties)
        + `<dt>read</dt><dd><a href="/explore#/p/${encodeURIComponent(node.id)}">Open in Explore →</a></dd>`;
      previewEl.textContent = node.preview || "(no preview)";
      previewSection.hidden = false;
      list.classList.add("hidden");
      list.innerHTML = "";
    } else {
      link.textContent = `${nodes.length} nodes selected`;
      link.removeAttribute("href");
      link.hidden = false;
      propsEl.innerHTML = `<dt>types</dt><dd>${escapeHtml(nodes.map((n) => n.type).filter((v, i, a) => a.indexOf(v) === i).join(", "))}</dd>`;
      previewSection.hidden = true;
      previewEl.textContent = "";
      list.classList.remove("hidden");
      list.innerHTML = nodes
        .slice(0, 20)
        .map((n) => `<li><a href="${obsidianUri(n.path || `wiki/${n.id}.md`)}" target="_blank" rel="noopener noreferrer">${escapeHtml(n.title || n.id)}</a></li>`)
        .join("") + (nodes.length > 20 ? `<li>…and ${nodes.length - 20} more</li>` : "");
    }
  }

  function hideInspector() {
    const panel = el("node-inspector");
    panel.hidden = true;
    panel.classList.add("hidden");
  }

  function showInspector() {
    const panel = el("node-inspector");
    panel.hidden = false;
    panel.classList.remove("hidden");
  }

  let lastClick = { id: null, at: 0 };

  function exploreUrl(id) {
    return `/explore#/p/${encodeURIComponent(id)}`;
  }

  function handleNodeClick(node, event) {
    if (suppressGraphPick) return;
    if (!node.pile && window.Selection && window.Selection.onNodeClick(node, event)) {
      nodeClickHandled = true;
      setTimeout(() => { nodeClickHandled = false; }, 120);
      return;
    }
    if (node.pile) {
      document.dispatchEvent(new CustomEvent("datalayer:pile", { detail: { format: node.format } }));
      return;
    }
    const now = Date.now();
    if (lastClick.id === node.id && now - lastClick.at < 380) {
      lastClick = { id: null, at: 0 };
      if (window.SideReader && !event.shiftKey) window.SideReader.open(node.id);
      else location.href = exploreUrl(node.id);
      return;
    }
    lastClick = { id: node.id, at: now };
    nodeClickHandled = true;
    setTimeout(() => { nodeClickHandled = false; }, 120);

    if (event.shiftKey) {
      if (selectedNodeIds.has(node.id)) selectedNodeIds.delete(node.id);
      else selectedNodeIds.add(node.id);
      reconcileSelectedNodes();
      updateSelectionUi();
      updateInspector();
      ensureNeighborMap();
      computeVisibility();
      refreshVisuals();
      return;
    } else if (event.ctrlKey || event.metaKey) {
      toggleSelection(node);
      return;
    } else {
      setSelection([node], { additive: false });
      return;
    }
  }

  function currentSettings() {
    return {
      view: readView(),
      search: el("search-nodes").value,
      nodeFilters: getNodeFilters("node-filters"),
      visibleTypes: shownTypes ? [...shownTypes] : null,
      labelMode: el("label-mode").value,
      labelField: el("label-field").value,
      labelTruncate: el("label-truncate").checked,
      labelSizeThreshold: el("label-size-threshold").checked,
      labelMinSize: Number(el("label-min-size").value),
      labelFilters: getNodeFilters("label-filters"),
      labelTypes: [...activeLabelTypes],
      colorBy: el("color-by").value,
      sizeBy: el("size-by").value,
      nodeSize: Number(el("node-size").value),
      linkOpacity: Number(el("link-opacity").value),
      showArrows: el("show-arrows").checked,
      highlightPath: el("highlight-path").checked,
      forceCharge: Number(el("force-charge").value),
      forceLink: Number(el("force-link").value),
      forceCenter: Number(el("force-center").value),
    };
  }

  function applySettings(s) {
    el("search-nodes").value = s.search || "";
    setNodeFilters("node-filters", s.nodeFilters || [], "btn-add-node-filter");
    setShownTypes(s.visibleTypes);
    el("label-mode").value = s.labelMode || "hover";
    el("label-field").value = s.labelField || "slug";
    el("label-truncate").checked = s.labelTruncate !== false;
    el("label-size-threshold").checked = s.labelSizeThreshold !== false;
    el("label-min-size").value = s.labelMinSize ?? 5.5;
    setNodeFilters("label-filters", s.labelFilters || [], "btn-add-label-filter");
    setActiveLabelTypes(s.labelTypes || []);
    el("color-by").value = s.colorBy || "type";
    el("size-by").value = s.sizeBy || "connections";
    el("node-size").value = s.nodeSize ?? 5;
    el("link-opacity").value = s.linkOpacity ?? 0.35;
    el("show-arrows").checked = !!s.showArrows;
    el("highlight-path").checked = s.highlightPath !== false;
    el("force-charge").value = s.forceCharge ?? -120;
    el("force-link").value = s.forceLink ?? 70;
    el("force-center").value = s.forceCenter ?? 0.3;
    toggleLabelFilterUi();
    applyForces();
    applyFilters();
    applyNodeSizing();
    if (s.view && isValidView(s.view)) {
      applyView(s.view);
    } else if (s.visibleTypes) {
      // a type-limited view lays out a smaller graph than the one just fitted
      setTimeout(fitToView, 900);
    }
  }

  function toggleLabelFilterUi() {
    const custom = el("label-mode").value === "custom";
    el("label-filters").classList.toggle("hidden", !custom);
    el("btn-add-label-filter").classList.toggle("hidden", !custom);
  }

  function typeChipTypes() {
    const fromData = snapshot?.facets?.types || [];
    if (!fromData.length) return [...TYPE_CHIP_ORDER];
    const ordered = TYPE_CHIP_ORDER.filter((type) => fromData.includes(type));
    const extras = fromData.filter((type) => !ordered.includes(type)).sort();
    return [...ordered, ...extras];
  }

  function renderLabelTypeChips() {
    const container = el("label-type-chips");
    if (!container) return;
    container.innerHTML = "";
    typeChipTypes().forEach((type) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `type-chip${activeLabelTypes.has(type) ? " active" : ""}`;
      btn.dataset.type = type;
      btn.title = `Toggle labels for ${TYPE_DISPLAY[type] || type}`;
      const dot = document.createElement("span");
      dot.className = "type-chip-dot";
      dot.style.background = TYPE_COLORS[type] || "#6c7086";
      const label = document.createElement("span");
      label.textContent = TYPE_DISPLAY[type] || type;
      btn.appendChild(dot);
      btn.appendChild(label);
      btn.addEventListener("click", () => toggleLabelType(type));
      container.appendChild(btn);
    });
    el("btn-clear-label-types")?.classList.toggle("hidden", activeLabelTypes.size === 0);
  }

  // ---- node-type visibility (which types are drawn at all; labels are separate) ----
  function isTypeShown(type) {
    return !shownTypes || shownTypes.has(type || "unknown");
  }

  function setShownTypes(types) {
    shownTypes = Array.isArray(types) ? new Set(types.filter(Boolean)) : null;
    renderShowTypeChips();
  }

  function toggleShownType(type) {
    const all = typeChipTypes();
    const next = new Set(shownTypes || all);
    if (next.has(type)) next.delete(type);
    else next.add(type);
    shownTypes = all.every((t) => next.has(t)) ? null : next;
    renderShowTypeChips();
    applyFilters();
  }

  function showTypes(types) {
    setShownTypes(types);
    applyFilters();
    setTimeout(fitToView, 900);
  }

  function renderShowTypeChips() {
    const container = el("show-type-chips");
    if (!container) return;
    container.innerHTML = "";
    typeChipTypes().forEach((type) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `type-chip${isTypeShown(type) ? " active" : ""}`;
      btn.dataset.type = type;
      btn.title = `Show or hide every ${TYPE_DISPLAY[type] || type}`;
      const dot = document.createElement("span");
      dot.className = "type-chip-dot";
      dot.style.background = TYPE_COLORS[type] || "#6c7086";
      const label = document.createElement("span");
      label.textContent = TYPE_DISPLAY[type] || type;
      btn.appendChild(dot);
      btn.appendChild(label);
      btn.addEventListener("click", () => toggleShownType(type));
      container.appendChild(btn);
    });
  }

  function setActiveLabelTypes(types) {
    activeLabelTypes = new Set((types || []).filter(Boolean));
    renderLabelTypeChips();
  }

  function toggleLabelType(type) {
    if (activeLabelTypes.has(type)) activeLabelTypes.delete(type);
    else activeLabelTypes.add(type);
    renderLabelTypeChips();
    ensureNeighborMap();
    computeVisibility();
    refreshVisuals();
  }

  function resizeGraph() {
    if (!graph) return;
    graph.width(graphWidth()).height(graphHeight());
  }

  function initGraph() {
    graph = ForceGraph()(el("graph-root"))
      .width(graphWidth())
      .height(graphHeight())
      .backgroundColor("rgba(0,0,0,0)")
      .nodeId("id")
      .nodeRelSize(nodeRadius())
      .nodeVal((n) => nodeVisualRadius(n) ** 2)
      .linkWidth(linkWidthFn)
      .linkLabel(linkLabelFn)
      .linkLineDash((l) => (l.kind === "shared" ? [2, 2] : null))
      .linkCanvasObjectMode((l) => (l.kind === "shared" ? "after" : undefined))
      .linkCanvasObject(drawSharedCount)
      .linkDirectionalParticles(0)
      .cooldownTicks(120)
      .nodeCanvasObject(drawNode)
      .nodeCanvasObjectMode(() => "replace")
      .nodePointerAreaPaint(paintPointerArea)
      .linkColor(linkColorFn)
      .onNodeHover((node) => {
        el("graph-root").style.cursor = node ? "pointer" : null;
        // graph-magnet.js owns the hover while it is on: taking force-graph's pick too would undo its hysteresis
        if (magnetOn()) return;
        requestHover(node);
      })
      .onNodeClick(handleNodeClick)
      // a near miss can land on an edge: with the magnet on, that click belongs to the pulled node
      .onLinkClick((link, ev) => { if (magnetOn() && pointedNode && !suppressGraphPick && !nodeClickHandled) handleNodeClick(pointedNode, ev); })
      .onBackgroundClick((ev) => {
        if (suppressGraphPick || nodeClickHandled) return;
        if (magnetOn() && pointedNode) { handleNodeClick(pointedNode, ev); return; }   // a near miss clicks the pulled node
        if (!ev.shiftKey && !ev.metaKey && !ev.ctrlKey && selectedNodeIds.size) clearSelection();
      })
      .onNodeDrag((node, translate) => {
        if (!selectedNodeIds.has(node.id) || selectedNodeIds.size < 2) return;
        for (const sel of selectedNodes) {
          if (sel === node) continue;
          sel.fx = (sel.fx ?? sel.x) + translate.x;
          sel.fy = (sel.fy ?? sel.y) + translate.y;
        }
      })
      .onNodeDragEnd((node) => {
        if (!selectedNodeIds.has(node.id) || selectedNodeIds.size < 2) return;
        for (const sel of selectedNodes) {
          if (sel === node) continue;
          sel.fx = undefined;
          sel.fy = undefined;
        }
      })
      .onRenderFramePost((ctx, globalScale) => { if (declutterOn()) drawLabelsDecluttered(ctx, globalScale); })
      .onZoom(() => {
        viewState = readView();
        updateZoomUi();
        updateStatusLine();
      })
      .onEngineStop(() => {
        if (needsInitialFit) {
          needsInitialFit = false;
          fitToView();
          if (onFirstFit) {
            const cb = onFirstFit;
            onFirstFit = null;
            setTimeout(cb, 450);
          }
        }
      });

    window.addEventListener("resize", debounce(() => {
      resizeGraph();
      if (viewState) applyView(viewState);
    }, 150));

    document.addEventListener("themechange", () => {
      refreshVisuals();
    });

    applyInteractionSettings();
    graph.linkDirectionalArrowLength(el("show-arrows").checked ? 4 : 0);
    graph.linkDirectionalArrowRelPos(0.85);
    applyForces();
    applyFilters();
  }

  async function fetchGraph() {
    const res = await fetch(dataLayerOn() ? "/api/graph?layer=raw" : "/api/graph");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  function updateStatusLine() {
    if (!snapshot) return;
    const zoom = viewState ? `${Math.round(viewState.k * 100)}%` : "";
    el("status-line").textContent =
      `${snapshot.node_count} nodes · ${snapshot.link_count} links` +
      (zoom ? ` · ${zoom}` : "") +
      ` · updated ${snapshot.generated_at}`;
  }

  async function loadGraph({ preserveView = true } = {}) {
    const prevEtag = snapshot?.etag;
    const data = await fetchGraph();
    if (data.schema) applySchema(data.schema);
    const firstLoad = !snapshot;
    snapshot = data;
    updateStatusLine();
    renderLabelTypeChips();

    if (!firstLoad && prevEtag === data.etag) return false;

    if (!graph) initGraph();
    else applyFilters();
    document.dispatchEvent(new CustomEvent("graph:changed"));

    return true;
  }

  function startPolling() {
    stopPolling();
    if (!el("live-sync").checked) return;
    pollTimer = setInterval(async () => {
      try {
        const changed = await loadGraph({ preserveView: true });
        if (changed) toast("Graph synced from wiki");
      } catch { /* ignore */ }
    }, dataLayerOn() ? 30000 : 4000);  // the raw-layer payload is large; poll it slowly
  }

  function stopPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = null;
  }

  function loadUiFold() {
    try {
      const raw = localStorage.getItem(UI_FOLD_KEY);
      if (!raw) return null;
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }

  function saveUiFold(state) {
    localStorage.setItem(UI_FOLD_KEY, JSON.stringify(state));
  }

  function defaultUiFold() {
    return {
      toolbar: false,
      hudLeft: false,
      hudRight: false,
      panels: {},
    };
  }

  function getUiFold() {
    return { ...defaultUiFold(), ...(loadUiFold() || {}) };
  }

  function setShellOpen(shellId, tabId, open) {
    const shell = el(shellId);
    const tab = el(tabId);
    shell.classList.toggle("is-collapsed", !open);
    tab.setAttribute("aria-expanded", String(open));
  }

  function setupCollapsibleUi() {
    const state = getUiFold();

    setShellOpen("graph-toolbar", "btn-toggle-toolbar", state.toolbar);
    setShellOpen("hud-left-shell", "btn-toggle-hud-left", state.hudLeft);
    setShellOpen("hud-right-shell", "btn-toggle-hud-right", state.hudRight);

    document.querySelectorAll("details.fold-panel[data-panel]").forEach((panel) => {
      const id = panel.dataset.panel;
      const open = Object.prototype.hasOwnProperty.call(state.panels, id)
        ? state.panels[id]
        : false;
      panel.open = open;
    });

    function persistUi() {
      const panels = {};
      document.querySelectorAll("details.fold-panel[data-panel]").forEach((panel) => {
        panels[panel.dataset.panel] = panel.open;
      });
      saveUiFold({
        toolbar: !el("graph-toolbar").classList.contains("is-collapsed"),
        hudLeft: !el("hud-left-shell").classList.contains("is-collapsed"),
        hudRight: !el("hud-right-shell").classList.contains("is-collapsed"),
        panels,
      });
    }

    el("btn-toggle-toolbar").addEventListener("click", () => {
      setShellOpen("graph-toolbar", "btn-toggle-toolbar", true);
      persistUi();
    });
    el("btn-collapse-toolbar").addEventListener("click", () => {
      setShellOpen("graph-toolbar", "btn-toggle-toolbar", false);
      persistUi();
    });
    el("btn-toggle-hud-left").addEventListener("click", () => {
      setShellOpen("hud-left-shell", "btn-toggle-hud-left", true);
      persistUi();
    });
    el("btn-collapse-hud-left").addEventListener("click", () => {
      setShellOpen("hud-left-shell", "btn-toggle-hud-left", false);
      persistUi();
    });
    el("btn-toggle-hud-right").addEventListener("click", () => {
      setShellOpen("hud-right-shell", "btn-toggle-hud-right", true);
      persistUi();
    });
    el("btn-collapse-hud-right").addEventListener("click", () => {
      setShellOpen("hud-right-shell", "btn-toggle-hud-right", false);
      persistUi();
    });

    document.querySelectorAll("details.fold-panel[data-panel]").forEach((panel) => {
      panel.addEventListener("toggle", persistUi);
    });

    document.querySelectorAll(".panel-summary-actions").forEach((actions) => {
      actions.addEventListener("click", (ev) => ev.stopPropagation());
    });
    document.querySelectorAll(".panel-summary-actions button").forEach((btn) => {
      btn.addEventListener("click", (ev) => ev.stopPropagation());
    });
  }

  function bindUi() {
    setupCollapsibleUi();
    refreshPresetSelect();

    el("btn-zoom-in").addEventListener("click", () => zoomBy(1.25));
    el("btn-zoom-out").addEventListener("click", () => zoomBy(1 / 1.25));
    el("btn-fit").addEventListener("click", fitToView);
    el("btn-reset-view").addEventListener("click", resetView);

    el("btn-help").addEventListener("click", () => {
      const panel = el("shortcuts-panel");
      const open = panel.classList.toggle("hidden");
      el("btn-help").setAttribute("aria-expanded", String(!open));
    });

    document.addEventListener("click", (ev) => {
      if (!el("btn-help").contains(ev.target) && !el("shortcuts-panel").contains(ev.target)) {
        el("shortcuts-panel").classList.add("hidden");
        el("btn-help").setAttribute("aria-expanded", "false");
      }
    });

    [
      "search-nodes", "label-mode", "label-field", "label-truncate", "label-size-threshold", "label-min-size",
      "color-by", "size-by",
      "node-size", "link-opacity", "show-arrows", "highlight-path",
      "force-charge", "force-link", "force-center",
    ].forEach((id) => {
      const node = el(id);
      const evt = node.type === "range" || node.type === "checkbox" ? "input" : "change";
      node.addEventListener(evt, () => {
        if (id.startsWith("force-")) applyForces();
        if (id === "label-mode") toggleLabelFilterUi();
        if (id === "node-size" || id === "size-by") applyNodeSizing();
        if (id.startsWith("label-")) refreshVisuals();
        applyFilters();
      });
    });

    el("search-nodes").addEventListener("input", debounce(applyFilters, 180));

    el("btn-add-node-filter").addEventListener("click", () => {
      addFilterRow("node-filters", "btn-add-node-filter", { field: "type", op: "is" });
      applyFilters();
    });
    el("btn-add-label-filter").addEventListener("click", () => {
      addFilterRow("label-filters", "btn-add-label-filter", { field: "type", op: "is" });
      applyFilters();
    });

    el("btn-show-all-types").addEventListener("click", () => showTypes(null));
    el("btn-show-overview-types").addEventListener("click", () => showTypes(OVERVIEW_TYPES));

    el("btn-clear-label-types").addEventListener("click", () => {
      setActiveLabelTypes([]);
      applyFilters();
    });

    el("btn-reheat").addEventListener("click", () => graph && graph.d3ReheatSimulation());
    el("btn-refresh").addEventListener("click", async () => {
      await loadGraph({ preserveView: true });
      toast("Refreshed");
    });

    const dl = el("data-layer");
    if (dl) {
      if (window.KB_STATIC) {                       // the shared site has no raw data: hide the toggle
        const row = dl.closest("label");
        (row || dl).hidden = true;
        dl.checked = false;
      } else {
        try { dl.checked = localStorage.getItem(DATA_LAYER_KEY) === "1"; } catch (_) { /* private mode */ }
        dl.addEventListener("change", () => {
          try { localStorage.setItem(DATA_LAYER_KEY, dl.checked ? "1" : "0"); } catch (_) { /* ignore */ }
          document.dispatchEvent(new CustomEvent("datalayer:toggle", { detail: { on: dl.checked } }));
          // the piles sit outside the page cluster: refit so they are on screen
          loadGraph({ preserveView: true }).then(() => setTimeout(fitToView, 900)).catch(() => {});
          if (el("live-sync").checked) startPolling();  // re-arm at the interval for this layer
        });
      }
    }

    el("live-sync").addEventListener("change", () => {
      if (el("live-sync").checked) startPolling();
      else stopPolling();
    });

    el("btn-apply-preset").addEventListener("click", () => {
      const presets = loadPresets();
      const idx = Number(el("preset-select").value);
      if (presets[idx]) {
        applySettings(presets[idx]);
        toast(`Applied “${presets[idx].name}”`);
      }
    });

    el("btn-save-preset").addEventListener("click", () => {
      const name = prompt("Preset name");
      if (!name) return;
      const presets = loadPresets();
      const entry = { name: name.trim(), ...currentSettings() };
      const existing = presets.findIndex((p) => p.name === entry.name);
      if (existing >= 0) presets[existing] = entry;
      else presets.push(entry);
      savePresets(presets);
      toast(`Saved “${entry.name}”`);
    });

    el("btn-delete-preset").addEventListener("click", () => {
      const presets = loadPresets();
      const idx = Number(el("preset-select").value);
      const name = presets[idx]?.name;
      if (!name || !confirm(`Delete preset “${name}”?`)) return;
      presets.splice(idx, 1);
      savePresets(presets.length ? presets : [...DEFAULT_PRESETS]);
      toast("Preset deleted");
    });

    el("btn-export-presets").addEventListener("click", () => {
      const blob = new Blob([JSON.stringify(loadPresets(), null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "thesis-wiki-graph-presets.json";
      a.click();
      URL.revokeObjectURL(a.href);
    });

    el("import-presets").addEventListener("change", async (e) => {
      const file = e.target.files?.[0];
      if (!file) return;
      try {
        const imported = JSON.parse(await file.text());
        if (!Array.isArray(imported)) throw new Error("bad format");
        savePresets(imported);
        toast("Presets imported");
      } catch {
        toast("Import failed");
      }
      e.target.value = "";
    });

    setupInspectorUi();
  }

  function setupInspectorUi() {
    const closeBtn = el("close-inspector");

    closeBtn.addEventListener("pointerdown", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      ev.stopImmediatePropagation();
      closeInspector();
    }, true);

    closeBtn.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      ev.stopImmediatePropagation();
    }, true);
  }

  function focusNode(id, { zoom = true } = {}) {
    const node = nodeById(id);
    if (!node) return false;
    if (!isTypeShown(node.type)) {
      // a page of a hidden type was asked for: bring its type back, then focus once it is laid out
      toggleShownType(node.type || "unknown");
      setTimeout(() => focusNode(id, { zoom }), 700);
      return true;
    }
    setSelection([node], { additive: false });
    if (graph && Number.isFinite(node.x) && Number.isFinite(node.y)) {
      graph.centerAt(node.x, node.y, 600);
      if (zoom && graph.zoom() < 1.6) graph.zoom(2.2, 600);
    }
    return true;
  }

  function legendKey(node, by) {
    if (by === "type") return TYPE_DISPLAY[node.type] || node.type || "Unknown";
    if (by === "status") return node.status || "(none)";
    if (by === "area") return (node.areas && node.areas[0]) || "(none)";
    if (by === "degree") {
      const d = (node.inDegree || 0) + (node.outDegree || 0);
      return d >= 12 ? "12+ links" : d >= 6 ? "6–11 links" : d >= 2 ? "2–5 links" : "0–1 links";
    }
    return "All pages";
  }

  function legend() {
    if (!snapshot) return { by: "type", rows: [] };
    const by = el("color-by").value;
    const rows = new Map();
    for (const node of snapshot.nodes) {
      const hidden = by === "type" && !isTypeShown(node.type);
      if (!hidden && !visibleNodeIds.has(node.id)) continue;
      const label = legendKey(node, by);
      const row = rows.get(label) || { label, color: colorForNode(node), count: 0, type: by === "type" ? node.type : null, hidden };
      row.count += 1;
      rows.set(label, row);
    }
    return { by, rows: [...rows.values()].sort((a, b) => (a.hidden - b.hidden) || (b.count - a.count)) };
  }

  window.WikiGraph = {
    focus: focusNode,
    clear: () => clearSelection(),
    nodes: () => (snapshot ? snapshot.nodes : []),
    node: (id) => nodeById(id),
    neighbors: (id) => { ensureNeighborMap(); return neighborMap.get(id) || []; },
    legend,
    colorFor: (node) => colorForNode(node),
    exploreUrl,
    obsidianUri,
    activeLabelTypes: () => new Set(activeLabelTypes),
    toggleType: toggleShownType,
    showTypes,
    overviewTypes: () => [...OVERVIEW_TYPES],
    typesFiltered: () => !!shownTypes,
    sources: rawSources,
    sourcesOf,
    seeSources,
    sourcesRevealed,
    layerOf,
    select: (ids, opts) => {
      const nodes = ids.map(nodeById).filter(Boolean);
      if (nodes.length || !(opts && opts.additive)) setSelection(nodes, opts || {});
    },
    selectedIds: () => [...selectedNodeIds],
    visibleLinks: () => (graph ? graph.graphData().links : []).map((l) => ({
      source: l.source.id || l.source, target: l.target.id || l.target, kind: l.kind })),
    visibleNodes: () => (graph ? graph.graphData().nodes.filter((n) => !n.pile) : []),
    screenOf: (n) => {                                   // viewport (client) coordinates
      const p = graph.graph2ScreenCoords(n.x, n.y), o = rootOffset();
      return { x: p.x + o.x, y: p.y + o.y };
    },
    hovered: () => pointedNode,                           // what the pointer is on now (clicks, drags)
    focused: () => hoveredNode,                           // what the focus shows (after the hover intent)
    setHover: (node) => {                                // graph-magnet.js: the pulled node becomes the hovered one
      if (sameNode(node, pointedNode)) return;
      requestHover(node);
    },
    hoverTuning,                                          // console tuning: WikiGraph.hoverTuning.DWELL = 200
    radiusOf: (node) => nodeVisualRadius(node),            // graph units
    labeledIds: () => [...labeledNodeIds],
    opacityOf: (id) => { const n = nodeById(id); return n ? nodeOpacity(n) : null; },
    zoomAt,
    panBy,
    view: () => readView(),
    setExternalFilter: (set, { force = false } = {}) => { externalFilter = set; externalForce = !!(set && force); applyFilters(); },
    isVisible: (id) => visibleNodeIds.has(id),
    redraw: () => refreshVisuals(),
    dataLayerOn,
    rawSnapshot: () => snapshot,
    reload: () => loadGraph({ preserveView: true }),
  };

  async function boot() {
    bindUi();
    renderLabelTypeChips();
    renderShowTypeChips();
    setupWheel();
    setupKeyboard();

    try {
      await loadSchema();
      renderLabelTypeChips();
      renderShowTypeChips();
      const preset = loadPresets()[0];
      // Filters, labels and colours go on before the first load, so the graph opens already in the
      // default view instead of drawing every page for a few seconds first; only a saved camera waits
      // for the layout to settle.
      applySettings({ ...preset, view: null });
      onFirstFit = preset.view && isValidView(preset.view) ? () => applyView(preset.view) : null;
      await loadGraph({ preserveView: false });
      setTimeout(() => {
        if (!needsInitialFit) return;
        needsInitialFit = false;
        fitToView();
        if (onFirstFit) {
          const cb = onFirstFit;
          onFirstFit = null;
          setTimeout(cb, 450);
        }
      }, 1500);
      startPolling();
      const focusId = new URLSearchParams(location.search).get("focus");
      if (focusId) setTimeout(() => focusNode(focusId), 2400);
      document.dispatchEvent(new CustomEvent("graph:ready"));
    } catch (err) {
      el("status-line").textContent = `Failed to load graph: ${err.message}`;
    }
  }

  document.addEventListener("DOMContentLoaded", boot);
})();
