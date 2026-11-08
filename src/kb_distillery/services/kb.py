"""The knowledge base behind this app (`/api/kb`) and every one the explorer can see (`/api/kb/list`).

Facts only, read from kb.toml, the folder and its git repo: no writes. Switching the active knowledge base
is a relaunch (`distill launch --kb <id|path>`): ROOT is resolved when the process starts.
"""
import os
import subprocess

from kb_distillery.config import kb as kbconfig
from kb_distillery.config import paths
from kb_distillery.vault import schema
from kb_distillery.vault.digest import instruction_files


def _git(root, *args):
    try:
        return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, check=False, timeout=10).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def git_state(root):
    """{repo, branch, last_tag, dirty} for a folder; repo False (and the rest empty) when it is not a git repo."""
    if not os.path.exists(os.path.join(root, ".git")):
        return {"repo": False, "branch": "", "last_tag": "", "dirty": 0}
    tags = _git(root, "for-each-ref", "--sort=-creatordate", "--format=%(refname:short)", "--count=1", "refs/tags/kb-*")
    porcelain = _git(root, "status", "--porcelain", "--untracked-files=all")
    return {"repo": True, "branch": _git(root, "symbolic-ref", "--short", "-q", "HEAD"),
            "last_tag": tags, "dirty": len([l for l in porcelain.splitlines() if l.strip()])}


def _types():
    return [{"id": t, "label": schema.TYPE_LABEL[t], "layer": schema.LAYER_OF[t], "prefix": schema.SLUG_PREFIX.get(t, ""),
             "color": schema.TYPE_COLOR[t], "maturities": sorted(schema.TYPE_STATUS[t])} for t in schema.TYPE_ORDER]


def _meta_overrides(root):
    """Which of the explorer's src/kb_distillery/kits/base/defaults this knowledge base overrides with its own meta/<x>."""
    out = [name for name in ("flags.toml", "templates", "docs") if os.path.exists(os.path.join(root, "meta", name))]
    if os.path.isdir(os.path.join(root, "digest")):
        out.append("digest")
    return out


def active():
    from kb_distillery.config.flags.registry import FLAGS_SOURCE
    cfg = paths.KB
    root = paths.ROOT
    return {
        "id": cfg.id if cfg else None, "name": cfg.name if cfg else "No knowledge base selected",
        "root": root, "read_only": kbconfig.is_read_only(root), "config": cfg.path if cfg else None,
        "schema_version": ".".join(map(str, cfg.schema_version if cfg else schema.SCHEMA_VERSION)),
        "git": git_state(root),
        "think_root": paths.THINK_PATH, "think_git": git_state(paths.THINK_PATH),
        "types": _types(), "areas": sorted(schema.TOPIC_SLUGS), "source_fields": list(schema.SOURCE_FIELDS),
        "digest": [{"part": part, "origin": origin, "path": path} for part, (path, origin) in instruction_files().items()],
        "flags_registry": FLAGS_SOURCE, "meta_overrides": _meta_overrides(root),
        "bases_dir": kbconfig.bases_dir(),
        "relaunch": "distill launch --kb <id|path>",
    }


def listing():
    rows = []
    for kb_id, root in kbconfig.discover().items():
        row = {"id": kb_id, "root": root, "name": "", "schema_version": "", "error": "", "git": git_state(root),
               "active": bool(paths.KB and os.path.realpath(paths.KB.root) == os.path.realpath(root))}
        try:
            cfg = kbconfig.load_dir(root, kb_id)
            row["name"], row["schema_version"] = cfg.name, ".".join(map(str, cfg.schema_version))
        except kbconfig.KbConfigError as e:
            row["error"] = str(e)
        rows.append(row)
    return {"bases_dir": kbconfig.bases_dir(),
            "think_root": paths.THINK_PATH, "active": paths.KB.id if paths.KB else None, "kbs": rows}
