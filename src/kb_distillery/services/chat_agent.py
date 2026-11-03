"""Chat with the KB, agent backend: a read-only research agent over the Claude Agent SDK.

Instead of pasting six guessed pages into one Messages call (chat_data.stream_claude), the agent
runs the `query-knowledge` workflow itself inside the real Claude Code harness: `src/kb_distillery/search/query.py
candidates`, Grep, Read `wiki/<slug>.md`, then an answer that cites `[Title](slug.md)`. It bills the same
Console API key (ANTHROPIC_API_KEY or ~/.config/kb-distillery/anthropic_key).

The agent is READ-ONLY. `tool_policy` is the single source of truth and is enforced twice: as a
PreToolUse hook (runs first, a deny wins in every permission mode) and as the `can_use_tool`
callback. `setting_sources=[]` keeps the subprocess away from this repo's CLAUDE.md and hooks —
this module is the guard.

SSE event contract shared with static/chat.js (names → JSON data):

    session  {"id": str}                      first thing, and again after the result (resume key)
    tool     {"name", "summary", "id", "error"?}   one per tool call ("read tensor-rank", "grep …")
    sources  {"hits": [{kind, slug, score, summary, in_context} | {kind: "web", url, title, score, ...}], "new": [slug]}
    ask      {"id", "questions": [...]}       agent-mode: the agent asks the user; answer via POST /api/chat/answer
    delta    str                              streamed answer text
    notice   {"text": str}                    e.g. the previous session expired, started fresh
    usage    {input_tokens, …, model, cost_usd, num_turns, duration_ms, spend}
    error    {"error": str}
    done     {}
    ping     None                             heartbeat; serve.py writes an SSE comment

The SDK itself is owned by `kb_distillery.llm.agent` (lazy import), so the dashboard and the tests load without it.
"""
import asyncio
import ipaddress
import json
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from kb_distillery.config import kb as kbconfig
from kb_distillery.config.flags import runtime
from kb_distillery.llm import agent as llm_agent
from kb_distillery.vault import links
from kb_distillery.config.paths import vault_root
META_DIR = os.path.join(vault_root(), "meta")
ROOT = vault_root()

from kb_distillery.search import query
from kb_distillery.services import chat as chat_data

WIKI = os.path.join(ROOT, "wiki")
RAW = os.path.join(ROOT, "raw")
from kb_distillery.config.paths import THINK_PATH as THINK      # the shared think space, outside the vault
from kb_distillery.vault.schema import INDEX_REL, is_index_path, is_page_file
INDEX = os.path.join(ROOT, INDEX_REL)
READ_ROOTS = (WIKI, RAW, THINK)
RAW_TEXT_EXT = {".md", ".txt", ".html", ".eml", ".json", ".tsv", ".csv"}

CA_PEM = os.path.join(chat_data.CONFIG_DIR, "ca-roots.pem")

MAX_TURNS = 30
TOOLS = ["Read", "Grep", "Glob", "Bash"]
AGENT_MODE_TOOLS = ["WebSearch", "WebFetch", "AskUserQuestion", "TodoWrite"]   # leave DISALLOWED under the agent-mode flag
DISALLOWED_TOOLS = ["Write", "Edit", "MultiEdit", "NotebookEdit", "WebFetch", "WebSearch",
                    "Agent", "Task", "TodoWrite", "AskUserQuestion", "Skill", "KillShell"]

# Bash: exactly one simple command, python running one of these entry points.
BASH_SCRIPTS = {"src/kb_distillery/search/query.py", "src/kb_distillery/search/semfind.py", "src/kb_distillery/search/explore_raw.py"}
BASH_MODULES = {("kb_distillery.ingest", "resolve")} | {
    ("kb_distillery.search.explore_raw", sub) for sub in ("find", "read", "check", "recommend")}
# query / semfind run as modules (any arguments); the scope rules below narrow them
BASH_ANY_MODULES = {"kb_distillery.search.query", "kb_distillery.search.semfind"}
BASH_FORBIDDEN_CHARS = set(";&|$`()<>{}\n\\")
PING_SECONDS = 2.0
JOIN_SECONDS = 5.0
HISTORY_TURNS = 6
HISTORY_CHARS = 800

