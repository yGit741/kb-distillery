"""Chat with the KB: retrieval over wiki/, a streaming Claude client, and save-to-inbox.

Stdlib only. Retrieval reuses src/kb_distillery/search/query.py (index-first scoring, 0 LLM). The API key is read
from ANTHROPIC_API_KEY or ~/.config/kb-distillery/anthropic_key and never leaves this process.

Prompt caching: the system prompt is stable, and each user turn carries only the pages first
retrieved on that turn, so the message history is append-only and the whole prefix is cached
from one turn to the next.
"""
import calendar
import datetime
import json
import os
import re
import sys
import threading
import urllib.error
import urllib.request

from kb_distillery.config import pages as page_conventions
from kb_distillery.config import userdir
from kb_distillery.config.paths import vault_root
META_DIR = os.path.join(vault_root(), "meta")
ROOT = vault_root()

from kb_distillery.vault import links
from kb_distillery.search import query
from kb_distillery.vault.graph import tokenize

PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "llm", "prompts")
INBOX = os.path.join(ROOT, "raw", "inbox")
KEY_FILE = userdir.path("anthropic_key")
API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"

MODELS = [
    {"id": "claude-sonnet-5-5", "label": "Sonnet 5.5", "default": True, "context": 200000},
    {"id": "claude-opus-5-5", "label": "Opus 5.5", "context": 200000},
    {"id": "claude-haiku-5-5", "label": "Haiku 5.5", "context": 200000},
]
MODEL_IDS = {m["id"] for m in MODELS}

# USD per million tokens (Anthropic first-party list prices, checked 2026-10-21).
# Cache writes use the 5-minute TTL (1.25x input); 1-hour writes would be 2x.
PRICES = {
    "claude-sonnet-5-5": {"in": 2.00, "out": 10.00, "cache_read": 0.20},
    "claude-opus-5-5": {"in": 4.00, "out": 20.00, "cache_read": 0.20},
    "claude-haiku-5-5": {"in": 0.10, "out": 0.50, "cache_read": 0.01},
}
CACHE_WRITE_5M = 1.25
CACHE_WRITE_1H = 2.0

CONFIG_DIR = userdir.config_dir()
SETTINGS_FILE = os.path.join(CONFIG_DIR, "chat.json")     # key name, monthly credit, reset day
LEDGER_FILE = os.path.join(CONFIG_DIR, "usage.jsonl")     # one line per answered request
BACKENDS = ("agent", "direct")   # agent: read-only research agent (chat_agent.py); direct: this module
AUTH_MODES = ("api_key", "subscription")   # subscription = the `claude login` account; agent backend only
KEYS_DIR = os.path.join(CONFIG_DIR, "keys")   # one file per named key, mode 0600
LEGACY_KEY = "default"                        # the original ~/.config/kb-distillery/anthropic_key
ENV_KEY = "env"                               # ANTHROPIC_API_KEY of the dashboard process
KEY_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
DEFAULT_SETTINGS = {"key_name": "", "monthly_credit": 100.0, "reset_day": 30, "backend": "agent",
                    "auth_mode": "api_key", "active_key": ""}
DEFAULT_MODEL = "claude-sonnet-5-5"
MAX_TOKENS = 4096

TOP_K = 6                 # pages retrieved per turn
PAGE_CHARS = 14000        # cap per page body
TURN_CHARS = 60000        # cap on new page text added per turn
STOPWORDS = set("""
a an and are as at be but by can could did do does doing for from had has have how i if in into
is it its me my no not of on or our please should so tell than that the their them then there
these they this to was we were what when where which who why will with would you your about
know explain show give between vs versus
notes note my according sentence sentences two three short brief briefly words teach me tell
""".split())
SCOPE_PAGE_CAP = 300      # pages listed in a scoped system prompt
SCOPE_SUMMARY_CHARS = 100
SCOPE_UNCOVERED_CAP = 100  # undigested files listed in a scoped system prompt
PHRASE_BONUS = 15         # every word of the slug appears in the question ("tensor rank" → tensor-rank)

