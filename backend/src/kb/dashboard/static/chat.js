/* Chat tab: streams answers from /api/chat, keeps the conversation in this tab until saved. */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const LS = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (_) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (_) { /* private mode */ } },
  };
  const SS = {
    get(k, d) { try { const v = sessionStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (_) { return d; } },
    set(k, v) { try { sessionStorage.setItem(k, JSON.stringify(v)); } catch (_) { /* ignore */ } },
  };

  const newId = () => "kb-chat:" + new Date().toISOString().slice(0, 19).replace(/[-:T]/g, "") +
    "-" + Math.random().toString(36).slice(2, 8);

  // ── state ────────────────────────────────────────────────────────────────
  let prompts = [];                                   // [{id,title,description,text}]
  let edits = LS.get("kbchat.edits", {});             // template id → edited text
  let templateId = LS.get("kbchat.template", "query");
  let chat = SS.get("kbchat.chat", null) || { id: newId(), session: null, messages: [] };
  if (chat.session === undefined) chat.session = null;   // agent session id (resume key)
  let agentAvailable = true;
  let busy = null;                                    // AbortController while streaming

  const thread = $("ch-thread");

  // ── rendering ────────────────────────────────────────────────────────────
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function renderMarkdown(text) {
    if (!window.marked) return `<p>${esc(text).replace(/\n/g, "<br>")}</p>`;
    const math = [];
    const keep = (tex, display) => { math.push({ tex, display }); return `@@MATH${math.length - 1}@@`; };
    let src = text
      .replace(/\$\$([\s\S]+?)\$\$/g, (_, t) => keep(t, true))
      .replace(/\\\[([\s\S]+?)\\\]/g, (_, t) => keep(t, true))
      .replace(/(^|[^\\$])\$([^\s$](?:[^$\n]*?[^\s$])?)\$/g, (_, pre, t) => pre + keep(t, false))
      .replace(/\\\((.+?)\\\)/g, (_, t) => keep(t, false));
    src = src.replace(/\[\[([^\]|#]+)(?:\|([^\]]+))?\]\]/g, (_, slug, label) =>
      `<a class="ch-cite" href="/explore#/p/${encodeURIComponent(slug.trim())}" target="_blank" rel="noopener">${esc(label || slug.trim())}</a>`);
    let html = window.marked.parse(src, { gfm: true, breaks: false });
    html = html.replace(/@@MATH(\d+)@@/g, (_, i) => {
      const m = math[+i];
      if (!window.katex) return esc(m.display ? `$$${m.tex}$$` : `$${m.tex}$`);
      try { return window.katex.renderToString(m.tex, { displayMode: m.display, throwOnError: false }); }
      catch (_) { return esc(m.tex); }
    });
    return html;
  }

  function msgNode(m) {
    const div = document.createElement("div");
    div.className = `ch-msg ch-msg-${m.role}`;
    const role = m.role === "user" ? "You" : "Claude";
    const body = m.role === "user" ? esc(m.content) : renderMarkdown(m.content || "");
    const meta = m.meta ? `<div class="ch-msg-meta">${esc(m.meta)}</div>` : "";
    const err = m.error ? `<div class="ch-msg-meta ch-msg-error">${esc(m.error)}</div>` : "";
    div.innerHTML = `<div class="ch-msg-role">${role}</div>${traceBlock(m.trace)}<div class="ch-msg-body">${body}</div>${meta}${tokenLine(m.usage)}${err}`;
    return div;
  }

  // Agent tool trace: a live activity line while streaming, a collapsed list afterwards.
  function traceBlock(trace, live) {
    if (!trace || !trace.length) return "";
    const items = trace.map((t) => `<li class="${t.error ? "ch-trace-err" : ""}"><span class="ch-trace-tool">${esc(t.name)}</span> ${esc(t.summary || "")}</li>`).join("");
    const reads = trace.filter((t) => t.name === "Read" && /^read /.test(t.summary || "")).length;
    if (live) {
      const last = trace[trace.length - 1];
      return `<div class="ch-activity"><span class="ch-activity-dots"></span>${esc(last.name.toLowerCase())}: ${esc(last.summary || "")}</div>`;
    }
    return `<details class="ch-trace"><summary>${trace.length} step${trace.length === 1 ? "" : "s"} · ${reads} page${reads === 1 ? "" : "s"} read</summary><ol>${items}</ol></details>`;
  }

  const num = (x) => (x || 0).toLocaleString();
  const usd = (x) => (x >= 1 ? `$${x.toFixed(2)}` : x >= 0.01 ? `$${x.toFixed(3)}` : `$${(x || 0).toFixed(4)}`);

  function tokenLine(u) {
    if (!u) return "";
    const input = (u.input_tokens || 0) + (u.cache_read_input_tokens || 0) + (u.cache_creation_input_tokens || 0);
    const parts = [`${num(input)} in`];
    if (u.cache_read_input_tokens) parts.push(`${num(u.cache_read_input_tokens)} cached`);
    parts.push(`${num(u.output_tokens)} out`);
    if (u.billing === "subscription") parts.push(`subscription${typeof u.est_cost_usd === "number" ? ` (≈${usd(u.est_cost_usd)} at API prices)` : ""}`);
    else if (typeof u.cost_usd === "number") parts.push(usd(u.cost_usd));
    return `<div class="ch-tokens" title="input incl. cache reads/writes · output incl. thinking">${parts.join(" · ")}</div>`;
  }

  // ── account (API key or Claude subscription) ─────────────────────────────
  function renderAuth(st) {
    const a = st.auth || { mode: "api_key", keys: [], subscription: {} };
    const sel = $("ch-auth");
    const sub = a.subscription || {};
    const opts = [];
    const subLabel = sub.logged_in
      ? `Claude subscription — ${sub.plan ? sub.plan.toUpperCase() + " · " : ""}${sub.email || "logged in"}`
      : "Claude subscription — not logged in";
    opts.push(`<option value="subscription" ${sub.logged_in ? "" : "disabled"}>${esc(subLabel)}</option>`);
    for (const k of a.keys) {
      const label = k.name === "env" ? `API key — ANTHROPIC_API_KEY (${k.hint})`
        : k.name === "default" ? `API key — default file (${k.hint})` : `API key — ${k.name} (${k.hint})`;
      opts.push(`<option value="key:${esc(k.name)}">${esc(label)}</option>`);
    }
    if (!a.keys.length) opts.push(`<option value="key:" disabled>No API key stored yet</option>`);
    sel.innerHTML = opts.join("");
    const current = a.mode === "subscription" ? "subscription" : `key:${a.active_key || (a.keys[0] && a.keys[0].name) || ""}`;
    sel.value = current;
    if (sel.value !== current && a.keys.length) sel.value = `key:${a.keys[0].name}`;
    const hint = $("ch-auth-hint");
    if (sel.value === "subscription") {
      hint.textContent = "Agent backend only · usage counts against your plan, not the credit · personal use";
    } else if (sub.logged_in) {
      hint.textContent = `Billed to the selected key. Your ${sub.plan ? sub.plan.toUpperCase() : "Claude"} subscription is also available.`;
    } else {
      hint.textContent = sub.error ? `Subscription: ${sub.error}` : "";
    }
    if (st.auth && st.auth.keys_dir) $("ch-keys-dir").textContent = st.auth.keys_dir;
    $("ch-key-remove").disabled = !sel.value.startsWith("key:") || sel.value === "key:env" || sel.value === "key:";
  }

  function authPayload() {
    const v = $("ch-auth").value || "";
    if (v === "subscription") return { auth_mode: "subscription" };
    return { auth_mode: "api_key", active_key: v.startsWith("key:") ? v.slice(4) : "" };
  }

  async function postJSON(url, body) {
    const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const out = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(out.hint ? `${out.error}: ${out.hint}` : (out.error || `HTTP ${res.status}`));
    return out;
  }

  async function chooseAuth() {
    const msg = $("ch-key-msg");
    try {
      const st = await postJSON("/api/chat/settings", authPayload());
      renderKey(st);
      renderAuth(st);
      msg.textContent = "";
    } catch (e) {
      msg.className = "ch-hint bad";
      msg.textContent = ` ${e.message}`;
    }
  }

  async function addKey() {
    const msg = $("ch-key-msg");
    try {
      const st = await postJSON("/api/chat/keys", { name: $("ch-key-name").value, key: $("ch-key-value").value });
      $("ch-key-value").value = "";
      $("ch-key-name").value = "";
      renderKey(st);
      renderAuth(st);
      msg.className = "ch-hint ok";
      msg.textContent = " Key stored and selected.";
    } catch (e) {
      msg.className = "ch-hint bad";
      msg.textContent = ` ${e.message}`;
    }
  }

  async function removeKey() {
    const v = $("ch-auth").value || "";
    if (!v.startsWith("key:") || !v.slice(4)) return;
    const msg = $("ch-key-msg");
    try {
      const st = await postJSON("/api/chat/keys/remove", { name: v.slice(4) });
      renderKey(st);
      renderAuth(st);
      msg.className = "ch-hint ok";
      msg.textContent = ` Removed ${v.slice(4)}.`;
    } catch (e) {
      msg.className = "ch-hint bad";
      msg.textContent = ` ${e.message}`;
    }
  }

  function renderSpend(s) {
    if (!s) return;
    const box = $("ch-budget");
    box.classList.remove("hidden");
    const left = Math.max(0, s.left);
    $("ch-left").textContent = usd(left).replace(/(\.\d{2})\d+$/, "$1");
    const used = s.credit > 0 ? Math.min(100, (s.spent / s.credit) * 100) : 0;
    $("ch-bar").style.width = `${used}%`;
    box.classList.toggle("low", s.credit > 0 && left < s.credit * 0.1);
    const fmt = (d) => new Date(d + "T00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" });
    $("ch-budget-detail").textContent =
      `of $${s.credit} · spent ${usd(s.spent)} in ${s.turns} request${s.turns === 1 ? "" : "s"} since ${fmt(s.cycle_start)} · resets ${fmt(s.next_reset)}` +
      (s.subscription_turns ? ` · ${s.subscription_turns} on the subscription` : "");
  }

  function renderKey(st) {
    const key = $("ch-key");
    const sub = (st.auth && st.auth.subscription) || {};
    if (st.auth && st.auth.mode === "subscription" && sub.logged_in) {
      key.className = "ch-key ok";
      key.innerHTML = `<span class="ch-dot"></span><span>Claude subscription (${esc(sub.plan || "plan")})</span>`;
      $("ch-keyname").innerHTML = esc(sub.email || "");
    } else if (st.key) {
      key.className = "ch-key ok";
      key.innerHTML = `<span class="ch-dot"></span><span>API key loaded (${esc(st.key_origin)})</span>`;
      $("ch-keyname").innerHTML = `${st.key_name ? `<strong>${esc(st.key_name)}</strong> · ` : ""}${esc(st.key_hint)}`;
    } else {
      key.className = "ch-key bad";
      key.innerHTML = `<span class="ch-dot"></span><span>No API key. Set <code>ANTHROPIC_API_KEY</code> or create <code>${esc(st.key_file)}</code> (no restart needed), then reload this page.</span>`;
      $("ch-keyname").textContent = "";
    }
    $("ch-set-name").value = st.key_name || "";
    $("ch-set-credit").value = st.spend ? st.spend.credit : 100;
    renderSpend(st.spend);
  }

  function renderThread() {
    thread.querySelectorAll(".ch-msg").forEach((n) => n.remove());
    $("ch-empty").classList.toggle("hidden", chat.messages.length > 0);
    chat.messages.forEach((m) => thread.appendChild(msgNode(m)));
    thread.scrollTop = thread.scrollHeight;
    $("ch-save").disabled = !chat.messages.some((m) => m.role === "assistant" && m.content);
  }

  function renderSources(hits) {
    const ul = $("ch-sources");
    if (!hits || !hits.length) {
      ul.innerHTML = `<li class="ch-muted">No matching pages. The answer relies on earlier context or general knowledge.</li>`;
      return;
    }
    ul.innerHTML = hits.map((h) => `<li>
      <a class="ch-cite" href="/explore#/p/${encodeURIComponent(h.slug)}" target="_blank" rel="noopener">${esc(h.slug)}</a>
      <span class="ch-score" title="${agentMode() ? "times the agent read this page" : "index-first retrieval score"}">${h.score}</span>
      ${h.in_context ? '<span class="ch-tag"> · already in context</span>' : ""}
      ${h.summary ? `<span class="ch-sum">${esc(h.summary)}</span>` : ""}
    </li>`).join("");
  }

  function persist() { SS.set("kbchat.chat", chat); }
  const agentMode = () => $("ch-backend").value === "agent";

  function renderBackend(st) {
    const sel = $("ch-backend");
    const hint = $("ch-backend-hint");
    agentAvailable = !!(st.agent && st.agent.available);
    const saved = LS.get("kbchat.backend", st.backend || "agent");
    sel.querySelector('option[value="agent"]').disabled = !agentAvailable;
    sel.value = agentAvailable || saved === "direct" ? saved : "direct";
    if (!agentAvailable) {
      hint.textContent = `Agent backend unavailable: ${st.agent && st.agent.error ? st.agent.error : "SDK missing"}. Using Direct.`;
      hint.classList.remove("hidden");
    } else {
      hint.textContent = st.agent.version ? `Claude Agent SDK ${st.agent.version} · read-only over wiki/, raw/, think/` : "";
      hint.classList.toggle("hidden", !hint.textContent);
    }
  }

  // ── prompt panel ─────────────────────────────────────────────────────────
  const currentTemplate = () => prompts.find((p) => p.id === templateId) || prompts[0];
  const systemText = () => $("ch-system").value;

  function showPrompt() {
    const t = currentTemplate();
    if (!t) return;
    templateId = t.id;
    $("ch-template").value = t.id;
    $("ch-system").value = edits[t.id] ?? t.text;
    $("ch-prompt-name").textContent = t.title;
    $("ch-prompt-desc").textContent = t.description ? `· ${t.description}` : "";
    updateBadge();
  }

  function updateBadge() {
    const t = currentTemplate();
    const custom = !!t && systemText().trim() !== t.text.trim();
    $("ch-custom-badge").classList.toggle("hidden", !custom);
    return custom;
  }

  function selectTemplate(id) {
    templateId = id;
    LS.set("kbchat.template", id);
    showPrompt();
  }

  // ── streaming ────────────────────────────────────────────────────────────
  async function send(question) {
    question = question.trim();
    if (!question || busy) return;
    const history = chat.messages.filter((m) => !m.failed && !(m.error && !m.content)).map((m) => ({ role: m.role, content: m.content, sources: m.sources }));
    const userMsg = { role: "user", content: question, sources: [] };
    const botMsg = { role: "assistant", content: "" };
    chat.messages.push(userMsg, botMsg);
    renderThread();
    const node = thread.lastElementChild;
    const bodyEl = node.querySelector(".ch-msg-body");
    bodyEl.classList.add("ch-cursor");

    busy = new AbortController();
    $("ch-send").classList.add("hidden");
    $("ch-stop").classList.remove("hidden");

    const model = $("ch-model").value;
    const backend = $("ch-backend").value;
    const scope = $("ch-scope").value;
    const traceEl = document.createElement("div");
    node.insertBefore(traceEl, bodyEl);
    const paintTrace = (live) => { traceEl.innerHTML = traceBlock(botMsg.trace, live); };
    let usage = null;
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, history, model, backend, scope, session: chat.session, ...authPayload(),
                               system: systemText(), template: templateId }),
        signal: busy.signal,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.hint ? `${err.error}: ${err.hint}` : (err.error || `HTTP ${res.status}`));
      }
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      let pending = false;
      const paint = () => {
        pending = false;
        bodyEl.innerHTML = renderMarkdown(botMsg.content);
        thread.scrollTop = thread.scrollHeight;
      };
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let cut;
        while ((cut = buf.indexOf("\n\n")) !== -1) {
          const raw = buf.slice(0, cut);
          buf = buf.slice(cut + 2);
          const ev = /^event: (.+)$/m.exec(raw);
          const data = /^data: (.*)$/m.exec(raw);
          if (!ev || !data) continue;
          const payload = JSON.parse(data[1]);
          if (ev[1] === "sources") {
            userMsg.sources = payload.new;
            renderSources(payload.hits);
          } else if (ev[1] === "session") {
            chat.session = payload.id;
            persist();
          } else if (ev[1] === "tool") {
            botMsg.trace = botMsg.trace || [];
            const prev = payload.id && botMsg.trace.find((t) => t.id === payload.id);
            if (prev) Object.assign(prev, payload); else botMsg.trace.push(payload);
            paintTrace(true);
            thread.scrollTop = thread.scrollHeight;
          } else if (ev[1] === "notice") {
            botMsg.notice = payload.text;
          } else if (ev[1] === "delta") {
            botMsg.content += payload;
            if (!pending) { pending = true; requestAnimationFrame(paint); }
          } else if (ev[1] === "usage") {
            usage = payload;
            botMsg.usage = {
              input_tokens: payload.input_tokens, cache_read_input_tokens: payload.cache_read_input_tokens,
              cache_creation_input_tokens: payload.cache_creation_input_tokens,
              output_tokens: payload.output_tokens, cost_usd: payload.cost_usd,
            };
            renderSpend(payload.spend);
          } else if (ev[1] === "error") {
            throw new Error(payload.error);
          }
        }
      }
      paint();
    } catch (e) {
      if (e.name === "AbortError") botMsg.meta = "stopped";
      else botMsg.error = e.message;
      if (!botMsg.content) botMsg.content = "";
    } finally {
      busy = null;
      $("ch-send").classList.remove("hidden");
      $("ch-stop").classList.add("hidden");
    }
    if (usage) {
      botMsg.meta = `${currentTemplate()?.title || templateId}${updateBadge() ? " (custom)" : ""} · ${model}` +
        (backend === "agent" ? ` · agent${usage.num_turns ? `, ${usage.num_turns} turns` : ""}` : "") +
        (botMsg.notice ? ` · ${botMsg.notice}` : "");
    }
    // keep a failed question visible but out of the history sent next time
    if (botMsg.error && !botMsg.content) userMsg.failed = true;
    persist();
    renderThread();
  }

  async function saveSettings() {
    const msg = $("ch-set-msg");
    try {
      const res = await fetch("/api/chat/settings", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          key_name: $("ch-set-name").value,
          monthly_credit: Number($("ch-set-credit").value),
          reset_day: Number($("ch-set-day").value),
        }),
      });
      const out = await res.json();
      if (!res.ok) throw new Error(out.error || `HTTP ${res.status}`);
      renderKey(out);
      $("ch-set-day").value = out.reset_day ?? $("ch-set-day").value;
      msg.className = "ch-hint ok";
      msg.textContent = " Saved.";
    } catch (e) {
      msg.className = "ch-hint bad";
      msg.textContent = ` ${e.message}`;
    }
  }

  // ── save ─────────────────────────────────────────────────────────────────
  let toastTimer = null;
  function toast(html, bad) {
    const t = $("ch-toast");
    t.className = `ch-toast${bad ? " bad" : ""}`;
    t.innerHTML = html;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.add("hidden"), bad ? 6000 : 4000);
  }

  async function save() {
    const btn = $("ch-save");
    const messages = chat.messages.filter((m) => !m.failed && m.content)
      .map(({ trace, notice, ...m }) => m);   // the tool trace stays in the browser
    const body = {
      id: chat.id,
      title: (messages[0]?.content || "KB chat").split("\n")[0].slice(0, 80),
      model: $("ch-model").value,
      template: templateId,
      custom: updateBadge(),
      system: systemText(),
      messages,
    };
    btn.disabled = true;
    try {
      const res = await fetch("/api/chat/save", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const out = await res.json();
      if (!res.ok) throw new Error(out.error || `HTTP ${res.status}`);
      btn.classList.add("done");
      setTimeout(() => btn.classList.remove("done"), 2500);
      toast(`Saved to <code>${esc(out.path)}</code>`);
    } catch (e) {
      toast(`Save failed: ${esc(e.message)}`, true);
    } finally {
      btn.disabled = false;
    }
  }

  // ── scope ────────────────────────────────────────────────────────────────
  // "All knowledge" (empty) or a scope-* slug; ?scope=scope-x preselects it (the /scopes "Ask in chat" link).
  function scopeHint() {
    const sel = $("ch-scope"), hint = $("ch-scope-hint");
    const opt = sel.options[sel.selectedIndex];
    hint.classList.toggle("hidden", !sel.value);
    if (sel.value) hint.textContent = `Answers use only this scope's pages${opt && opt.dataset.cov ? ` (${opt.dataset.cov})` : ""} and end with what is not yet digested.`;
  }
  async function loadScopes() {
    let list = [];
    try { list = (await fetch("/api/scopes").then((r) => r.json())).scopes || []; } catch (_) { /* no scopes API */ }
    const sel = $("ch-scope");
    sel.innerHTML = '<option value="">All knowledge</option>' + list.map((s) => {
      const cov = s.coverage == null ? "" : `${Math.round(100 * s.coverage)}% digested`;
      return `<option value="${esc(s.slug)}" data-cov="${esc(cov)}">${esc(s.title || s.slug)}${cov ? ` · ${esc(cov)}` : ""}</option>`;
    }).join("");
    let want = "";
    try { want = new URLSearchParams(window.location.search).get("scope") || ""; } catch (_) { /* ignore */ }
    if (want && !list.some((s) => s.slug === want)) {
      sel.insertAdjacentHTML("beforeend", `<option value="${esc(want)}">${esc(want)}</option>`);
    }
    sel.value = want;
    scopeHint();
  }

  // ── boot ─────────────────────────────────────────────────────────────────
  async function boot() {
    const [st, pr] = await Promise.all([
      fetch("/api/chat/status").then((r) => r.json()),
      fetch("/api/chat/prompts").then((r) => r.json()),
    ]);

    renderKey(st);
    renderBackend(st);
    renderAuth(st);
    $("ch-set-day").value = st.reset_day || 30;

    const savedModel = LS.get("kbchat.model", st.default_model);
    $("ch-model").innerHTML = st.models.map((m) => `<option value="${esc(m.id)}">${esc(m.label)}</option>`).join("");
    $("ch-model").value = st.models.some((m) => m.id === savedModel) ? savedModel : st.default_model;

    await loadScopes();

    prompts = pr.prompts || [];
    $("ch-template").innerHTML = prompts.map((p) => `<option value="${esc(p.id)}">${esc(p.title)}</option>`).join("");
    if (!prompts.some((p) => p.id === templateId)) templateId = prompts[0]?.id || "query";
    showPrompt();
    renderThread();
  }

  $("ch-template").addEventListener("change", (e) => selectTemplate(e.target.value));
  $("ch-system").addEventListener("input", () => {
    const t = currentTemplate();
    if (!t) return;
    if (systemText().trim() === t.text.trim()) delete edits[t.id];
    else edits[t.id] = systemText();
    LS.set("kbchat.edits", edits);
    updateBadge();
  });
  $("ch-reset").addEventListener("click", () => {
    delete edits[templateId];
    LS.set("kbchat.edits", edits);
    showPrompt();
  });
  $("ch-model").addEventListener("change", (e) => LS.set("kbchat.model", e.target.value));
  $("ch-scope").addEventListener("change", () => {
    chat.session = null;                      // a resumed agent session would carry the old scope's pages
    scopeHint();
    persist();
  });
  $("ch-backend").addEventListener("change", (e) => {
    LS.set("kbchat.backend", e.target.value);
    fetch("/api/chat/settings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ backend: e.target.value }),
    }).catch(() => { /* the browser copy still applies */ });
  });

  $("ch-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const q = $("ch-question").value;
    $("ch-question").value = "";
    send(q);
  });
  $("ch-question").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      $("ch-form").requestSubmit();
    }
  });
  $("ch-stop").addEventListener("click", () => busy && busy.abort());
  $("ch-new").addEventListener("click", () => {
    if (busy) busy.abort();
    chat = { id: newId(), session: null, messages: [] };
    renderSources(null);
    $("ch-sources").innerHTML = '<li class="ch-muted">Ask something to see which pages were used.</li>';
    persist();
    renderThread();
  });
  $("ch-save").addEventListener("click", save);
  $("ch-set-save").addEventListener("click", saveSettings);
  $("ch-auth").addEventListener("change", chooseAuth);
  $("ch-key-add").addEventListener("click", addKey);
  $("ch-key-remove").addEventListener("click", removeKey);
  $("ch-examples").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-q]");
    if (!b) return;
    if (b.dataset.t) selectTemplate(b.dataset.t);
    send(b.dataset.q);
  });

  try {                                              // /chat?prefill=… (the graph's data layer links here)
    const pf = new URLSearchParams(window.location.search).get("prefill");
    if (pf) $("ch-question").value = pf;
  } catch (_) { /* ignore */ }
  boot().catch((e) => {
    $("ch-key").className = "ch-key bad";
    $("ch-key").textContent = `Dashboard API unreachable: ${e.message}`;
  });
})();
