"""The nightly report — one readable digest of the vault's git/ops state, mailed every night.

Built from the generic blocks in src/kb_distillery/ops/report/: a status banner, what needs you, every open work
thread (src/kb_distillery/ops/threads.py) with its one next command, what changed in the last 24 h, the vault
backlog, and — when the sync failed — the cleaned log tail. The same `Doc` feeds the email
(src/kb_distillery/ops/notify.py), the Ops dashboard tab and this CLI.

    python3 -m kb_distillery.ops.nightly_report              # text preview (runs hygiene + threads, no sync)
    python3 -m kb_distillery.ops.nightly_report --html FILE  # the exact HTML mail
    python3 -m kb_distillery.ops.nightly_report --json
    python3 -m kb_distillery.ops.nightly_report --send       # send it now (ignores mode and throttle)
"""
import argparse
import datetime
import json
import os
import sys

from kb_distillery.paths import vault_root
META_DIR = os.path.join(vault_root(), "meta")
ROOT = vault_root()

from kb_distillery.ops.report import model as m
from kb_distillery.ops.report import sanitize

from . import threads as threads_mod  # noqa: E402

TITLE = "thesis-kb · nightly report"
DASHBOARD_URL = "http://127.0.0.1:8765/ops"
# hygiene finding kind → thread id, for findings that name no branch or path
KIND_TO_THREAD = {"unpushed-steps": "main:unpushed", "behind-origin": "main:behind", "other-lane": "dirty:other"}
RESTATING = {"stale-worktree", "unpruned-branch", "behind-origin", "unpushed-steps", "other-lane", "old-pr",
             "session-worktree", "stale-session"}


# ---------- data ----------

def attach(findings, threads):
    """Map each finding to the thread it is about → ({thread id: [findings]}, unattached findings)."""
    by_thread, loose = {}, []
    for f in findings:
        target = KIND_TO_THREAD.get(f.kind)
        if not target:
            for t in threads:
                key = t.id.split(":", 1)[1] if t.kind == "session" else None
                if (t.branch and t.branch != "main" and t.branch in f.detail) or (t.path and t.path in f.detail) \
                        or (key and key in f.detail):
                    target = t.id
                    break
        if target and any(t.id == target for t in threads):
            by_thread.setdefault(target, []).append(f)
        else:
            loose.append(f)
    return by_thread, loose


def recent_steps(root, now, hours=24, limit=60):
    from .history import timeline
    since = now - datetime.timedelta(hours=hours)
    rows = []
    for r in timeline(root, "main", limit=limit):
        when = threads_mod._parse(r["date"])
        if when and when >= since:
            rows.append(r)
    return rows


def vault_counts(root):
    """Backlog from meta/corpus.tsv (no lint run) + files waiting in raw/inbox/."""
    counts = {"source": 0, "queued": 0, "partial": 0, "skip": 0}
    try:
        with open(os.path.join(root, "meta", "corpus.tsv"), encoding="utf-8") as f:
            for line in f:
                cols = line.rstrip("\n").split("\t")
                if len(cols) >= 4 and not line.startswith("#") and cols[0] != "path" and cols[3] in counts:
                    counts[cols[3]] += 1
    except OSError:
        pass
    inbox = 0
    for _dir, _dirs, files in os.walk(os.path.join(root, "raw", "inbox")):
        inbox += sum(1 for name in files if not name.startswith("."))
    counts["inbox"] = inbox
    return counts


def site_status(root):
    try:
        from kb_distillery import publish
        return publish.current(root=root).status(root) or {}
    except Exception:  # noqa: BLE001 — the report renders without a publisher
        return {}


def kb_version(root):
    try:
        from kb_distillery.git import commit_policy as cp
        v = cp.last_version(root, "main")
        return f"kb-{cp.fmt_version(v)}" if v else ""
    except Exception:  # noqa: BLE001
        return ""


# ---------- doc ----------

def _local(dt):
    return dt.astimezone().strftime("%a %d %b %H:%M")


def _ago(iso, now):
    when = threads_mod._parse(iso)
    return threads_mod.age_label((now - when).total_seconds() / 3600) + " ago" if when else ""