FIXED_SUFFIX = """\
---
How this chat works (always applies):
- Each user turn may start with <kb-pages>: wiki pages from the user's knowledge base,
  retrieved for that turn. Pages from earlier turns stay in the conversation.
- Cite a page as a markdown link `[Title](slug.md)` using its exact slug, whenever you draw on it.
- If the pages do not cover something, say so plainly before adding anything from general knowledge,
  and mark that part as not from the KB.
- Write math in LaTeX with $…$ and $$…$$."""


# ── API key ────────────────────────────────────────────────────────────────

def _read_file_key(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def read_key(name, keys_dir=None):
    """The key stored under `name`: "env" (ANTHROPIC_API_KEY), "default" (the legacy key file) or a
    file in ~/.config/kb-distillery/keys/. None when missing."""
    if name == ENV_KEY:
        return os.environ.get("ANTHROPIC_API_KEY", "").strip() or None
    if name == LEGACY_KEY:
        return _read_file_key(KEY_FILE)
    if not KEY_NAME_RE.match(name or ""):
        return None
    return _read_file_key(os.path.join(keys_dir or KEYS_DIR, name))


def list_keys(keys_dir=None):
    """Every key the dashboard can switch to: [{name, origin, hint}] — env first, legacy file, then
    the named files, sorted."""
    out = []
    env = read_key(ENV_KEY)
    if env:
        out.append({"name": ENV_KEY, "origin": "env", "hint": key_hint(env)})
    legacy = read_key(LEGACY_KEY)
    if legacy:
        out.append({"name": LEGACY_KEY, "origin": "file", "hint": key_hint(legacy)})
    d = keys_dir or KEYS_DIR
    names = sorted(n for n in os.listdir(d)) if os.path.isdir(d) else []
    for n in names:
        if KEY_NAME_RE.match(n) and n not in (ENV_KEY, LEGACY_KEY):
            k = _read_file_key(os.path.join(d, n))
            if k:
                out.append({"name": n, "origin": "file", "hint": key_hint(k)})
    return out


def add_key(name, key, keys_dir=None):
    """Store a key under a kebab name (0600). Returns the key list entry. Raises ValueError."""
    name = (name or "").strip().lower()
    key = (key or "").strip()
    if not KEY_NAME_RE.match(name) or name in (ENV_KEY, LEGACY_KEY):
        raise ValueError("key name: lowercase letters, digits and dashes (not `env` or `default`)")
    if not key.startswith("sk-ant-") or len(key) < 20 or any(c.isspace() for c in key):
        raise ValueError("that does not look like an Anthropic API key (sk-ant-…)")
    d = keys_dir or KEYS_DIR
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(key + "\n")
    return {"name": name, "origin": "file", "hint": key_hint(key)}


def remove_key(name, keys_dir=None):
    """Delete a stored key file ("env" cannot be removed; "default" removes the legacy file)."""
    if name == ENV_KEY:
        raise ValueError("the env key comes from the dashboard's environment; unset ANTHROPIC_API_KEY instead")
    if name == LEGACY_KEY:
        path = KEY_FILE
    elif KEY_NAME_RE.match(name or ""):
        path = os.path.join(keys_dir or KEYS_DIR, name)
    else:
        raise ValueError("unknown key")
    try:
        os.remove(path)
    except FileNotFoundError:
        raise ValueError("no such key") from None


def load_api_key(settings=None, keys_dir=None):
    """(key, origin) for the API-key mode. The `active_key` setting wins when it names a readable
    key; otherwise env, then the legacy key file. (None, None) when nothing is set."""
    settings = settings or load_settings()
    active = settings.get("active_key") or ""
    if active:
        key = read_key(active, keys_dir)
        if key:
            return key, active
    for name in (ENV_KEY, LEGACY_KEY):
        key = read_key(name)
        if key:
            return key, name
    return None, None


def key_hint(key):
    """What the console shows for a key: its last four characters."""
    return f"sk-ant-…{key[-4:]}" if key and len(key) > 8 else ""


def status():
    settings = load_settings()
    key, origin = load_api_key(settings)
    from kb_distillery.services import chat_agent  # here, not at the top: chat_agent imports this module
    return {"key": bool(origin), "key_origin": origin, "key_file": KEY_FILE,
            "key_hint": key_hint(key), "key_name": settings["key_name"], "reset_day": settings["reset_day"],
            "backend": settings["backend"], "agent": chat_agent.sdk_info(),
            "auth": {"mode": settings["auth_mode"], "active_key": origin or "", "keys": list_keys(),
                     "keys_dir": KEYS_DIR, "subscription": chat_agent.subscription_status()},
            "models": MODELS, "default_model": DEFAULT_MODEL, "spend": spend_summary(settings=settings)}


# ── Spend tracking (local estimate) ──────────────────────────────────────
# The API exposes no credit balance to a regular key, so the dashboard keeps its own ledger
# outside the repo and prices each request from its usage block.

_LEDGER_LOCK = threading.Lock()


def load_settings(path=None):
    s = dict(DEFAULT_SETTINGS)
    try:
        with open(path or SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            s.update({k: data[k] for k in DEFAULT_SETTINGS if k in data})
    except (OSError, ValueError):
        pass
    return s


def save_settings(payload, path=None):
    """Validate and store {key_name, monthly_credit, reset_day}. Returns the saved settings."""
    s = load_settings(path)
    if "key_name" in payload:
        s["key_name"] = re.sub(r"\s+", " ", str(payload["key_name"] or "")).strip()[:80]
    if "monthly_credit" in payload:
        credit = float(payload["monthly_credit"])
        if not 0 <= credit <= 100000:
            raise ValueError("monthly credit must be between 0 and 100000")
        s["monthly_credit"] = round(credit, 2)
    if "reset_day" in payload:
        day = int(payload["reset_day"])
        if not 1 <= day <= 31:
            raise ValueError("reset day must be 1–31")
        s["reset_day"] = day
    if "backend" in payload:
        backend = str(payload["backend"] or "")
        if backend not in BACKENDS:
            raise ValueError(f"backend must be one of {', '.join(BACKENDS)}")
        s["backend"] = backend
    if "auth_mode" in payload:
        mode = str(payload["auth_mode"] or "")
        if mode not in AUTH_MODES:
            raise ValueError(f"auth_mode must be one of {', '.join(AUTH_MODES)}")
        s["auth_mode"] = mode
    if "active_key" in payload:
        name = str(payload["active_key"] or "").strip()
        if name and not (name in (ENV_KEY, LEGACY_KEY) or KEY_NAME_RE.match(name)):
            raise ValueError("unknown key name")
        s["active_key"] = name
    path = path or SETTINGS_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)
    return s


def cost_usd(model, usage):
    """Dollar cost of one request from its usage block (output includes thinking tokens)."""
    p = PRICES.get(model)
    if not p or not usage:
        return 0.0
    split = usage.get("cache_creation") or {}
    w1h = split.get("ephemeral_1h_input_tokens") or 0
    w5m = (usage.get("cache_creation_input_tokens") or 0) - w1h
    total = ((usage.get("input_tokens") or 0) * p["in"]
             + w5m * p["in"] * CACHE_WRITE_5M + w1h * p["in"] * CACHE_WRITE_1H
             + (usage.get("cache_read_input_tokens") or 0) * p["cache_read"]
             + (usage.get("output_tokens") or 0) * p["out"])
    return total / 1_000_000


def _cycle_bounds(today, reset_day):
    """(start, next_reset) of the credit cycle containing `today`; day clamps to month length."""
    def on(year, month):
        last = calendar.monthrange(year, month)[1]
        return datetime.date(year, month, min(reset_day, last))
    this = on(today.year, today.month)
    if today >= this:
        start = this
        ny, nm = (today.year + (today.month == 12), today.month % 12 + 1)
        return start, on(ny, nm)
    py, pm = (today.year - (today.month == 1), (today.month - 2) % 12 + 1)
    return on(py, pm), this


def record_usage(model, usage, ledger=None, now=None, cost=None, billing="api"):
    """Append one request to the ledger and return its cost. Never raises on a full disk etc.
    `cost` overrides the price-table estimate (the Agent SDK reports the exact total_cost_usd).
    `billing="subscription"` turns cost nothing against the credit; the estimate is kept as
    `est_cost_usd` for information."""
    est = float(cost) if cost is not None else cost_usd(model, usage)
    cost = 0.0 if billing == "subscription" else est
    now = now or datetime.datetime.now()
    row = {"ts": now.isoformat(timespec="seconds"), "model": model, "cost_usd": round(cost, 6),
           "billing": billing, "est_cost_usd": round(est, 6),
           **{k: usage.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens",
                                             "cache_read_input_tokens", "output_tokens")}}
    path = ledger or LEDGER_FILE
    try:
        with _LEDGER_LOCK:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
    except OSError:
        pass
    return cost