AGENT_WORKFLOW = """\
How to research a question in this knowledge base (always applies):
- You are a read-only research agent inside the user's wiki (the current directory).
  `wiki/` holds flat markdown notes, one per slug; `wiki/index.md` is a tiny root listing the page types, and
  `wiki/<type>/index.md` lists that type's pages with their one-line summaries; `raw/` holds the sources; `think/` is the user's own notebook.
- Locate first, with no guessing: run `python3 -m kb_distillery.search.query candidates "<keywords>"` (and
  `python3 -m kb_distillery.search.query mocs` for broad questions), read `wiki/index.md`, then only the section index you need,
  then Grep `wiki/` for the exact terms. Never say the vault has nothing on a topic before both the
  index and candidates were checked.
- Read 3–8 pages with Read on `wiki/<slug>.md`. Prefer `theme-*` and `q-*` pages for high-level
  questions and `paper-`, `part-`, `lecture-`, `article-`, `mail-`, `chat-` pages for citations.
  Follow `related:` and the page links (`[Title](slug.md)`) when they matter. An unknown slug may be an alias:
  `python3 -m kb_distillery.ingest resolve <slug>`.
- Structural questions (what links to X, which ideas share sources, paths between pages) go to the
  graph: `python3 -m kb_distillery.search.cypher run 'MATCH (s:Source)-[:MENTIONS]->(i:Idea) WHERE i.slug = "x"
  RETURN s.slug'` (one single-quoted query, strings in double quotes, arrows always directed) or a named
  query: `python3 -m kb_distillery.search.cypher list` shows which this knowledge base has (always `gaps`,
  `shortest-path`, `neighbourhood`), then `… named <name> --param key=value`. A rejected query says what
  to use instead.
- Prefer the wiki over your own knowledge. Cite a page as [Title](slug.md) with its exact slug whenever you
  draw on it. Note gaps: `to-read` papers, queued raw files, open `q-*` questions.
- If the wiki does not cover something, say so plainly before adding anything from general
  knowledge, and mark that part as not from the KB.
- Raw through one door: the wiki is what you read. To look at a source (an undigested file, a
  contradiction between pages, an explicit request) run
  `python3 -m kb_distillery.search.explore_raw find|read|check|recommend …` — never Read a PDF. Attribute every
  sentence drawn from a source with its raw path and the reason you opened it; when the file is
  undigested say so and give a tier recommendation (skip, easy, full or deep).
- Write math in LaTeX with $…$ and $$…$$. Answer in the chat; do not create or edit files, do not
  run git, and do not try other tools — only Read, Grep, Glob and the python commands above."""


# ── Environment ────────────────────────────────────────────────────────────

def sdk_info():
    """{available, version, cli, error} — whether the agent backend can run at all."""
    return llm_agent.sdk_info()


def ca_bundle_path(path=CA_PEM, now=None):
    """PEM file with the macOS keychain roots for the Node CLI (NODE_EXTRA_CA_CERTS). The TLS
    proxy fix of chat_data.ssl_context(), replayed for the subprocess. None when not needed."""
    return llm_agent.ca_bundle_path(chat_data.CONFIG_DIR, chat_data.keychain_pem, path=path, now=now)


def cli_path():
    """The Claude Code binary: the one bundled with the SDK, else `claude` on PATH, else None."""
    return llm_agent.cli_path()


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
    """Extra environment for the claude subprocess; `key=None` means subscription mode (see llm.agent)."""
    ca = ca_path if ca_path is not None else ca_bundle_path()
    return llm_agent.agent_env(key, ca)


def build_agent_system(system_text, scope=None):
    """User-editable template + KB theme map + the research workflow nobody can remove
    (+ the Scope block when `scope` — a scopes.scope_context dict — is set)."""
    index = query.parse_index()
    themes = [f"- {links.link(s, m.get('title') or s)} — {m['summary']}" for s, m in sorted(index.items()) if s.startswith("theme-")]
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
        # `think/<note>`: the shared think space beside the vault, not a folder of it (kb_distillery.config.paths.THINK_PATH)
        p = os.path.join(THINK, q[len("think/"):]) if q == "think" or q.startswith("think/") else os.path.join(ROOT, p)
    return os.path.realpath(p)


READ_DENY = "read-only KB agent: only wiki/ (with its index.md files), think/ and text files under raw/ can be read"
BASH_DENY = ("read-only KB agent: only `python3 -m kb_distillery.search.query candidates|mocs …`, "
             "`python3 -m kb_distillery.search.semfind …`, `python3 -m kb_distillery.search.explore_raw …` / "
             "`python3 -m kb_distillery.search.explore_raw find|read|check|recommend …` and "
             "`python3 -m kb_distillery.ingest resolve …` may run")


