"""The part of the index every tier shares: the pinned commit and the tracked files of each repository, and the file layer
of the graph. Language tiers (cpp/, pylang/) build on it and add their own layers."""
from __future__ import annotations

import posixpath

from kb_distillery.codekb.generic.graph import Graph
from kb_distillery.codekb.generic.project import Repo, head_sha, tracked_files


class RepoIndex:
    def __init__(self, repos: list[Repo]):
        self.repos = repos
        self.sha: dict[str, str] = {}
        self.tracked: dict[str, dict[str, str]] = {}   # repo -> {path: blob sha}
        for r in repos:
            self.sha[r.name] = head_sha(r)
            self.tracked[r.name] = dict(tracked_files(r))

    def repo_of(self, name: str) -> Repo:
        return next(r for r in self.repos if r.name == name)


def fid(repo: str, path: str) -> str:
    return f"file:{repo}:{path}"


def emit_files(ix: RepoIndex, g: Graph) -> dict:
    """The file layer: one node per tracked file, whatever its language (a tier later sets `lang` and `loc`)."""
    n = 0
    for r in ix.repos:
        for path, blob in ix.tracked[r.name].items():
            g.node(fid(r.name, path), "file", path, repo=r.name, path=path, blob=blob,
                   lang=posixpath.splitext(path)[1].lstrip(".").lower() or "other", role=r.role)
            n += 1
    return {"files": n}