def spend_summary(ledger=None, settings=None, today=None):
    """Spent this credit cycle (from the ledger), the monthly credit, and the estimated remainder."""
    settings = settings or load_settings()
    today = today or datetime.date.today()
    start, nxt = _cycle_bounds(today, settings["reset_day"])
    spent, turns, sub_turns = 0.0, 0, 0
    try:
        with open(ledger or LEDGER_FILE, encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                    day = datetime.date.fromisoformat(row["ts"][:10])
                except (ValueError, KeyError):
                    continue
                if start <= day < nxt:
                    if row.get("billing") == "subscription":
                        sub_turns += 1    # covered by the plan, not the credit
                        continue
                    spent += float(row.get("cost_usd") or 0)
                    turns += 1
    except OSError:
        pass
    credit = float(settings["monthly_credit"])
    return {"spent": round(spent, 4), "credit": credit, "left": round(credit - spent, 4),
            "turns": turns, "subscription_turns": sub_turns,
            "cycle_start": start.isoformat(), "next_reset": nxt.isoformat()}


# ── Prompt templates ───────────────────────────────────────────────────────

def _split_fm(text):
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm = {}
    for line in text[3:end].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm, text[end + 4:].lstrip("\n")


def kit_prompt_dirs(kb=None):
    """`kits/<kit>/prompts` for each kit in the active kb's chain, root first: a kit words the engine's generic
    prompts for its own field (the research kit speaks to a researcher)."""
    from kb_distillery.config import kb as kbconfig, kit
    cfg = kb if kb is not None else kbconfig.current()
    if not cfg or not cfg.kit:
        return []
    try:
        names = kit.chain(cfg.kit)
    except kit.KitError:
        return []
    return [d for d in (os.path.join(kit.kits_dir(), n, "prompts") for n in names) if os.path.isdir(d)]


def list_prompts(prompts_dir=PROMPTS_DIR, extra_dirs=None):
    """Templates from src/kb_distillery/llm/prompts/*.md, then the kit's `prompts/` (same file name = the kit's
    wording wins), `query` first."""
    found = {}
    for d in [prompts_dir, *(kit_prompt_dirs() if extra_dirs is None else extra_dirs)]:
        for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
            if not name.endswith(".md"):
                continue
            with open(os.path.join(d, name), encoding="utf-8") as f:
                fm, body = _split_fm(f.read())
            tid = name[:-3]
            found[tid] = {"id": tid, "title": fm.get("title", tid), "description": fm.get("description", ""),
                          "order": int(fm.get("order", 99)), "text": body.strip()}
    return sorted(found.values(), key=lambda p: (p["order"], p["id"]))


def scope_section(ctx, index=None, agent=False):
    """The "Scope" block of a scoped chat's system prompt (both backends): what the scope is, the
    only pages that may be used, the undigested sources, and the closing line every answer needs."""
    index = index if index is not None else query.parse_index()
    slugs = sorted(ctx["pages"])
    lines = ["## Scope: " + ctx["title"] + " (" + ctx["slug"] + ")", "",
             "This question is asked INSIDE this scope, a personal working set of raw sources. Answer only "
             "from the scope's knowledge pages listed below and cite only those pages as `[Title](slug.md)`. A page "
             "outside the list does not exist for this answer; if the scope does not cover something, say "
             "so plainly rather than reaching for other pages or general knowledge.",
             scope_coverage(ctx), ""]
    if agent:
        lines += ["Tools: add `--scope " + ctx["slug"] + "` to `python3 -m kb_distillery.search.query candidates` and to "
                  "`python3 -m kb_distillery.search.explore_raw find`; `python3 -m kb_distillery.search.query scope-status " + ctx["slug"] +
                  "` repeats this block. Read only the pages below.", ""]
    lines.append("Pages in this scope (" + str(len(slugs)) + (", first " + str(SCOPE_PAGE_CAP) + " shown"
                 if len(slugs) > SCOPE_PAGE_CAP else "") + "):")
    for s in slugs[:SCOPE_PAGE_CAP]:
        summ = (index.get(s, {}).get("summary") or "")[:SCOPE_SUMMARY_CHARS]
        lines.append("- " + links.page_link(s, {s: links.read_title(query.WIKI, s)}) + (" — " + summ if summ else ""))
    unc = [u["path"] for u in ctx["uncovered"]]
    shown = unc[:SCOPE_UNCOVERED_CAP]
    more = (" … and " + str(len(unc) - len(shown)) + " more") if len(unc) > len(shown) else ""
    lines += ["", "Undigested sources in this scope (" + str(len(unc)) + "): " +
              (", ".join(shown) + more if unc else "none"), "",
              "End every answer with: Not yet digested in this scope: <list of uncovered files>"
              + (" (here: " + (", ".join(shown) + more) + ")" if unc else " (here: none)") + "."]
    return "\n".join(lines)


def scope_coverage(ctx):
    n_cov, n_unc = len(ctx["covered"]), len(ctx["uncovered"])
    total = n_cov + n_unc
    if not total:
        return "Coverage: no digestible files yet."
    return "Coverage: " + str(n_cov) + "/" + str(total) + " files digested, " + str(n_unc) + " not yet."


def build_system(system_text, scope=None):
    """User-editable instructions + the KB map + the fixed suffix nobody can remove
    (+ the Scope block when the question is asked inside a scope)."""
    index = query.parse_index()
    themes = [f"- {links.link(s, m.get('title') or s)} — {m['summary']}" for s, m in sorted(index.items()) if s.startswith("theme-")]
    kb_map = "Research themes in this KB:\n" + "\n".join(themes) if themes else ""
    parts = [(system_text or "").strip(), kb_map, FIXED_SUFFIX]
    if scope:
        parts.append(scope_section(scope, index))
    return "\n\n".join(p for p in parts if p)


# ── Retrieval ──────────────────────────────────────────────────────────────

def _qtokens(text):
    return [t for t in tokenize(text) if t not in STOPWORDS]


def retrieve(question, k=TOP_K, index=None, allowed=None):
    """Top-k wiki slugs for a question: [{slug, score, summary}], best first (0 LLM).
    `allowed` (a set of slugs, e.g. a scope's pages) restricts the candidates."""
    qtokens = _qtokens(question)
    if not qtokens:
        return []
    index = index if index is not None else query.parse_index()
    qset = set(qtokens)
    ranked = []
    for slug, meta in index.items():
        if slug in page_conventions.skip_slugs() or not os.path.isfile(query.wiki_path(slug)):
            continue
        if allowed is not None and slug not in allowed:
            continue
        score, _hits = query.score_slug(slug, meta, qtokens)
        words = [w for w in tokenize(slug.replace("-", " ")) if w not in STOPWORDS]
        if score > 0 and words and all(w in qset for w in words):
            score += PHRASE_BONUS
        if score > 0:
            ranked.append((score, slug, meta.get("summary", "")))
    ranked.sort(key=lambda r: (-r[0], r[1]))
    return [{"slug": s, "score": sc, "summary": sm} for sc, s, sm in ranked[:k]]


def pages_block(slugs):
    """<kb-pages> text for these slugs (deterministic, so replays hit the cache)."""
    chunks, used = [], 0
    for slug in slugs:
        body = query.read_body(slug).strip()
        if not body:
            continue
        if len(body) > PAGE_CHARS:
            body = body[:PAGE_CHARS] + "\n[…truncated]"
        if used + len(body) > TURN_CHARS:
            break
        used += len(body)
        chunks.append(f'<page slug="{slug}">\n{body}\n</page>')
    return "<kb-pages>\n" + "\n\n".join(chunks) + "\n</kb-pages>" if chunks else ""


def plan_turn(history, question, scope=None):
    """Retrieve for the new question. Returns (hits, new_slugs): hits for the rail, new_slugs the
    pages not already in context. A follow-up ("how does it relate to depth?") is searched together
    with the previous question, so its pronouns keep their topic."""
    prev = [m["content"] for m in history if m.get("role") == "user"]
    allowed = scope["pages"] if scope else None
    hits = retrieve(f"{prev[-1]} {question}", allowed=allowed) if prev else retrieve(question, allowed=allowed)
    if not hits and prev:
        hits = retrieve(question, allowed=allowed)
    seen = {s for m in history for s in (m.get("sources") or [])}
    for h in hits:
        h["in_context"] = h["slug"] in seen
    return hits, [h["slug"] for h in hits if not h["in_context"]]


def build_messages(history, question, new_slugs):
    """API messages: past turns replayed with the pages they introduced, then the new turn.
    The last block gets the cache breakpoint so the next turn reads the whole prefix."""
    msgs = []
    for m in history:
        if m.get("role") == "user":
            block = pages_block(m.get("sources") or [])
            text = f"{block}\n\n{m['content']}" if block else m["content"]
            msgs.append({"role": "user", "content": [{"type": "text", "text": text}]})
        elif m.get("role") == "assistant" and m.get("content"):
            msgs.append({"role": "assistant", "content": [{"type": "text", "text": m["content"]}]})
    block = pages_block(new_slugs)
    text = f"{block}\n\n{question}" if block else question
    msgs.append({"role": "user", "content": [{"type": "text", "text": text,
                                              "cache_control": {"type": "ephemeral"}}]})
    return msgs


# ── Claude streaming ──────────────────────────────────────────────────────

class ChatError(Exception):
    pass


_SSL_CTX = None
MAC_KEYCHAINS = ["/Library/Keychains/System.keychain",
                 "/System/Library/Keychains/SystemRootCertificates.keychain"]


def keychain_pem():
    """The macOS system keychain roots as PEM text (what curl trusts); "" elsewhere or on failure."""
    if sys.platform != "darwin":
        return ""
    import subprocess
    try:
        return subprocess.run(["security", "find-certificate", "-a", "-p", *MAC_KEYCHAINS],
                              capture_output=True, text=True, timeout=10).stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


def ssl_context():
    """Verifying TLS context that also trusts the macOS system keychain roots — what curl trusts.
    Behind a TLS-inspecting proxy (corporate laptop) Python's own CA bundle lacks the proxy root.
    SSL_CERT_FILE, when set, is honoured by the default context as usual."""
    global _SSL_CTX
    if _SSL_CTX is None:
        import ssl
        ctx = ssl.create_default_context()
        pem = keychain_pem()
        if pem:
            try:
                ctx.load_verify_locations(cadata=pem)
                # Python 3.13 turns on RFC 5280 strict mode, which rejects common proxy certs
                # ("Missing Authority Key Identifier"). Chain + hostname checks stay on.
                ctx.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0)
            except ssl.SSLError:
                pass
        _SSL_CTX = ctx
    return _SSL_CTX


