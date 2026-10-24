"""Public snapshots: audit a public build, publish it as its own Worker, list / remove / prune.

    pixi run share -- audit <ref> [--allow-flags]                 build public, scan, no deploy
    pixi run share -- snapshot <name> <ref> [--replace [--force]] [--allow-flags] [--dry-run]
    pixi run share -- list [--json]
    pixi run share -- history <name-or-worker> [--json]
    pixi run share -- remove <name-or-worker> [--yes]
    pixi run share -- prune [--apply]

Snapshots are PUBLIC by design (no sign-in): Worker `snapshot-<YYYYMMDD>-<name>` at
`https://snapshot-<YYYYMMDD>-<name>.<subdomain>.workers.dev/`. Cloudflare is the registry —
`list` / `prune` recognise ours by the `snapshot-` prefix and the `kb-share` deploy message.
The live Worker `kb` is never touched by anything here.

**Updating a snapshot whose link is already out** is `snapshot <name> <ref> --replace`: the same
Worker (same URL) starts serving the new build, so the link keeps working and the recipient
sees the newer knowledge version in the footer (`kb x.y.z · built <commit date>`; the URL keeps
its creation date). What makes that safe rather than a silent rewrite: the audit runs again,
the never-same / never-older guard of `deploy` applies (an older ref needs `--force`), every
previous version stays on Cloudflare — `history <name>` lists them with their kb version and
`rollback --worker <worker> [--to <id>]` brings one back — and `list` shows how many times a
snapshot was updated.

`audit` scans the data embedded in the public build (`<script id="kb-data">`): page counts by
type, and flags person pages, `conversation-` / `ai-chat` pages, email addresses, phone-number
patterns, `raw/` paths in prose and any `distilled-think` page. `snapshot` runs it first and
refuses on flags unless `--allow-flags`.

Cloudflare goes through `kb.share.cf_api` (mockable seams); the upload reuses
`kb.share.deploy.deploy(require_access=False)` with its own status file under CACHE_DIR.
"""
import datetime as _dt
import json
import re
import tempfile
from collections import Counter
from pathlib import Path
from typing import Optional

from kb.share import cf_api
from kb.share.contracts import (ACCOUNT_SUBDOMAIN, CACHE_DIR, DEPLOY_MESSAGE_PREFIX, REPO, SNAPSHOT_PREFIX,
                                  WORKER_MAIN, snapshot_worker_name)

MANIFEST_TIMEOUT = 10
_DATA_RE = re.compile(r'<script type="application/json" id="kb-data">(.*?)</script>', re.S)
_SNAPSHOT_RE = re.compile(rf"^{re.escape(SNAPSHOT_PREFIX)}(?P<date>\d{{8}})-(?P<name>[a-z0-9]([a-z0-9-]*[a-z0-9])?)$")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_PHONE_RE = re.compile(r"(?<![\w/-])(?<!\d\.)(?:\+\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)|\d{2,4})[\s.-]\d{3}[\s.-]?\d{4}(?!\w|[./-]\d)")
_RAW_RE = re.compile(r"(?<![\w/])raw/(?:inbox|papers|slides|notes|mail|web|assets|chats|printed-docs|handwritten|presentations|llm-chats|emails|web-clips|images)(?:/[^\s`'\")\]]*)?")
_CHAT_RE = re.compile(r"(?:^|-)(?:conversation|ai-chat)(?:-|$)")
FLAG_KINDS = ("person", "chat", "email", "phone", "raw-path", "distilled-think")


# ---------- audit ----------

def extract_data(html: str) -> dict:
    m = _DATA_RE.search(html)
    if not m:
        raise RuntimeError("build has no embedded kb-data")
    return json.loads(m.group(1))


def _texts(page: dict):
    """Strings of a page doc worth scanning: markdown body, frontmatter values, card title/preview."""
    yield page.get("markdown") or ""
    for v in (page.get("frontmatter") or {}).values():
        yield " ".join(map(str, v)) if isinstance(v, list) else str(v)
    card = page.get("card") or {}
    yield str(card.get("title") or "")
    yield str(card.get("preview") or "")


