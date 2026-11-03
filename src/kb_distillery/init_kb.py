"""distill init: create a first knowledge base from a kit, run doctor, print how to open the dashboard.

    distill init [--kb-id ID] [--name NAME] [--kit base|research] [--dir PATH] [--yes]
    distill init --refresh [--kb <id|path>]

Creates `<dir>/<id>/` (dir defaults to the bases dir, `~/knowledge`) as its OWN git repository: kb.toml (current schema
version, `[kb] kit`), wiki/, raw/inbox/, meta/, a minimal .gitignore, and the kit's files, then one first commit:

    .claude/skills/    copies of the kit's skills (and those of the kits it `extends`)
    .claude/docs/      copies of the kit's docs that `AGENTS.md` routes to
    .claude/hooks/, .claude/settings.json   the Claude Code guards (each one runs `distill hook <name>`)
    AGENTS.md, README.md   rendered from `kits/<kit>/AGENTS.template.md` / `README.template.md`

and, once the folder is in place, `core.hooksPath` -> the kit's git hooks. It is built in a hidden sibling folder and
renamed into place, so a failure leaves nothing half made. It refuses to touch anything that exists.

`--refresh` re-syncs `.claude/skills/`, `.claude/docs/`, the hooks, `settings.json` and `core.hooksPath` of an EXISTING kb
with its kit, prints what changed (nothing to do prints "already up to date") and is idempotent. It never touches `raw/`,
`wiki/`, `meta/`, `think/` or `AGENTS.md` / `README.md` / `kb.toml`; for those it only says what it found. It does not
commit: review the changes and commit them with `distill ops chore hooks "refresh kit files"`.

No LLM is needed or asked for: init never reads or stores a key. AI features stay off until a Claude subscription login
or an API key exists (`distill doctor` shows which). Prompts appear only when stdin is a terminal and `--yes` is absent.

The first commit goes through the engine's own kb-repo code (`kb_distillery.ops.core._git` / `_commit_paths`: no hooks, no push, no
lint), as `kb(import): …` because commit_policy has no init op. Identity: the user's git config, else a local fallback.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import re
import shutil
import stat
import sys

from kb_distillery.config import kb as kbconfig
from kb_distillery.config import userdir
from kb_distillery.git import install_hooks

DEFAULT_KIT = "base"
DEFAULT_ID = "my-kb"
RESERVED_IDS = {"think", "demo"}
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
AGENTS_FILE, README_FILE = "AGENTS.template.md", "README.template.md"
LLM_LINE = ("AI features (digest, chat, proposals) stay off until you add a Claude subscription login (`claude login`) or an "
            "API key (ANTHROPIC_API_KEY, or " + userdir.display("anthropic_key") + "); `distill doctor` shows which backends work.")


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
        raise InitError(f"{target} already exists: init never overwrites. Pick another --kb-id, or open it with `distill launch --kb {kb_id}`")
    return target


# --- the kit's files -------------------------------------------------------------------------------------------

def _kit_dir(kit_name: str) -> str:
    from kb_distillery.config import kit as kits
    return os.path.join(kits.kits_dir(), kits.canonical(kit_name))


def _sync_file(src: str, dest: str) -> str | None:
    """Make `dest` a byte copy of `src` (mode kept) -> "added", "updated" or None when it already matched."""
    want = open(src, "rb").read()
    mode = stat.S_IMODE(os.stat(src).st_mode) | 0o600
    if os.path.isfile(dest) and open(dest, "rb").read() == want:
        if stat.S_IMODE(os.stat(dest).st_mode) == mode:
            return None
        os.chmod(dest, mode)
        return "updated"
    state = "updated" if os.path.isfile(dest) else "added"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(want)
    os.chmod(dest, mode)
    return state


def _sync_tree(src: str, dest: str, rel: str, report: list[str], extra: list[str]) -> None:
    """`dest` becomes a copy of the folder `src`: files are added or updated; a file the kit does not have is never deleted, it is listed in `extra`."""
    want = set()
    for base, _dirs, files in os.walk(src):
        for name in sorted(files):
            if name == ".DS_Store" or name.endswith(".pyc"):
                continue
            sub = os.path.relpath(os.path.join(base, name), src)
            want.add(sub)
            state = _sync_file(os.path.join(src, sub), os.path.join(dest, sub))
            if state:
                report.append(f"{state} {rel}/{sub}")
    if not os.path.isdir(dest):
        return
    for base, _dirs, files in os.walk(dest, topdown=False):
        for name in files:
            sub = os.path.relpath(os.path.join(base, name), dest)
            if sub not in want:
                extra.append(f"{rel}/{sub} is not in the kit (any more): left in place, delete it if it is not yours")


def skill_sources(kit: str) -> dict[str, str]:
    """skill name -> source folder, for the kit and every kit it extends (a child's skill replaces its parent's)."""
    from kb_distillery.config import kit as kits
    out: dict[str, str] = {}
    for name in kits.chain(kit):
        root = os.path.join(_kit_dir(name), "skills")
        if not os.path.isdir(root):
            continue
        for skill in sorted(os.listdir(root)):
            if not skill.startswith(("_", ".")) and os.path.isfile(os.path.join(root, skill, "SKILL.md")):
                out[skill] = os.path.join(root, skill)
    return out


def skills_readme(kit: str) -> str:
    """The kits' skills READMEs one after the other, parents first."""
    from kb_distillery.config import kit as kits
    parts = []
    for name in kits.chain(kit):
        path = os.path.join(_kit_dir(name), "skills", "README.md")
        if os.path.isfile(path):
            parts.append(open(path, encoding="utf-8").read().rstrip("\n"))
    return "\n\n---\n\n".join(parts) + "\n"