def _is_index_file(real):
    """The root wiki/index.md or a generated section index (wiki/<type>/index.md)."""
    return real == os.path.realpath(INDEX) or is_index_path(os.path.relpath(real, os.path.realpath(ROOT)).replace(os.sep, "/"))


def _readable_in_scope(real, scope, allow_dirs=False):
    """_readable, narrowed to a scope: the wiki indexes, the scope's pages, its own raw text files; no think/."""
    if real is None:
        return False
    if _is_index_file(real):
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


# Citation graph (src/kb_distillery/search/citations.py): the read-only subcommands only, never `fetch` (network writes).
CITATION_SUBS = ("neighbors", "rank", "missing", "path", "status")
BASH_MODULES = BASH_MODULES | {("kb_distillery.search.citations", sub) for sub in CITATION_SUBS}
BASH_DENY = BASH_DENY + "; also `python3 -m kb_distillery.search.citations neighbors|rank|missing|path|status …`"

# Graph queries (src/kb_distillery/search/cypher.py, read-only): `named`/`list` take plain tokens; `run` takes
# Cypher, whose ( ) < > { } | the forbidden-char rule would refuse, so it is allowed in exactly this shape —
# one single-quoted argument, which the shell passes through literally.
BASH_MODULES = BASH_MODULES | {("kb_distillery.search.cypher", "named"), ("kb_distillery.search.cypher", "list")}
CYPHER_RUN = re.compile(r"(?:\S*/)?python(?:3(?:\.\d+)?)? -m kb_distillery\.search\.cypher run '[^'\n\\]+'"
                        r"(?: --limit \d{1,3})?(?: --json)?")
BASH_DENY = BASH_DENY + ("; also `python3 -m kb_distillery.search.cypher run '<query>'` (one single-quoted query) "
                         "and `python3 -m kb_distillery.search.cypher named|list …`")


SCOPE_READ_DENY = ("scoped chat: only the scope's pages (wiki/<slug>.md listed in the system prompt), "
                   "the wiki indexes (wiki/index.md and wiki/<type>/index.md) and the scope's own text files under raw/ can be read; think/ is closed")
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
    if mod in ("kb_distillery.search.semfind", "src/kb_distillery/search/semfind.py", "kb_distillery.search.cypher"):
        return False                                    # whole-graph tools would leak pages outside the scope
    if mod in ("kb_distillery.search.query", "src/kb_distillery/search/query.py"):
        if sub == "scope-status":
            return bool(rest) and rest[0] == slug
        return sub == "candidates" and _scope_flag(rest) == slug
    if mod in ("kb_distillery.search.explore_raw", "src/kb_distillery/search/explore_raw.py"):
        if sub == "find":
            return _scope_flag(rest) == slug
        first = next((t for t in rest if not t.startswith("-")), None)
        return first in set(scope.get("rows") or ())
    if mod in ("kb_distillery.search.citations", "src/kb_distillery/search/citations.py") and sub == "missing":
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
    if CYPHER_RUN.fullmatch(command.strip()):
        return True
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
    if os.path.normpath(script) == "src/kb_distillery/search/citations.py":   # read-only subcommands only (never fetch)
        return len(toks) >= 3 and ("kb_distillery.search.citations", toks[2]) in BASH_MODULES
    return os.path.normpath(script) in BASH_SCRIPTS


# One helper per tool group, so the web / skills / attachments PRs each edit their own function. Each takes
# (tool_name, tool_input, scope) and returns a Decision, or None when the tool is not in its group.
WEB_TOOLS = ("WebSearch", "WebFetch")
SKILL_TOOLS = ("Skill", "Agent", "Task")
ATTACHMENT_TOOLS = ()       # attachments are read with Read; the per-session read scope lands with them


def _policy_files(tool_name, tool_input, scope):
    """Read / Grep / Glob over the wiki, think/ and text files under raw/ (narrowed to the scope's pages)."""
    if scope is not None:
        readable = lambda real, allow_dirs=False: _readable_in_scope(real, scope, allow_dirs)  # noqa: E731
        read_deny = SCOPE_READ_DENY
    else:
        readable, read_deny = _readable, READ_DENY
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
    return None


def _policy_bash(tool_name, tool_input, scope):
    """Bash: one allow-listed python entry point (narrowed further inside a scope)."""
    if tool_name != "Bash":
        return None
    bash_deny = BASH_DENY if scope is None else BASH_DENY + "; " + SCOPE_BASH_DENY
    return (Decision(True) if _bash_allowed(tool_input.get("command"), scope)
            else Decision(False, bash_deny))


