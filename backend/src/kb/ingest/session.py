"""Transaction lifecycle: begin, finalize, abort, rollback."""
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

from .paths import ROOT, load_session, save_session, session_dir, sha1_file
from .schemas import validate_plan
from . import book as book_mod
from .verify import existing_digest_for_raw, verify_raw
from kb.core import wikiio


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _backup_path(sha, wiki_rel):
    return os.path.join(session_dir(sha), "backup", os.path.basename(wiki_rel))


def _staging_dir(sha):
    return os.path.join(session_dir(sha), "staging")


def session_id(sha, scope):
    """One session per raw file — or per page range for a book part, so a second part of the
    same book never inherits the first part's claims/plan/staging."""
    if (scope or {}).get("book") and (scope or {}).get("pages"):
        a, b = scope["pages"]
        return f"{sha}-p{a}-{b}"
    return sha


def find_open_session(raw_rel):
    ingest = os.path.join(ROOT, "meta", ".ingest")
    if not os.path.isdir(ingest):
        return None
    for sha in os.listdir(ingest):
        sp = os.path.join(ingest, sha, "session.json")
        if not os.path.isfile(sp):
            continue
        with open(sp, encoding="utf-8") as f:
            s = json.load(f)
        if s.get("raw") == raw_rel and s.get("status") == "open":
            return sha
    return None


def _stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")


def _archive_stale(sha):
    """A closed/aborted session folder is history, not a place to start over in: rename it with
    a timestamp so the new session never inherits its files. Returns the claims/plan of an
    aborted one (to restore); empty for a closed one."""
    sdir = session_dir(sha)
    sp = os.path.join(sdir, "session.json")
    if not os.path.isfile(sp):
        return {}
    try:
        with open(sp, encoding="utf-8") as f:
            status = json.load(f).get("status")
    except (OSError, ValueError):
        status = None
    if status not in ("closed", "aborted"):
        return {}
    carried = {}
    if status == "aborted":
        for name in ("claims.json", "plan.json"):
            path = os.path.join(sdir, name)
            if os.path.isfile(path):
                with open(path, "rb") as f:
                    carried[name] = f.read()
    dest = f"{sdir}-{status}-{_stamp()}"
    n = 1
    while os.path.exists(dest):
        n += 1
        dest = f"{sdir}-{status}-{_stamp()}-{n}"
    os.rename(sdir, dest)
    print(f"archived previous {status} session → {os.path.relpath(dest, ROOT)}")
    return carried


def begin(raw_rel, depth="full", scope=None):
    raw_rel = verify_raw(raw_rel)
    existing = find_open_session(raw_rel)
    if existing:
        print(f"session already open: {existing}")
        return existing

    sha = session_id(sha1_file(raw_rel), scope)
    sdir = session_dir(sha)
    carried = _archive_stale(sha)
    os.makedirs(os.path.join(sdir, "backup"), exist_ok=True)
    for name, data in carried.items():          # an aborted attempt keeps its claims/plan
        with open(os.path.join(sdir, name), "wb") as f:
            f.write(data)
    if carried:
        print(f"restored {', '.join(sorted(carried))} from the aborted session")
    os.makedirs(_staging_dir(sha), exist_ok=True)

    backup_files = []
    book = (scope or {}).get("book")
    digest = existing_digest_for_raw(raw_rel, scope["pages"] if book else None)
    hub = book_mod.find_hub(raw_rel) if book else None
    for rel in dict.fromkeys(r for r in (digest, hub and hub[0]) if r):
        shutil.copy2(os.path.join(ROOT, rel), _backup_path(sha, rel))
        backup_files.append(rel)

    session = {
        "raw": raw_rel,
        "sha1": sha,
        "status": "open",
        "depth": depth,
        "opened_at": _now(),
        "backup_files": backup_files,
        "new_files": [],
        "modified_files": list(backup_files),
        "scope": scope or {},
    }
    save_session(sha, session)
    label = (scope or {}).get("label")
    print(f"session {sha} opened for {raw_rel}" + (f"\n  scope: {label}" if label else ""))
    return sha