def _write_if_different(path: str, text: str) -> str | None:
    if os.path.isfile(path) and open(path, encoding="utf-8").read() == text:
        return None
    state = "updated" if os.path.isfile(path) else "added"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return state


def sync_kit_files(root: str, kit: str, report: list[str], extra: list[str] | None = None) -> None:
    """The kit's copies in a kb: `.claude/skills/` (every skill of the kit chain, plus the README listing them) and
    `.claude/docs/`. A skill folder the kit does not have (the kb's own) is left alone."""
    from kb_distillery.config import kit as kits
    extra = [] if extra is None else extra
    skills = os.path.join(root, ".claude", "skills")
    for skill, src in skill_sources(kit).items():
        _sync_tree(src, os.path.join(skills, skill), f".claude/skills/{skill}", report, extra)
    state = _write_if_different(os.path.join(skills, "README.md"), skills_readme(kit))
    if state:
        report.append(f"{state} .claude/skills/README.md")
    docs = os.path.join(root, ".claude", "docs")
    for name in kits.chain(kit):
        src = os.path.join(_kit_dir(name), "defaults", "docs")
        for doc in kits.KB_DOCS:
            if os.path.isfile(os.path.join(src, f"{doc}.md")):
                state = _sync_file(os.path.join(src, f"{doc}.md"), os.path.join(docs, f"{doc}.md"))
                if state:
                    report.append(f"{state} .claude/docs/{doc}.md")


def render_template(kit: str, filename: str, context: dict[str, str]) -> str:
    """`kits/<kit>/<filename>` with `{{name}}`, `{{kb_id}}`, `{{kit}}` filled in. A kit's template may put `{{parent}}`
    where the template of the kit it extends goes; a kit with no such file uses its parent's."""
    from kb_distillery.config import kit as kits
    chain = kits.chain(kit)
    for i in range(len(chain) - 1, -1, -1):
        path = os.path.join(_kit_dir(chain[i]), filename)
        if not os.path.isfile(path):
            continue
        text = open(path, encoding="utf-8").read()
        if "{{parent}}" in text:
            parent = render_template(chain[i - 1], filename, context) if i else ""
            text = text.replace("{{parent}}", parent.rstrip("\n"))
        for key, value in context.items():
            text = text.replace("{{" + key + "}}", value)
        return text if text.endswith("\n") else text + "\n"
    raise InitError(f"the kit {kit!r} has no {filename} (looked in {', '.join(chain)})")


def _quiet(fn, root: str, report: list[str] | None = None) -> int:
    """Run an install_hooks step without its progress lines (init and refresh print their own summary)."""
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(root, [] if report is None else report)


def _context(kb_id: str, name: str, kit: str) -> dict[str, str]:
    return {"kb_id": kb_id, "name": name, "kit": kit}


def kb_toml(kb_id: str, name: str, kit: str) -> str:
    major, minor = kbconfig.SCHEMA_VERSION
    esc = name.replace("\\", "\\\\").replace('"', '\\"')
    return (f'[kb]\nid = "{kb_id}"\nname = "{esc}"\nschema_version = "{major}.{minor}"\nkit = "{kit}"\n\n'
            f'[git]\ntag_prefix = "kb-"\n')


