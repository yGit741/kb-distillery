#!/usr/bin/env python3
"""Skill linter — validates skills/ structure, README ladder sync, and CLI references.

    python3 -m kb.lint.lint_skills          ERROR fail, WARN print
    python3 -m kb.lint.lint_skills --strict WARN promoted to ERROR

Run before sync-skills and in pre-commit when skills change.
"""
import os
import re
import sys
from typing import Optional

from kb.maintenance.sync_skills import DEPRECATED
from kb.paths import CHECKOUT_ROOT, CODE_DIR, vault_root

ROOT = CHECKOUT_ROOT          # skills are code: they live with the explorer
SKILLS_ROOT = os.path.join(ROOT, "skills")
README_PATH = os.path.join(SKILLS_ROOT, "README.md")
PIXI_TOML = os.path.join(ROOT, "pixi.toml")

META_SKILLS = frozenset({"create-skill"})
ROOT_EXCLUDE = frozenset({"README.md", "SKILL_TEMPLATE.md"})
ALLOWED_TIERS = frozenset({
    "none", "light", "medium", "heavy", "light-medium", "light–medium",
})
NEGATIVE_TRIGGER_RE = re.compile(r"Do NOT|ONLY|never|Never", re.I)
USE_TRIGGER_RE = re.compile(r"\bUse\b")
DO_NOT_CLAUSE_RE = re.compile(r"Do NOT")
LADDER_SKILL_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|")
SKILLS_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+/SKILL\.md)\)")
BASH_BLOCK_RE = re.compile(r"```bash\s*\n(.*?)```", re.S)
ADD_PARSER_RE = re.compile(r"add_parser\(\s*[\"']([^\"']+)[\"']")
errors: list[str] = []
warnings: list[str] = []


def err(path: str, msg: str) -> None:
    errors.append(f"{path}: {msg}")


def warn(path: str, msg: str) -> None:
    warnings.append(f"{path}: {msg}")


def parse_frontmatter(text: str) -> Optional[dict]:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    fm: dict = {}
    block_lines = text[3:end].splitlines()
    i = 0
    while i < len(block_lines):
        line = block_lines[i]
        raw = line.split("#")[0].rstrip()
        if not raw.strip():
            i += 1
            continue
        if ":" not in raw or raw.startswith((" ", "\t", "-")):
            i += 1
            continue
        k, v = raw.split(":", 1)
        k = k.strip()
        v = v.strip()
        if v in (">-", ">", "|", "|-"):
            parts: list[str] = []
            i += 1
            while i < len(block_lines):
                cont = block_lines[i]
                if cont.startswith((" ", "\t")):
                    parts.append(cont.strip())
                    i += 1
                else:
                    break
            fm[k] = " ".join(parts).strip()
            continue
        if v.startswith(">") or v.startswith("|"):
            v = v.lstrip(">|- ").strip()
        fm[k] = v
        i += 1
    return fm


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _subcommands(cli_path: str) -> frozenset[str]:
    if not os.path.isfile(cli_path):
        return frozenset()
    text = _read(cli_path)
    return frozenset(ADD_PARSER_RE.findall(text))


def _pixi_tasks() -> frozenset[str]:
    if not os.path.isfile(PIXI_TOML):
        return frozenset()
    tasks: set[str] = set()
    in_tasks = False
    for line in _read(PIXI_TOML).splitlines():
        if line.strip() == "[tasks]":
            in_tasks = True
            continue
        if in_tasks and line.startswith("[") and line.endswith("]"):
            break
        if in_tasks and "=" in line and not line.strip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key:
                tasks.add(key)
    return frozenset(tasks)


def _kb_modules() -> frozenset[str]:
    """Every runnable `python -m kb.<dotted>` target: modules and packages with a __main__."""
    mods: set[str] = set()
    for dp, dns, fns in os.walk(CODE_DIR):
        dns[:] = [d for d in dns if d != "__pycache__"]
        rel = os.path.relpath(dp, CODE_DIR)
        prefix = "kb" if rel == "." else "kb." + rel.replace(os.sep, ".")
        if "__main__.py" in fns:
            mods.add(prefix)
        for fn in fns:
            if fn.endswith(".py") and fn not in ("__init__.py", "__main__.py") and not fn[:4].isdigit():
                mods.add(f"{prefix}.{fn[:-3]}")
    return frozenset(mods)


INGEST_SUBCMDS = _subcommands(os.path.join(CODE_DIR, "ingest", "cli.py"))
DISTILL_SUBCMDS = _subcommands(os.path.join(CODE_DIR, "distill", "cli.py"))
PIXI_TASKS = _pixi_tasks()
KB_MODULES = _kb_modules()


def parse_ladder_skills(readme_text: str) -> list[str]:
    skills: list[str] = []
    in_table = False
    for line in readme_text.splitlines():
        if "## Token budgets" in line:
            in_table = True
            continue
        if in_table and line.startswith("## ") and "Token budgets" not in line:
            break
        if in_table:
            m = LADDER_SKILL_RE.match(line)
            if m:
                skills.append(m.group(1))
    return skills


