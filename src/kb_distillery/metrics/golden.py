"""Golden tasks: a fixed set of real workflows re-run before and after each change, graded by checks + a judge.

    pixi run metrics -- golden list
    pixi run metrics -- golden run [<task>…] --label baseline [--repeat 1] [--dry-run]

Each run gets a throwaway local clone of this vault on `main` at a pinned commit, outside the vault
(`~/local-workspace/agent-metrics/golden/<run>/<task>/kb-golden-<task>`) — on main because knowledge
steps (kb(digest), kb(catalog), kb(refine)) only commit there — with the primary checkout's `.pixi`,
`web/node_modules` and untracked raw files symlinked in (files a task moves are real copies), and:

- `origin` is a local bare sink seeded with the commit, plus `remote.origin.pushurl` → sink, `KB_NO_PUSH=1`
  and `gh` pointed at an empty config — a golden run can never reach GitHub or the share site;
- the agent run headless: `claude -p "[golden:<id>] <prompt>" --model --effort --permission-mode auto`,
  stdin closed (a nested `claude -p` waits on it otherwise). Its JSON result is the official
  usage: `total_cost_usd`, `modelUsage`, `num_turns`, `duration_ms`;
- then the task's `checks` (shell commands, exit 0 = pass) and the judge (kb_distillery.metrics.judge) run.

The record (golden.jsonl) holds the cost, the checks, both judge grades and whether they disagree.
Tasks live in meta/ops/golden.toml; changing a task makes old runs of it incomparable, so bump its `v`.
"""
import datetime
import json
import os
import shutil
import subprocess
import time
import tomllib
import uuid

from kb_distillery.git.ship import primary_checkout
from kb_distillery.metrics import judge, store
from kb_distillery.metrics.sessions import parse_session, PROJECTS_DIR
from kb_distillery.paths import vault_root

TASKS_FILE = os.path.join("meta", "ops", "golden.toml")
RUNS_DIR = os.path.expanduser("~/local-workspace/agent-metrics/golden")
LINKED = (".pixi", "web/node_modules")
AGENT_TIMEOUT = 75 * 60   # a busy machine (parallel sessions running test suites) slows ship gates a lot
CHECK_TIMEOUT = 15 * 60


def load_tasks(root=None):
    with open(os.path.join(root or vault_root(), TASKS_FILE), "rb") as f:
        cfg = tomllib.load(f)
    defaults = cfg.get("defaults", {})
    return {t["id"]: {**defaults, **t} for t in cfg.get("task", [])}, cfg.get("judge", {})


def _git(args, cwd, check=True):
    return subprocess.run(["git", *args], cwd=cwd, check=check, capture_output=True, text=True)


def make_workspace(task, run_id, ref, primary):
    """A local clone on `main` at `ref` whose `origin` is a bare sink seeded with that commit — knowledge
    steps commit on main and push only into the sink, `ship` finds origin/main. Returns (repo, sink)."""
    base = os.path.join(RUNS_DIR, run_id, task["id"])
    repo, sink = os.path.join(base, f"kb-golden-{task['id']}"), os.path.join(base, "push-sink.git")
    os.makedirs(base, exist_ok=True)
    _git(["init", "-q", "--bare", sink], cwd=base)
    _git(["clone", "-q", "--shared", "--no-checkout", primary, repo], cwd=base)
    _git(["checkout", "-q", "-B", "main", ref], cwd=repo)
    _git(["remote", "set-url", "origin", sink], cwd=repo)
    for rel in LINKED:
        src, dst = os.path.join(primary, rel), os.path.join(repo, rel)
        if os.path.exists(src) and not os.path.lexists(dst):
            os.symlink(src, dst)
    link_raw(primary, repo)
    for rel in task.get("copy", []):            # files the task may move or edit: real copies, never links
        src, dst = os.path.join(primary, rel), os.path.join(repo, rel)
        if os.path.lexists(dst):
            os.unlink(dst)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
    for cmd in task.get("setup", []):
        subprocess.run(cmd, shell=True, cwd=repo, check=True, capture_output=True, text=True, env=_env(sink, repo))
    # seed the sink only now: origin/main must include the setup (a replayed bug), or `ship start --worktree`
    # branches from the fixed code
    _git(["push", "-q", "origin", "main"], cwd=repo)
    _git(["fetch", "-q", "origin"], cwd=repo)
    return repo, sink


