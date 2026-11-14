"""Turn the last nightly run (one line of meta/.ops/runs.jsonl) into failures with a stable signature.

A failure is `fixable` (goes to the fixer) only when it can be engine work: the sync step's own error or skip, or a
crash inside a step (an exception name in its error). Hygiene findings are kb data and credential errors need the
owner: those get a ticket only.
"""
import dataclasses
import hashlib
import json
import os
import re

# steps that only summarise others: their "error" status repeats a failure already counted
SUMMARY_STEPS = {"hygiene", "report", "notify"}
CREDENTIAL = re.compile(r"authenticat|unauthori[sz]ed|forbidden|\b401\b|\b403\b|access token|credential|password|"
                        r"api key", re.I)
NETWORK = re.compile(r"could not resolve|connection (refused|reset|timed out)|network is unreachable|timed? ?out|"
                     r"failed to push some refs|remote rejected|\[rejected\]|non-fast-forward|could not read from remote|"
                     r"\b50[234]\b|temporary failure", re.I)
CRASH = re.compile(r"\b[A-Z][A-Za-z]*(Error|Exception)\b|Traceback")


@dataclasses.dataclass
class Failure:
    step: str
    message: str
    fixable: bool
    why: str = ""

    @property
    def signature(self):
        return signature(self.step, self.message)

    def title(self):
        from kb_distillery.autofix.issue import scrub
        line = " ".join(scrub(self.message).split())
        return f"nightly: {self.step}: {line[:80]}{'…' if len(line) > 80 else ''}"


def normalize(text):
    """The message without what changes from night to night: urls, paths, hashes, numbers, dates, extra spaces."""
    t = (text or "").strip().splitlines()[-1] if (text or "").strip() else ""
    t = re.sub(r"https?://\S+", "<url>", t)
    t = re.sub(r"(?<![\w'])(~|/)[\w.\-/@]+", "<path>", t)
    t = re.sub(r"\b[0-9a-f]{7,}\b", "<hex>", t, flags=re.I)
    t = re.sub(r"\d+", "<n>", t)
    return " ".join(t.lower().split())


def signature(step, message):
    return hashlib.sha1(f"{step}|{normalize(message)}".encode()).hexdigest()[:10]


def last_run(root):
    """The newest nightly entry of `<root>/meta/.ops/runs.jsonl`, or None."""
    path = os.path.join(root, "meta", ".ops", "runs.jsonl")
    try:
        with open(path, encoding="utf-8") as f:
            lines = [l for l in f.read().splitlines() if l.strip()]
    except OSError:
        return None
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("kind", "nightly") in ("nightly", "sync"):
            return entry
    return None


def failures(run):
    """The failures of one run entry (empty unless its status is `error`)."""
    if not run or run.get("status") != "error":
        return []
    out = []
    for step in run.get("steps") or []:
        name, err = step.get("name", "?"), (step.get("error") or "").strip()
        if step.get("status") != "error" or not err:
            continue
        if name in SUMMARY_STEPS and not CRASH.search(err):
            continue
        out.append(_classify(name, err))
    seen_sync = any(f.step == "sync" for f in out)
    for f in (run.get("hygiene") or {}).get("findings") or []:
        if f.get("severity") != "error":
            continue
        if f.get("kind") == "sync-skipped" and seen_sync:
            continue                                  # the same failure as the sync step's error
        kind = f.get("kind", "?")      # the detail names kb pages: the issue carries only the finding's kind
        out.append(Failure(f"hygiene:{kind}", f"hygiene finding {kind} (details in the nightly mail)", False,
                           "a kb data finding"))
    uniq = {}
    for f in out:
        uniq.setdefault(f.signature, f)
    return list(uniq.values())


def _classify(step, err):
    if CREDENTIAL.search(err):
        return Failure(step, err, False, "a credential problem: the owner fixes it")
    if NETWORK.search(err):
        return Failure(step, err, False, "network or remote: usually passes on the next night")
    if step == "sync" or CRASH.search(err):
        return Failure(step, err, True, "engine: the sync or a crash")
    return Failure(step, err, False, "not an engine crash")
