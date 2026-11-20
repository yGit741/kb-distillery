"""A code project: which repositories (or plain folders) to index, where their checkouts live, and how a fact links back
to the code. Read from one YAML (or TOML) file, or from the `[code]` table of a kb's `kb.toml`; nothing else in the
package names a repository, a host or a company.

    name: my-service
    tiers: [cpp, python]              # which language tiers run (default: python and cpp)
    repos_dir: ~/code                 # checkouts live in <repos_dir>/<name> unless a repo gives `path:`
    repos:
      - {name: core, role: focus}                        # every layer, its own cards
      - {name: shared, role: platform, display: Shared}  # symbols and calls too
      - {name: vendor, role: neighbour}                  # files, includes
      - {name: scripts, path: raw/scripts, git: false, web: "https://example.com/blob/main/scripts"}   # a plain folder

In a kb's `kb.toml` the same keys sit under `[code]` and `[[code.repos]]`.

Roles: `focus` gets every layer and its own cards; `platform` adds symbols and calls; `neighbour` adds files and includes.
The commit of each repository is read from its checkout, so building twice at two commits gives two IRs to diff.

Permalinks. A git repository links to the web page of its remote (`git remote get-url origin`, credentials dropped) at
the pinned commit. `style:` (`github` or `gitlab`; default: gitlab when the host name contains "gitlab", else github)
picks the URL form of the repository's host; `remote:` overrides the remote; `web:` is the base address itself. A
project-level `permalink:` table overrides the forms:

    permalink: {blob: "{base}/src/{sha}/{path}", tree: "{base}/src/{sha}/{path}", range: "lines-{start}:{end}", pull: "{base}/pulls/{iid}"}

A repository with no remote and no `web:` has no links: its facts keep the `path:line` label only.
"""
from __future__ import annotations

import copy
import hashlib
import os
import re
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import yaml

CPP_EXT = {".h", ".hpp", ".hh", ".c", ".cc", ".cpp", ".cxx", ".inl"}
ROLES = ("focus", "platform", "neighbour")
TIERS = ("cpp", "python")
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".pixi", ".venv", "venv", ".mypy_cache", ".pytest_cache"}

# URL forms per host kind. `range` is the fragment of a line range ({start}, {end}); `pull` is a merged change request.
STYLES = {
    "github": {"blob": "{base}/blob/{sha}/{path}", "tree": "{base}/tree/{sha}/{path}", "range": "L{start}-L{end}",
               "pull": "{base}/pull/{iid}"},
    "gitlab": {"blob": "{base}/-/blob/{sha}/{path}", "tree": "{base}/-/tree/{sha}/{path}", "range": "L{start}-{end}",
               "pull": "{base}/-/merge_requests/{iid}"},
}

DEFAULTS: dict = {"tiers": list(TIERS), "permalink": {}}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def web_base(remote: str) -> str:
    """The https address of a repository from its remote URL: `git@host:group/repo.git`, `ssh://git@host/group/repo.git`
    and `https://user:token@host/group/repo.git` all give `https://host/group/repo`. Credentials never survive."""
    remote = (remote or "").strip()
    m = re.match(r"^[\w.-]+@([\w.-]+):(?!//)(.+)$", remote)                      # scp form
    if m:
        host, path = m.group(1), m.group(2)
    else:
        m = re.match(r"^(?:https?|ssh|git)://(?:[^@/]*@)?([\w.-]+)(?::\d+)?/(.+)$", remote)
        if not m:
            return ""
        host, path = m.group(1), m.group(2)
    path = path.strip("/").removesuffix(".git")
    return f"https://{host}/{path}" if path else ""


def detect_style(base: str) -> str:
    host = base.split("/")[2] if base.count("/") >= 2 else ""
    return "gitlab" if "gitlab" in host.lower() else "github"