def stream_claude(system, messages, model, key):
    """Yield ("text", str) chunks, then ("usage", dict). Raises ChatError with a readable message."""
    body = json.dumps({
        "model": model, "max_tokens": MAX_TOKENS, "stream": True,
        "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        "messages": messages,
    }).encode("utf-8")
    req = urllib.request.Request(API_URL, data=body, method="POST", headers={
        "x-api-key": key, "anthropic-version": API_VERSION, "content-type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=300, context=ssl_context())
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
        except Exception:
            detail = ""
        raise ChatError(f"API {e.code}: {detail or e.reason}") from None
    except urllib.error.URLError as e:
        raise ChatError(f"cannot reach the API: {e.reason}") from None

    usage = {}
    with resp:
        for raw in resp:
            line = raw.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            try:
                ev = json.loads(line[5:].strip())
            except ValueError:
                continue
            kind = ev.get("type")
            if kind == "message_start":
                usage.update(ev.get("message", {}).get("usage", {}))
            elif kind == "content_block_delta" and ev.get("delta", {}).get("type") == "text_delta":
                yield "text", ev["delta"]["text"]
            elif kind == "message_delta":
                usage.update(ev.get("usage", {}))
                if ev.get("delta", {}).get("stop_reason") == "max_tokens":
                    yield "text", "\n\n*[answer cut at the token limit]*"
            elif kind == "error":
                raise ChatError(ev.get("error", {}).get("message", "stream error"))
    yield "usage", usage


# ── Save to inbox ──────────────────────────────────────────────────────────

def _kebab(text, fallback="kb-chat"):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:60].rstrip("-") or fallback


def _one_line(text):
    return re.sub(r"\s+", " ", (text or "").replace("#", "")).strip()


def render_chat(chat, today=None):
    """Clip-format markdown the catalog routes to raw/llm-chats/ and chat.py parses into turns."""
    today = today or datetime.date.today().isoformat()
    turns = [m for m in chat.get("messages", []) if m.get("role") in ("user", "assistant")
             and (m.get("content") or "").strip()]
    retrieved = []
    for m in turns:
        for s in m.get("sources") or []:
            if s not in retrieved:
                retrieved.append(s)
    custom = bool(chat.get("custom"))
    fm = [
        "---",
        f"title: {_one_line(chat.get('title')) or 'KB chat'}",
        f"source: {_one_line(chat.get('id')) or 'kb-chat'}",
        f"clipped: {today}",
        f"model: {_one_line(chat.get('model')) or DEFAULT_MODEL}",
        f"prompt_template: {_one_line(chat.get('template')) or 'query'}",
        f"system_prompt: {'custom' if custom else 'template'}",
        f"retrieved: [{', '.join(retrieved)}]",
        "---",
        "",
    ]
    out = list(fm)
    if custom and (chat.get("system") or "").strip():
        out.append("System prompt used (edited):")
        out.append("")
        out.extend("> " + line if line else ">" for line in chat["system"].strip().splitlines())
        out.append("")
    for i, m in enumerate(turns):
        if i:
            out += ["---", ""]
        out += ["**You**" if m["role"] == "user" else "**Claude**", "", m["content"].strip(), ""]
    return "\n".join(out).rstrip() + "\n"


def save_chat(chat, inbox=INBOX, today=None):
    """Write raw/inbox/<kebab-title>.md (never overwrites another file). Returns the repo path."""
    if not any((m.get("content") or "").strip() for m in chat.get("messages", [])
               if m.get("role") == "assistant"):
        raise ValueError("nothing to save yet — ask something first")
    os.makedirs(inbox, exist_ok=True)
    stem = _kebab(chat.get("title"))
    path = os.path.join(inbox, f"{stem}.md")
    n = 2
    while os.path.exists(path):
        path = os.path.join(inbox, f"{stem}-{n}.md")
        n += 1
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_chat(chat, today))
    return os.path.relpath(path, ROOT)