WEB_DENY = "read-only KB agent: tool {} is not available"
WEB_SCOPE_DENY = "scoped chat: the web tools are off"
WEB_SCHEMES = ("http", "https")
WEB_BLOCKED_SUFFIXES = (".local", ".internal", ".localhost")
ASK_TIMEOUT_SECONDS = 600.0
DEFAULT_WEB_FETCH_CAP = 20
DEFAULT_WEB_SEARCH_CAP = 10


def _agent_cap(name, default):
    """`[agent] <name>` of the selected kb.toml as a non-negative int, else `default`."""
    try:
        cfg = kbconfig.current()
        value = cfg.section("agent").get(name) if cfg else None
    except Exception:
        return default
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else default


def _resolve_host(host):
    """Every IP address `host` resolves to (blocking; the hook runs the web policy off the event loop)."""
    return [info[4][0] for info in socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)]


def web_url_problem(url, resolve=None):
    """Why a WebFetch URL is refused (None = fine): http/https only; no localhost, loopback, link-local,
    private-range or `.local` / `.internal` host. A hostname is resolved once and refused when ANY address is
    not a public one (an unresolvable host is refused too)."""
    if not isinstance(url, str) or not url.strip():
        return "no URL"
    try:
        parts = urlsplit(url.strip())
        host = (parts.hostname or "").rstrip(".").lower()
    except ValueError:
        return "malformed URL"
    if parts.scheme.lower() not in WEB_SCHEMES:
        return "only http and https URLs can be fetched"
    if not host:
        return "no host in the URL"
    if host == "localhost" or host.endswith(WEB_BLOCKED_SUFFIXES):
        return f"host {host} is local"
    try:
        addrs = [str(ipaddress.ip_address(host))]           # an IP literal needs no lookup
    except ValueError:
        try:
            addrs = (resolve or _resolve_host)(host)
        except (OSError, UnicodeError):
            addrs = []
        if not addrs:
            return f"host {host} does not resolve"
    for a in addrs:
        try:
            ip = ipaddress.ip_address(a.split("%")[0])
        except ValueError:
            return f"host {host} resolves to an unreadable address"
        ip = getattr(ip, "ipv4_mapped", None) or ip
        if not ip.is_global:
            return f"host {host} is not on the public internet ({ip})"
    return None


class AskRegistry:
    """Pending AskUserQuestion prompts, shared by the agent's event loop and the HTTP thread that answers them."""
    CANCELLED = object()

    def __init__(self):
        self._lock = threading.Lock()
        self._pending = {}                  # ask id → (session, loop, future)

    def register(self, ask_id, session):
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        with self._lock:
            self._pending[ask_id] = (session or "", loop, fut)
        return fut

    def drop(self, ask_id):
        with self._lock:
            self._pending.pop(ask_id, None)

    def answer(self, session, ask_id, answers):
        """Hand `answers` to the waiting turn. False when nothing waits under that id (or it is another session's)."""
        with self._lock:
            entry = self._pending.get(ask_id)
            if entry is None or (entry[0] and entry[0] != session):
                return False
            del self._pending[ask_id]
        return self._resolve(entry, answers)

    def cancel(self, ask_ids):
        for ask_id in list(ask_ids):
            with self._lock:
                entry = self._pending.pop(ask_id, None)
            if entry:
                self._resolve(entry, self.CANCELLED)

    @staticmethod
    def _resolve(entry, value):
        _, loop, fut = entry
        try:
            loop.call_soon_threadsafe(lambda: fut.done() or fut.set_result(value))
        except RuntimeError:                # the turn's loop is gone
            return False
        return True


ASKS = AskRegistry()


@dataclass
class RunContext:
    """Per-turn state the tool policy and hooks share: agent-mode switch, web counters and caps, the ask channel."""
    agent_mode: bool = False
    web_fetch_cap: int = DEFAULT_WEB_FETCH_CAP
    web_search_cap: int = DEFAULT_WEB_SEARCH_CAP
    fetches: int = 0
    searches: int = 0
    emit: object = None                     # callable((event, data)); the SSE queue
    session: str = None
    asks: AskRegistry = field(default_factory=lambda: ASKS)
    ask_timeout: float = ASK_TIMEOUT_SECONDS
    resolve: object = None                  # host → addresses; tests inject, None = DNS
    decided: list = field(default_factory=list)     # (tool, input) pairs the hook allowed, for can_use_tool
    pending_asks: set = field(default_factory=set)

    def cap_problem(self, tool_name):
        if tool_name == "WebFetch" and self.fetches >= self.web_fetch_cap:
            return f"web fetch limit reached ({self.web_fetch_cap} per turn)"
        if tool_name == "WebSearch" and self.searches >= self.web_search_cap:
            return f"web search limit reached ({self.web_search_cap} per turn)"
        return None

    def charge(self, tool_name):
        if tool_name == "WebFetch":
            self.fetches += 1
        elif tool_name == "WebSearch":
            self.searches += 1

    def cancel(self):
        self.asks.cancel(self.pending_asks)


