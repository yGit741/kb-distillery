"""Claude Code session logs → one usage record per session (0 LLM).

Claude Code writes every session of this vault to `~/.claude/projects/<cwd-slug>/<id>.jsonl`, and the
subagents it spawned to `<id>/subagents/agent-*.jsonl`. Each assistant reply carries the exact
`message.usage` (input, cache write, cache read, output); a reply split into several content blocks
repeats the same `message.id`, so usage is counted once per id.

A record never holds reply text, and only a 120-char first prompt (kept local, never uploaded):

    id, start, end, minutes, branch, cwd, title, task, golden, skills, tools, human_turns, calls,
    subagents, models{model: tokens}, main{tokens}, sub{tokens}, first_context, usd, first_prompt
"""
import datetime
import glob
import json
import os
import re

PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
# every checkout and worktree of this vault, before (OneDrive "Thesis-Knowledge-Base", ~/kb-work) and
# after the 2026-10-24 move, plus the scratch clones of golden runs
VAULT_MARKS = ("personal-knowledge-base", "thesis-knowledge-base", "kb-work", "kb-golden")

# API list price per million tokens (USD), from the claude-api model table (cached 2026-10-06).
# On a subscription this is not a bill: it is the weight that makes Opus, Sonnet and Haiku tokens comparable.
PRICES = {
    "fable": {"in": 10.0, "out": 50.0, "cr": 0.25},
    "opus": {"in": 4.0, "out": 20.0, "cr": 0.20},
    "sonnet": {"in": 2.0, "out": 10.0, "cr": 0.20},
    "haiku": {"in": 0.10, "out": 0.50, "cr": 0.01},
}
CACHE_WRITE_5M, CACHE_WRITE_1H = 1.25, 2.0   # multipliers on the input price

GOLDEN_TAG = re.compile(r"\[golden:([a-z0-9-]+)\]")
# What a session did decides its task, not its first prompt (often a 3-word title). Rules run in order
# over `acts`: one line per tool call — `tool:<name>` plus the Bash command, the edited path or the skill.
TASK_RULES = [
    ("digest", r"(easy|full|deep)-digest|kb(?:_distillery)?\.ingest (draft|finalize)"),
    ("catalog", r"kb(?:_distillery)?\.ingest (catalog|scrap|drain-inbox)|scrap-wordpress|ingest-to-catalog|scrap-data"),
    ("researcher", r"index-researcher|build-researcher-profile"),
    ("feature", r"ship -- (start|commit|pr)|edit:(backend|frontend|skills|share|tools)/"),
    ("wiki-edit", r"ops -- (begin|commit)|edit:wiki/|wiki-edit"),
    ("query", r"kb(?:_distillery)?\.search|query candidates|query-knowledge|explore-raw"),
    ("research", r"tool:Web(Search|Fetch)|deep-research"),
]
TOKEN_KEYS = ("in", "cw", "cr", "out")


def family(model):
    m = (model or "").lower()
    return next((f for f in PRICES if f in m), "opus")


def usd(model, t):
    p = PRICES[family(model)]
    return (t["in"] * p["in"] + t.get("cw5", 0) * p["in"] * CACHE_WRITE_5M + t.get("cw1", 0) * p["in"] * CACHE_WRITE_1H
            + t["cr"] * p["cr"] + t["out"] * p["out"]) / 1e6


def zero():
    return {"in": 0, "cw": 0, "cw5": 0, "cw1": 0, "cr": 0, "out": 0}


def add_usage(acc, u):
    cw = u.get("cache_creation_input_tokens") or 0
    cw1 = (u.get("cache_creation") or {}).get("ephemeral_1h_input_tokens") or 0
    acc["in"] += u.get("input_tokens") or 0
    acc["cw"] += cw
    acc["cw1"] += cw1
    acc["cw5"] += max(cw - cw1, 0)
    acc["cr"] += u.get("cache_read_input_tokens") or 0
    acc["out"] += u.get("output_tokens") or 0


def _lines(path):
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    yield json.loads(line)
                except ValueError:
                    continue
    except OSError:
        return


def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _is_human(d):
    """A prompt the user typed: not a tool result, not a subagent turn, not a system notification."""
    if d.get("type") != "user" or d.get("isSidechain") or (d.get("origin") or {}).get("kind", "human") != "human":
        return False
    content = (d.get("message") or {}).get("content")
    if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
        return False
    return bool(_text(content).strip())


def _rel(path, root):
    if "/.claude/worktrees/" in path:
        return path.split("/.claude/worktrees/", 1)[1].split("/", 1)[-1]
    return os.path.relpath(path, root) if root and path.startswith(root) else path


