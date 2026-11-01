"""kbd init: create a first knowledge base from a template, run doctor, print how to open the dashboard.

    kbd init [--kb-id ID] [--name NAME] [--template starter|academic-research] [--dir PATH] [--yes]

Creates `<dir>/<id>/` (dir defaults to the bases dir, `kbs/`) as its OWN git repository: kb.toml (current schema
version, `[kb] template`), wiki/, raw/inbox/, meta/, a minimal .gitignore, and one first commit. It is built in a hidden
sibling folder and renamed into place, so a failure leaves nothing half made. It refuses to touch anything that exists.

No LLM is needed or asked for: init never reads or stores a key. AI features stay off until a Claude subscription login
or an API key exists (`kbd doctor` shows which). Prompts appear only when stdin is a terminal and `--yes` is absent.

The first commit goes through the engine's own kb-repo code (`kb_distillery.ops.core._git` / `_commit_paths`: no hooks, no push, no
lint), as `kb(import): …` because commit_policy has no init op. Identity: the user's git config, else a local fallback.
"""
from __future__ import annotations

import argparse
import contextlib
import os
import re
import shutil
import sys

from kb_distillery import kbconfig
from kb_distillery.config import userdir

DEFAULT_TEMPLATE = "starter"
DEFAULT_ID = "my-kb"
RESERVED_IDS = {"think", "yonatan-thesis", "demo"}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
FALLBACK_IDENTITY = {"GIT_AUTHOR_NAME": "kb-distillery", "GIT_AUTHOR_EMAIL": "kb@localhost",
                     "GIT_COMMITTER_NAME": "kb-distillery", "GIT_COMMITTER_EMAIL": "kb@localhost"}
GITIGNORE = """# OS
.DS_Store
__pycache__/

# Engine runtime state: never knowledge
meta/.ops/
meta/.ingest/
meta/.catalog/
meta/.migrate/
.cache/
.exported/
"""
KEEP = ("wiki/.gitkeep", "raw/inbox/.gitkeep", "meta/.gitkeep")
LLM_LINE = ("AI features (digest, chat, proposals) stay off until you add a Claude subscription login (`claude login`) or an "
            "API key (ANTHROPIC_API_KEY, or " + userdir.display("anthropic_key") + "); `kbd doctor` shows which backends work.")


class InitError(Exception):
    """Nothing was created; the message says why and what to do."""


def validate_id(kb_id: str) -> str:
    if not ID_RE.match(kb_id or ""):
        raise InitError(f"kb id {kb_id!r} must be lowercase letters, digits and dashes (e.g. my-notes)")
    if kb_id in RESERVED_IDS:
        raise InitError(f"kb id {kb_id!r} is reserved: pick another id")
    return kb_id


def plan_target(parent: str, kb_id: str, home: str | None = None) -> str:
    """The folder to create, or InitError when it must not be touched."""
    parent = os.path.realpath(os.path.expanduser(parent))
    home = os.path.realpath(home or os.path.expanduser("~"))
    target = os.path.join(parent, kb_id)
    if parent == home or target == home:
        raise InitError(f"refusing to create a knowledge base directly in your home directory ({home}): pass --dir <folder>")
    if os.path.lexists(target):
        raise InitError(f"{target} already exists: init never overwrites. Pick another --kb-id, or open it with `kbd launch --kb {kb_id}`")
    return target


def kb_toml(kb_id: str, name: str, template: str) -> str:
    major, minor = kbconfig.SCHEMA_VERSION
    esc = name.replace("\\", "\\\\").replace('"', '\\"')
    return (f'[kb]\nid = "{kb_id}"\nname = "{esc}"\nschema_version = "{major}.{minor}"\ntemplate = "{template}"\n\n'
            f'[git]\ntag_prefix = "kb-"\n')


def commit_message(kb_id: str, template: str) -> str:
    major, minor = kbconfig.SCHEMA_VERSION
    return f"kb(import): create {kb_id} from template {template} (kb-{major}.{minor}.0)\n"


def _write(root: str, rel: str, text: str) -> None:
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


