"""Chat with the KB, agent backend: a read-only research agent over the Claude Agent SDK.

Instead of pasting six guessed pages into one Messages call (chat_data.stream_claude), the agent
runs the `query-knowledge` workflow itself inside the real Claude Code harness: `backend/src/kb/search/query.py
candidates`, Grep, Read `wiki/<slug>.md`, then an answer that cites `[[slug]]`. It bills the same
Console API key (ANTHROPIC_API_KEY or ~/.config/thesis-kb/anthropic_key).

The agent is READ-ONLY. `tool_policy` is the single source of truth and is enforced twice: as a
PreToolUse hook (runs first, a deny wins in every permission mode) and as the `can_use_tool`
callback. `setting_sources=[]` keeps the subprocess away from this repo's CLAUDE.md and hooks —
this module is the guard.

SSE event contract shared with static/chat.js (names → JSON data):

    session  {"id": str}                      first thing, and again after the result (resume key)
    tool     {"name", "summary", "id", "error"?}   one per tool call ("read tensor-rank", "grep …")
    sources  {"hits": [{slug, score, summary, in_context}], "new": [slug]}   pages read so far
    delta    str                              streamed answer text
    notice   {"text": str}                    e.g. the previous session expired, started fresh
    usage    {input_tokens, …, model, cost_usd, num_turns, duration_ms, spend}
    error    {"error": str}
    done     {}
    ping     None                             heartbeat; serve.py writes an SSE comment

`claude_agent_sdk` is imported lazily so the dashboard and the tests load without it.
"""
import asyncio
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field

from kb.paths import vault_root
META_DIR = os.path.join(vault_root(), "meta")
ROOT = vault_root()

from kb.search import query
from kb.services import chat as chat_data

WIKI = os.path.join(ROOT, "wiki")
RAW = os.path.join(ROOT, "raw")
from kb.paths import THINK_PATH as THINK      # the shared think space, outside the vault
INDEX = os.path.join(ROOT, "index.md")
READ_ROOTS = (WIKI, RAW, THINK)
RAW_TEXT_EXT = {".md", ".txt", ".html", ".eml", ".json", ".tsv", ".csv"}

CA_PEM = os.path.join(chat_data.CONFIG_DIR, "ca-roots.pem")
CA_MAX_AGE = 24 * 3600

MAX_TURNS = 30
TOOLS = ["Read", "Grep", "Glob", "Bash"]
DISALLOWED_TOOLS = ["Write", "Edit", "MultiEdit", "NotebookEdit", "WebFetch", "WebSearch",
                    "Agent", "Task", "TodoWrite", "AskUserQuestion", "Skill", "KillShell"]

# Bash: exactly one simple command, python running one of these entry points.
BASH_SCRIPTS = {"backend/src/kb/search/query.py", "backend/src/kb/search/semfind.py", "backend/src/kb/search/explore_raw.py"}
BASH_MODULES = {("kb.ingest", "resolve")} | {
    ("kb.search.explore_raw", sub) for sub in ("find", "read", "check", "recommend")}
# query / semfind run as modules (any arguments); the scope rules below narrow them
BASH_ANY_MODULES = {"kb.search.query", "kb.search.semfind"}
BASH_FORBIDDEN_CHARS = set(";&|$`()<>{}\n\\")
PING_SECONDS = 2.0
JOIN_SECONDS = 5.0
HISTORY_TURNS = 6
HISTORY_CHARS = 800