def parse_skills_table_links(readme_text: str) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    in_table = False
    for line in readme_text.splitlines():
        if line.startswith("## Skills"):
            in_table = True
            continue
        if in_table and line.startswith("## ") and "Skills" not in line:
            break
        if in_table:
            for m in SKILLS_LINK_RE.finditer(line):
                links.append((m.group(1), m.group(2)))
    return links


def top_level_skill_dirs(skills_root: str) -> list[str]:
    dirs: list[str] = []
    if not os.path.isdir(skills_root):
        return dirs
    for name in sorted(os.listdir(skills_root)):
        if name in DEPRECATED or name in ROOT_EXCLUDE:
            continue
        path = os.path.join(skills_root, name)
        if os.path.isdir(path):
            dirs.append(name)
    return dirs


def find_subskills(skills_root: str, parent: str) -> list[tuple[str, str]]:
    """Return [(subdir_name, rel_path)] for nested SKILL.md files."""
    out: list[tuple[str, str]] = []
    parent_path = os.path.join(skills_root, parent)
    if not os.path.isdir(parent_path):
        return out
    for sub in sorted(os.listdir(parent_path)):
        sub_path = os.path.join(parent_path, sub)
        skill_md = os.path.join(sub_path, "SKILL.md")
        if os.path.isdir(sub_path) and os.path.isfile(skill_md):
            prefix = os.path.relpath(skills_root, ROOT).replace(os.sep, "/")
            rel = f"{prefix}/{parent}/{sub}/SKILL.md"
            out.append((sub, rel))
    return out


def _strip_comment(line: str) -> str:
    if "#" in line:
        line = line.split("#", 1)[0]
    return line.strip()


def _has_placeholder(line: str) -> bool:
    return "<" in line or ">" in line or "…" in line


def validate_cli_line(rel_path: str, line: str) -> None:
    line = _strip_comment(line)
    if not line:
        return
    if _has_placeholder(line):
        return

    if line.startswith("pixi run "):
        parts = line.split()
        if len(parts) >= 3:
            task = parts[2]
            if task not in PIXI_TASKS:
                err(rel_path, f"unknown pixi task: {task}")
        return

    if line.startswith("python3 -m kb.ingest "):
        parts = line.split()
        if len(parts) >= 4:
            sub = parts[3]
            if sub not in INGEST_SUBCMDS:
                err(rel_path, f"unknown kb.ingest subcommand: {sub}")
        return

    if line.startswith("python3 -m kb.distill "):
        parts = line.split()
        if len(parts) >= 4:
            sub = parts[3]
            if sub not in DISTILL_SUBCMDS:
                err(rel_path, f"unknown kb.distill subcommand: {sub}")
        return

    m = re.match(r"python3 -m (kb(?:\.\w+)*)(?:\s|$)", line)
    if m:
        if m.group(1) not in KB_MODULES:
            err(rel_path, f"unknown module: {m.group(1)}")
        return


def validate_cli_blocks(rel_path: str, body: str) -> None:
    for block in BASH_BLOCK_RE.findall(body):
        for raw_line in block.splitlines():
            validate_cli_line(rel_path, raw_line)


def check_skill_md(rel_path: str, is_top_level: bool, parent: Optional[str] = None) -> None:
    full = os.path.join(ROOT, rel_path.replace("/", os.sep))
    if not os.path.isfile(full):
        err(rel_path, "missing SKILL.md")
        return

    text = _read(full)
    lines = text.splitlines()
    fm = parse_frontmatter(text)
    body = text
    if fm is not None:
        body_start = text.find("\n---", 3)
        if body_start != -1:
            body = text[body_start + 4:]

    dir_name = rel_path.split("/")[-2]

    if fm is None:
        err(rel_path, "missing YAML frontmatter")
        return

    name = fm.get("name", "").strip()
    desc = fm.get("description", "").strip()

    if not name:
        err(rel_path, "frontmatter missing name")
    if not desc:
        err(rel_path, "frontmatter missing description")
    elif len(desc) < 20:
        err(rel_path, f"description too short ({len(desc)} chars, min 20)")
    elif len(desc) > 500:
        err(rel_path, f"description too long ({len(desc)} chars, max 500)")

    if is_top_level:
        if name and name != dir_name:
            err(rel_path, f"name '{name}' != directory '{dir_name}'")
    else:
        expected = f"{parent}-{dir_name}"
        if name and name != expected:
            err(rel_path, f"name '{name}' != expected '{expected}'")

    if not re.search(r"## Triggers", body):
        warn(rel_path, "missing ## Triggers section")
    if not re.search(r"## Do NOT", body):
        warn(rel_path, "missing ## Do NOT section")
    if "**LLM tier:**" not in body:
        warn(rel_path, "missing **LLM tier:** line in body")

    if desc and not NEGATIVE_TRIGGER_RE.search(desc):
        warn(rel_path, "description lacks negative trigger (Do NOT / ONLY / never)")
    if desc and not USE_TRIGGER_RE.search(desc):
        warn(rel_path, 'description lacks a "Use for/when ..." trigger line')
    if desc and not DO_NOT_CLAUSE_RE.search(desc):
        warn(rel_path, 'description lacks a "Do NOT use for ..." near-miss clause')

    if len(lines) > 400:
        warn(rel_path, f"SKILL.md too long ({len(lines)} lines, max 400)")

    digest_skills = {"easy-digest", "full-digest", "deep-digest"}
    skill_slug = dir_name if is_top_level else parent
    if skill_slug in digest_skills:
        combined = desc + body
        if not re.search(r"ask|bare [`']digest[`']|[`']digest[`'] alone", combined, re.I):
            warn(rel_path, "digest skill missing ask-tier / bare digest rule")

    wiki_write = re.search(r"write.*wiki/|wiki/.*write", body, re.I)
    guard_ref = re.search(r"guard|finalize|ingest session", body, re.I)
    if wiki_write and not guard_ref:
        warn(rel_path, "mentions writing wiki/ without guard/session/finalize reference")

    validate_cli_blocks(rel_path, body)


