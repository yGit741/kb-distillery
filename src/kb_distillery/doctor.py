"""kbd doctor: check the environment and a knowledge base, and say how to fix each problem.

    kbd doctor [--kb <id|path>] [--json]

Prints PASS / WARN / FAIL / INFO with a one-line fix each. Exit code 0 unless something FAILs. Read-only: no network,
no LLM call, no lint (lint writes index.md), nothing written. Every check is a small function that takes what it looks
at as arguments, so a test fakes the world instead of touching it.

INFO is for things that are fine to leave off (no publisher, no LLM login): AI features stay off until a Claude
subscription login or an API key exists, and the knowledge base works without them.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass

from kb_distillery import kbconfig
from kb_distillery.config.resources import repo_root, resource
from kb_distillery.publish.null import DEFAULT_REASON

PASS, WARN, FAIL, INFO = "PASS", "WARN", "FAIL", "INFO"
MIN_PYTHON = (3, 11)


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str
    fix: str = ""


def _git_config(key: str) -> str:
    try:
        cp = subprocess.run(["git", "config", "--get", key], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return cp.stdout.strip()


# --- environment ---------------------------------------------------------------------------------------------
def check_python(version=None, prefix=None, env=None) -> list[Check]:
    version = version or sys.version_info[:3]
    prefix = prefix if prefix is not None else sys.prefix
    env = os.environ if env is None else env
    out = []
    if tuple(version[:2]) < MIN_PYTHON:
        out.append(Check("python", FAIL, f"python {'.'.join(map(str, version))} is too old (need {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+)",
                         "run through pixi: `pixi install`, then `pixi run kbd doctor`"))
    else:
        out.append(Check("python", PASS, f"python {'.'.join(map(str, version))}"))
    if ".pixi" in prefix or env.get("PIXI_PROJECT_ROOT") or env.get("CONDA_PREFIX"):
        out.append(Check("pixi env", PASS, "running inside the pixi environment"))
    else:
        out.append(Check("pixi env", WARN, "not running inside the pixi environment",
                         "install pixi, then `pixi install` and use `pixi run kbd …`"))
    return out


def check_node(which=shutil.which) -> Check:
    path = which("node")
    if path:
        return Check("node", PASS, f"node at {path}")
    return Check("node", WARN, "node not found (only the frontend build needs it)", "run `pixi install` (nodejs is in the pixi env)")


def check_git(which=shutil.which, config=_git_config) -> list[Check]:
    if not which("git"):
        return [Check("git", FAIL, "git not found", "install git (macOS: `xcode-select --install`)")]
    out = [Check("git", PASS, "git found")]
    name, email = config("user.name"), config("user.email")
    if name and email:
        out.append(Check("git identity", PASS, f"{name} <{email}>"))
    else:
        out.append(Check("git identity", WARN, "git user.name / user.email not set",
                         'run `git config --global user.name "You"` and `git config --global user.email you@example.com`'))
    return out


# --- knowledge base ------------------------------------------------------------------------------------------
def check_kb_found(known: dict, bases_dir: str, ref: str | None) -> Check:
    if ref:
        return Check("knowledge base", PASS, f"checking {ref}")
    if not known:
        return Check("knowledge base", WARN, f"no knowledge base in {bases_dir}", "run `kbd init` to create one")
    if len(known) == 1:
        return Check("knowledge base", PASS, f"found {next(iter(known))}")
    return Check("knowledge base", WARN, f"{len(known)} knowledge bases ({', '.join(sorted(known))}) and none selected",
                 "pass `--kb <id|path>` or set KB")


def check_kb_config(ref: str, loader=kbconfig.load):
    """→ (Check, KbConfig | None). Schema mismatch and an unknown template are FAILs that name the fix."""
    try:
        cfg = loader(ref)
    except kbconfig.KbConfigError as e:
        msg = str(e)
        if "schema_version" in msg:
            return Check("kb.toml", FAIL, msg, "run `pixi run ops -- migrate` on that knowledge base"), None
        if "not a known template" in msg:
            return Check("kb template", FAIL, msg, "set `[kb] template` to a known template, or remove it"), None
        return Check("kb.toml", FAIL, msg, "fix kb.toml, or create a new kb with `kbd init`"), None
    out = Check("kb.toml", PASS, f"{cfg.id}: schema {'.'.join(map(str, cfg.schema_version))}"
                + (f", template {cfg.template}" if cfg.template else ""))
    return out, cfg


def check_kb_layout(cfg) -> Check:
    missing = [d for d in ("wiki", "meta") if not os.path.isdir(os.path.join(cfg.root, d))]
    if missing:
        return Check("kb folders", WARN, f"missing {', '.join(m + '/' for m in missing)} in {cfg.root}",
                     "create them (empty folders are fine) or recreate with `kbd init`")
    if cfg.git_root is None:
        return Check("kb folders", INFO, "the kb folder is not its own git repository (fine for the tracked demo kb)",
                     f"to version a kb of your own, run `git init` in {cfg.root}")
    return Check("kb folders", PASS, "wiki/ and meta/ present, own git repository")


def check_storage(cfg, connector_for=None) -> Check:
    if connector_for is None:
        from kb_distillery.storage import registry
        connector_for = registry.for_kb
    try:
        status = connector_for(cfg).auth()
    except Exception as e:                                   # a connector that cannot even load
        return Check("storage", FAIL, str(e), "check `[storage]` in kb.toml (`connector`, `options`)")
    if status.ok:
        return Check("storage", PASS, "storage connector is ready")
    return Check("storage", WARN, status.message or "storage connector is not ready", "fix the connector login or its options in kb.toml")


def check_publisher(cfg, publisher_for=None) -> Check:
    if publisher_for is None:
        from kb_distillery.publish import registry
        publisher_for = registry.current
    pub = publisher_for(cfg)
    name = type(pub).__name__
    if name == "NullPublisher":
        reason = getattr(pub, "reason", "") or ""
        if reason and reason != DEFAULT_REASON:
            return Check("publisher", WARN, reason, "check `[publish]` in kb.toml, or remove it to publish nothing")
        return Check("publisher", INFO, "no publisher configured (publishing is optional)")
    return Check("publisher", PASS, f"publisher {name}")


# --- llm, frontend -------------------------------------------------------------------------------------------
def check_llm(avail=None) -> list[Check]:
    if avail is None:
        from kb_distillery import llm
        avail = llm.availability()
    out = []
    for backend, a in avail.items():
        if a["ok"]:
            out.append(Check(f"llm {backend}", PASS, a["why"]))
        else:
            out.append(Check(f"llm {backend}", INFO, f"{a['why']}; AI features that use it stay off", a["fix"]))
    if not any(a["ok"] for a in avail.values()):
        out.append(Check("llm", INFO, "no AI backend available: everything else works without one",
                         "add a Claude subscription login (`claude login`) or an API key when you want AI features"))
    return out


def check_frontend(frontend_dir: str, node: bool, dist: str = "") -> Check:
    """`frontend_dir` is the checkout's web/ folder, "" for an installed package (nothing to build from)."""
    dist = dist or str(resource("_webapp"))
    if os.path.isfile(os.path.join(dist, "index.html")):
        return Check("frontend", PASS, "src/kb_distillery/_webapp is built")
    if not frontend_dir:
        return Check("frontend", WARN, "the web app is not bundled in this install",
                     "install a release wheel, or run from a checkout of the repository (it builds the app on first launch)")
    if not node:
        return Check("frontend", WARN, "src/kb_distillery/_webapp is not built and node is missing", "run `pixi install` (it provides node), then launch again")
    if os.path.isdir(os.path.join(frontend_dir, "node_modules")):
        return Check("frontend", PASS, "src/kb_distillery/_webapp is built on first launch (node_modules present)")
    return Check("frontend", INFO, "src/kb_distillery/_webapp is not built yet and node_modules is missing",
                 "nothing to do: the first launch installs the frontend dependencies and builds the app (needs the network, takes a minute or two)")


