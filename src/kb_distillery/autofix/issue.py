"""Open or reuse the `nightly-fail` issue of one failure signature on the engine repo. Never raises.

Dedupe: list the open `nightly-fail` issues and match the hidden signature marker locally (GitHub search does not
index HTML comments). gh runs as the GitHub App (`git.events._gh`) and falls back to the user's own gh login.
"""
import json
import os
import re
import subprocess

from kb_distillery.autofix import LABEL

MARK = "<!-- nightly-sig: {} -->"
UNKNOWN = -1          # the open issues could not be listed: never open a duplicate on a flaky GitHub
MARK_RE = re.compile(r"<!-- nightly-sig: ([0-9a-f]+) -->")


def gh(args, root):
    """`gh args` as the App, then as the user; a CompletedProcess either way. Never from a test (AGENTS.md rule 10)."""
    if "PYTEST_CURRENT_TEST" in os.environ:
        return subprocess.CompletedProcess(["gh", *args], 1, "", "refused: no GitHub calls from tests")
    from kb_distillery.git import events
    cp = events._gh(args, root)
    if cp.returncode == 0:
        return cp
    exe = os.environ.get("GH_BIN", "gh")
    try:
        return subprocess.run([exe, *args], cwd=root, capture_output=True, text=True, check=False, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        return subprocess.CompletedProcess([exe, *args], 1, "", str(e))


def scrub(text):
    """No addresses, account ids or tokens in an issue: emails, long hex/base64 runs and home paths are masked."""
    t = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "<email>", text or "")
    t = re.sub(r"\b[0-9a-f]{16,}\b|\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", "<id>", t, flags=re.I)
    t = re.sub(r"\b(gh[pousr]_|sk-)[A-Za-z0-9_\-.]{10,}", "<token>", t)
    return re.sub(r"/Users/[^/\s]+", "~", t)


def body(failure, run, log_tail="", kb=""):
    started = (run or {}).get("started", "?")
    route = "goes to the fixer" if failure.fixable else f"ticket only ({failure.why})"
    log_tail = ""      # the log may quote private kb content: the owner reads it locally, never in an issue
    parts = [MARK.format(failure.signature),
             f"The nightly run of {started}{f' on kb `{kb}`' if kb else ''} failed at step `{failure.step}`.",
             "", "```", scrub(failure.message).strip()[-3000:], "```", "",
             f"Signature `{failure.signature}`: {route}."]
    if log_tail:
        parts += ["", "<details><summary>Log tail</summary>", "", "```", log_tail.strip()[-4000:], "```", "</details>"]
    return "\n".join(parts)


def find_open(signature, root, run_gh=gh):
    cp = run_gh(["issue", "list", "--label", LABEL, "--state", "open", "--limit", "200",
                 "--json", "number,body"], root)
    if cp.returncode != 0:
        return UNKNOWN
    try:
        items = json.loads(cp.stdout or "[]")
    except ValueError:
        return UNKNOWN
    for it in items:
        m = MARK_RE.search(it.get("body") or "")
        if m and m.group(1) == signature:
            return it.get("number")
    return None


def open_or_reuse(failure, run, root, log_tail="", kb="", run_gh=gh, dry_run=False, comment_again=True):
    """(issue number or None, "created"|"reused"|"dry-run"|"failed: …"). `comment_again=False` reuses an open issue
    without the "seen again" comment (the caller already commented today)."""
    try:
        number = find_open(failure.signature, root, run_gh)
        if number == UNKNOWN:
            return None, "failed: could not list the open nightly-fail issues"
        if dry_run:
            return number, f"dry-run: would {'comment on #%s' % number if number else 'open a new issue'}"
        if number:
            if comment_again:
                run_gh(["issue", "comment", str(number), "--body",
                        f"Seen again in the nightly run of {(run or {}).get('started', '?')}."], root)
            return number, "reused"
        run_gh(["label", "create", LABEL, "--force", "--color", "B60205",
                "--description", "a nightly run failed (kb_distillery.autofix)"], root)
        cp = run_gh(["issue", "create", "--title", failure.title(), "--label", LABEL,
                     "--body", body(failure, run, log_tail, kb)], root)
        m = re.search(r"/issues/(\d+)", cp.stdout or "")
        if cp.returncode != 0 or not m:
            return None, f"failed: {(cp.stderr or cp.stdout or '').strip()[:200]}"
        return int(m.group(1)), "created"
    except Exception as e:  # noqa: BLE001 — the ticket is best effort; the nightly never fails on it
        return None, f"failed: {type(e).__name__}: {e}"


def comment(number, text, root, run_gh=gh):
    if not number:
        return False
    try:
        return run_gh(["issue", "comment", str(number), "--body", text], root).returncode == 0
    except Exception:  # noqa: BLE001
        return False