def scan(data: dict) -> dict:
    """{counts: {type: n}, flags: [{kind, page, detail}]} for the embedded public data."""
    pages = data.get("pages") or {}
    cards = {c["id"]: c for c in (data.get("index") or {}).get("pages") or []}
    nodes = {n["id"]: n for n in (data.get("graph") or {}).get("nodes") or []}
    counts = Counter()
    flags = []

    def flag(kind, page, detail):
        flags.append({"kind": kind, "page": page, "detail": detail})

    slugs = sorted(set(pages) | set(cards) | set(nodes))
    for slug in slugs:
        page = pages.get(slug) or {}
        card = cards.get(slug) or page.get("card") or {}
        ptype = card.get("type") or nodes.get(slug, {}).get("type") or "unknown"
        counts[ptype] += 1
        if ptype == "person":
            flag("person", slug, "person page")
        if ptype == "distilled-think":
            flag("distilled-think", slug, "distilled-think page survived the public profile")
        if _CHAT_RE.search(slug) or ptype in ("conversation", "ai-chat"):
            flag("chat", slug, "conversation / ai-chat page")
        text = "\n".join(_texts(page))
        for found in sorted(set(_EMAIL_RE.findall(text))):
            flag("email", slug, found)
        for found in sorted(set(m.group(0).strip() for m in _PHONE_RE.finditer(text))):
            flag("phone", slug, found)
        for found in sorted(set(_RAW_RE.findall(text))):
            flag("raw-path", slug, found)
    return {"counts": dict(sorted(counts.items())), "flags": flags, "pages": len(slugs)}


def audit_build(ref: str, root: Path = REPO):
    """Build `ref` with the public profile into a temp dir and scan it → (report, build_dir, tmpdir)."""
    from kb.share.build import build  # lazy: the builder is heavy and its own module
    tmp = tempfile.TemporaryDirectory(prefix="kb-share-audit-")
    result = build(ref, profile="public", root=root, out_root=Path(tmp.name), label="public")
    html = (Path(result.dir) / "index.html").read_text(encoding="utf-8")
    report = scan(extract_data(html))
    report["manifest"] = json.loads((Path(result.dir) / "manifest.json").read_text(encoding="utf-8"))
    return report, result.dir, tmp


def print_report(report: dict) -> None:
    m = report.get("manifest") or {}
    if m:
        print(f"public build of {m.get('content_ref')} — kb {m.get('kb_version')} · {str(m.get('content_sha', ''))[:7]}")
    print(f"{'type':<18}{'pages':>6}")
    for t, n in report["counts"].items():
        print(f"{t:<18}{n:>6}")
    print(f"{'total':<18}{report['pages']:>6}")
    flags = report["flags"]
    if not flags:
        print("flags: none")
        return
    by_kind = Counter(f["kind"] for f in flags)
    print(f"flags: {len(flags)} (" + ", ".join(f"{k} {by_kind[k]}" for k in FLAG_KINDS if by_kind[k]) + ")")
    print(f"{'kind':<16}{'page':<48}detail")
    for f in flags:
        print(f"{f['kind']:<16}{f['page'][:46]:<48}{f['detail']}")


def cmd_audit(args) -> int:
    try:
        report, _dir, tmp = audit_build(args.ref)
    except Exception as e:  # noqa: BLE001 — the user wants the reason, not a traceback
        print(f"audit failed: {e}")
        return 1
    with tmp:
        print_report(report)
    if report["flags"] and not args.allow_flags:
        print("audit: flags found — fix them or pass --allow-flags")
        return 1
    return 0


# ---------- registry helpers ----------

def worker_url(worker: str) -> str:
    return f"https://{worker}.{ACCOUNT_SUBDOMAIN}.workers.dev/"


def parse_worker(worker: str) -> Optional[dict]:
    """{date, name} when `worker` is one of our snapshot Workers by name, else None."""
    m = _SNAPSHOT_RE.match(worker or "")
    return {"date": m.group("date"), "name": m.group("name")} if m else None