# --- run -----------------------------------------------------------------------------------------------------
def run_checks(ref: str | None = None) -> list[Check]:
    node = check_node()
    checks = [*check_python(), node, *check_git()]
    known = kbconfig.discover()
    checks.append(check_kb_found(known, kbconfig.bases_dir(), ref))
    pick = ref or (next(iter(known)) if len(known) == 1 else None)
    if pick:
        found, cfg = check_kb_config(pick)
        checks.append(found)
        if cfg:
            checks += [check_kb_layout(cfg), check_storage(cfg), check_publisher(cfg)]
    checks += check_llm()
    repo = repo_root()
    checks.append(check_frontend(str(repo / "web") if repo else "", node.status == PASS))
    return checks


def render(checks: list[Check]) -> str:
    lines = []
    for c in checks:
        lines.append(f"{c.status:<4}  {c.name:<16} {c.detail}")
        if c.fix and c.status != PASS:
            lines.append(f"      fix: {c.fix}")
    counts = {s: sum(c.status == s for c in checks) for s in (PASS, WARN, FAIL, INFO)}
    lines.append(f"\n{counts[PASS]} pass, {counts[WARN]} warn, {counts[FAIL]} fail, {counts[INFO]} info")
    return "\n".join(lines)


def exit_code(checks: list[Check]) -> int:
    return 1 if any(c.status == FAIL for c in checks) else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="kbd doctor", description=__doc__.split("\n\n")[0])
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)
    ref = kbconfig.explicit_kb() or os.environ.get("KB")     # kbconfig already stripped --kb from argv
    checks = run_checks(ref)
    if args.json:
        print(json.dumps([asdict(c) for c in checks], indent=1))
    else:
        print(render(checks))
    return exit_code(checks)


if __name__ == "__main__":
    raise SystemExit(main())