AGENT_WORKFLOW = """\
How to research a question in this knowledge base (always applies):
- You are a read-only research agent inside the user's thesis wiki (the current directory).
  `wiki/` holds flat markdown notes, one per slug; `index.md` lists every page with its one-line
  summary; `raw/` holds the sources; `think/` is the user's own notebook.
- Locate first, with no guessing: run `python3 -m kb.search.query candidates "<keywords>"` (and
  `python3 -m kb.search.query mocs` for broad questions), look at the matching section of `index.md`,
  then Grep `wiki/` for the exact terms. Never say the vault has nothing on a topic before both the
  index and candidates were checked.
- Read 3–8 pages with Read on `wiki/<slug>.md`. Prefer `theme-*` and `q-*` pages for thesis-level
  questions and `paper-`, `part-`, `lecture-`, `article-`, `mail-`, `chat-` pages for citations.
  Follow `related:` and `[[links]]` when they matter. An unknown slug may be an alias:
  `python3 -m kb.ingest resolve <slug>`.
- Prefer the wiki over your own knowledge. Cite a page as [[slug]] with its exact slug whenever you
  draw on it. Note gaps: `to-read` papers, queued raw files, open `q-*` questions.
- If the wiki does not cover something, say so plainly before adding anything from general
  knowledge, and mark that part as not from the KB.
- Raw through one door: the wiki is what you read. To look at a source (an undigested file, a
  contradiction between pages, an explicit request) run
  `python3 -m kb.search.explore_raw find|read|check|recommend …` — never Read a PDF. Attribute every
  sentence drawn from a source with its raw path and the reason you opened it; when the file is
  undigested say so and give a tier recommendation (skip, easy, full or deep).
- Write math in LaTeX with $…$ and $$…$$. Answer in the chat; do not create or edit files, do not
  run git, and do not try other tools — only Read, Grep, Glob and the python commands above."""


# ── Environment ────────────────────────────────────────────────────────────

def sdk_info():
    """{available, version, cli, error} — whether the agent backend can run at all."""
    info = {"available": False, "version": None, "cli": shutil.which("claude"), "error": None}
    try:
        import claude_agent_sdk  # noqa: F401
    except ImportError as e:
        info["error"] = f"claude-agent-sdk not installed ({e}); run `pixi install`"
        return info
    info["available"] = True
    info["version"] = getattr(claude_agent_sdk, "__version__", None)
    return info


def ca_bundle_path(path=CA_PEM, now=None):
    """PEM file with the macOS keychain roots for the Node CLI (NODE_EXTRA_CA_CERTS). The TLS
    proxy fix of chat_data.ssl_context(), replayed for the subprocess. None when not needed."""
    preset = os.environ.get("NODE_EXTRA_CA_CERTS")
    if preset:
        return preset
    if sys.platform != "darwin":
        return None
    now = now or time.time()
    try:
        if os.path.isfile(path) and now - os.path.getmtime(path) < CA_MAX_AGE:
            return path
    except OSError:
        pass
    pem = chat_data.keychain_pem()
    if not pem:
        return None
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(pem)
    except OSError:
        return None
    return path


def cli_path():
    """The Claude Code binary: the one bundled with the SDK, else `claude` on PATH, else None."""
    try:
        import claude_agent_sdk
        pkg = getattr(claude_agent_sdk, "__file__", None)
        if pkg:
            p = os.path.join(os.path.dirname(pkg), "_bundled", "claude")
            if os.access(p, os.X_OK):
                return p
    except ImportError:
        pass
    return shutil.which("claude")


_SUB_CACHE = {"at": 0.0, "value": None}
SUB_CACHE_SECONDS = 60


def subscription_status(now=None, cli=None, timeout=8):
    """Whether the `claude login` account can serve the agent: {logged_in, email, plan, error}.
    Runs `claude auth status` with the API key variable blanked, cached for a minute."""
    now = now or time.time()
    if _SUB_CACHE["value"] is not None and now - _SUB_CACHE["at"] < SUB_CACHE_SECONDS:
        return _SUB_CACHE["value"]
    cli = cli or cli_path()
    out = {"logged_in": False, "email": None, "plan": None, "error": None}
    if not cli:
        out["error"] = "claude CLI not found"
    else:
        env = {**os.environ, "ANTHROPIC_API_KEY": "", "CLAUDECODE": ""}
        try:
            r = subprocess.run([cli, "auth", "status"], capture_output=True, text=True,
                               timeout=timeout, env=env)
            data = json.loads(r.stdout or "{}")
            out["logged_in"] = bool(data.get("loggedIn")) and data.get("authMethod") == "claude.ai"
            out["email"] = data.get("email")
            out["plan"] = data.get("subscriptionType")
            if not out["logged_in"]:
                out["error"] = "not logged in — run `claude login` in a terminal"
        except (OSError, subprocess.SubprocessError, ValueError) as e:
            out["error"] = f"auth status failed: {e}"
    _SUB_CACHE.update(at=now, value=out)
    return out