def snapshot_scripts() -> list:
    return [s for s in cf_api.list_scripts() if parse_worker(s["name"])]


def resolve_target(target: str, scripts=None) -> list:
    """Snapshot Workers matching a bare name or a full worker name (never `kb`)."""
    target = (target or "").strip()
    scripts = snapshot_scripts() if scripts is None else [s for s in scripts if parse_worker(s["name"])]
    if not target or target == WORKER_MAIN:
        return []
    return [s for s in scripts if s["name"] == target or parse_worker(s["name"])["name"] == target]


def main_versions(root: Path = REPO, rev: str = "main") -> list:
    """Distinct knowledge versions on `rev`'s first-parent history, newest first (x.y.z strings)."""
    from kb.git.commit_policy import _git, fmt_version, parse_trailers, parse_version
    out = _git(str(root), "log", "--first-parent", "-n2000", "--format=%B%x1e", rev, "--")
    seen, versions = set(), []
    if out.returncode != 0:
        return versions
    for body in out.stdout.split("\x1e"):
        v = parse_version(parse_trailers(body).get("KB-Version"))
        if v and v not in seen:
            seen.add(v)
            versions.append(fmt_version(v))
    return versions


def behind_main(version: Optional[str], versions: list) -> Optional[int]:
    """Number of knowledge steps between `version` and main's head; None when not on main."""
    from kb.git.commit_policy import parse_version
    v = parse_version(version)
    if not v:
        return None
    key = "%d.%d.%d" % v
    return versions.index(key) if key in versions else None


def _utc_today() -> _dt.date:
    return _dt.datetime.now(_dt.timezone.utc).date()


# ---------- snapshot ----------

def cmd_snapshot(args) -> int:
    from kb.share.deploy import deploy
    try:
        worker = snapshot_worker_name(args.name, _utc_today())
    except ValueError as e:
        print(f"snapshot: {e}")
        return 2
    try:
        report, build_dir, tmp = audit_build(args.ref)
    except Exception as e:  # noqa: BLE001
        print(f"snapshot: build/audit failed: {e}")
        return 1
    with tmp:
        print_report(report)
        if report["flags"] and not args.allow_flags:
            print("snapshot: audit flags found — fix them or pass --allow-flags")
            return 1
        try:
            existing = resolve_target(args.name)
        except cf_api.CloudflareError as e:
            print(f"snapshot: {e}")
            return 1
        if existing and not args.replace:
            print("snapshot: a Worker with this name already exists — pass --replace to redeploy it in place:")
            for s in existing:
                print(f"  {s['name']}  {worker_url(s['name'])}")
            return 1
        if existing and args.replace:
            if len(existing) > 1:
                print("snapshot: --replace is ambiguous, several Workers carry this name:")
                for s in existing:
                    print(f"  {s['name']}")
                return 1
            worker = existing[0]["name"]
        m = report["manifest"]
        message = f"{DEPLOY_MESSAGE_PREFIX} {m['content_sha']} {m['kb_version']} {m['profile']}"
        url = worker_url(worker)
        if existing:
            live = _live_version(worker)
            print(f"update: {worker} serves kb {live or '?'} → will serve kb {m['kb_version']} at the same URL"
                  + (" (--force: downgrade allowed)" if args.force else ""))
        if args.dry_run:
            print(f"dry-run: would {'replace' if existing else 'create'} {worker} ← {message}")
            print(f"dry-run: {url}")
            return 0
        # Replacing keeps deploy's never-same / never-older guard: an update that would hand the
        # recipient an older knowledge version than the one they already saw needs --force.
        result = deploy(build_dir, worker, require_access=False, force=bool(existing) and args.force, message=message,
                        status_path=Path(CACHE_DIR) / f"status-{worker}.json")
    if result.state == "deployed":
        print(f"{'replaced' if existing else 'created'} {worker} (public, no sign-in)")
        if existing:
            print(f"previous versions stay on Cloudflare: `share history {args.name}`; "
                  f"undo with `share rollback --worker {worker}`")
        print(url)
        return 0
    if result.state == "skipped-same":
        print(f"snapshot: {worker} already serves this content (kb {m['kb_version']}) — nothing deployed")
        print(url)
        return 0
    if result.state == "skipped-older":
        print(f"snapshot: refused — {worker} serves a NEWER knowledge version than {args.ref} "
              f"({result.error}); pass --force to downgrade the link on purpose")
        return 1
    print(f"snapshot: {result.state} {result.url or ''}" + (f" — {result.error}" if result.error else ""))
    return 1