def commit_message(kb_id: str, kit: str) -> str:
    major, minor = kbconfig.SCHEMA_VERSION
    return f"kb(import): create {kb_id} from kit {kit} (kb-{major}.{minor}.0)\n"


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


def create(kb_id: str, name: str, kit: str, parent: str, home: str | None = None) -> str:
    """Make the kb folder with its own git repo and first commit → its path. Raises InitError, leaving nothing behind."""
    from kb_distillery.config import kit as kits
    validate_id(kb_id)
    if not kits.exists(kit):
        raise InitError(f"unknown kit {kit!r} (known: {', '.join(kits.names()) or 'none'})")
    kit = kits.canonical(kit)                 # the old names starter / academic-research write the current ones
    target = plan_target(parent, kb_id, home)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    work = os.path.join(os.path.dirname(target), f".init-{kb_id}-{os.getpid()}")      # hidden: discovery skips dots
    try:
        os.makedirs(work)
        _write(work, "kb.toml", kb_toml(kb_id, name, kit))
        _write(work, ".gitignore", GITIGNORE)
        for rel in KEEP:
            _write(work, rel, "")
        _write(work, "AGENTS.md", render_template(kit, AGENTS_FILE, _context(kb_id, name, kit)))
        _write(work, "README.md", render_template(kit, README_FILE, _context(kb_id, name, kit)))
        sync_kit_files(work, kit, [])
        if _quiet(install_hooks.install_claude, work):
            raise InitError("could not install the Claude Code hooks (see above)")
        from kb_distillery.ops.core import OpsError, _commit_paths, _git        # the engine's kb-repo git helpers
        try:
            _git(work, "init", "-q", "-b", "main", check=True)
            with _identity_if_missing():
                sha = _commit_paths(work, ["kb.toml", ".gitignore", "AGENTS.md", "README.md", ".claude", *KEEP],
                                    commit_message(kb_id, kit))
        except OpsError as e:
            raise InitError(f"could not make the first commit: {e}") from None
        if not sha:
            raise InitError("could not make the first commit: nothing was staged")
        os.rename(work, target)
        work = ""
        if _quiet(install_hooks.install_git, target):          # core.hooksPath is relative to the kb's final place
            raise InitError(f"{target} was created, but its git hooks could not be installed: "
                            f"run `distill hooks install --kb {target}` once the cause above is fixed")
    finally:
        if work and os.path.isdir(work):
            shutil.rmtree(work, ignore_errors=True)
    return target


# --- --refresh ---------------------------------------------------------------------------------------------------

def refresh(root: str) -> tuple[list[str], list[str], int]:
    """Re-sync an existing kb's kit files -> (changes, notes, rc). `changes` are the files written or removed,
    `notes` what was found and left alone (the user's AGENTS.md, files the kit no longer ships). Idempotent."""
    from kb_distillery.config import kit as kits
    cfg = kbconfig.load_dir(root, strict=False)       # tooling files only: a kb on an older schema is refreshed too
    if not cfg.kit:
        raise InitError(f"{cfg.path} names no kit ([kb] kit = \"base\" or \"research\"): --refresh has nothing to sync from")
    kit, changes, notes = cfg.kit, [], []
    try:
        kits.chain(kit)
    except kits.KitError as e:
        raise InitError(str(e)) from None
    sync_kit_files(root, kit, changes, notes)
    rc = _quiet(install_hooks.install_claude, root, changes) or _quiet(install_hooks.install_git, root, changes)
    hooks = os.path.join(root, ".claude", "hooks")
    shipped = set(install_hooks.CLAUDE_HOOKS)
    for name in sorted(os.listdir(hooks)) if os.path.isdir(hooks) else []:
        if name not in shipped:
            notes.append(f".claude/hooks/{name} is not part of the kit any more (the kit hooks call `distill hook <name>` and "
                         f"do not use it): left in place, delete it when nothing of yours calls it")
    agents = os.path.join(root, "AGENTS.md")
    if not os.path.isfile(agents):
        notes.append("AGENTS.md: none in this kb; --refresh never creates it")
    else:
        wanted = render_template(kit, AGENTS_FILE, _context(cfg.id, cfg.name, kit))
        notes.append("AGENTS.md: matches the kit template" if open(agents, encoding="utf-8").read() == wanted
                     else "AGENTS.md: yours (it differs from the kit template); left alone")
    return changes, notes, rc


