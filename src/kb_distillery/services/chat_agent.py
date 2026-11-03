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
    sources  {"hits": [{slug, score, summary, in_context}], "new": [slug]}   pages read so far
    delta    str                              streamed answer text
    notice   {"text": str}                    e.g. the previous session expired, started fresh
    usage    {input_tokens, …, model, cost_usd, num_turns, duration_ms, spend}
    error    {"error": str}
    done     {}
    ping     None                             heartbeat; serve.py writes an SSE comment

The SDK itself is owned by `kb_distillery.llm.agent` (lazy import), so the dashboard and the tests load without it.
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


def _policy_web(tool_name, tool_input, scope):
    """WebSearch / WebFetch: denied for now (the web-tools PR adds the URL checks and per-turn caps)."""
    if tool_name in WEB_TOOLS:
        return Decision(False, f"read-only KB agent: tool {tool_name} is not available")
    return None


def _policy_skills(tool_name, tool_input, scope):
    """Skill / subagents: denied for now (the skills PR adds the whitelist)."""
    if tool_name in SKILL_TOOLS:
        return Decision(False, f"read-only KB agent: tool {tool_name} is not available")
    return None


def _policy_attachments(tool_name, tool_input, scope):
    """Chat attachments: nothing yet (the attachments PR adds the per-session read scope)."""
    return None


POLICY_GROUPS = (_policy_files, _policy_bash, _policy_web, _policy_skills, _policy_attachments)


def tool_policy(tool_name, tool_input, scope=None):
    """The whole read-only policy, pure and testable. Returns a Decision.
    `scope` (a scopes.scope_context dict) narrows it to one scope's pages and files; None = unchanged."""
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    for group in POLICY_GROUPS:
        d = group(tool_name, tool_input, scope)
        if d is not None:
            return d
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
        PermissionResultAllow, PermissionResultDeny = llm_agent.permission_results()
        d = _decide(policy, tool_name, tool_input, scope)
        if d.allow:
            return PermissionResultAllow(updated_input=d.updated_input)
        return PermissionResultDeny(message=d.reason)
    return can_use_tool


def agent_request(question, model, system, session_id=None, scope=None, history=None, effort=None, budget=None):
    return llm_agent.AgentRequest(
        question=question, model=model, system=system, effort=effort, budget=budget, session=session_id or None,
        tools=tuple(TOOLS), disallowed=tuple(DISALLOWED_TOOLS), scope=scope, cwd=ROOT, max_turns=MAX_TURNS,
        fresh_prompt=_history_prefix(history) + question if history else None)


def build_options(model, system, key, session_id=None, cli_path=None, ca_path=None, stderr=None, scope=None):
    req = agent_request("", model, system, session_id=session_id, scope=scope)
    return llm_agent.build_options(req, key, policy_hook=make_hook(scope=scope),
                                   can_use_tool=make_can_use_tool(scope=scope), resume=session_id,
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
               scope=None, effort=None, budget=None):
    index = query.parse_index()
    req = agent_request(question, model, system, session_id=session_id, scope=scope, history=history,
                        effort=effort, budget=budget)
    if req.fresh_prompt is None:
        req.fresh_prompt = question
    state = TurnState(index=index)
    backend = "subscription" if billing == "subscription" else "api"
    gen = llm_agent.stream(
        req, backend, key=key, policy_hook=make_hook(scope=scope), can_use_tool=make_can_use_tool(scope=scope),
        usage_sink=lambda m, usage, est, b: chat_data.record_usage(m, usage, cost=est, billing=b),
        stop_event=stop_event, log=log, ca_path=ca_bundle_path())
    async for kind, data in gen:
        if kind == "reset":
            state = TurnState(index=index)
        elif kind == "message":
            for ev in map_message(data, state):
                emit(ev)
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
                 scope=None, effort=None, budget=None):
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
                             scope=scope, effort=effort, budget=budget))
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