def agent_env(key, ca_path=None):
    """Extra environment for the claude subprocess (merged over os.environ by the SDK).
    `key=None` means subscription mode: the API key variable is blanked so the CLI falls back
    to the `claude login` credentials (a blank value counts as unset)."""
    env = {"ANTHROPIC_API_KEY": key or "", "CLAUDE_CODE_ENTRYPOINT": "sdk-py",
           # a dashboard started from a Claude Code terminal inherits CLAUDECODE, which makes the
           # CLI refuse to start a nested session
           "CLAUDECODE": "",
           # a shell that routes Claude through a corporate gateway exports these; the dashboard's
           # key belongs to the public API, so pin it there (the token would win over the key)
           "ANTHROPIC_BASE_URL": "https://api.anthropic.com", "ANTHROPIC_AUTH_TOKEN": ""}
    ca = ca_path if ca_path is not None else ca_bundle_path()
    if ca:
        env["NODE_EXTRA_CA_CERTS"] = ca
    return env


def build_agent_system(system_text, scope=None):
    """User-editable template + KB theme map + the research workflow nobody can remove
    (+ the Scope block when `scope` — a scopes.scope_context dict — is set)."""
    index = query.parse_index()
    themes = [f"- [[{s}]] — {m['summary']}" for s, m in sorted(index.items()) if s.startswith("theme-")]
    kb_map = "Research themes in this KB:\n" + "\n".join(themes) if themes else ""
    parts = [(system_text or "").strip(), kb_map, AGENT_WORKFLOW]
    if scope:
        parts.append(chat_data.scope_section(scope, index, agent=True))
    return "\n\n".join(p for p in parts if p)


# ── Tool policy ────────────────────────────────────────────────────────────

@dataclass
class Decision:
    allow: bool
    reason: str = ""
    updated_input: dict = None


def _under(path, root):
    root = os.path.realpath(root)
    return path == root or path.startswith(root + os.sep)


def _real(p):
    if not isinstance(p, str) or not p:
        return None
    if not os.path.isabs(p):
        q = p.replace("\\", "/")
        # `think/<note>`: the shared think space beside the vault, not a folder of it (kb.paths.THINK_PATH)
        p = os.path.join(THINK, q[len("think/"):]) if q == "think" or q.startswith("think/") else os.path.join(ROOT, p)
    return os.path.realpath(p)


READ_DENY = "read-only KB agent: only wiki/, index.md, think/ and text files under raw/ can be read"
BASH_DENY = ("read-only KB agent: only `python3 -m kb.search.query candidates|mocs …`, "
             "`python3 -m kb.search.semfind …`, `python3 -m kb.search.explore_raw …` / "
             "`python3 -m kb.search.explore_raw find|read|check|recommend …` and "
             "`python3 -m kb.ingest resolve …` may run")


def _readable_in_scope(real, scope, allow_dirs=False):
    """_readable, narrowed to a scope: index.md, the scope's pages, its own raw text files; no think/."""
    if real is None:
        return False
    if real == os.path.realpath(INDEX):
        return True
    if allow_dirs and os.path.isdir(real):
        return _under(real, WIKI) or _under(real, RAW)
    if _under(real, WIKI):
        wiki = os.path.realpath(WIKI)
        return (os.path.dirname(real) == wiki and real.endswith(".md")
                and os.path.basename(real)[:-3] in scope["pages"])
    if _under(real, RAW):
        rel = os.path.relpath(real, ROOT)
        return os.path.splitext(real)[1].lower() in RAW_TEXT_EXT and rel in set(scope.get("rows") or ())
    return False


def _readable(real, allow_dirs=False):
    if real is None:
        return False
    if real == os.path.realpath(INDEX):
        return True
    if allow_dirs and os.path.isdir(real) and any(_under(real, r) for r in READ_ROOTS):
        return True
    if _under(real, WIKI) or _under(real, THINK):
        return True
    if _under(real, RAW):
        return os.path.splitext(real)[1].lower() in RAW_TEXT_EXT
    return False