def _policy_web(tool_name, tool_input, scope, run=None):
    """WebSearch / WebFetch: only in agent mode and unscoped; WebFetch needs a public http(s) URL;
    both are capped per turn (`run` counts, the hook charges an allowed call)."""
    if tool_name not in WEB_TOOLS:
        return None
    if run is None or not run.agent_mode:
        return Decision(False, WEB_DENY.format(tool_name))
    if scope is not None:
        return Decision(False, WEB_SCOPE_DENY)
    if tool_name == "WebFetch":
        problem = web_url_problem(tool_input.get("url"), run.resolve)
        if problem:
            return Decision(False, f"WebFetch refused: {problem}")
    elif not str(tool_input.get("query") or "").strip():
        return Decision(False, "WebSearch needs a query")
    problem = run.cap_problem(tool_name)
    return Decision(False, problem) if problem else Decision(True)


def _policy_agent_ui(tool_name, tool_input, scope, run=None):
    """AskUserQuestion / TodoWrite: agent mode only (the hook below runs the ask round trip)."""
    if tool_name not in ("AskUserQuestion", "TodoWrite"):
        return None
    if run is None or not run.agent_mode:
        return Decision(False, WEB_DENY.format(tool_name))
    return Decision(True)


def _policy_skills(tool_name, tool_input, scope):
    """Skill / subagents: denied for now (the skills PR adds the whitelist)."""
    if tool_name in SKILL_TOOLS:
        return Decision(False, f"read-only KB agent: tool {tool_name} is not available")
    return None


def _policy_attachments(tool_name, tool_input, scope):
    """Chat attachments: nothing yet (the attachments PR adds the per-session read scope)."""
    return None


POLICY_GROUPS = (_policy_files, _policy_bash, _policy_web, _policy_agent_ui, _policy_skills, _policy_attachments)
RUN_GROUPS = (_policy_web, _policy_agent_ui)      # the groups that read the per-turn RunContext


def tool_policy(tool_name, tool_input, scope=None, run=None):
    """The whole read-only policy, pure and testable. Returns a Decision.
    `scope` (a scopes.scope_context dict) narrows it to one scope's pages and files; None = unchanged.
    `run` (a RunContext) switches the agent-mode tools on; without it they stay denied."""
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    for group in POLICY_GROUPS:
        d = group(tool_name, tool_input, scope, run) if group in RUN_GROUPS else group(tool_name, tool_input, scope)
        if d is not None:
            return d
    return Decision(False, f"read-only KB agent: tool {tool_name} is not available")


def _decide(policy, name, inp, scope, run=None):
    if run is not None:
        return policy(name, inp, scope, run=run)
    return policy(name, inp) if scope is None else policy(name, inp, scope)


def _input_key(name, inp):
    return (name, json.dumps(inp, sort_keys=True, default=str))


async def _ask_user(run, tool_input, ask_id):
    """Emit an `ask` event and wait for POST /api/chat/answer. Returns (answers dict, None) or (None, deny reason)."""
    ask_id = ask_id or f"ask-{uuid.uuid4().hex[:12]}"
    questions = [q for q in (tool_input.get("questions") or []) if isinstance(q, dict)]
    fut = run.asks.register(ask_id, run.session)
    run.pending_asks.add(ask_id)
    try:
        if run.emit:
            run.emit(("ask", {"id": ask_id, "questions": questions}))
        try:
            answers = await asyncio.wait_for(fut, run.ask_timeout)
        except asyncio.TimeoutError:
            return None, f"the user did not answer within {int(run.ask_timeout // 60) or 1} minutes"
        if answers is AskRegistry.CANCELLED:
            return None, "the chat was closed before the user answered"
        return answers, None
    finally:
        run.asks.drop(ask_id)
        run.pending_asks.discard(ask_id)