def _live_version(worker: str) -> Optional[str]:
    """kb version the Worker serves now (manifest first, deploy message as fallback), or None."""
    try:
        state, manifest = cf_api.fetch_manifest(worker_url(worker), MANIFEST_TIMEOUT)
        if state == "ok" and manifest and manifest.get("kb_version"):
            return str(manifest["kb_version"])
        dep = cf_api.latest_deployment(worker) or {}
        parts = (dep.get("message") or "").split()
        return parts[2] if len(parts) > 2 and parts[0] == DEPLOY_MESSAGE_PREFIX else None
    except cf_api.CloudflareError:
        return None


# ---------- list ----------

def list_snapshots(fetch_manifests: bool = True, versions: Optional[list] = None) -> list:
    """Rows for our snapshot Workers: {worker, name, date, url, version, sha, behind_main, deployed_at, views,
    views_note, online, updates, first_version} — `updates` = in-place replacements so far (uploaded
    versions − 1), `first_version` the kb version it was created with."""
    rows = []
    for s in snapshot_scripts():
        dep = cf_api.latest_deployment(s["name"]) or {}
        message = dep.get("message") or ""
        if not message.startswith(DEPLOY_MESSAGE_PREFIX):
            continue
        parts = message.split()
        info = parse_worker(s["name"])
        trail = history(s["name"])
        rows.append({"worker": s["name"], "name": info["name"], "date": info["date"], "url": worker_url(s["name"]),
                     "sha": parts[1] if len(parts) > 1 else "", "version": parts[2] if len(parts) > 2 else "",
                     "deployed_at": dep.get("created_on") or s.get("modified_on"), "online": None,
                     "views": 0, "views_note": "", "updates": max(len(trail) - 1, 0),
                     "first_version": trail[-1]["version"] if trail else ""})
    if not rows:
        return rows
    if fetch_manifests:
        for r in rows:
            state, manifest = cf_api.fetch_manifest(r["url"], MANIFEST_TIMEOUT)
            r["online"] = "unknown" if state == "timeout" else state == "ok"
            if manifest and manifest.get("kb_version"):
                r["version"] = manifest["kb_version"]
                r["sha"] = manifest.get("content_sha") or r["sha"]
    counts = cf_api.views([r["worker"] for r in rows])
    for r in rows:
        if counts is None:
            r["views"], r["views_note"] = 0, "analytics unavailable"
        else:
            r["views"] = counts.get(r["worker"], 0)
    versions = main_versions() if versions is None else versions
    for r in rows:
        r["behind_main"] = behind_main(r["version"], versions)
    return rows


def _online_str(v) -> str:
    return "unknown" if v == "unknown" else ("yes" if v else "no" if v is not None else "-")


def cmd_list(args) -> int:
    try:
        rows = list_snapshots()
    except cf_api.CloudflareError as e:
        print(f"list: {e}")
        return 1
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    if not rows:
        print("no snapshots")
        return 0
    print(f"{'worker':<40}{'version':<10}{'behind':>7}  {'deployed':<20}{'views 7d':>9}  {'updates':<16}online")
    for r in rows:
        behind = "?" if r["behind_main"] is None else str(r["behind_main"])
        views = f"{r['views']}" + ("*" if r["views_note"] else "")
        updates = str(r["updates"]) + (f" (was {r['first_version']})" if r["updates"] and r["first_version"] else "")
        print(f"{r['worker']:<40}{r['version']:<10}{behind:>7}  {(r['deployed_at'] or '')[:19]:<20}{views:>9}  "
              f"{updates:<16}{_online_str(r['online'])}")
    for r in rows:
        print(r["url"])
    if any(r["views_note"] for r in rows):
        print("* views: analytics unavailable (set CLOUDFLARE_API_TOKEN with Analytics read, or wait for data)")
    return 0