@contextlib.contextmanager
def _identity_if_missing():
    """Give the first commit an author when git has none configured, then restore the environment."""
    from kb_distillery.doctor import _git_config
    if (os.environ.get("GIT_AUTHOR_NAME") or _git_config("user.name")) and (os.environ.get("GIT_AUTHOR_EMAIL") or _git_config("user.email")):
        yield
        return
    saved = {k: os.environ.get(k) for k in FALLBACK_IDENTITY}
    os.environ.update({k: v for k, v in FALLBACK_IDENTITY.items() if not os.environ.get(k)})
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def create(kb_id: str, name: str, template: str, parent: str, home: str | None = None) -> str:
    """Make the kb folder with its own git repo and first commit → its path. Raises InitError, leaving nothing behind."""
    from kb_distillery.core import template as templates
    validate_id(kb_id)
    if not templates.exists(template):
        raise InitError(f"unknown template {template!r} (known: {', '.join(templates.names()) or 'none'})")
    target = plan_target(parent, kb_id, home)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    work = os.path.join(os.path.dirname(target), f".init-{kb_id}-{os.getpid()}")      # hidden: discovery skips dots
    try:
        os.makedirs(work)
        _write(work, "kb.toml", kb_toml(kb_id, name, template))
        _write(work, ".gitignore", GITIGNORE)
        for rel in KEEP:
            _write(work, rel, "")
        from kb_distillery.ops.core import OpsError, _commit_paths, _git        # the engine's kb-repo git helpers
        try:
            _git(work, "init", "-q", "-b", "main", check=True)
            with _identity_if_missing():
                sha = _commit_paths(work, ["kb.toml", ".gitignore", *KEEP], commit_message(kb_id, template))
        except OpsError as e:
            raise InitError(f"could not make the first commit: {e}") from None
        if not sha:
            raise InitError("could not make the first commit: nothing was staged")
        os.rename(work, target)
        work = ""
    finally:
        if work and os.path.isdir(work):
            shutil.rmtree(work, ignore_errors=True)
    return target


def launch_command(target: str, kb_id: str, parent: str) -> str:
    in_bases = os.path.realpath(parent) == os.path.realpath(kbconfig.bases_dir())
    return f"kbd launch --kb {kb_id if in_bases else target}"


def _ask(prompt: str, default: str) -> str:
    answer = input(f"{prompt} [{default}]: ").strip()
    return answer or default


def main(argv=None) -> int:
    from kb_distillery.core import template as templates
    ap = argparse.ArgumentParser(prog="kbd init", description=__doc__.split("\n\n")[0])
    ap.add_argument("--kb-id", help=f"folder name and id (default {DEFAULT_ID})")
    ap.add_argument("--name", help="display name (default: the id, spaced and capitalised)")
    ap.add_argument("--template", help=f"ontology template (default {DEFAULT_TEMPLATE}; known: {', '.join(templates.names())})")
    ap.add_argument("--dir", help="parent folder the kb folder is created in (default: the bases dir, kbs/)")
    ap.add_argument("--yes", action="store_true", help="never prompt; take defaults for what is not given")
    args = ap.parse_args(argv)
    interactive = sys.stdin.isatty() and not args.yes
    kb_id = args.kb_id or (_ask("Knowledge base id", DEFAULT_ID) if interactive else DEFAULT_ID)
    default_name = kb_id.replace("-", " ").capitalize()
    name = args.name or (_ask("Display name", default_name) if interactive else default_name)
    template = args.template or (_ask(f"Template ({'/'.join(templates.names())})", DEFAULT_TEMPLATE) if interactive else DEFAULT_TEMPLATE)
    parent = args.dir or kbconfig.bases_dir()
    try:
        target = create(kb_id, name, template, parent)
    except InitError as e:
        print(f"kbd init: {e}", file=sys.stderr)
        return 1
    print(f"created {target} (own git repository, template {template}, schema {'.'.join(map(str, kbconfig.SCHEMA_VERSION))})\n")
    from kb_distillery import doctor
    checks = doctor.run_checks(target)
    print(doctor.render(checks))
    print(f"\nOpen the dashboard:  {launch_command(target, kb_id, parent)}")
    print(LLM_LINE)
    return doctor.exit_code(checks)


if __name__ == "__main__":
    raise SystemExit(main())
