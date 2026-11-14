"""The diff gate: a script, not the model, decides whether an automated fix may merge itself.

`reasons(...)` lists why a diff is dramatic; an empty list means it may merge once CI is green. Any reason means
the PR opens with `--hold` and the fixer never calls `ship merge` on it.
"""
import re
import subprocess

MAX_LINES = 80
MAX_FILES = 5

# (prefix or pattern, why): touching any of these needs the owner
SENSITIVE = [
    (re.compile(r"^src/kb_distillery/vault/schema\.py$"), "schema"),
    (re.compile(r"^src/kb_distillery/migrations/"), "migrations"),
    (re.compile(r"(^|/)(wiki|raw|think)/"), "knowledge paths (wiki/raw/think)"),
    (re.compile(r"^\.github/"), "CI workflows"),
    (re.compile(r"^scripts/|^src/kb_distillery/git/"), "scripts, git hooks or ship"),
    (re.compile(r"^src/kb_distillery/(lint|llm|kits)/"), "lint, the LLM gateway (billing) or kits"),
    (re.compile(r"(^|/)(ruff\.toml|\.importlinter|setup\.cfg|conftest\.py)$"), "test or lint config"),
    (re.compile(r"^\.claude/"), "agent settings"),
    (re.compile(r"^examples/launchd/"), "launchd jobs"),
    (re.compile(r"^src/kb_distillery/(publish|hosting)/|wrangler|(^|/)deploy"), "deploy"),
    (re.compile(r"^(pixi\.toml|pixi\.lock|pyproject\.toml)$"), "dependencies or build config"),
    (re.compile(r"flags\.toml$"), "feature flags"),
    (re.compile(r"^src/kb_distillery/autofix/"), "the auto-fixer itself"),
]
WEAKEN = re.compile(r"pytest\.mark\.(skip|xfail)|pytest\.skip\(|@unittest\.skip|\.skip\(|it\.skip|test\.skip")


def reasons(numstat, name_status, patch=""):
    """`numstat`: `git diff --numstat` text; `name_status`: `git diff --name-status`; `patch`: the unified diff."""
    why = []
    files, lines = [], 0
    for row in (numstat or "").splitlines():
        parts = row.split("\t")
        if len(parts) < 3:
            continue
        added, deleted, path = parts[0], parts[1], parts[-1]
        files.append(path)
        if added == "-" and deleted == "-":
            why.append(f"binary file {path}")
        lines += (int(added) if added.isdigit() else 0) + (int(deleted) if deleted.isdigit() else 0)
    if len(files) > MAX_FILES:
        why.append(f"{len(files)} files (more than {MAX_FILES})")
    if lines > MAX_LINES:
        why.append(f"{lines} changed lines (more than {MAX_LINES})")
    for row in (name_status or "").splitlines():
        parts = row.split("\t")
        if parts and parts[0][:1] in ("D", "R"):
            why.append(f"deletes {parts[-1]}")
    hit = {}
    for path in files:
        for pattern, label in SENSITIVE:
            if pattern.search(path):
                hit.setdefault(label, path)
    why += [f"touches {label} ({path})" for label, path in hit.items()]
    why += _weakened_tests(patch)
    return why


def _weakened_tests(patch):
    why, current, removed_asserts, added_asserts = [], "", 0, 0
    for line in (patch or "").splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else line[4:]
            continue
        if not re.search(r"(^|/)tests?/|test_[^/]*\.py$|\.test\.[jt]sx?$", current):
            continue
        if line.startswith("+") and not line.startswith("+++"):
            if WEAKEN.search(line):
                why.append(f"skips or xfails a test ({current})")
            added_asserts += len(re.findall(r"\bassert\b|expect\(", line))
        elif line.startswith("-") and not line.startswith("---"):
            removed_asserts += len(re.findall(r"\bassert\b|expect\(", line))
    if removed_asserts > added_asserts:
        why.append(f"removes {removed_asserts - added_asserts} test assertion(s)")
    return sorted(set(why), key=why.index)


def measure(cwd, base="origin/main"):
    """The gate's reasons for the diff of HEAD against `base` in `cwd`."""
    def git(*args):
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False).stdout
    rng = f"{base}...HEAD"     # --no-renames: a move out of a protected path is a delete plus an add, never a dodge
    return reasons(git("diff", "--no-renames", "--numstat", rng), git("diff", "--no-renames", "--name-status", rng),
                   git("diff", "--no-renames", rng))