def _act(b, root):
    name, inp = b.get("name") or "", b.get("input") or {}
    if name == "Bash":
        return f"tool:Bash {str(inp.get('command', ''))[:300]}"
    if name in ("Edit", "Write", "NotebookEdit"):
        return f"tool:{name} edit:{_rel(inp.get('file_path') or inp.get('notebook_path') or '', root)}"
    if name == "Skill":
        return f"tool:Skill {inp.get('skill', '')}"
    return f"tool:{name}"


def _fold(rows, models, bucket, seen, acts):
    """Fold one log's assistant replies into `models`/`bucket` and its tool calls into `acts`;
    returns (first-call context, calls, skills)."""
    first, calls, skills, root = None, 0, [], None
    for d in rows:
        if d.get("type") != "assistant":
            continue
        msg = d.get("message") or {}
        root = root or d.get("cwd")
        for b in msg.get("content") or []:
            if isinstance(b, dict) and b.get("type") == "tool_use":
                acts.append(_act(b, root))
                if b.get("name") == "Skill" and (b.get("input") or {}).get("skill"):
                    skills.append(b["input"]["skill"])
        mid, u, model = msg.get("id"), msg.get("usage"), msg.get("model") or "unknown"
        if not u or mid in seen or model == "<synthetic>":
            continue
        seen.add(mid)
        calls += 1
        add_usage(models.setdefault(model, zero()), u)
        add_usage(bucket, u)
        if first is None:
            first = sum(u.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    return first, calls, skills


def classify(acts, branch):
    hay = "\n".join(acts)
    for task, rule in TASK_RULES:
        if re.search(rule, hay):
            return task
    if (branch or "").startswith(("infra/", "worktree-")):
        return "feature"
    return "ops" if "tool:Bash" in hay else "chat"


def parse_session(path):
    """One record for the session log at `path` (its subagents included), or None when it has no usage."""
    sid = os.path.basename(path)[:-len(".jsonl")]
    rows = list(_lines(path))
    models, main, sub, seen, acts = {}, zero(), zero(), set(), []
    first, calls, skills = _fold(rows, models, main, seen, acts)
    subs = sorted(glob.glob(os.path.join(path[:-len(".jsonl")], "subagents", "*.jsonl")))
    for sp in subs:
        _, c, s = _fold(_lines(sp), models, sub, seen, acts)
        calls += c
        skills += s
    if not calls:
        return None
    stamps = [d["timestamp"] for d in rows if d.get("timestamp")]
    prompts = [_text(d["message"]["content"]) for d in rows if _is_human(d)]
    typed = [p for p in prompts if not p.lstrip().startswith("<")] or prompts
    first_prompt = (typed[0] if typed else "").strip()
    meta = {}
    for d in rows:
        for k in ("gitBranch", "cwd"):
            if d.get(k) and k not in meta:
                meta[k] = d[k]
        if d.get("type") in ("custom-title", "ai-title", "agent-name"):
            meta.setdefault("title", d.get("customTitle") or d.get("aiTitle") or d.get("agentName"))
    golden = GOLDEN_TAG.search(first_prompt)
    start, end = (min(stamps), max(stamps)) if stamps else (None, None)
    return {
        "id": sid, "start": start, "end": end, "minutes": _minutes(start, end),
        "branch": meta.get("gitBranch"), "cwd": meta.get("cwd"), "title": meta.get("title"),
        "task": "golden" if golden else classify(acts, meta.get("gitBranch")),
        "golden": golden.group(1) if golden else None,
        "skills": sorted(set(skills)), "tools": _tool_counts(acts),
        "human_turns": len(typed), "calls": calls, "subagents": len(subs),
        "models": {m: _pub(t) for m, t in models.items()}, "main": _pub(main), "sub": _pub(sub),
        "first_context": first or 0,
        "usd": round(sum(usd(m, t) for m, t in models.items()), 4),
        "first_prompt": first_prompt[:120],
    }


def _tool_counts(acts):
    out = {}
    for a in acts:
        name = a.split(" ", 1)[0][len("tool:"):]
        out[name] = out.get(name, 0) + 1
    return out


def _pub(t):
    return {k: t[k] for k in TOKEN_KEYS}


def _minutes(a, b):
    try:
        f = lambda s: datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return round((f(b) - f(a)).total_seconds() / 60, 1)
    except (TypeError, ValueError, AttributeError):
        return None


def session_files(sources=None):
    """Top-level session logs of this vault under each source dir (default: ~/.claude/projects)."""
    out = []
    for src in sources or [PROJECTS_DIR]:
        for proj in sorted(glob.glob(os.path.join(src, "*"))):
            if any(m in os.path.basename(proj).lower() for m in VAULT_MARKS):
                out += sorted(glob.glob(os.path.join(proj, "*.jsonl")))
    return out


def scan(sources=None):
    for p in session_files(sources):
        rec = parse_session(p)
        if rec:
            yield rec