def work_dir(repo, base):
    """Where the agent's result is: the clone, or the nested `infra/*` worktree it made with
    `ship start --worktree` (the newest one with commits past `base`)."""
    out = _git(["worktree", "list", "--porcelain"], cwd=repo, check=False).stdout
    best, best_t = repo, None
    for block in out.strip().split("\n\n"):
        lines = dict(l.split(" ", 1) for l in block.splitlines() if " " in l)
        path, branch = lines.get("worktree"), lines.get("branch", "")
        if not path or os.path.realpath(path) == os.path.realpath(repo) or not branch.startswith("refs/heads/infra/"):
            continue
        if _git(["rev-list", "--count", f"{base}..HEAD"], cwd=path, check=False).stdout.strip() in ("", "0") \
                and not _git(["status", "--porcelain"], cwd=path, check=False).stdout.strip():
            continue
        t = _git(["log", "-1", "--format=%ct"], cwd=path, check=False).stdout.strip()
        if best_t is None or t > best_t:
            best, best_t = path, t
    return best


def link_raw(primary, repo):
    """Symlink the primary's gitignored raw/ files (PDFs…) into the clone, read-only use."""
    out = _git(["ls-files", "-z", "--others", "--ignored", "--exclude-standard", "--", "raw/"], cwd=primary, check=False)
    made = 0
    for rel in filter(None, out.stdout.split("\0")):
        dst = os.path.join(repo, rel)
        if not os.path.lexists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.symlink(os.path.join(primary, rel), dst)
            made += 1
    return made


def remove_workspace(repo, primary=None):
    """The clone, its sink and any worktrees a task made inside it are all under one directory."""
    shutil.rmtree(os.path.dirname(repo), ignore_errors=True)


SCRUBBED = ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY",   # subscription only
            "KB_ROOT", "KB", "KB_BASES_DIR", "PYTHONPATH", "VIRTUAL_ENV", "PYTHONHOME")
SCRUBBED_PREFIXES = ("PIXI_", "CONDA_")   # the runner's own `pixi run` activation must not leak in


def _env(sink, repo):
    """The run's environment: this clone is the vault (KB_ROOT) and its own code is imported
    (PYTHONPATH beats the shared env's editable install, which points at another checkout)."""
    env = {k: v for k, v in os.environ.items() if k not in SCRUBBED and not k.startswith(SCRUBBED_PREFIXES)}
    env["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep) if "/.pixi/envs/" not in p)
    gh_dir = os.path.join(os.path.dirname(repo), "gh-empty")
    os.makedirs(gh_dir, exist_ok=True)
    env.update({
        # relative on purpose: whichever checkout the agent stands in (the clone, or a worktree it made
        # with `ship start --worktree`) imports its own code and so is its own vault; outside one, kb
        # fails to import instead of writing to some other vault. No KB_ROOT for the same reason.
        "PYTHONPATH": "src",
        "KB_NO_PUSH": "1", "KB_GOLDEN": "1", "GH_CONFIG_DIR": gh_dir, "GH_TOKEN": "golden-run-no-github",
        "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "remote.origin.pushurl", "GIT_CONFIG_VALUE_0": sink,
    })
    return env


def run_agent(task, repo, env):
    prompt = f"[golden:{task['id']}] {task['prompt'].strip()}"
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--model", task["model"],
           "--permission-mode", task.get("permission_mode", "auto")]
    if task.get("effort"):
        cmd += ["--effort", task["effort"]]
    t0 = time.monotonic()
    try:
        cp = subprocess.run(cmd, cwd=repo, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                            timeout=task.get("timeout", AGENT_TIMEOUT))
        out = json.loads(cp.stdout or "{}")
    except subprocess.TimeoutExpired:
        out = {"is_error": True, "result": "timeout"}
    except ValueError:
        out = {"is_error": True, "result": (cp.stdout or cp.stderr)[-2000:]}
    out["_wall_s"] = round(time.monotonic() - t0, 1)
    return out


def run_checks(task, repo, env):
    results = []
    for cmd in task.get("checks", []):
        try:
            cp = subprocess.run(cmd, shell=True, cwd=repo, env=env, stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=CHECK_TIMEOUT)
            results.append({"cmd": cmd, "ok": cp.returncode == 0, "tail": (cp.stdout + cp.stderr)[-1500:]})
        except subprocess.TimeoutExpired:
            results.append({"cmd": cmd, "ok": False, "tail": "timeout"})
    return results