# Citation graph (backend/src/kb/search/citations.py): the read-only subcommands only, never `fetch` (network writes).
CITATION_SUBS = ("neighbors", "rank", "missing", "path", "status")
BASH_MODULES = BASH_MODULES | {("kb.search.citations", sub) for sub in CITATION_SUBS}
BASH_DENY = BASH_DENY + "; also `python3 -m kb.search.citations neighbors|rank|missing|path|status …`"


SCOPE_READ_DENY = ("scoped chat: only the scope's pages (wiki/<slug>.md listed in the system prompt), "
                   "index.md and the scope's own text files under raw/ can be read; think/ is closed")
SCOPE_BASH_DENY = ("scoped chat: `candidates` and `find` need --scope <this scope>, `explore_raw read|check|"
                   "recommend` only take this scope's files, and `mocs` / `semfind` are not available")


def _scope_flag(toks):
    """The value of --scope in a token list (either `--scope X` or `--scope=X`), else None."""
    for i, t in enumerate(toks):
        if t == "--scope" and i + 1 < len(toks):
            return toks[i + 1]
        if t.startswith("--scope="):
            return t[len("--scope="):]
    return None


def _scope_bash_ok(toks, scope):
    """Extra rules for Bash inside a scope (the command already passed the unscoped allow-list)."""
    slug = scope["slug"]
    if toks[1] == "-m":
        mod, sub, rest = toks[2], toks[3], toks[4:]
    else:
        mod, sub, rest = os.path.normpath(toks[1]), (toks[2] if len(toks) > 2 else ""), toks[3:]
        if os.path.isabs(mod):
            mod = os.path.relpath(os.path.realpath(mod), ROOT)
    if mod in ("kb.search.semfind", "backend/src/kb/search/semfind.py"):
        return False
    if mod in ("kb.search.query", "backend/src/kb/search/query.py"):
        if sub == "scope-status":
            return bool(rest) and rest[0] == slug
        return sub == "candidates" and _scope_flag(rest) == slug
    if mod in ("kb.search.explore_raw", "backend/src/kb/search/explore_raw.py"):
        if sub == "find":
            return _scope_flag(rest) == slug
        first = next((t for t in rest if not t.startswith("-")), None)
        return first in set(scope.get("rows") or ())
    if mod in ("kb.search.citations", "backend/src/kb/search/citations.py") and sub == "missing":
        return _scope_flag(rest) == slug
    return True


def _bash_allowed(command, scope=None):
    ok = _bash_allowed_unscoped(command)
    if not ok or scope is None:
        return ok
    import shlex
    return _scope_bash_ok(shlex.split(command), scope)


def _bash_allowed_unscoped(command):
    if not isinstance(command, str) or not command.strip():
        return False
    if set(command) & BASH_FORBIDDEN_CHARS:
        return False
    import shlex
    try:
        toks = shlex.split(command)
    except ValueError:
        return False
    if len(toks) < 2 or not re.fullmatch(r"(.*/)?python(3(\.\d+)?)?", toks[0]):
        return False
    if toks[1] == "-m":
        if len(toks) >= 3 and toks[2] in BASH_ANY_MODULES:
            return True
        return len(toks) >= 4 and (toks[2], toks[3]) in BASH_MODULES
    script = toks[1]
    if os.path.isabs(script):
        script = os.path.relpath(os.path.realpath(script), ROOT)
    if os.path.normpath(script) == "backend/src/kb/search/citations.py":   # read-only subcommands only (never fetch)
        return len(toks) >= 3 and ("kb.search.citations", toks[2]) in BASH_MODULES
    return os.path.normpath(script) in BASH_SCRIPTS


