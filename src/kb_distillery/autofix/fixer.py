"""The fixer: one attempt per failure signature. Sonnet works in an `infra/nightly-fix-<sig>` worktree and may consult
an Opus `advisor` subagent; then the script, not the model, runs the steps that matter:

  ship commit (local gates)  ->  Opus review of the committed diff (llm.ask)  ->  ship review --pass
  ->  diff gate (gate.py) + review concerns  ->  ship pr [--hold]  ->  ship merge (only when nothing held it)

Every outcome is commented on the issue. Billing: every call goes through `kb_distillery.llm` on
`$KB_AUTOFIX_BACKEND` (default `api`; `subscription` also works; `batch` cannot run live tools, so only the review
call falls back to `api` there). Spend: `$KB_AUTOFIX_BUDGET` USD per attempt (default 5, the SDK's hard ceiling) and
`$KB_AUTOFIX_DAILY_CAP` USD per day (default 10). `$KB_AUTOFIX_GUARD` (optional) names a machine-load check run as
`<it> status --want 1`; "does NOT fit" waits, up to an hour, then the attempt is postponed to the next night.
"""
import asyncio
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import time

from kb_distillery.autofix import gate, issue

MODEL = "sonnet"
ADVISOR = "opus"
MAX_TURNS = 80
_OPT = r"(\s+-\S+(\s+[^\s-]\S*)?)*"     # options between the tool and its subcommand: git -C . commit
DENY_BASH = re.compile(
    r"(^|[^\w.-])git" + _OPT + r"\s+(commit|push|merge|rebase|reset|tag|checkout|switch|stash|branch|worktree|remote|"
    r"config|clean|revert|cherry-pick|am|apply|update-ref|filter-branch)\b"
    r"|(^|[^\w.-])gh\s|(^|[^\w.-])(curl|wget|ssh|scp|sudo|launchctl|crontab|chmod)\s"
    r"|(^|[^\w.-])rm\s+(-[a-z]*r|--recursive)|pip\s+install|npm\s+(install|i)\b|pixi\s+(add|install|global)"
    r"|\bship\b.*\b(commit|pr|merge|approve|start|prune|review)\b|\bshare\b.*\b(deploy|rollback|snapshot)\b"
    r"|subprocess|os\.system|knowledge/|KB_DISTILLERY_HOME|GH_TOKEN|GITHUB_TOKEN")
DENY_EDIT = re.compile(r"(^|/)(wiki|raw|think)/|^\.github/|^\.git/|^\.claude/")

SYSTEM = """You fix one failure of kb-distillery's nightly job, in the engine repository checked out in your working
directory (a worktree on its own branch). You never write to a knowledge base (wiki/, raw/, think/) and you never run
git writes, gh, ship or deploys: the script around you commits, reviews, opens the PR and decides whether it merges.

Work like this:
1. Reproduce or locate the cause from the error and the code. Read AGENTS.md first.
2. Make the smallest change that fixes the cause in the engine. Add or adjust a test that would have caught it.
   Never weaken, skip or delete a test.
3. Run the tests that cover the change: `python -m pytest <paths> -q -n 4` and `ruff check <files>` (both are on
   your PATH; KB_APP_CONFIG already points at no config).
4. Before you finish, ask the `advisor` subagent (Opus) to check the cause and your diff, and act on what it says.

If the cause is in a knowledge base's data, in the owner's credentials, in the machine's setup outside this repository,
or you cannot find a safe fix, change nothing and say so.

End your last message with exactly one line:
RESULT: fixed - <one-line summary of the change>
RESULT: not-engine - <why>
RESULT: gave-up - <why>
"""

ADVISOR_SPEC = {
    "description": "Senior reviewer (Opus). Ask before you finish: is the diagnosis right, is the diff the smallest "
                   "safe fix, is the test meaningful?",
    "prompt": "You are a senior reviewer of kb-distillery (read AGENTS.md). You get a nightly failure, a diagnosis and "
              "a diff. Read the code you need, then answer briefly: agree, or name the specific problem and the "
              "better fix. You never edit files.",
    "tools": ["Read", "Grep", "Glob"],
    "model": "opus",
}