@dataclass(frozen=True)
class Repo:
    name: str
    role: str
    path: Path
    display: str
    git: bool = True        # False: a plain folder (files copied into a kb's raw/, an unpacked archive)
    web: str = ""           # git: the base address of the repository page; plain folder: where its files can be opened
    style: str = "github"
    include_prefix: str = ""   # `#include "<prefix>/x.h"` names x.h of this repository (C++ include resolution)

    @property
    def focus(self) -> bool:
        return self.role == "focus"


@dataclass
class Project:
    name: str
    base: Path                      # folder that relative paths in the project are relative to
    repos: list[Repo]
    out: Path
    tiers: tuple[str, ...] = TIERS
    permalink_cfg: dict = field(default_factory=dict)
    by_name: dict[str, Repo] = field(default_factory=dict)

    def repo(self, name: str) -> Repo:
        return self.by_name[name]

    @property
    def focus(self) -> list[Repo]:
        return [r for r in self.repos if r.focus]

    @property
    def call_repos(self) -> set[str]:
        return {r.name for r in self.repos if r.role in ("focus", "platform")}

    def display(self, name: str) -> str:
        return self.by_name[name].display if name in self.by_name else name

    def _form(self, r: Repo, key: str) -> str:
        return self.permalink_cfg.get(key) or STYLES.get(r.style, STYLES["github"])[key]

    def permalink(self, repo: str, sha: str, path: str, line: int | None = None, end: int | None = None, kind: str = "blob") -> str:
        """Address of `path` (at `line`..`end`) in the host's web interface, pinned at `sha`; "" when the repository has none."""
        r = self.by_name.get(repo)
        if r is None or not r.web:
            return ""
        if not r.git:
            url = f"{r.web.rstrip('/')}/{path}".rstrip("/")
        else:
            url = self._form(r, kind if kind in ("blob", "tree") else "blob").format(base=r.web.rstrip("/"), sha=sha, path=path).rstrip("/")
        if line and kind == "blob":
            frag = f"L{line}"
            if end and end != line:
                frag = self._form(r, "range").format(start=line, end=end)
            url += "#" + frag
        return url

    def change_url(self, repo: str, iid: int) -> str:
        r = self.by_name.get(repo)
        if r is None or not r.web or not r.git:
            return ""
        return self._form(r, "pull").format(base=r.web.rstrip("/"), iid=iid)


def git(repo: Repo, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo.path), *args], capture_output=True, text=True, check=True).stdout


def head_sha(repo: Repo) -> str:
    if not repo.git:  # a plain folder is pinned by its content: the same files give the same id
        h = hashlib.sha1()
        for path, blob in tracked_files(repo):
            h.update(f"{path}\0{blob}\n".encode())
        return h.hexdigest()
    return git(repo, "rev-parse", "HEAD").strip()


def tracked_files(repo: Repo) -> list[tuple[str, str]]:
    """(path, blob sha) for every tracked file that is present on disk (sparse checkouts skip the rest)."""
    if not repo.git:
        out = []
        for f in sorted(repo.path.rglob("*")):
            rel = f.relative_to(repo.path)
            if f.is_file() and not (set(rel.parts[:-1]) & SKIP_DIRS) and not rel.name.startswith("."):
                data = f.read_bytes()
                out.append((rel.as_posix(), hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()))
        return out
    out = []
    for line in git(repo, "ls-files", "-s").splitlines():
        meta, path = line.split("\t", 1)
        if (repo.path / path).is_file():
            out.append((path, meta.split()[1]))
    return out