def rollback(sha, reason="aborted"):
    session = load_session(sha)
    sdir = session_dir(sha)

    for wiki_rel in session.get("backup_files", []):
        bak = _backup_path(sha, wiki_rel)
        if os.path.isfile(bak):
            shutil.copy2(bak, os.path.join(ROOT, wiki_rel))

    staging = _staging_dir(sha)
    if os.path.isdir(staging):
        if os.listdir(staging):                # keep hand-written drafts
            keep = os.path.join(sdir, f"staging-aborted-{_stamp()}")
            n = 1
            while os.path.exists(keep):
                n += 1
                keep = os.path.join(sdir, f"staging-aborted-{_stamp()}-{n}")
            os.rename(staging, keep)
            print(f"staging kept at {os.path.relpath(keep, ROOT)}")
        else:
            shutil.rmtree(staging)
    os.makedirs(staging, exist_ok=True)

    for wiki_rel in session.get("new_files", []):
        target = os.path.join(ROOT, wiki_rel)
        if os.path.isfile(target) and wiki_rel not in session.get("backup_files", []):
            os.remove(target)

    session["status"] = reason
    session["closed_at"] = _now()
    save_session(sha, session)
    print(f"session {sha} {reason}")


def abort(sha):
    session = load_session(sha)
    if session["status"] != "open":
        print(f"session {sha} status is {session['status']!r}, nothing to abort")
        return 1
    rollback(sha, "aborted")
    return 0


def finalize(sha):
    session = load_session(sha)
    if session["status"] != "open":
        print(f"session {sha} status is {session['status']!r}, cannot finalize")
        return 1

    plan_path = os.path.join(session_dir(sha), "plan.json")
    if not os.path.isfile(plan_path):
        print("plan.json missing — run map first")
        return 1

    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)
    validate_plan(plan)

    staging = _staging_dir(sha)
    staged = [f for f in os.listdir(staging) if f.endswith(".md")]
    if not staged:
        print("staging/ empty — run draft first")
        return 1

    session["status"] = "finalizing"
    save_session(sha, session)

    # backup MOCs that will be patched
    for upd in plan.get("moc_updates", []):
        moc_rel = f"wiki/{upd['moc']}.md"
        if moc_rel not in session["backup_files"]:
            src = os.path.join(ROOT, moc_rel)
            if os.path.isfile(src):
                shutil.copy2(src, _backup_path(sha, moc_rel))
                session["backup_files"].append(moc_rel)
                session["modified_files"].append(moc_rel)
    save_session(sha, session)      # rollback() reloads session.json: persist the backups first

    promoted = []
    try:
        for fn in staged:
            src = os.path.join(staging, fn)
            dst_rel = f"wiki/{fn}"
            dst = os.path.join(ROOT, dst_rel)
            if os.path.isfile(dst):             # overwriting an existing page: back it up
                if dst_rel not in session["backup_files"]:
                    shutil.copy2(dst, _backup_path(sha, dst_rel))
                    session["backup_files"].append(dst_rel)
                    session["modified_files"].append(dst_rel)
            elif dst_rel not in session.setdefault("new_files", []):
                session["new_files"].append(dst_rel)     # concept/q- stubs: rollback deletes them
            save_session(sha, session)
            with open(src, encoding="utf-8") as f:
                wikiio.write_page(dst, f.read())     # an existing page keeps its ## My notes
            promoted.append(dst_rel)

        _apply_moc_updates(plan)
        _record_book_part(sha, session, plan)
        _record_hub_row(sha, session, plan)

        for q in plan.get("question_updates", []):
            if q.get("action") == "create" and q.get("staging_file"):
                qsrc = os.path.join(staging, q["staging_file"])
                qrel = f"wiki/{q['staging_file']}"
                if os.path.isfile(qsrc):
                    if not os.path.isfile(os.path.join(ROOT, qrel)) and qrel not in session["new_files"]:
                        session["new_files"].append(qrel)
                        save_session(sha, session)
                    with open(qsrc, encoding="utf-8") as f:
                        wikiio.write_page(os.path.join(ROOT, qrel), f.read())

        strict_slugs = [os.path.splitext(fn)[0] for fn in staged]
        lint_args = [sys.executable, "-m", "kb.lint.lint",
                     f"--ingest-strict={','.join(strict_slugs)}"]
        lint = subprocess.run(lint_args, cwd=ROOT, capture_output=True, text=True)
        if lint.returncode != 0:
            print(lint.stdout)
            print(lint.stderr, file=sys.stderr)
            raise RuntimeError("lint --ingest-strict failed")

        session["status"] = "closed"
        session["closed_at"] = _now()
        save_session(sha, session)
        _append_log(session, plan)
        print(f"session {sha} closed — {len(promoted)} file(s) promoted")
        try:
            from kb.search.semfind import bundle_from_ingest
            bundle_from_ingest(sha)
        except Exception as e:
            print(f"semfind bundle skipped: {e}", file=sys.stderr)
        return 0

    except Exception as e:
        print(f"finalize failed: {e}", file=sys.stderr)
        rollback(sha, "aborted")
        return 1


