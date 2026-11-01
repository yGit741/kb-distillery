"""Pull files from a mounted Google Drive folder into raw/inbox/. Zero LLM.

Why this exists as a script rather than agent steps:

- Drive's MCP `download_file_content` returns base64 into the agent context. A
  284 MB PDF is unrecoverable that way. `cp` from the local mount streams instead.
- The macOS Drive mount stalls (`ls: fts_read: Operation timed out`) when the
  File Provider extension is up but Google Drive.app is not. `_ensure_awake`
  relaunches and polls rather than hanging forever.
- File *size* on the mount is free metadata — `stat` does not materialize bytes.
  So "already have it" is decided before anything downloads, which makes a
  re-run of a pull cost roughly nothing.
"""
import glob
import os
import re
import shutil
import subprocess
import sys
import threading
import time

from .paths import ROOT, sha1_file
from . import resolve as resolve_mod

INBOX = os.path.join(ROOT, "raw", "inbox")
RAW = os.path.join(ROOT, "raw")

DEFAULT_FOLDER = "Notes to Obsedian"
DEFAULT_EXTS = ("pdf",)
DEFAULT_WARN_MB = 100

MOUNT_GLOB = os.path.expanduser("~/Library/CloudStorage/GoogleDrive-*")
LIST_TIMEOUT = 10      # seconds before a listdir is treated as stalled
WAKE_TIMEOUT = 60      # seconds to wait for Google Drive.app to come up
WAKE_POLL = 3
CHUNK = 1 << 20


def _fmt_size(n):
    if n >= 1 << 20:
        return f"{n / (1 << 20):.1f} MB"
    if n >= 1 << 10:
        return f"{n / (1 << 10):.0f} KB"
    return f"{n} B"


def _listdir_timeout(path, timeout=LIST_TIMEOUT):
    """os.listdir that gives up instead of hanging on a stalled mount.

    Returns a list, or None if the call stalled or errored. The worker thread is
    a daemon: a wedged File Provider call can never be interrupted, so we leak
    the thread rather than block the process.
    """
    box = {}

    def work():
        try:
            box["names"] = os.listdir(path)
        except OSError as exc:
            box["error"] = exc

    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive() or "error" in box:
        return None
    return box.get("names")


def _find_mount(account=None):
    cands = sorted(p for p in glob.glob(MOUNT_GLOB) if os.path.isdir(p))
    if account:
        want = f"GoogleDrive-{account}"
        cands = [p for p in cands if os.path.basename(p) == want]
        if not cands:
            raise ValueError(f"no Google Drive mount for account {account!r} under ~/Library/CloudStorage/")
    if not cands:
        raise ValueError(
            "no Google Drive mount under ~/Library/CloudStorage/GoogleDrive-*\n"
            "Install and sign in to Google Drive for desktop, then retry."
        )
    if len(cands) > 1:
        names = ", ".join(os.path.basename(p).replace("GoogleDrive-", "") for p in cands)
        raise ValueError(f"multiple Drive accounts mounted ({names}) — pass --account <email>")
    mount = os.path.join(cands[0], "My Drive")
    if not os.path.isdir(mount):
        raise ValueError(f"Drive mount has no 'My Drive' folder: {cands[0]}")
    return mount


def _ensure_awake(mount):
    """Wake a stalled Drive mount. Idempotent and fast when already healthy."""
    if _listdir_timeout(mount):
        return
    print("gdrive: mount unresponsive (File Provider stalled) — launching Google Drive.app", file=sys.stderr)
    subprocess.run(["open", "-a", "Google Drive"], check=False)
    waited = 0
    while waited < WAKE_TIMEOUT:
        time.sleep(WAKE_POLL)
        waited += WAKE_POLL
        if _listdir_timeout(mount):
            print(f"gdrive: mount awake after {waited}s", file=sys.stderr)
            return
    raise ValueError(
        f"Drive mount still unresponsive after {WAKE_TIMEOUT}s: {mount}\n"
        "Open Google Drive.app and confirm the account is signed in, then retry."
    )


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _resolve_folder(mount, folder):
    """Locate <folder> under My Drive, tolerant of spelling drift.

    Matching is slug-based on purpose: the folder has been spelled both
    'Notes to Obsedian' and 'notes-to-obsedian', and it is misspelled
    ('Obsedian', not 'Obsidian'). Case and space/hyphen differences must not
    break the default invocation.
    """
    direct = os.path.join(mount, folder)
    if os.path.isdir(direct):
        return direct
    names = _listdir_timeout(mount) or []
    dirs = sorted(n for n in names if os.path.isdir(os.path.join(mount, n)))
    want = _slug(folder)
    hits = [n for n in dirs if _slug(n) == want]
    if len(hits) == 1:
        return os.path.join(mount, hits[0])
    if len(hits) > 1:
        raise ValueError(f"folder {folder!r} is ambiguous in My Drive: {', '.join(hits)}")
    hint = "\n".join(f"  {d}" for d in dirs[:20])
    raise ValueError(f"no folder {folder!r} in My Drive. Available:\n{hint}")