def run_refresh() -> int:
    """The kb is `$KB_ROOT` (a hook's choice), else what `--kb` / `$KB` / the folder you are in selects; resolved fresh each call."""
    root = os.environ.get("KB_ROOT")
    try:
        ref = kbconfig.selected()               # --kb, $KB, the folder you are in: an explicit choice beats $KB_ROOT
        if ref:
            cfg = kbconfig.load(ref, strict=False)
        elif root and os.path.isfile(os.path.join(root, kbconfig.CONFIG_NAME)):
            cfg = kbconfig.load_dir(root, strict=False)
        else:
            cfg = None
    except kbconfig.KbConfigError as e:
        print(f"distill init --refresh: {e}", file=sys.stderr)
        return 1
    if cfg is None:
        print("distill init --refresh: no knowledge base selected - pass --kb <id|path>, set KB, or run it inside the kb folder",
              file=sys.stderr)
        return 1
    try:
        changes, notes, rc = refresh(cfg.root)
    except InitError as e:
        print(f"distill init --refresh: {e}", file=sys.stderr)
        return 1
    print(f"refresh {cfg.root} (kit {cfg.kit}); raw/, wiki/, meta/ and think/ are never touched")
    for line in changes:
        print(f"  {line}")
    if not changes:
        print("  already up to date")
    for line in notes:
        print(f"  note: {line}")
    if changes:
        print("Nothing is committed: review the changes, then `KB_NO_PUSH=1 distill ops chore hooks \"refresh kit files\"` (without KB_NO_PUSH it pushes main).")
    return rc


def launch_command(target: str, kb_id: str, parent: str) -> str:
    in_bases = os.path.realpath(parent) == os.path.realpath(kbconfig.bases_dir())
    return f"distill launch --kb {kb_id if in_bases else target}"


def _ask(prompt: str, default: str) -> str:
    answer = input(f"{prompt} [{default}]: ").strip()
    return answer or default


def main(argv=None) -> int:
    from kb_distillery.config import kit as kits
    ap = argparse.ArgumentParser(prog="distill init", description=__doc__.split("\n\n")[0])
    ap.add_argument("--kb-id", help=f"folder name and id (default {DEFAULT_ID})")
    ap.add_argument("--name", help="display name (default: the id, spaced and capitalised)")
    ap.add_argument("--kit", "--template", dest="kit", help=f"ontology kit (default {DEFAULT_KIT}; known: {', '.join(kits.names())}; "
                    f"--template is the older spelling)")
    ap.add_argument("--dir", help="parent folder the kb folder is created in (default: the bases dir, ~/knowledge)")
    ap.add_argument("--yes", action="store_true", help="never prompt; take defaults for what is not given")
    ap.add_argument("--refresh", action="store_true", help="re-sync the skills, docs, hooks and settings of an existing kb "
                    "(--kb <id|path>, $KB, or run inside it) with its kit; prints what changed")
    args = ap.parse_args(argv)
    if args.refresh:
        if args.kb_id or args.name or args.kit or args.dir:
            ap.error("--refresh works on an existing kb (--kb <id|path>); it takes none of --kb-id, --name, --kit, --dir")
        return run_refresh()
    interactive = sys.stdin.isatty() and not args.yes
    kb_id = args.kb_id or (_ask("Knowledge base id", DEFAULT_ID) if interactive else DEFAULT_ID)
    default_name = kb_id.replace("-", " ").capitalize()
    name = args.name or (_ask("Display name", default_name) if interactive else default_name)
    kit = args.kit or (_ask(f"Kit ({'/'.join(kits.names())})", DEFAULT_KIT) if interactive else DEFAULT_KIT)
    parent = args.dir or kbconfig.bases_dir()
    try:
        target = create(kb_id, name, kit, parent)
    except InitError as e:
        print(f"distill init: {e}", file=sys.stderr)
        return 1
    print(f"created {target} (own git repository, kit {kits.canonical(kit)}, schema {'.'.join(map(str, kbconfig.SCHEMA_VERSION))})\n")
    from kb_distillery import doctor
    checks = doctor.run_checks(target)
    print(doctor.render(checks))
    print(f"\nOpen the dashboard:  {launch_command(target, kb_id, parent)}")
    print(LLM_LINE)
    hint = install_hooks.path_hint()
    if hint:
        print("\n" + hint, file=sys.stderr)
    return doctor.exit_code(checks)


if __name__ == "__main__":
    raise SystemExit(main())