def _record_book_part(sha, session, plan):
    """A part digest ticks its row on the book hub page — creating the hub if needed."""
    scope = session.get("scope") or {}
    if plan.get("type") != "part" or not scope.get("pages"):
        return
    claims = {}
    cpath = os.path.join(session_dir(sha), "claims.json")
    if os.path.isfile(cpath):
        with open(cpath, encoding="utf-8") as f:
            claims = json.load(f)
    meta = {"authors": claims.get("authors"), "year": claims.get("year"),
            "url": claims.get("url"), "area": plan.get("areas_resolved") or [],
            "book_title": claims.get("book_title")}
    a, b = scope["pages"]
    status = session.get("depth") or "full"
    hub_rel, created = book_mod.record_part(session["raw"], a, b, plan["wiki_slug"], status,
                                            scope.get("label") or f"Pages {a}–{b}", meta)
    if created:
        session.setdefault("new_files", []).append(hub_rel)
    save_session(sha, session)
    print(f"book hub {hub_rel} {'created — write its ## Overview' if created else 'updated'}")


def _record_hub_row(sha, session, plan):
    """A course/series row digest ticks its row on the hub's Contents table."""
    scope = session.get("scope") or {}
    if not scope.get("hub"):
        return
    from . import course
    hub_rel = f"wiki/{scope['hub']}.md"
    if hub_rel not in session["backup_files"]:            # rollback restores it if lint fails
        shutil.copy2(os.path.join(ROOT, hub_rel), _backup_path(sha, hub_rel))
        session["backup_files"].append(hub_rel)
    status = session.get("depth") or "full"
    hub_rel = course.record_row(scope["hub"], scope.get("raws") or [session["raw"]],
                                plan["wiki_slug"], status)
    if hub_rel not in session.setdefault("modified_files", []):
        session["modified_files"].append(hub_rel)
    save_session(sha, session)
    print(f"hub {hub_rel} row {scope.get('row')} → [[{plan['wiki_slug']}]] ({status})")


def _insert_under_papers(text, wikilink):
    """Append `- [[x]]` at the end of the `## Papers` section (before the next `## `); create the
    section before `## Threads` (or at the end) if the theme has none."""
    lines = text.rstrip("\n").split("\n")
    bullet = f"- {wikilink}"
    start = next((i for i, l in enumerate(lines) if l.strip() == "## Papers"), None)
    if start is None:
        at = next((i for i, l in enumerate(lines) if l.strip() == "## Threads"), len(lines))
        block = ["## Papers", "", bullet, ""]
        if at == len(lines):
            block = [""] + block[:-1]
        lines[at:at] = block
        return "\n".join(lines).rstrip("\n") + "\n"
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    last = end
    while last > start + 1 and not lines[last - 1].strip():
        last -= 1
    lines.insert(last, bullet)
    return "\n".join(lines).rstrip("\n") + "\n"


def _apply_moc_updates(plan):
    for upd in plan.get("moc_updates", []):
        moc = upd["moc"]
        link = upd["link"]
        path = os.path.join(ROOT, "wiki", f"{moc}.md")
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            text = f.read()
        wikilink = f"[[{link}]]"
        if wikilink in text:
            continue
        wikiio.write_page(path, wikiio.edit_body(text, lambda t: _insert_under_papers(t, wikilink)))


def _append_log(session, plan):
    from kb.core import log as kblog
    kblog.append(ROOT, "ingest", plan.get("wiki_slug", "?"), (session["raw"],), when=_now())