def _build_skip_index():
    """Map (basename, size) -> raw-relative path for everything already in raw/.

    Name+size is a cheap proxy for identity that costs zero downloaded bytes.
    A byte-level sha1 check still runs after each copy to catch renames.
    """
    idx = {}
    for dirpath, dirnames, filenames in os.walk(RAW):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in filenames:
            if fn.startswith("."):
                continue
            full = os.path.join(dirpath, fn)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            idx.setdefault((fn, size), os.path.relpath(full, ROOT))
    return idx


def _normalize_exts(exts):
    out = set()
    for e in exts:
        for part in str(e).split(","):
            part = part.strip().lstrip(".").lower()
            if part:
                out.add(part)
    return out


def _list_source(src, exts):
    entries = []
    for name in sorted(os.listdir(src)):
        path = os.path.join(src, name)
        if not os.path.isfile(path):
            continue
        if exts and os.path.splitext(name)[1].lstrip(".").lower() not in exts:
            continue
        try:
            entries.append((name, os.path.getsize(path)))
        except OSError:
            continue
    return entries


def _copy_stream(src, dest):
    """Chunked copy — never loads a multi-hundred-MB file into memory."""
    with open(src, "rb") as fin, open(dest, "wb") as fout:
        shutil.copyfileobj(fin, fout, CHUNK)


def scrap_gdrive(folder=DEFAULT_FOLDER, exts=DEFAULT_EXTS, dry_run=False,
                 warn_mb=DEFAULT_WARN_MB, account=None, force=False):
    """Copy matching Drive files into raw/inbox/. Returns an exit code."""
    exts = _normalize_exts(exts)
    mount = _find_mount(account)
    _ensure_awake(mount)
    src = _resolve_folder(mount, folder)

    entries = _list_source(src, exts)
    kinds = ",".join(sorted(exts)) if exts else "all"
    print(f"gdrive: {os.path.relpath(src, os.path.dirname(mount))} — {len(entries)} file(s) matching [{kinds}]")
    if not entries:
        return 0

    skip_idx = _build_skip_index()
    warn_bytes = warn_mb * (1 << 20)

    plan = []
    for name, size in entries:
        existing = None if force else skip_idx.get((name, size))
        plan.append({"name": name, "size": size, "pull": existing is None, "at": existing})

    for item in plan:
        mark = "pull" if item["pull"] else "skip"
        note = "" if item["pull"] else f"  (already at {item['at']})"
        print(f"  {mark}  {_fmt_size(item['size']):>9}  {item['name']}{note}")

    # Size pushback: loud, but never a gate. The caller decides.
    big = [i for i in plan if i["pull"] and i["size"] >= warn_bytes]
    if big:
        sys.stdout.flush()  # keep the warning below the listing, not above it
        print("", file=sys.stderr)
        print(f"  !!  WARNING: {len(big)} file(s) over {warn_mb} MB", file=sys.stderr)
        for item in big:
            print(f"  !!    {_fmt_size(item['size']):>9}  {item['name']}", file=sys.stderr)
        print("  !!  These stream from Drive and can take minutes each.", file=sys.stderr)
        print("  !!  Proceeding anyway — re-run with --dry-run to preview without copying.", file=sys.stderr)
        print("", file=sys.stderr)
        sys.stderr.flush()

    to_pull = [i for i in plan if i["pull"]]
    total = sum(i["size"] for i in to_pull)
    print(f"gdrive: {len(to_pull)} to pull ({_fmt_size(total)}), {len(plan) - len(to_pull)} already present")

    if dry_run:
        print("gdrive: dry-run — nothing copied")
        return 0
    if not to_pull:
        return 0

    os.makedirs(INBOX, exist_ok=True)
    copied, blocked, failed = [], [], []

    for item in to_pull:
        name, size = item["name"], item["size"]
        src_path = os.path.join(src, name)
        dest = os.path.join(INBOX, name)
        rel = f"raw/inbox/{name}"
        print(f"gdrive: pulling {name} ({_fmt_size(size)})…", flush=True)
        try:
            _copy_stream(src_path, dest)
        except OSError as exc:
            if os.path.isfile(dest):
                os.remove(dest)
            print(f"  FAILED {name}: {exc}", file=sys.stderr)
            failed.append(name)
            continue

        got = os.path.getsize(dest)
        if got != size:
            os.remove(dest)
            print(f"  FAILED {name}: size mismatch (expected {size}, got {got}) — partial removed", file=sys.stderr)
            failed.append(name)
            continue

        if not force:
            h = sha1_file(rel)
            dupes = resolve_mod.find_by_sha1(h, exclude_path=rel)
            if dupes:
                os.remove(dest)
                print(f"  DUPLICATE bytes (sha1 {h}) — already at {dupes[0]}")
                blocked.append(name)
                continue

        print(f"  → {rel}")
        copied.append(name)

    print(f"gdrive: copied {len(copied)}, skipped {len(plan) - len(to_pull)}, "
          f"blocked {len(blocked)}, failed {len(failed)}")
    if copied:
        print("Next: python3 -m kb_distillery.lint.lint, then catalog the inbox")
    return 1 if failed else 0
