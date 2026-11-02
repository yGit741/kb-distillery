"""The `distill` command table: each command's help, its kind and the module (or script) it runs. Pure data.

`kb_distillery.cli.tree` dispatches it and builds the help; `kb_distillery.lint.lint_skills` checks the `distill …`
lines in skills against it. Imports nothing from kb_distillery (never `kbconfig`: it strips `--kb` from argv the moment
it is imported).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Cmd:
    """One command. kind: "module" (python -m target), "script" (bash target, from a checkout), "launch" (see run) or
    "group" (sub holds the subcommands). forward_help: `--help` goes to the module, which must be argparse-based; for
    the others `--help` is answered here, since a module that ignores it would run (the linter does)."""
    help: str
    kind: str = "module"
    target: str = ""
    fixed: tuple[str, ...] = ()
    forward_help: bool = False
    fail_closed: bool = False           # a guard: allow (0) or deny (2), nothing else; an import error or crash denies
    checkout_only: bool = False         # hidden from --help and refused when the package runs outside a checkout
    config_check: bool = True           # refuse while only the old config folder exists (userdir.check)
    sub: dict[str, "Cmd"] = field(default_factory=dict)


COMMANDS: dict[str, Cmd] = {
    "init": Cmd("create a first knowledge base from a kit (own git repo), then run doctor", target="kb_distillery.init_kb",
                forward_help=True),
    "doctor": Cmd("check the environment and a kb, with a fix for each problem (--json)", target="kb_distillery.doctor",
                  forward_help=True, config_check=False),
    "kb": Cmd("knowledge bases", "group", sub={
        "list": Cmd("every knowledge base and where it is", target="kb_distillery.kbconfig", fixed=("list",), config_check=False),
        "show": Cmd("the selected knowledge base, resolved", target="kb_distillery.kbconfig", fixed=("show",), config_check=False),
    }),
    "launch": Cmd("restart the app detached and open it (outside a checkout: serve it in the foreground)", "launch",
                  "scripts/launch.sh"),
    "hooks": Cmd("git and Claude Code hooks", "group", sub={
        "install": Cmd("install the git + Claude Code hooks into a kb (--kb <id|path>)", target="kb_distillery.git.install_hooks",
                       forward_help=True, config_check=False),
    }),
    "hook": Cmd("stable entry for the kb-side hooks (git hooks and Claude Code guards call these)", "group", sub={
        "guard": Cmd("Claude Code write guard: may this file be edited?", target="kb_distillery.git.guard", config_check=False, fail_closed=True),
        "git-guard": Cmd("Claude Code Bash guard: block ad-hoc git writes", target="kb_distillery.git.git_guard",
                         config_check=False, fail_closed=True),
        "pre-commit": Cmd("git pre-commit: the linter is the schema", target="kb_distillery.lint.lint", config_check=False, fail_closed=True),
        "commit-msg": Cmd("git commit-msg: kb(op) conventional commits", target="kb_distillery.git.commit_policy",
                          fixed=("msg",), config_check=False, fail_closed=True),
        "pre-push": Cmd("git pre-push: main only moves forward by kb steps", target="kb_distillery.git.commit_policy",
                        fixed=("push",), config_check=False, fail_closed=True),
    }),
    "ops": Cmd("knowledge operations: sessions, snapshots, undo, restore, status, migrate", target="kb_distillery.ops",
               forward_help=True),
    "ship": Cmd("ship tooling through infra/* branches (start, commit, pr, merge, …)", target="kb_distillery.git.ship",
                forward_help=True, checkout_only=True, config_check=False),
    "ingest": Cmd("scrap, catalog and digest sources (scrap, catalog, resolve, status, …)", target="kb_distillery.ingest",
                  forward_help=True),
    "digest": Cmd("digest a source page: easy, full or deep", "group", sub={
        "easy": Cmd("abstract skim (light LLM)", target="kb_distillery.ingest", fixed=("easy-digest",), forward_help=True),
        "full": Cmd("standard paper note (medium LLM)", target="kb_distillery.ingest", fixed=("full-digest",), forward_help=True),
        "deep": Cmd("thesis-critical digest (heavy LLM)", target="kb_distillery.ingest", fixed=("deep-digest",), forward_help=True),
        "many": Cmd("batch-fill claims for many sources, then full-digest them one by one (LLM)",
                    target="kb_distillery.ingest", fixed=("digest-many",), forward_help=True),
        "instructions": Cmd("the digest focus of the selected kb", target="kb_distillery.vault.digest", config_check=False),
    }),
    "send": Cmd("send a think note into knowledge bases: distill send <note> --to a,b", target="kb_distillery.distill.send",
                forward_help=True),
    "lint": Cmd("lint the selected knowledge base (the schema is the linter); --health adds the summary",
                target="kb_distillery.lint.lint", config_check=False),
    "llm": Cmd("the one door to Claude: ask, submit, status, collect", target="kb_distillery.llm", forward_help=True),
    "share": Cmd("publish the wiki graph + explorer as a site (build, snapshot, status, …)", target="kb_distillery.publish.cloudflare",
                 forward_help=True),
    "propose": Cmd("typed relation proposals between wiki pages: submit, collect, review, apply", target="kb_distillery.graph.propose",
                   forward_help=True),
}