REVIEW = """Review this automated fix of a nightly failure in kb-distillery. Failure (step `{step}`):
{error}

Diff:
{diff}

Answer with one JSON object only: {{"verdict": "pass" | "concerns", "summary": "<one line>", "concerns": ["..."]}}.
"pass" only when the change fixes the cause, is minimal, adds or keeps a meaningful test and changes nothing unrelated."""


def backend():
    return os.environ.get("KB_AUTOFIX_BACKEND") or "api"


def budget():
    return float(os.environ.get("KB_AUTOFIX_BUDGET") or 5)


def daily_cap():
    return float(os.environ.get("KB_AUTOFIX_DAILY_CAP") or 10)


def tool_path():
    """This interpreter's bin (ruff, pytest) and pixi's bin first: launchd's PATH has neither."""
    extra = [os.path.dirname(sys.executable), os.path.expanduser("~/.pixi/bin")]
    return os.pathsep.join([*extra, os.environ.get("PATH", "")])


def child_env(tokens=True):
    env = dict(os.environ, PATH=tool_path(), KB_APP_CONFIG="/nonexistent/app.toml", KB_SHARE_AUTODEPLOY="0")
    if not tokens:
        for k in ("GH_TOKEN", "GITHUB_TOKEN", "KB_GIT_TOKEN"):
            env.pop(k, None)
    return env


def ship(args, cwd, timeout=3600):
    """`python -m kb_distillery.git.ship args` with this interpreter (no pixi on a launchd PATH needed)."""
    try:
        return subprocess.run([sys.executable, "-m", "kb_distillery.git.ship", *args], cwd=cwd, capture_output=True,
                              text=True, check=False, timeout=timeout, env=child_env())
    except subprocess.TimeoutExpired as e:
        return subprocess.CompletedProcess(e.cmd, 124, e.stdout or "", f"timed out after {timeout}s")


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False).stdout


def tail(cp, n=25):
    text = ((cp.stdout or "") + (cp.stderr or "")).strip().splitlines()
    return "\n".join(text[-n:])


def decide(name, inp, wt):
    """(allow, reason) for one tool call of the fixer agent."""
    inp = inp if isinstance(inp, dict) else {}
    if name in ("Read", "Glob", "Grep", "Task", "Agent", "TodoWrite"):
        return True, ""
    if name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        path = os.path.realpath(os.path.join(wt, inp.get("file_path") or inp.get("notebook_path") or ""))
        root = os.path.realpath(wt)
        if not path.startswith(root + os.sep):
            return False, "edit outside the worktree"
        rel = os.path.relpath(path, root)
        if DENY_EDIT.search(rel):
            return False, f"{rel}: knowledge, CI, git or agent settings are not the fixer's to edit"
        return True, ""
    if name == "Bash":
        cmd = inp.get("command") or ""
        if DENY_BASH.search(cmd):
            return False, "git writes, gh, ship, network, installs and deletes belong to the script, not the fixer"
        return True, ""
    return False, f"{name} is not available to the fixer"


def _hooks(wt):
    from kb_distillery.llm import agent as llm_agent

    async def hook(input_data, tool_use_id, context):
        ok, why = decide(input_data.get("tool_name"), input_data.get("tool_input"), wt)
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                       "permissionDecision": "allow" if ok else "deny",
                                       "permissionDecisionReason": why or "fixer policy"}}

    async def can_use_tool(tool_name, tool_input, context):
        allow, deny = llm_agent.permission_results()
        ok, why = decide(tool_name, tool_input, wt)
        return allow(updated_input=tool_input) if ok else deny(message=why)
    return hook, can_use_tool