def make_hook(policy=tool_policy, scope=None, run=None):
    """PreToolUse hook: every call gets an explicit allow/deny (never an empty dict). With a `run`, an allowed
    AskUserQuestion waits for the user's answer and returns it as `updatedInput`; allowed web calls are counted."""
    async def hook(input_data, tool_use_id, context):
        name, inp = input_data.get("tool_name"), input_data.get("tool_input")
        if run is not None and name in WEB_TOOLS:
            d = await asyncio.to_thread(_decide, policy, name, inp, scope, run)     # DNS lookup off the event loop
        else:
            d = _decide(policy, name, inp, scope, run)
        if d.allow and run is not None:
            if name in WEB_TOOLS:
                problem = run.cap_problem(name)         # re-check after the lookup: parallel calls share the cap
                if problem:
                    d = Decision(False, problem)
                else:
                    run.charge(name)
                    run.decided.append(_input_key(name, inp))
            elif name == "AskUserQuestion":
                answers, reason = await _ask_user(run, inp if isinstance(inp, dict) else {}, tool_use_id)
                if answers is None:
                    d = Decision(False, reason)
                else:
                    d = Decision(True, updated_input={**(inp if isinstance(inp, dict) else {}), "answers": answers})
        out = {"hookEventName": "PreToolUse",
               "permissionDecision": "allow" if d.allow else "deny",
               "permissionDecisionReason": d.reason or ("read-only KB agent" if d.allow else "denied")}
        if d.allow and d.updated_input is not None:
            out["updatedInput"] = d.updated_input
        return {"hookSpecificOutput": out}
    return hook


def make_can_use_tool(policy=tool_policy, scope=None, run=None):
    """can_use_tool callback: second line behind the hook (it may be skipped after a hook allow). A call the hook
    already allowed is not counted or asked twice."""
    async def can_use_tool(tool_name, tool_input, context):
        PermissionResultAllow, PermissionResultDeny = llm_agent.permission_results()
        if run is not None and tool_name == "AskUserQuestion" and isinstance(tool_input, dict) and "answers" in tool_input:
            return PermissionResultAllow(updated_input=tool_input)       # the hook already got the answer
        key = _input_key(tool_name, tool_input) if run is not None and tool_name in WEB_TOOLS else None
        if key is not None and key in run.decided:
            run.decided.remove(key)
            return PermissionResultAllow(updated_input=None)
        d = _decide(policy, tool_name, tool_input, scope, run)
        if d.allow and run is not None and tool_name in WEB_TOOLS:
            run.charge(tool_name)
        if d.allow and run is not None and tool_name == "AskUserQuestion":
            answers, reason = await _ask_user(run, tool_input if isinstance(tool_input, dict) else {},
                                              getattr(context, "tool_use_id", None))
            if answers is None:
                return PermissionResultDeny(message=reason)
            return PermissionResultAllow(updated_input={**tool_input, "answers": answers})
        if d.allow:
            return PermissionResultAllow(updated_input=d.updated_input)
        return PermissionResultDeny(message=d.reason)
    return can_use_tool


def agent_request(question, model, system, session_id=None, scope=None, history=None, effort=None, budget=None,
                  agent_mode=False):
    tools, disallowed = list(TOOLS), list(DISALLOWED_TOOLS)
    if agent_mode:                      # ship dark: today's tool set unless the flag is on; scoped chat gets no web
        extra = [t for t in AGENT_MODE_TOOLS if scope is None or t not in WEB_TOOLS]
        tools += extra
        disallowed = [t for t in disallowed if t not in extra]
    return llm_agent.AgentRequest(
        question=question, model=model, system=system, effort=effort, budget=budget, session=session_id or None,
        tools=tuple(tools), disallowed=tuple(disallowed), scope=scope, cwd=ROOT, max_turns=MAX_TURNS,
        fresh_prompt=_history_prefix(history) + question if history else None)


def build_options(model, system, key, session_id=None, cli_path=None, ca_path=None, stderr=None, scope=None, run=None):
    req = agent_request("", model, system, session_id=session_id, scope=scope,
                        agent_mode=bool(run and run.agent_mode))
    return llm_agent.build_options(req, key, policy_hook=make_hook(scope=scope, run=run),
                                   can_use_tool=make_can_use_tool(scope=scope, run=run), resume=session_id,
                                   cli=cli_path, ca_path=ca_path if ca_path is not None else ca_bundle_path(),
                                   stderr=stderr)


# ── Event mapping ──────────────────────────────────────────────────────────