def diff_of(repo, ref):
    """Everything the agent changed: commits since `ref` plus the working tree, raw/ binaries excluded."""
    skip = [":!raw", ":!index.md", ":!meta/corpus.tsv", *(f":!{p}" for p in LINKED)]
    _git(["add", "-A", "-N", "--", ".", *skip], cwd=repo, check=False)
    return _git(["diff", ref, "--", ".", *skip], cwd=repo, check=False).stdout


def _session_record(session_id, repo):
    slug = "".join(c if c.isalnum() else "-" for c in os.path.realpath(repo))
    p = os.path.join(PROJECTS_DIR, slug, f"{session_id}.jsonl")
    return parse_session(p) if session_id and os.path.exists(p) else None


def run_task(task, judge_cfg, run_id, label, ref, primary, dry_run=False, keep=False):
    sha = _git(["rev-parse", ref], cwd=primary).stdout.strip()
    rec = {"run": run_id, "label": label, "task": task["id"], "v": task.get("v", 1), "kind": task.get("kind"),
           "sha": sha, "model": task["model"], "effort": task.get("effort"),
           "started": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    if dry_run:
        print(f"[dry-run] {task['id']}: {task['model']}/{task.get('effort')} at {sha[:8]}, "
              f"{len(task.get('checks', []))} checks")
        return rec
    repo, sink = make_workspace(task, run_id, sha, primary)
    env = _env(sink, repo)
    try:
        base = _git(["rev-parse", "HEAD"], cwd=repo).stdout.strip()   # after setup (a replayed bug is a commit)
        env["GOLDEN_BASE"] = base                                    # checks diff against it
        out = run_agent(task, repo, env)
        where = work_dir(repo, base)                                 # the clone, or the worktree the agent made
        checks = run_checks(task, where, env)
        diff = diff_of(where, base)
        sess = _session_record(out.get("session_id"), repo)
        grade = judge.grade(task, out.get("result") or "", diff, checks, judge_cfg, env=env)
        rec.update({
            "session": out.get("session_id"), "ok": not out.get("is_error"),
            "usd": round(out.get("total_cost_usd") or 0, 4), "turns": out.get("num_turns"),
            "minutes": round((out.get("duration_ms") or out["_wall_s"] * 1000) / 60000, 1),
            "models": {m: {"in": u.get("inputTokens", 0), "cw": u.get("cacheCreationInputTokens", 0),
                           "cr": u.get("cacheReadInputTokens", 0), "out": u.get("outputTokens", 0)}
                       for m, u in (out.get("modelUsage") or {}).items()},
            "first_context": (sess or {}).get("first_context"), "subagents": (sess or {}).get("subagents"),
            "checks": [{"cmd": c["cmd"], "ok": c["ok"]} for c in checks],
            "diff_lines": diff.count("\n"), "judge": grade,
            "passed": all(c["ok"] for c in checks) and bool(grade.get("pass")) and not out.get("is_error"),
        })
        store.append("golden.jsonl", rec)
        return rec
    finally:
        if not keep:
            remove_workspace(repo, primary)


def run(task_ids=None, label="adhoc", ref="HEAD", repeat=1, dry_run=False, keep=False, root=None):
    tasks, judge_cfg = load_tasks(root)
    primary = primary_checkout(root or vault_root())
    chosen = [tasks[t] for t in task_ids] if task_ids else [t for t in tasks.values() if t.get("core", True)]
    run_id = datetime.datetime.now().strftime("%Y%m%d-%H%M") + "-" + uuid.uuid4().hex[:4]
    ref = _git(["rev-parse", ref], cwd=primary).stdout.strip()   # pinned once: main may move mid-run
    print(f"golden run {run_id} ({label}) at {ref[:8]}", flush=True)
    out = []
    for i in range(repeat):
        for task in chosen:   # each pass in its own directory: a second clone into the same path fails
            rec = run_task(task, judge_cfg, f"{run_id}-r{i + 1}", label, ref, primary, dry_run=dry_run, keep=keep)
            out.append(rec)
            if not dry_run:
                j = rec["judge"]
                print(f"{task['id']:24} {'PASS' if rec['passed'] else 'FAIL'}  ${rec['usd']:.2f}  "
                      f"{rec['minutes']}m  judge {j.get('score')}{' ⚑' if j.get('flagged') else ''}  "
                      f"checks {sum(c['ok'] for c in rec['checks'])}/{len(rec['checks'])}", flush=True)
    return out
