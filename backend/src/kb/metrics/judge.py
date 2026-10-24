"""LLM judge for golden runs: a fixed rubric, a fixed model, graded twice; disagreement is flagged.

The judge runs `claude -p` on the subscription (no API key) from an empty directory, so no vault
instructions leak into the grade, and sees only: the task, its reference notes, the hard-check results,
the agent's final reply and its diff (capped). It answers one JSON object:

    {"correct": 1-5, "complete": 1-5, "conventions": 1-5, "pass": true|false, "why": "…"}

`score` is the mean of the three criteria. The two grades disagree when their scores differ by ≥ 1 or
their `pass` differs — those runs are flagged for a human look; otherwise the mean is kept.
"""
import json
import os
import re
import subprocess
import tempfile

DIFF_CAP = 60_000
REPLY_CAP = 12_000
RUBRIC = """You grade one run of a coding/knowledge agent on a fixed task in a personal research
knowledge base (a Karpathy-style LLM wiki: wiki/ pages, raw/ sources, a Python backend and a React app).

Score each criterion 1-5 (5 = what a careful expert would produce, 3 = usable with fixes, 1 = wrong):
- correct: the result is right — facts match the sources, code works, nothing broken or invented.
- complete: everything the task asked for is done, nothing required is missing.
- conventions: it follows the vault's rules as stated in the task and reference (file names, page
  sections, commit/ops flow, read-only when asked) and changes nothing it was not asked to change.
pass = true only if a maintainer would accept this run as is (minor style nits allowed).
Hard checks are ground truth: a failed check means correct <= 2 and pass = false, unless the reference
says that check is expected to fail.

Reply with ONLY one JSON object, no prose before or after:
{"correct": n, "complete": n, "conventions": n, "pass": true|false, "why": "<= 3 sentences"}"""


def _prompt(task, reply, diff, checks):
    check_lines = "\n".join(f"- {'PASS' if c['ok'] else 'FAIL'} `{c['cmd']}`\n{c['tail'][-600:] if not c['ok'] else ''}"
                            for c in checks) or "(none)"
    if len(diff) > DIFF_CAP:
        diff = diff[:DIFF_CAP] + f"\n… [diff cut: {len(diff) - DIFF_CAP} more chars]"
    return (f"{RUBRIC}\n\n## Task\n{task['prompt'].strip()}\n\n## Reference (what a good run does)\n"
            f"{task.get('reference', '(none)').strip()}\n\n## Hard checks\n{check_lines}\n\n"
            f"## Agent's final reply\n{reply[-REPLY_CAP:]}\n\n## Agent's diff\n```diff\n{diff or '(no changes)'}\n```")


def _parse(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        g = json.loads(m.group(0))
        g["score"] = round(sum(float(g[k]) for k in ("correct", "complete", "conventions")) / 3, 2)
        g["pass"] = bool(g.get("pass"))
        return g
    except (ValueError, KeyError, TypeError):
        return None


def _ask(prompt, cfg, env):
    with tempfile.TemporaryDirectory(prefix="kb-judge-") as cwd:
        cmd = ["claude", "-p", prompt, "--output-format", "json", "--model", cfg.get("model", "sonnet"),
               "--effort", cfg.get("effort", "medium"), "--tools", "", "--strict-mcp-config",
               "--no-session-persistence"]
        try:
            cp = subprocess.run(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, timeout=cfg.get("timeout", 600))
            out = json.loads(cp.stdout or "{}")
        except (subprocess.TimeoutExpired, ValueError):
            return None, 0.0
    return _parse(out.get("result")), out.get("total_cost_usd") or 0.0


def grade(task, reply, diff, checks, cfg, env=None):
    prompt = _prompt(task, reply, diff, checks)
    grades, cost = [], 0.0
    for _ in range(cfg.get("samples", 2)):
        g, c = _ask(prompt, cfg, env or dict(os.environ))
        cost += c
        if g:
            grades.append(g)
    if not grades:
        return {"score": None, "pass": False, "flagged": True, "why": "judge returned no grade", "usd": round(cost, 4)}
    scores, passes = [g["score"] for g in grades], {g["pass"] for g in grades}
    flagged = len(grades) < cfg.get("samples", 2) or max(scores) - min(scores) >= 1 or len(passes) > 1
    return {"score": round(sum(scores) / len(scores), 2), "pass": all(passes) if not flagged else False,
            "flagged": flagged, "grades": grades, "usd": round(cost, 4)}