def slug_from_read(tool_input):
    real = _real((tool_input or {}).get("file_path"))
    if real and _under(real, WIKI) and is_page_file(os.path.basename(real)):
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
    if name == "WebFetch":
        return f"fetch {tool_input.get('url', '')}".strip()[:80]
    if name == "WebSearch":
        return f"search {tool_input.get('query', '')}".strip()[:80]
    if name == "Bash":
        cmd = (tool_input.get("command") or "").strip()
        e = re.match(r"\S*python3?\s+(?:-m\s+kb_distillery\.search\.explore_raw|(?:\S*/)?src/kb_distillery/search/explore_raw\.py)\s+(\w+)\s*(.*)", cmd)
        if e:
            verb, rest = e.group(1), e.group(2).strip()
            arg = os.path.basename(rest.split()[0].strip("\"'")) if verb != "find" and rest else rest
            text = f"explore {verb} {arg}".strip()
            return text[:60] + ("…" if len(text) > 60 else "")
        m = re.match(r"\S*python3?\s+(?:-m\s+kb_distillery\.ingest\s+|-m\s+kb_distillery\.search\.(?:query|semfind)\s+|(?:\S*/)?src/kb_distillery/search/(?:query|semfind)\.py\s+)(.*)", cmd)
        text = m.group(1) if m else cmd
        return text[:60] + ("…" if len(text) > 60 else "")
    return name.lower()


def harvest_citations(text, index):
    out = []
    for slug in links.targets(text):
        if slug in index and slug not in out:
            out.append(slug)
    return out


def _host(url):
    try:
        return urlsplit(url).hostname or url
    except ValueError:
        return url


def search_links(content):
    """[{url, title}] from a WebSearch tool result: the `Links: [{"title", "url"}, …]` line of its text."""
    if isinstance(content, list):
        content = "\n".join(str(b.get("text", "")) if isinstance(b, dict) else str(b) for b in content)
    if not isinstance(content, str):
        return []
    m = re.search(r"Links:\s*(\[.*?\])\s*(?:\n|$)", content, re.S)
    if not m:
        return []
    try:
        items = json.loads(m.group(1))
    except ValueError:
        return []
    return [{"url": i["url"], "title": str(i.get("title") or _host(i["url"]))} for i in items
            if isinstance(i, dict) and isinstance(i.get("url"), str) and i["url"].startswith(("http://", "https://"))]


@dataclass
class TurnState:
    reads: dict = field(default_factory=dict)      # slug → times read, insertion ordered
    web: dict = field(default_factory=dict)        # url → {"title", "count"}: pages fetched / found by a search
    text: str = ""
    session_id: str = None
    tools: list = field(default_factory=list)
    index: dict = None

    def sources(self, extra=()):
        slugs = list(self.reads) + [s for s in extra if s not in self.reads]
        index = self.index if self.index is not None else {}
        hits = [{"kind": "wiki", "slug": s, "score": self.reads.get(s, 0), "summary": index.get(s, {}).get("summary", ""),
                 "in_context": False} for s in slugs]
        hits += [{"kind": "web", "url": u, "title": w["title"], "score": w["count"], "summary": "", "in_context": False}
                 for u, w in self.web.items()]
        return {"hits": hits, "new": slugs}

    def add_web(self, url, title=None, count=0):
        w = self.web.setdefault(url, {"title": title or _host(url), "count": 0})
        if title and (w["title"] == _host(url) or not count):
            w["title"] = title
        w["count"] += count


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
                url = inp.get("url") if name == "WebFetch" else None
                if isinstance(url, str) and url.startswith(("http://", "https://")):
                    state.add_web(url, count=1)
                    out.append(("sources", state.sources()))
            elif b == "TextBlock" and state.text and not state.text.endswith("\n\n"):
                # a new text segment after tool use: keep paragraphs apart in the stream
                pass
        return out
    if kind == "UserMessage":
        for block in getattr(msg, "content", None) or []:
            if _name(block) != "ToolResultBlock":
                continue
            tid = getattr(block, "tool_use_id", None)
            match = next((t for t in reversed(state.tools) if t.get("id") == tid), None)
            if getattr(block, "is_error", False):
                if match:
                    match["error"] = True
                    out.append(("tool", match))
            elif match and match.get("name") == "WebSearch":
                found = search_links(getattr(block, "content", None))
                for link in found:
                    state.add_web(link["url"], link["title"])
                if found:
                    out.append(("sources", state.sources()))
        return out
    if kind == "ResultMessage":
        if getattr(msg, "session_id", None):
            state.session_id = msg.session_id
        return out
    return out