def run_agent(prompt, wt, log=print):
    """(final text, cost USD, error) of one fixer session."""
    from kb_distillery.llm import agent as llm_agent
    req = llm_agent.AgentRequest(question=prompt, model=MODEL, system=SYSTEM, effort="high", cwd=wt,
                                 tools=("Read", "Edit", "Write", "Glob", "Grep", "Bash", "Task", "Agent"),
                                 agents={"advisor": ADVISOR_SPEC}, budget=budget(), max_turns=MAX_TURNS)
    hook, can_use = _hooks(wt)
    saved = dict(os.environ)
    os.environ.clear()
    os.environ.update(child_env(tokens=False))      # the agent's CLI inherits this: tool PATH, no GitHub token

    async def go():
        texts, cost, err = [], 0.0, ""
        async for kind, payload in llm_agent.stream(req, backend(), policy_hook=hook, can_use_tool=can_use, log=log):
            if kind == "reset":
                texts = []
            elif kind == "message" and type(payload).__name__ == "AssistantMessage":
                for block in getattr(payload, "content", None) or []:
                    if type(block).__name__ == "TextBlock":
                        texts.append(block.text)
                    elif type(block).__name__ == "ToolUseBlock":
                        log(f"  tool: {block.name} {json.dumps(block.input)[:160]}")
            elif kind == "result":
                cost = payload.get("cost_usd") or payload.get("est_cost_usd") or 0.0
                res = getattr(payload.get("result"), "result", None)
                if res:
                    texts.append(res)
            elif kind == "error":
                err = payload.get("error", "error")
            elif kind == "pending":
                err = "the batch backend cannot run a live fixer: use api or subscription"
        return "\n".join(texts), float(cost or 0), err
    try:
        return asyncio.run(go())
    finally:
        os.environ.clear()
        os.environ.update(saved)


def outcome_line(text):
    m = None
    for m in re.finditer(r"^RESULT:\s*(fixed|not-engine|gave-up)\s*[-:]\s*(.*)$", text or "", re.M):
        pass
    return (m.group(1), m.group(2).strip()) if m else ("gave-up", "the fixer ended without a RESULT line")


def review(failure, diff):
    """(passed, summary, concerns) from one Opus call through kb_distillery.llm."""
    from kb_distillery import llm
    r = llm.ask(REVIEW.format(step=failure.step, error=failure.message[-2000:], diff=diff[-30000:]),
                backend=backend() if backend() != "batch" else "api", model=ADVISOR, effort="high", max_tokens=4000)
    if not r.ok:
        return False, f"advisor review failed: {r.error[:200]}", [r.error[:200]], 0.0
    data = llm.json_object(r.text) or {}
    passed = data.get("verdict") == "pass"
    return passed, str(data.get("summary") or "no summary")[:200], [str(c)[:300] for c in data.get("concerns") or []], r.usd


def scope_of(paths):
    for p in paths:
        m = re.match(r"src/kb_distillery/([a-z_]+)/", p)
        if m:
            return m.group(1).replace("_", "-")
    return "ops"


def wait_for_room(log=print, tries=6, pause=600):
    guard = os.environ.get("KB_AUTOFIX_GUARD")
    if not guard or not os.path.exists(guard):
        return True
    for i in range(tries):
        cp = subprocess.run([guard, "status", "--want", "1"], capture_output=True, text=True, check=False)
        if "does NOT fit" not in (cp.stdout or ""):
            return True
        log(f"autofix: machine busy, waiting ({i + 1}/{tries})")
        time.sleep(pause)
    return False


def spent_today(state, today):
    return sum(float((e.get("attempt") or {}).get("usd") or 0) for e in state.values()
               if (e.get("attempt") or {}).get("at", "").startswith(today))