def tool_policy(tool_name, tool_input, scope=None):
    """The whole read-only policy, pure and testable. Returns a Decision.
    `scope` (a scopes.scope_context dict) narrows it to one scope's pages and files; None = unchanged."""
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    if scope is not None:
        readable = lambda real, allow_dirs=False: _readable_in_scope(real, scope, allow_dirs)  # noqa: E731
        read_deny, bash_deny = SCOPE_READ_DENY, BASH_DENY + "; " + SCOPE_BASH_DENY
    else:
        readable, read_deny, bash_deny = _readable, READ_DENY, BASH_DENY
    if tool_name == "Read":
        return (Decision(True) if readable(_real(tool_input.get("file_path")))
                else Decision(False, read_deny))
    if tool_name in ("Grep", "Glob"):
        path = tool_input.get("path")
        if not path:
            return Decision(True, updated_input={**tool_input, "path": WIKI})
        real = _real(path)
        return (Decision(True) if readable(real, allow_dirs=True)
                else Decision(False, read_deny))
    if tool_name == "Bash":
        return (Decision(True) if _bash_allowed(tool_input.get("command"), scope)
                else Decision(False, bash_deny))
    return Decision(False, f"read-only KB agent: tool {tool_name} is not available")


def _decide(policy, name, inp, scope):
    return policy(name, inp) if scope is None else policy(name, inp, scope)


def make_hook(policy=tool_policy, scope=None):
    """PreToolUse hook: every call gets an explicit allow/deny (never an empty dict)."""
    async def hook(input_data, tool_use_id, context):
        d = _decide(policy, input_data.get("tool_name"), input_data.get("tool_input"), scope)
        out = {"hookEventName": "PreToolUse",
               "permissionDecision": "allow" if d.allow else "deny",
               "permissionDecisionReason": d.reason or ("read-only KB agent" if d.allow else "denied")}
        if d.allow and d.updated_input is not None:
            out["updatedInput"] = d.updated_input
        return {"hookSpecificOutput": out}
    return hook


def make_can_use_tool(policy=tool_policy, scope=None):
    """can_use_tool callback — second line behind the hook."""
    async def can_use_tool(tool_name, tool_input, context):
        from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny
        d = _decide(policy, tool_name, tool_input, scope)
        if d.allow:
            return PermissionResultAllow(updated_input=d.updated_input)
        return PermissionResultDeny(message=d.reason)
    return can_use_tool


def build_options(model, system, key, session_id=None, cli_path=None, ca_path=None, stderr=None, scope=None):
    from claude_agent_sdk import ClaudeAgentOptions, HookMatcher
    kw = dict(
        cwd=ROOT, model=model, system_prompt=system,
        # no allowed_tools: an allow-list auto-approves before can_use_tool runs; with the default
        # permission mode every call goes through the PreToolUse hook and then the callback
        tools=list(TOOLS), disallowed_tools=list(DISALLOWED_TOOLS),
        permission_mode="default", can_use_tool=make_can_use_tool(scope=scope),
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[make_hook(scope=scope)])]},
        setting_sources=[], max_turns=MAX_TURNS, include_partial_messages=True,
        env=agent_env(key, ca_path), resume=session_id or None,
    )
    if cli_path:
        kw["cli_path"] = cli_path
    if stderr:
        kw["stderr"] = stderr
    return ClaudeAgentOptions(**kw)


# ── Event mapping ──────────────────────────────────────────────────────────

def slug_from_read(tool_input):
    real = _real((tool_input or {}).get("file_path"))
    if real and _under(real, WIKI) and real.endswith(".md"):
        return os.path.basename(real)[:-3]
    return None


def tool_summary(name, tool_input):
    tool_input = tool_input or {}
    if name == "Read":
        slug = slug_from_read(tool_input)
        if slug:
            return f"read {slug}"
        p = tool_input.get("file_path") or ""
        return f"read {os.path.relpath(p, ROOT) if os.path.isabs(p) else p}"
    if name == "Grep":
        return f"grep {tool_input.get('pattern', '')}".strip()
    if name == "Glob":
        return f"glob {tool_input.get('pattern', '')}".strip()
    if name == "Bash":
        cmd = (tool_input.get("command") or "").strip()
        e = re.match(r"\S*python3?\s+(?:-m\s+kb\.search\.explore_raw|(?:\S*/)?backend/src/kb/search/explore_raw\.py)\s+(\w+)\s*(.*)", cmd)
        if e:
            verb, rest = e.group(1), e.group(2).strip()
            arg = os.path.basename(rest.split()[0].strip("\"'")) if verb != "find" and rest else rest
            text = f"explore {verb} {arg}".strip()
            return text[:60] + ("…" if len(text) > 60 else "")
        m = re.match(r"\S*python3?\s+(?:-m\s+kb\.ingest\s+|-m\s+kb\.search\.(?:query|semfind)\s+|(?:\S*/)?backend/src/kb/search/(?:query|semfind)\.py\s+)(.*)", cmd)
        text = m.group(1) if m else cmd
        return text[:60] + ("…" if len(text) > 60 else "")
    return name.lower()