def check_parent_subskill_table(parent: str, subdirs: list[str], body: str) -> None:
    rel = f"skills/{parent}/SKILL.md"
    for sub in subdirs:
        if sub not in body:
            warn(rel, f"parent missing subskill table reference for '{sub}'")


def check_readme(readme_text: str, skills_root: str) -> tuple[list[str], list[tuple[str, str]]]:
    ladder = parse_ladder_skills(readme_text)
    links = parse_skills_table_links(readme_text)

    tier_section = False
    for line in readme_text.splitlines():
        if "## Token budgets" in line:
            tier_section = True
            continue
        if tier_section and line.startswith("|") and "`" in line:
            for tier in ALLOWED_TIERS:
                if tier in line:
                    break
            else:
                if LADDER_SKILL_RE.match(line):
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) > 2:
                        tier_val = parts[2].strip()
                        normalized = tier_val.replace("–", "-")
                        if normalized not in {t.replace("–", "-") for t in ALLOWED_TIERS}:
                            warn("skills/README.md", f"unusual tier value: {tier_val}")

    readme_rel = os.path.relpath(os.path.join(skills_root, "README.md"), ROOT).replace(os.sep, "/")
    for label, href in links:
        target = os.path.join(skills_root, href.replace("/", os.sep))
        if not os.path.isfile(target):
            err(readme_rel, f"broken skills link [{label}]({href})")

    return ladder, links


def run_checks(strict: bool = False, skills_root: Optional[str] = None) -> tuple:
    global errors, warnings
    errors = []
    warnings = []

    root_skills = skills_root or SKILLS_ROOT
    readme_path = os.path.join(root_skills, "README.md")
    skills_prefix = os.path.relpath(root_skills, ROOT).replace(os.sep, "/")

    if not os.path.isdir(root_skills):
        err(skills_prefix, "skills directory missing")
        return len(errors), len(warnings)

    if skills_root is None:
        from kb.maintenance.sync_skills import LINKS, LINK_TARGET, link_ok
        for link in LINKS:
            if not link_ok(link):
                warn(os.path.relpath(link, ROOT).replace(os.sep, "/"),
                     f"not a symlink to {LINK_TARGET} (run pixi run sync-skills)")

    for dep in DEPRECATED:
        dep_path = os.path.join(root_skills, dep)
        if os.path.isdir(dep_path):
            err(f"{skills_prefix}/{dep}", "deprecated skill directory still present")

    tops = top_level_skill_dirs(root_skills)
    readme_text = _read(readme_path) if os.path.isfile(readme_path) else ""
    ladder, _ = check_readme(readme_text, root_skills) if readme_text else ([], [])

    ladder_set = set(ladder)

    for skill in ladder:
        skill_md = os.path.join(root_skills, skill, "SKILL.md")
        if not os.path.isfile(skill_md):
            err(f"{skills_prefix}/{skill}", "in README ladder but missing SKILL.md")

    for name in tops:
        skill_md = os.path.join(root_skills, name, "SKILL.md")
        rel = f"{skills_prefix}/{name}/SKILL.md"
        if not os.path.isfile(skill_md):
            err(f"{skills_prefix}/{name}", "directory without SKILL.md")
            continue
        if name not in META_SKILLS and name not in ladder_set:
            err(rel, "top-level skill not in README Token budgets table")
        check_skill_md(rel, is_top_level=True)

        subskills = find_subskills(root_skills, name)
        if subskills:
            parent_body = _read(skill_md)
            sub_names = [s[0] for s in subskills]
            check_parent_subskill_table(name, sub_names, parent_body)
        for sub, sub_rel in subskills:
            check_skill_md(sub_rel, is_top_level=False, parent=name)

    if strict:
        for w in warnings:
            errors.append(w)
        warnings = []

    return len(errors), len(warnings)


def main(argv: Optional[list] = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    strict = "--strict" in args
    n_err, n_warn = run_checks(strict=strict)

    for w in warnings:
        print(f"WARN {w}")
    for e in errors:
        print(f"ERROR {e}")

    print(f"skill lint: {n_err} error(s), {n_warn} warning(s)")
    return 1 if n_err else 0


if __name__ == "__main__":
    raise SystemExit(main())