def fix(failure, number, state, root, save, log=print):
    """One attempt for `failure` (issue `number`). `save()` persists `state`. Returns a short outcome string."""
    sig = failure.signature
    entry = state.setdefault(sig, {})
    if entry.get("attempt"):
        return f"skipped: already attempted on {entry['attempt'].get('at', '?')[:10]} (one attempt per signature)"
    today = datetime.date.today().isoformat()
    if spent_today(state, today) >= daily_cap():
        return f"skipped: daily cap of {daily_cap():.2f} USD spent"
    if not wait_for_room(log):
        return "postponed: the machine stayed busy"

    feature = f"nightly-fix-{sig}"
    branch = f"infra/{feature}"
    attempt = {"at": datetime.datetime.now().isoformat(timespec="seconds"), "branch": branch, "usd": 0.0}

    def finish(result, text, counted=True):
        """Record the outcome; an infrastructure failure before the agent really ran does not use up the attempt."""
        if counted:
            entry["attempt"] = {**attempt, "result": result}
        else:
            entry.setdefault("postponed", []).append({"at": attempt["at"], "result": result})
        save()
        issue.comment(number, text, root)
        return result

    cp = ship(["start", feature, "--worktree"], root, timeout=600)
    m = re.search(r"worktree ready: (\S+) on ", cp.stdout or "")
    if cp.returncode != 0 or not m:
        return finish("failed: ship start", f"The fixer could not start a worktree:\n```\n{tail(cp)}\n```",
                      counted=False)
    wt = m.group(1)

    def drop(result, text, counted=True):
        ship(["prune", "--drop", branch], root, timeout=300)
        return finish(result, text, counted)

    prompt = (f"The nightly job failed at step `{failure.step}` with:\n\n```\n{failure.message[-3000:]}\n```\n\n"
              f"Issue #{number} has the log tail. Find the cause in this engine checkout and fix it.")
    text, usd, err = run_agent(prompt, wt, log=log)
    attempt["usd"] = round(usd, 4)
    if err:
        return drop(f"failed: {err[:120]}", f"The fixer stopped: {err[:500]} (spent {usd:.2f} USD).",
                    counted=usd > 0.5)
    kind, summary = outcome_line(text)
    changed = [l[3:].split(" -> ")[-1] for l in git(wt, "status", "--porcelain", "--untracked-files=all").splitlines()
               if len(l) > 3]
    if kind != "fixed" or not changed:
        return drop(f"no fix: {kind}", f"The fixer made no change ({kind}): {summary}\n\nSpent {usd:.2f} USD.")

    scope = scope_of(changed)
    subject = f"fix({scope}): nightly {failure.step} failure"[:70]
    cp = ship(["commit", subject], wt)
    if cp.returncode != 0:
        return drop("failed: commit gates", f"The fix did not pass the commit gates:\n```\n{tail(cp)}\n```\n"
                                            f"Fixer summary: {summary}")

    diff = git(wt, "diff", "origin/main...HEAD")
    passed, rsummary, concerns, rusd = review(failure, diff)
    attempt["usd"] = round(usd + rusd, 4)
    if passed:
        ship(["review", "--pass", f"opus advisor: {rsummary}"[:200]], wt, timeout=120)

    why = gate.measure(wt)
    if not passed:
        why.append("the advisor review raised concerns: " + "; ".join(concerns)[:300])
    held = bool(why)
    fd, notes = tempfile.mkstemp(prefix="autofix-notes-", suffix=".md")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(f"Automated fix of the nightly failure in #{number} (signature `{sig}`).\n\n"
                f"Fixer: {summary}\n\nAdvisor (Opus): {rsummary}\n\n"
                + ("Held for the owner:\n" + "".join(f"- {w}\n" for w in why) if held else
                   "Diff gate: small, merges once CI is green.\n")
                + f"\nCloses #{number}\n")
    args = ["pr", "--title", subject, "--notes", notes] + (["--hold"] if held else [])
    if not passed:
        args += ["--no-review", f"opus advisor raised concerns: {rsummary}"[:200]]
    cp = ship(args, wt, timeout=900)
    os.unlink(notes)
    pr = re.search(r"https://github\.com/\S+/pull/(\d+)", (cp.stdout or "") + (cp.stderr or ""))
    if cp.returncode != 0 or not pr:
        return finish("failed: ship pr", f"The fix is on `{branch}` but the PR did not open:\n```\n{tail(cp)}\n```")
    url = pr.group(0)
    attempt.update(pr=int(pr.group(1)), held=held)
    if held:
        return finish(f"held: {url}", f"Fix proposed in {url}, **held for your approval**:\n"
                      + "".join(f"- {w}\n" for w in why) + f"\nSpent {attempt['usd']:.2f} USD.")
    cp = ship(["merge"], wt, timeout=3600)
    merged = cp.returncode == 0
    return finish(f"{'merged' if merged else 'merge pending'}: {url}",
                  f"Fix {url} {'merged' if merged else 'opened; the merge did not finish: ' + tail(cp, 8)}. "
                  f"Spent {attempt['usd']:.2f} USD.")