def harvest_citations(text, index):
    out = []
    for slug in re.findall(r"\[\[([^\]|#]+)(?:\|[^\]]*)?\]\]", text or ""):
        slug = slug.strip()
        if slug in index and slug not in out:
            out.append(slug)
    return out


@dataclass
class TurnState:
    reads: dict = field(default_factory=dict)      # slug → times read, insertion ordered
    text: str = ""
    session_id: str = None
    tools: list = field(default_factory=list)
    index: dict = None

    def sources(self, extra=()):
        slugs = list(self.reads) + [s for s in extra if s not in self.reads]
        index = self.index if self.index is not None else {}
        hits = [{"slug": s, "score": self.reads.get(s, 0), "summary": index.get(s, {}).get("summary", ""),
                 "in_context": False} for s in slugs]
        return {"hits": hits, "new": slugs}


def _name(obj):
    return type(obj).__name__


def map_message(msg, state):
    """SDK message → list of (event, data). Dispatches on class names so tests can use fakes."""
    kind = _name(msg)
    out = []
    if kind == "SystemMessage":
        if getattr(msg, "subtype", None) == "init":
            sid = (getattr(msg, "data", None) or {}).get("session_id")
            if sid:
                state.session_id = sid
                out.append(("session", {"id": sid}))
        return out
    if kind == "StreamEvent":
        if getattr(msg, "parent_tool_use_id", None):
            return out
        ev = getattr(msg, "event", None) or {}
        if ev.get("type") == "content_block_delta" and (ev.get("delta") or {}).get("type") == "text_delta":
            text = ev["delta"].get("text", "")
            if text:
                state.text += text
                out.append(("delta", text))
        return out
    if kind == "AssistantMessage":
        for block in getattr(msg, "content", None) or []:
            b = _name(block)
            if b == "ToolUseBlock":
                name, inp = getattr(block, "name", ""), getattr(block, "input", None) or {}
                entry = {"name": name, "summary": tool_summary(name, inp), "id": getattr(block, "id", None)}
                state.tools.append(entry)
                out.append(("tool", entry))
                slug = slug_from_read(inp) if name == "Read" else None
                if slug:
                    state.reads[slug] = state.reads.get(slug, 0) + 1
                    out.append(("sources", state.sources()))
            elif b == "TextBlock" and state.text and not state.text.endswith("\n\n"):
                # a new text segment after tool use: keep paragraphs apart in the stream
                pass
        return out
    if kind == "UserMessage":
        for block in getattr(msg, "content", None) or []:
            if _name(block) == "ToolResultBlock" and getattr(block, "is_error", False):
                tid = getattr(block, "tool_use_id", None)
                match = next((t for t in reversed(state.tools) if t.get("id") == tid), None)
                if match:
                    match["error"] = True
                    out.append(("tool", match))
        return out
    if kind == "ResultMessage":
        if getattr(msg, "session_id", None):
            state.session_id = msg.session_id
        return out
    return out


# ── Streaming bridge ───────────────────────────────────────────────────────

class _Stopped(Exception):
    pass


def _history_prefix(history):
    turns = [m for m in (history or []) if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip()]
    turns = turns[-HISTORY_TURNS:]
    if not turns:
        return ""
    lines = []
    for m in turns:
        who = "User" if m["role"] == "user" else "Assistant"
        body = m["content"].strip()
        if len(body) > HISTORY_CHARS:
            body = body[:HISTORY_CHARS] + " […]"
        lines.append(f"{who}: {body}")
    return "Earlier in this conversation:\n" + "\n\n".join(lines) + "\n\nNew question: "