# ── Streaming bridge ───────────────────────────────────────────────────────

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


WEB_WORKFLOW = """\
Web tools (this chat only): WebSearch and WebFetch are available for what the wiki does not cover. Search the wiki
first, use the web only for a gap or a fresh fact, fetch only public http(s) pages, and cite web pages as
[Title](https://…) next to the wiki links, saying which claims come from the web. When the question is ambiguous,
ask the user with AskUserQuestion instead of guessing; track a multi-step plan with TodoWrite."""


async def _run(question, *, model, system, key, session_id, history, emit, stop_event, log, billing="api",
               scope=None, effort=None, budget=None, agent_mode=False, run=None):
    index = query.parse_index()
    if agent_mode:
        run = run or RunContext(agent_mode=True, emit=emit, session=session_id,
                                web_fetch_cap=_agent_cap("web_fetch_cap", DEFAULT_WEB_FETCH_CAP),
                                web_search_cap=_agent_cap("web_search_cap", DEFAULT_WEB_SEARCH_CAP))
        if scope is None:
            system = f"{system}\n\n{WEB_WORKFLOW}"
    req = agent_request(question, model, system, session_id=session_id, scope=scope, history=history,
                        effort=effort, budget=budget, agent_mode=agent_mode)
    if req.fresh_prompt is None:
        req.fresh_prompt = question
    state = TurnState(index=index)
    backend = "subscription" if billing == "subscription" else "api"
    gen = llm_agent.stream(
        req, backend, key=key, policy_hook=make_hook(scope=scope, run=run),
        can_use_tool=make_can_use_tool(scope=scope, run=run),
        usage_sink=lambda m, usage, est, b: chat_data.record_usage(m, usage, cost=est, billing=b),
        stop_event=stop_event, log=log, ca_path=ca_bundle_path())
    async for kind, data in gen:
        if kind == "reset":
            state = TurnState(index=index)
        elif kind == "message":
            for ev in map_message(data, state):
                emit(ev)
            if run is not None and state.session_id:
                run.session = state.session_id
        elif kind == "notice":
            emit(("notice", data))
        elif kind == "error":
            emit(("error", data))
        elif kind == "pending":
            emit(("notice", {"text": f"Queued as batch {data['batch_id']}; the answer arrives when it completes."}))
            emit(("done", {}))
        elif kind == "result":
            usage = data["usage"]
            result = data["result"]
            emit(("usage", {**usage, "model": data["model"], "cost_usd": data["cost_usd"], "billing": data["billing"],
                            "est_cost_usd": data["est_cost_usd"],
                            "num_turns": getattr(result, "num_turns", None),
                            "duration_ms": getattr(result, "duration_ms", None),
                            "spend": chat_data.spend_summary()}))
            if state.session_id:
                emit(("session", {"id": state.session_id}))
            emit(("sources", state.sources(extra=harvest_citations(state.text, index))))
            emit(("done", {}))


def stream_agent(question, *, model, system, key, session_id=None, history=None, log=None, billing="api",
                 scope=None, effort=None, budget=None, agent_mode=None):
    """Sync generator of (event, data) for serve.py's SSE loop. Closing it stops the agent.
    `key=None` with `billing="subscription"` runs on the `claude login` account.
    `agent_mode=None` reads the runtime flag: off keeps today's read-only tool set."""
    log = log or (lambda s: print(s, flush=True))
    if agent_mode is None:
        agent_mode = bool(runtime.effective("agent-mode"))
    run = RunContext(agent_mode=True, emit=None, session=session_id,
                     web_fetch_cap=_agent_cap("web_fetch_cap", DEFAULT_WEB_FETCH_CAP),
                     web_search_cap=_agent_cap("web_search_cap", DEFAULT_WEB_SEARCH_CAP)) if agent_mode else None
    q = queue.Queue()
    stop_event = threading.Event()
    DONE = object()

    def emit(ev):
        q.put(ev)

    if run is not None:
        run.emit = emit

    def runner():
        try:
            asyncio.run(_run(question, model=model, system=system, key=key, session_id=session_id,
                             history=history, emit=emit, stop_event=stop_event, log=log, billing=billing,
                             scope=scope, effort=effort, budget=budget, agent_mode=agent_mode, run=run))
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
        if run is not None:
            run.cancel()                # a turn parked on an unanswered question must not outlive the stream
        t.join(JOIN_SECONDS)
