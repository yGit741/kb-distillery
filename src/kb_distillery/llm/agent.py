"""The agent runner: every Claude Agent SDK session goes through here (AGENTS.md rule 6).

`stream(req, backend, ...)` owns the lazy `claude_agent_sdk` import, backend resolution, the subprocess
environment (API key, TLS roots), the options and the resume / CLI-path fallbacks. This layer sits below
`services`, so everything service-specific arrives as a parameter: the tool policy hook, `can_use_tool`,
the usage sink and the config dir. It never imports from services, server or search.

Backends (`kb_distillery.llm.resolve_backend`):
  subscription  the `claude login` account (the API key variable is blanked for the CLI)
  api           the Console key (`key=` or `llm.api_key()`)
  batch         cannot run live tools: one tool-less request is `submit`ted and a pending marker returned

`stream` is an async generator of `(kind, payload)`:
  reset    {}                       a new attempt starts (drop per-attempt state)
  message  <SDK message>            every message of the session
  notice   {"text"}                 e.g. the previous session expired, started fresh
  result   {"result","usage","est_cost_usd","cost_usd","billing","model"}   the turn finished
  pending  {"batch_id","backend","model"}   batch backend: queued, answered later via `llm.collect`
  error    {"error"}
"""
import dataclasses
import os
import shutil
import sys
import time

from kb_distillery import llm

CA_NAME = "ca-roots.pem"
CA_MAX_AGE = 24 * 3600
MAX_TURNS = 30
EFFORTS = ("low", "medium", "high", "xhigh", "max")


@dataclasses.dataclass
class AgentRequest:
    question: str
    model: str = "sonnet"               # alias or full id (llm.model_id)
    system: str = ""
    effort: str = None                  # one of EFFORTS; None = the SDK default
    tools: tuple = ()                   # tools the session may see
    disallowed: tuple = ()
    skills: tuple = ()                  # SDK `skills` names (empty = not passed)
    budget: float = None                # hard ceiling in USD (SDK max_budget_usd); None = none
    session: str = None                 # resume key
    attachments: tuple = ()             # chat-only files (unused until the attachments PR)
    scope: object = None                # opaque to this layer; the caller's policy closes over it
    cwd: str = None
    max_turns: int = MAX_TURNS
    fresh_prompt: str = None            # prompt to use when `session` cannot be resumed (history replay)


def sdk_available():
    try:
        import claude_agent_sdk  # noqa: F401
    except ImportError:
        return False
    return True


def sdk_info():
    """{available, version, cli, error} — whether the agent backend can run at all."""
    info = {"available": False, "version": None, "cli": shutil.which("claude"), "error": None}
    try:
        import claude_agent_sdk
    except ImportError as e:
        info["error"] = f"claude-agent-sdk not installed ({e}); run `pixi install`"
        return info
    info["available"] = True
    info["version"] = getattr(claude_agent_sdk, "__version__", None)
    return info


def permission_results():
    """(PermissionResultAllow, PermissionResultDeny): the SDK's can_use_tool return types, imported lazily."""
    from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny
    return PermissionResultAllow, PermissionResultDeny


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


def ca_bundle_path(config_dir, pem_source, path=None, now=None):
    """PEM file with the macOS keychain roots for the Node CLI (NODE_EXTRA_CA_CERTS); None when not needed.
    `pem_source()` returns the PEM text (the caller owns keychain access)."""
    preset = os.environ.get("NODE_EXTRA_CA_CERTS")
    if preset:
        return preset
    if sys.platform != "darwin":
        return None
    path = path or os.path.join(config_dir, CA_NAME)
    now = now or time.time()
    try:
        if os.path.isfile(path) and now - os.path.getmtime(path) < CA_MAX_AGE:
            return path
    except OSError:
        pass
    pem = pem_source() if pem_source else ""
    if not pem:
        return None
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(pem)
    except OSError:
        return None
    return path


def agent_env(key, ca_path=None):
    """Extra environment for the claude subprocess (merged over os.environ by the SDK).
    `key=None` means subscription mode: the API key variable is blanked so the CLI falls back to the
    `claude login` credentials (a blank value counts as unset)."""
    env = {"ANTHROPIC_API_KEY": key or "", "CLAUDE_CODE_ENTRYPOINT": "sdk-py",
           # a dashboard started from a Claude Code terminal inherits CLAUDECODE, which makes the
           # CLI refuse to start a nested session
           "CLAUDECODE": "",
           # a shell that routes Claude through a corporate gateway exports these; the key belongs to the
           # public API, so pin it there (the token would win over the key)
           "ANTHROPIC_BASE_URL": "https://api.anthropic.com", "ANTHROPIC_AUTH_TOKEN": ""}
    if ca_path:
        env["NODE_EXTRA_CA_CERTS"] = ca_path
    return env