# ---------- history ----------

def history(worker: str) -> list:
    """Uploaded versions of a snapshot Worker, newest first: [{version_id, created_on, version, sha, live}].
    Versions without a `kb-share` message are kept (version/sha empty) — they are still what was served."""
    from kb.share.deploy import parse_message
    try:
        versions = cf_api.list_versions(worker)
        dep = cf_api.latest_deployment(worker) or {}
    except cf_api.CloudflareError:
        return []
    live_id = dep.get("version_id")
    rows = []
    for v in versions:
        parsed = parse_message(v.get("message")) or {}
        rows.append({"version_id": v["version_id"], "created_on": v.get("created_on") or "",
                     "version": parsed.get("version", ""), "sha": parsed.get("sha", ""),
                     "live": v["version_id"] == live_id})
    if live_id is None and rows:
        rows[0]["live"] = True
    return rows


def cmd_history(args) -> int:
    try:
        candidates = resolve_target(args.target)
    except cf_api.CloudflareError as e:
        print(f"history: {e}")
        return 1
    if not candidates:
        print(f"history: no snapshot Worker matches {args.target!r}")
        return 1
    if len(candidates) > 1:
        print(f"history: {args.target!r} is ambiguous — give the full worker name:")
        for s in candidates:
            print(f"  {s['name']}")
        return 1
    worker = candidates[0]["name"]
    rows = history(worker)
    if args.json:
        print(json.dumps({"worker": worker, "url": worker_url(worker), "versions": rows}, indent=2))
        return 0
    print(f"{worker}  {worker_url(worker)}")
    if not rows:
        print("no versions listed (wrangler could not read them)")
        return 1
    print(f"{'':2}{'uploaded':<20}{'kb version':<12}{'content':<9}version id")
    for r in rows:
        print(f"{'*' if r['live'] else ' ':2}{(r['created_on'] or '')[:19]:<20}{r['version'] or '?':<12}"
              f"{(r['sha'] or '')[:7]:<9}{r['version_id']}")
    print(f"{len(rows) - 1} update(s) since it was created; * = serving now. "
          f"Bring one back: pixi run share -- rollback --worker {worker} --to <version id>")
    return 0


# ---------- remove ----------

def remove_snapshot(worker: str) -> Optional[str]:
    """Delete `worker` and verify it is gone; None on success, else the reason."""
    if worker == WORKER_MAIN or not parse_worker(worker):
        return f"refusing to delete {worker!r}: only snapshot-* Workers can be removed here"
    err = cf_api.delete_worker(worker)
    if err:
        return f"wrangler delete failed for {worker}: {err}"
    if any(s["name"] == worker for s in cf_api.list_scripts()):
        return f"{worker} is still present after delete"
    return None


def cmd_remove(args) -> int:
    if args.target.strip() == WORKER_MAIN:
        print(f"remove: {WORKER_MAIN!r} is the live site; this command only removes snapshot-* Workers")
        return 1
    try:
        candidates = resolve_target(args.target)
    except cf_api.CloudflareError as e:
        print(f"remove: {e}")
        return 1
    if not candidates:
        print(f"remove: no snapshot Worker matches {args.target!r}")
        return 1
    if len(candidates) > 1:
        print(f"remove: {args.target!r} is ambiguous — give the full worker name:")
        for s in candidates:
            print(f"  {s['name']}")
        return 1
    worker = candidates[0]["name"]
    if not args.yes:
        typed = input(f"type the worker name to delete it ({worker}): ").strip()
        if typed != worker:
            print("remove: confirmation did not match — nothing deleted")
            return 1
    err = remove_snapshot(worker)
    if err:
        print(f"remove: {err}")
        return 1
    print(f"removed {worker} — {worker_url(worker)} is gone")
    return 0


