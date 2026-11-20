"""History layer, for any git repo: commits per file (count, authors, first/last change), merged change requests from
the first-parent merge commits (GitHub pull requests and GitLab merge requests), files that change together, and
CODEOWNERS. Runs on every focus repo. A shallow clone gives one commit: clone deep.

Where a repository has no merge commits (fast-forward or squash merges) a commit is the unit of change.
"""
from __future__ import annotations

import re
import subprocess
from collections import Counter, defaultdict
from itertools import combinations

from kb_distillery.codekb.generic.graph import Graph
from kb_distillery.codekb.generic.index import RepoIndex, fid
from kb_distillery.codekb.generic.project import Project, git

CODEOWNERS = ("CODEOWNERS", ".github/CODEOWNERS", ".gitlab/CODEOWNERS", "docs/CODEOWNERS")
GITLAB_SUBJECT = re.compile(r"!(\d+): Merge branch '([^']+)' into '([^']+)'")
MERGE_BRANCH = re.compile(r"Merge branch '([^']+)' into '([^']+)'")
GITLAB_BODY = re.compile(r"See merge request \S*!(\d+)")
GITHUB_SUBJECT = re.compile(r"Merge pull request #(\d+) from (\S+)")
MAX_FILES_PER_CHANGE = 25   # co-change counts changes that touch 2..25 files, so bulk moves do not dominate


def emit_history(p: Project, ix: RepoIndex, g: Graph) -> dict:
    out = {r.name: _history(p, ix, g, r.name) for r in p.focus if r.git}
    g.meta["history"] = {repo: g.meta.pop("_history_" + repo) for repo in out}
    return out


def _change(subject: str, body: str) -> tuple[int, str, str] | None:
    """(number, source branch, target branch) of a merge commit that merged a pull / merge request, else None."""
    m = GITLAB_SUBJECT.search(subject)
    if m:
        return int(m.group(1)), m.group(2), m.group(3)
    mb, mi = MERGE_BRANCH.search(subject), GITLAB_BODY.search(body)
    if mb and mi:
        return int(mi.group(1)), mb.group(1), mb.group(2)
    m = GITHUB_SUBJECT.search(subject)
    if m:
        return int(m.group(1)), m.group(2), ""
    return None


def _history(p: Project, ix: RepoIndex, g: Graph, repo: str) -> dict:
    stats: dict[str, int] = defaultdict(int)
    r = p.repo(repo)
    tracked = ix.tracked[repo]
    per_file: dict[str, dict] = defaultdict(lambda: {"commits": 0, "authors": Counter(), "first": None, "last": None})
    log = git(r, "log", "--no-merges", "--name-only", "--date=short", "--format=@@%H|%an|%ad|%s")
    commit_files: list[list[str]] = []
    commit_authors: Counter = Counter()
    for block in log.split("@@")[1:]:
        head, *files = [x for x in block.splitlines() if x.strip()]
        _, author, date, _ = head.split("|", 3)
        files = [f for f in files if f in tracked]
        commit_files.append(files)
        commit_authors[author] += 1
        stats["commits"] += 1
        for f in files:
            pf = per_file[f]
            pf["commits"] += 1
            pf["authors"][author] += 1
            pf["first"] = min(pf["first"] or date, date)
            pf["last"] = max(pf["last"] or date, date)
    mr_files: list[list[str]] = []
    merges = git(r, "log", "--first-parent", "--merges", "--date=short", "--format=%H%x1f%P%x1f%an%x1f%ad%x1f%s%x1f%b%x1e")
    for rec in merges.split("\x1e"):
        if not rec.strip():
            continue
        sha, parents, author, date, subject, body = rec.strip("\n").split("\x1f", 5)
        ch = _change(subject, body)
        if ch is None:
            continue
        iid, src_branch, dst_branch = ch
        try:
            files = [f for f in git(r, "diff", "--name-only", parents.split()[0], sha).splitlines() if f]
        except subprocess.CalledProcessError:
            continue
        title = next((ln.strip() for ln in body.splitlines() if ln.strip() and not GITLAB_BODY.search(ln)), "") if GITHUB_SUBJECT.search(subject) else ""
        mid = g.node(f"mr:{repo}!{iid}", "merge-request", f"!{iid} {title or src_branch}", repo=repo, iid=iid, sha=sha, date=date, author=author,
                     source_branch=src_branch, target_branch=dst_branch, n_files=len(files), title=title or None, url=p.change_url(repo, iid))
        stats["mrs"] += 1
        live = [f for f in files if f in tracked]
        for f in live:
            g.edge(mid, fid(repo, f), "touches", "history", repo, f, None)
        if not src_branch.startswith(("nightly/", "release/")):
            mr_files.append(live)
    for f, pf in per_file.items():
        n = g.nodes.get(fid(repo, f))
        if n is not None:
            n.update(n_commits=pf["commits"], authors=[a for a, _ in pf["authors"].most_common(4)], first_change=pf["first"], last_change=pf["last"])
    unit = "merge request"
    if not stats["mrs"] and stats["commits"] > 1:
        unit = "commit"
        mr_files = commit_files
    pair_mr: Counter = Counter()
    file_mr: Counter = Counter()
    for files in mr_files:
        for f in files:
            file_mr[f] += 1
        if 2 <= len(files) <= MAX_FILES_PER_CHANGE:
            for a, b in combinations(sorted(files), 2):
                pair_mr[(a, b)] += 1
    for (a, b), n in pair_mr.items():
        g.edge(fid(repo, a), fid(repo, b), "cochange", "history", conf="observed", n=n, jaccard=round(n / (file_mr[a] + file_mr[b] - n), 3))
        stats["cochange_pairs"] += 1
    for f, n in file_mr.items():
        if fid(repo, f) in g.nodes and unit == "merge request":
            g.nodes[fid(repo, f)]["n_mrs"] = n
    owners_path = next((c for c in CODEOWNERS if c in tracked), None)
    if owners_path:
        rules = []
        for i, line in enumerate((r.path / owners_path).read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            s = line.strip()
            if s and not s.startswith("#"):
                parts = s.split()
                rules.append({"pattern": parts[0], "owners": parts[1:], "line": i})
        g.node(f"owners:{repo}", "codeowners", f"{repo} CODEOWNERS", repo=repo, path=owners_path, line=1, rules=rules)
    g.meta["_history_" + repo] = {"feature_mrs": len(mr_files) if unit == "merge request" else 0, "commits": stats["commits"],
                                  "unit": unit, "cochange_pairs": stats["cochange_pairs"], "authors": commit_authors.most_common(20)}
    return dict(stats)