def _is_resume_failure(exc):
    text = str(exc).lower()
    return "no conversation found" in text or ("session" in text and ("not found" in text or "expired" in text))


async def _run(question, *, model, system, key, session_id, history, emit, stop_event, log, billing="api",
               scope=None):
    import claude_agent_sdk as sdk

    index = query.parse_index()
    cli_path = None
    tried_cli_fallback = False
    prompt = question
    resume = session_id or None
    stderr_lines = []

    def on_stderr(line):
        stderr_lines.append(line)
        if len(stderr_lines) > 50:
            del stderr_lines[0]
        log(f"  claude: {line.rstrip()}")

    while True:
        state = TurnState(index=index)
        options = build_options(model, system, key, session_id=resume, cli_path=cli_path, stderr=on_stderr,
                                scope=scope)
        result = None
        try:
            async with sdk.ClaudeSDKClient(options) as client:
                await client.query(prompt)
                async for msg in client.receive_response():
                    if stop_event.is_set():
                        try:
                            await client.interrupt()
                        except Exception:
                            pass
                        raise _Stopped()
                    for ev in map_message(msg, state):
                        emit(ev)
                    if _name(msg) == "ResultMessage":
                        result = msg
        except _Stopped:
            return
        except Exception as e:  # SDK errors: ProcessError, CLIConnectionError, CLINotFoundError, …
            name = _name(e)
            if name == "CLINotFoundError" and not tried_cli_fallback and shutil.which("claude"):
                tried_cli_fallback = True
                cli_path = shutil.which("claude")
                log(f"chat agent: bundled CLI missing, falling back to {cli_path}")
                continue
            if resume and _is_resume_failure(e):
                log("chat agent: previous session not found, starting fresh")
                emit(("notice", {"text": "Previous agent session expired; started a fresh one."}))
                resume = None
                prompt = _history_prefix(history) + question
                continue
            detail = str(e).strip()
            tail = " ".join(l.strip() for l in stderr_lines[-3:])
            if tail and tail not in detail:
                detail = f"{detail} — {tail}" if detail else tail
            emit(("error", {"error": f"agent: {detail or name}"}))
            return

        if result is None:
            emit(("error", {"error": "agent: the session ended without a result"}))
            return
        if getattr(result, "is_error", False):
            emit(("error", {"error": f"agent: {getattr(result, 'result', None) or 'error'}"}))
            return
        usage = dict(getattr(result, "usage", None) or {})
        est = getattr(result, "total_cost_usd", None)
        cost = chat_data.record_usage(model, usage, cost=est, billing=billing)
        emit(("usage", {**usage, "model": model, "cost_usd": cost, "billing": billing,
                        "est_cost_usd": est,
                        "num_turns": getattr(result, "num_turns", None),
                        "duration_ms": getattr(result, "duration_ms", None),
                        "spend": chat_data.spend_summary()}))
        if state.session_id:
            emit(("session", {"id": state.session_id}))
        emit(("sources", state.sources(extra=harvest_citations(state.text, index))))
        emit(("done", {}))
        return


def stream_agent(question, *, model, system, key, session_id=None, history=None, log=None, billing="api",
                 scope=None):
    """Sync generator of (event, data) for serve.py's SSE loop. Closing it stops the agent.
    `key=None` with `billing="subscription"` runs on the `claude login` account."""
    log = log or (lambda s: print(s, flush=True))
    q = queue.Queue()
    stop_event = threading.Event()
    DONE = object()

    def emit(ev):
        q.put(ev)

    def runner():
        try:
            asyncio.run(_run(question, model=model, system=system, key=key, session_id=session_id,
                             history=history, emit=emit, stop_event=stop_event, log=log, billing=billing,
                             scope=scope))
        except Exception as e:
            q.put(("error", {"error": f"agent: {e}"}))
        finally:
            q.put(DONE)

    t = threading.Thread(target=runner, name="kb-chat-agent", daemon=True)
    t.start()
    try:
        while True:
            try:
                ev = q.get(timeout=PING_SECONDS)
            except queue.Empty:
                yield ("ping", None)
                continue
            if ev is DONE:
                return
            yield ev
    finally:
        stop_event.set()
        t.join(JOIN_SECONDS)