def _card(t, findings, now):
    status = m.worst(t.status, *[f.severity for f in findings])
    facts = [["age", threads_mod.age_label(t.age_hours)]] if t.age_hours is not None else []
    if t.last_activity and t.kind not in ("session",):
        ago = _ago(t.last_activity, now)
        if ago:
            facts.append(["last commit" if t.branch else "last change", ago])
    for key in ("pr", "branch", "worktree", "dirty", "ahead", "behind", "files", "session"):
        if key in t.pieces and not (key == "branch" and t.kind == "pr" and t.title.endswith(t.branch)):
            facts.append([key, str(t.pieces[key])])
    # an attached finding usually restates the card ("… is merged into main"); keep only what adds to it
    notes = list(t.notes) + [f.detail for f in findings if f.detail not in t.notes
                             and (f.kind not in RESTATING or "uncommitted" in f.detail)]
    return m.Card(t.title, status=status, state=t.state, facts=facts, notes=notes, fix=t.next, link=t.link, id=t.id)


def build(root, report, threads, now=None, sync=None, log_tail=None, version=None, site=None, vault=None,
          steps=None):
    """Hygiene `report` + `threads` (+ sync outcome) → report Doc. Pure apart from the optional lookups."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    sync = sync or {}
    version = kb_version(root) if version is None else version
    site = site_status(root) if site is None else site
    vault = vault_counts(root) if vault is None else vault
    steps = recent_steps(root, now) if steps is None else steps
    by_thread, loose = attach(report.findings, threads)
    needs = [f for f in loose if f.severity == "error"] + [f for f in loose if f.severity != "error"]
    failed = bool(sync.get("failed"))
    errors = [f for f in report.findings if f.severity == "error"]
    stale = [t for t in threads if t.state != "active"]
    prs = [t for t in threads if t.kind == "pr"]

    if failed:
        status, title = "error", "Nightly sync failed"
    elif errors:
        status, title = "error", f"{len(errors)} thing{'s' if len(errors) != 1 else ''} need{'' if len(errors) != 1 else 's'} you"
    elif report.findings or stale:
        n = len(stale) + len(needs)
        status, title = "warn", f"{n} thing{'s' if n != 1 else ''} to tidy"
    else:
        status, title = "ok", "All clear"

    sub = [version] if version else []
    if failed:
        sub.append("sync failed")
    elif sync.get("skipped"):
        sub.append("sync skipped")
    elif sync.get("pushed") is not None:
        sub.append("pushed" if sync["pushed"] else "nothing pushed")
    sub.append(f"{len(threads)} open thread{'s' if len(threads) != 1 else ''}")
    if site.get("state"):
        sub.append(f"site {site['state']}" + (f" {_ago(site.get('at'), now)}" if site.get("at") else ""))

    head = m.Section("", [
        m.Banner(status, title, " · ".join(sub)),
        m.Stats([
            m.Stat("Open PRs", str(len(prs)), "warn" if any(t.state == "stale" for t in prs) else ""),
            m.Stat("Threads", str(len(threads)), "warn" if stale else "", f"{len(stale)} stale" if stale else "all active"),
            m.Stat("Steps 24 h", str(sum(1 for r in steps if r["kind"] == "kb"))),
        ]),
    ])
    sections = [head]

    if failed or needs:
        items = []
        if failed:
            items.append(m.Item("error", "sync", sanitize.summarize_error(sync.get("error") or "") or "the nightly sync did not finish",
                                "pixi run daily-sync   # after fixing", more=sanitize.clean_block(sync.get("error") or "", root)))
        items += [m.Item(f.severity, f.kind, f.detail, f.fix, getattr(f, "more", "")) for f in needs]
        sections.append(m.Section("Needs you", [m.Findings(items)], id="needs"))

    active = len(threads) - len(stale)
    sections.append(m.Section("Open threads", [m.Cards([_card(t, by_thread.get(t.id, []), now) for t in threads],
                                                       empty="No open work — every branch is merged and pruned.")],
                              note=f"{len(stale)} stale · {active} active" if threads else "", id="threads"))

    rows = []
    for r in steps:
        if r["kind"] == "kb":
            rows.append([f"kb-{r['kb_version']}" if r["kb_version"] else r["short"], r.get("op") or r.get("scope") or "",
                         sanitize.truncate(r.get("target") or r.get("summary") or "", 70)])
        elif r["kind"] == "pr-merge":
            rows.append([f"#{r['pr']}" if r.get("pr") else r["short"], "merge", sanitize.truncate(r.get("summary") or r["subject"], 70)])
    shown = rows[:12]
    blocks = [m.Table(["Step", "Op", "What"], shown)] if shown else [m.Text("No knowledge steps or merges.", muted=True)]
    if len(rows) > 3:
        ops = {}
        for r in rows:
            ops[r[1]] = ops.get(r[1], 0) + 1
        blocks.insert(0, m.Text(f"{len(rows)} steps — " + ", ".join(f"{n} {op}" for op, n in
                                                               sorted(ops.items(), key=lambda kv: -kv[1])), muted=True))
    if len(rows) > len(shown):
        blocks.append(m.Text(f"… and {len(rows) - len(shown)} more — pixi run ops -- log", muted=True))
    sections.append(m.Section("Last 24 hours", blocks, id="recent"))

    sections.append(m.Section("Vault", [m.Stats([
        m.Stat("Inbox", str(vault.get("inbox", 0)), "warn" if vault.get("inbox", 0) >= 30 else ""),
        m.Stat("Queued", str(vault.get("queued", 0)), hint="backlog"),
        m.Stat("Partial books", str(vault.get("partial", 0))),
        m.Stat("Sources", str(vault.get("source", 0))),
    ])], id="vault"))

    if failed and log_tail:
        sections.append(m.Section("Sync log", [m.Code(sanitize.clean_block(log_tail, root, max_lines=30),
                                                      "last lines of ~/Library/Logs/thesis-kb-daily-sync.log")], id="log"))

    footer = [f"run {_local(now)} · {report.elapsed:.1f} s · {len(report.checks)} checks",
              "config meta/ops/sync.toml · run log meta/.ops/runs.jsonl"]
    links = [["Ops dashboard", DASHBOARD_URL]]
    gh = threads_mod.github_url(root)
    if gh:
        links.append(["Pull requests", f"{gh}/pulls"])
    return m.Doc(TITLE, status, f"{title} — {' · '.join(sub)}", sections, footer, _local(now), links)


def subject(doc, report, prefix="[thesis-kb]"):
    kinds = report.kinds()
    tail = (" · " + ", ".join(kinds[:3]) + (", …" if len(kinds) > 3 else "")) if kinds else ""
    glyph = {"ok": "✓", "warn": "!", "error": "✗"}.get(doc.status, "·")
    banner = doc.sections[0].blocks[0] if doc.sections and doc.sections[0].blocks else None
    title = banner.title if isinstance(banner, m.Banner) else doc.headline
    if doc.status == "ok":
        n = sum(1 for s in doc.sections if s.id == "threads" for b in s.blocks for _ in b.items)
        return f"{prefix} {glyph} {title.lower()} · {n} open thread{'s' if n != 1 else ''}"
    return f"{prefix} {glyph} {title}{tail}"


# ---------- CLI ----------

def collect(root=ROOT, now=None, budget=None):
    """Run hygiene + threads now → (report, threads, doc)."""
    from . import hygiene
    now = now or datetime.datetime.now(datetime.timezone.utc)
    report = hygiene.run(root, now=now, **({"budget": budget} if budget else {}))
    threads = threads_mod.collect(root, now)
    return report, threads, build(root, report, threads, now)


def main(argv=None):
    p = argparse.ArgumentParser(prog="nightly-report", description="preview or send the nightly report")
    p.add_argument("--html", metavar="FILE", help="write the HTML mail to FILE")
    p.add_argument("--json", action="store_true")
    p.add_argument("--send", action="store_true", help="send it now (ignores mode and throttle)")
    p.add_argument("--root", default=None, help="vault checkout (default: the primary checkout)")
    args = p.parse_args(argv)
    from kb_distillery.ops.report import render_html, render_text
    from kb_distillery.git import ship
    root = args.root or ship.primary_checkout(ROOT)
    report, threads, doc = collect(root)
    if args.html:
        with open(args.html, "w", encoding="utf-8") as f:
            f.write(render_html.render(doc))
        print(f"wrote {args.html}")
    if args.json:
        print(json.dumps(doc.as_dict(), indent=2, ensure_ascii=False))
    elif not args.html:
        print(subject(doc, report))
        print(render_text.render(doc))
    if args.send:
        from kb_distillery.ops import notify
        cfg = notify.load_config(root)
        ok = notify.send_email(subject(doc, report), render_text.render(doc), cfg.get("email", ""),
                               html=render_html.render(doc))
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