def build_options(req, key, *, policy_hook, can_use_tool, resume=None, cli=None, ca_path=None, stderr=None):
    from claude_agent_sdk import ClaudeAgentOptions, HookMatcher
    kw = dict(
        cwd=req.cwd, model=llm.model_id(req.model), system_prompt=req.system,
        # no allowed_tools: an allow-list auto-approves before can_use_tool runs; with the default
        # permission mode every call goes through the PreToolUse hook and then the callback
        tools=list(req.tools), disallowed_tools=list(req.disallowed),
        permission_mode="default", can_use_tool=can_use_tool,
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[policy_hook])]},
        setting_sources=[], max_turns=req.max_turns, include_partial_messages=True,
        env=agent_env(key, ca_path), resume=resume or None,
    )
    if req.effort:
        if req.effort not in EFFORTS:
            raise llm.LLMError(f"unknown effort {req.effort!r}; pick one of {', '.join(EFFORTS)}")
        kw["effort"] = req.effort
    if req.skills:
        kw["skills"] = list(req.skills)
    if req.budget:
        kw["max_budget_usd"] = float(req.budget)
    if cli:
        kw["cli_path"] = cli
    if stderr:
        kw["stderr"] = stderr
    return ClaudeAgentOptions(**kw)


def _name(obj):
    return type(obj).__name__


def is_resume_failure(exc):
    text = str(exc).lower()
    return "no conversation found" in text or ("session" in text and ("not found" in text or "expired" in text))


async def stream(req, backend=None, *, key=None, policy_hook=None, can_use_tool=None, usage_sink=None,
                 stop_event=None, log=None, ca_path=None, config_dir=None, pem_source=None):
    """Run one agent turn on the chosen backend. See the module docstring for the yielded events."""
    log = log or (lambda s: None)
    backend = llm.resolve_backend(backend)
    model = llm.model_id(req.model)

    if backend == "batch":
        bid = llm.submit([llm.Request(prompt=req.question, system=req.system, model=req.model,
                                      effort=req.effort or "low")])
        yield ("pending", {"batch_id": bid, "backend": backend, "model": model})
        return
    if backend == "api":
        key = key or llm.api_key()
        if not key:
            yield ("error", {"error": "agent: no API key for the api backend"})
            return
    else:
        key = None
    billing = "subscription" if backend == "subscription" else "api"

    import claude_agent_sdk as sdk
    if ca_path is None and config_dir:
        ca_path = ca_bundle_path(config_dir, pem_source)
    cli = None
    tried_cli_fallback = False
    resume = req.session or None
    prompt = req.question
    stderr_lines = []

    def on_stderr(line):
        stderr_lines.append(line)
        if len(stderr_lines) > 50:
            del stderr_lines[0]
        log(f"  claude: {line.rstrip()}")

    while True:
        yield ("reset", {})
        options = build_options(req, key, policy_hook=policy_hook, can_use_tool=can_use_tool, resume=resume,
                                cli=cli, ca_path=ca_path, stderr=on_stderr)
        result = None
        try:
            async with sdk.ClaudeSDKClient(options) as client:
                await client.query(prompt)
                async for msg in client.receive_response():
                    if stop_event is not None and stop_event.is_set():
                        try:
                            await client.interrupt()
                        except Exception:
                            pass
                        return
                    yield ("message", msg)
                    if _name(msg) == "ResultMessage":
                        result = msg
        except Exception as e:  # SDK errors: ProcessError, CLIConnectionError, CLINotFoundError, …
            name = _name(e)
            if name == "CLINotFoundError" and not tried_cli_fallback and shutil.which("claude"):
                tried_cli_fallback = True
                cli = shutil.which("claude")
                log(f"chat agent: bundled CLI missing, falling back to {cli}")
                continue
            if resume and is_resume_failure(e):
                log("chat agent: previous session not found, starting fresh")
                yield ("notice", {"text": "Previous agent session expired; started a fresh one."})
                resume = None
                prompt = req.fresh_prompt if req.fresh_prompt is not None else req.question
                continue
            detail = str(e).strip()
            tail = " ".join(l.strip() for l in stderr_lines[-3:])
            if tail and tail not in detail:
                detail = f"{detail} — {tail}" if detail else tail
            yield ("error", {"error": f"agent: {detail or name}"})
            return

        if result is None:
            yield ("error", {"error": "agent: the session ended without a result"})
            return
        if getattr(result, "is_error", False):
            yield ("error", {"error": f"agent: {getattr(result, 'result', None) or 'error'}"})
            return
        usage = dict(getattr(result, "usage", None) or {})
        est = getattr(result, "total_cost_usd", None)
        cost = usage_sink(model, usage, est, billing) if usage_sink else est
        yield ("result", {"result": result, "usage": usage, "est_cost_usd": est, "cost_usd": cost,
                          "billing": billing, "model": model})
        return