# ---------- prune ----------

def prune_plan() -> dict:
    """{orphans: [worker], unknown: [worker], foreign: [worker], ok: [worker]}."""
    plan = {"orphans": [], "unknown": [], "foreign": [], "ok": []}
    for s in cf_api.list_scripts():
        name = s["name"]
        if name == WORKER_MAIN:
            continue
        if not parse_worker(name):
            plan["foreign"].append(name)
            continue
        state, _manifest = cf_api.fetch_manifest(worker_url(name), MANIFEST_TIMEOUT)
        plan["ok" if state == "ok" else "unknown" if state == "timeout" else "orphans"].append(name)
    return plan


def cmd_prune(args) -> int:
    try:
        plan = prune_plan()
    except cf_api.CloudflareError as e:
        print(f"prune: {e}")
        return 1
    for name in plan["ok"]:
        print(f"ok        {name}")
    for name in plan["unknown"]:
        print(f"unknown   {name}  (manifest timed out — not touched)")
    for name in plan["foreign"]:
        print(f"not ours  {name}  (neither {WORKER_MAIN} nor snapshot-*; never deleted)")
    for name in plan["orphans"]:
        print(f"orphan    {name}  (no reachable manifest)")
    if not plan["orphans"]:
        print("no orphans")
        return 0
    if not args.apply:
        print(f"{len(plan['orphans'])} orphan(s) — pass --apply to delete them")
        return 0
    rc = 0
    for name in plan["orphans"]:
        err = remove_snapshot(name)
        if err:
            print(f"prune: {err}")
            rc = 1
        else:
            print(f"deleted   {name}")
    return rc


# ---------- CLI ----------

def register(subparsers) -> None:
    a = subparsers.add_parser("audit", help="build <ref> with the public profile and scan it (no deploy)")
    a.add_argument("ref", help="main, a commit, kb-x.y.z or x.y.z")
    a.add_argument("--allow-flags", action="store_true", help="exit 0 even when flags are found")
    a.set_defaults(func=cmd_audit)

    s = subparsers.add_parser("snapshot", help="publish <ref> as the public Worker snapshot-<date>-<name>")
    s.add_argument("name", help="lowercase [a-z0-9-]; the CLI adds snapshot-<YYYYMMDD>-")
    s.add_argument("ref", help="main, a commit, kb-x.y.z or x.y.z")
    s.add_argument("--replace", action="store_true",
                   help="update an existing snapshot of this name in place — same Worker, same link")
    s.add_argument("--force", action="store_true",
                   help="with --replace: allow serving an older or unrelated knowledge version than the live one")
    s.add_argument("--allow-flags", action="store_true", help="deploy despite audit flags")
    s.add_argument("--dry-run", action="store_true", help="audit and resolve the Worker, but do not deploy")
    s.set_defaults(func=cmd_snapshot)

    ls = subparsers.add_parser("list", help="our snapshot Workers: version, behind-main, deployed, views, online")
    ls.add_argument("--json", action="store_true")
    ls.set_defaults(func=cmd_list)

    h = subparsers.add_parser("history", help="uploaded versions of one snapshot (its audit trail); * = live")
    h.add_argument("target", help="bare name or full snapshot-<date>-<name>")
    h.add_argument("--json", action="store_true")
    h.set_defaults(func=cmd_history)

    r = subparsers.add_parser("remove", help="delete one snapshot Worker (never kb)")
    r.add_argument("target", help="bare name or full snapshot-<date>-<name>")
    r.add_argument("--yes", action="store_true", help="skip the typed confirmation")
    r.set_defaults(func=cmd_remove)

    p = subparsers.add_parser("prune", help="list orphan snapshot Workers (no reachable manifest); --apply deletes them")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(func=cmd_prune)