def _remote(path: Path) -> str:
    try:
        return subprocess.run(["git", "-C", str(path), "remote", "get-url", "origin"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def from_dict(raw: dict, base: Path, source: str = "the project", default_name: str = "code") -> Project:
    """Build a project from its parsed file. Relative paths are relative to `base`. KB_CODE_REPOS overrides `repos_dir`,
    KB_CODE_OUT the output folder, KB_CODE_REPO_OVERRIDE="repo=/other/checkout,..." swaps checkouts (to build the IR of
    another commit without touching the first one)."""
    raw = _merge(DEFAULTS, raw or {})
    rel = lambda p: (base / Path(p).expanduser()).resolve()  # noqa: E731
    repos_dir = rel(os.environ.get("KB_CODE_REPOS") or raw.get("repos_dir") or ".")
    entries = [kv for kv in os.environ.get("KB_CODE_REPO_OVERRIDE", "").split(",") if kv.strip()]
    if any("=" not in kv for kv in entries):
        raise SystemExit('KB_CODE_REPO_OVERRIDE must be "repo=/path,repo=/path" (a path cannot contain a comma)')
    override = dict(kv.split("=", 1) for kv in entries)
    if not raw.get("repos"):
        raise SystemExit(f"{source}: no `repos:` (name each repository or folder to index)")
    repos = []
    for r in raw["repos"]:
        name = r.get("name")
        if not name or not re.match(r"^[A-Za-z0-9._-]+$", str(name)):
            raise SystemExit(f"{source}: every repo needs a `name` of letters, digits, `.`, `_` and `-`")
        role = r.get("role", "neighbour")
        if role not in ROLES:
            raise SystemExit(f"{source}: repo {name}: role must be one of {ROLES}")
        path = Path(override[name]) if name in override else (rel(r["path"]) if r.get("path") else repos_dir / name)
        is_git = bool(r.get("git", True))
        web = str(r.get("web") or "")
        if not web and is_git and r.get("remote"):
            web = web_base(r["remote"])
        elif not web and is_git and path.is_dir():
            web = web_base(_remote(path))
        style = r.get("style") or detect_style(web)
        if style not in STYLES:
            raise SystemExit(f"{source}: repo {name}: style must be one of {sorted(STYLES)}")
        repos.append(Repo(name, role, path, str(r.get("display") or name), is_git, web, style, str(r.get("include_prefix") or "").strip("/")))
    bad = [t for t in raw["tiers"] if t not in TIERS]
    if bad:
        raise SystemExit(f"{source}: unknown tier(s) {bad}; tiers are {list(TIERS)}")
    name = str(raw.get("name") or default_name)
    out = Path(os.environ["KB_CODE_OUT"]) if os.environ.get("KB_CODE_OUT") else rel(raw.get("out") or f".local/code/{name}")
    return Project(name, base, repos, out, tuple(raw["tiers"]), dict(raw.get("permalink") or {}), {r.name: r for r in repos})


def load(path: str | Path) -> Project:
    """A project from a YAML or TOML file."""
    file = Path(path).expanduser().resolve()
    if not file.is_file():
        raise SystemExit(f"{file} not found")
    text = file.read_text(encoding="utf-8")
    raw = tomllib.loads(text) if file.suffix == ".toml" else yaml.safe_load(text)
    if not isinstance(raw, dict):
        raise SystemExit(f"{file}: expected a mapping")
    if file.name == "kb.toml":
        raw = raw.get("code") or {}
        return from_dict(raw, file.parent, f"{file} [code]", file.parent.name)
    return from_dict(raw, file.parent, str(file), file.stem)


def load_kb(root: str | Path) -> Project:
    """The project of a kb: the `[code]` table of its kb.toml."""
    root = Path(root).resolve()
    file = root / "kb.toml"
    if not file.is_file():
        raise SystemExit(f"{root} is not a knowledge base (no kb.toml); give a project file instead")
    raw = (tomllib.loads(file.read_text(encoding="utf-8")).get("code") or {})
    if not raw:
        raise SystemExit(f"{file} has no [code] table: add [code] and [[code.repos]] (see `distill code --help`), or give a project file")
    return from_dict(raw, root, f"{file} [code]", root.name)


def check_checkouts(p: Project) -> None:
    missing = [r.name for r in p.repos if not ((r.path / ".git").exists() if r.git else r.path.is_dir())]
    if missing:
        raise SystemExit(f"no checkout for {missing}: give each repo a `path:` or put it under `repos_dir`")
