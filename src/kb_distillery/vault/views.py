"""Pinned graph views and recent shaping steps: the two files behind the explorer's saved-view list.

`meta/views.json` (committed, knowledge): a JSON list of pinned views `{id, name, created, spec}`. `id` is a slug the
engine owns, `name` is the label, `created` an ISO-8601 UTC timestamp, `spec` an opaque JSON object the frontend owns
(cypher, style, filters, layout, camera): it is stored as given, never interpreted. Only `ops view` writes the file
(`kb_distillery.ops.view`), so every change lands as one knowledge step.

`<kb>/.local/recent.json` (machine-local, never committed): the last `MAX_RECENT` shaping steps `{at, text, spec}`,
oldest first. It is ignored by the repo (`distill init` writes the rule; `append_recent` also adds it to the
repository's local exclude file, so a kb created before the rule never shows it as untracked) and the ops commit
path refuses to stage `.local/` regardless.

Pure file logic: no HTTP, no commits. Every function takes the kb root explicitly.
"""
from __future__ import annotations

import contextlib
import datetime
import json
import os
import re
import tempfile

from kb_distillery.vault.schema import LOCAL_DIR

VIEWS_REL = "meta/views.json"
RECENT_REL = f"{LOCAL_DIR}/recent.json"
MAX_RECENT = 20
MAX_NAME = 120
MAX_ID = 64
MAX_SPEC_BYTES = 256 * 1024          # a spec is a few hundred bytes of settings; a megabyte is a bug, not a view
MAX_TEXT = 500
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,%d}$" % (MAX_ID - 1))


class ViewsError(Exception):
    """A refusal with an HTTP-ish status (400 invalid, 404 unknown, 405 read-only, 409 conflict) and a plain message."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


# ---------- validation ----------

def clean_name(name):
    if not isinstance(name, str) or not name.strip():
        raise ViewsError(400, "a view needs a name")
    name = " ".join(name.split())          # one line, single spaces
    if len(name) > MAX_NAME:
        raise ViewsError(400, f"a view name is at most {MAX_NAME} characters")
    return name


def clean_id(view_id):
    if not isinstance(view_id, str) or not ID_RE.match(view_id):
        raise ViewsError(400, f"a view id is a slug of lowercase letters, digits and dashes (at most {MAX_ID})")
    return view_id


def clean_spec(spec):
    if spec is None:
        return {}
    if not isinstance(spec, dict):
        raise ViewsError(400, "a view spec is a JSON object")
    try:
        size = len(json.dumps(spec, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError):
        raise ViewsError(400, "a view spec must be plain JSON") from None
    if size > MAX_SPEC_BYTES:
        raise ViewsError(400, f"a view spec is at most {MAX_SPEC_BYTES // 1024} KB")
    return spec


def slugify(name):
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:MAX_ID - 4].strip("-")
    return slug or "view"


def unique_id(views, wanted):
    taken = {v["id"] for v in views}
    if wanted not in taken:
        return wanted
    n = 2
    while f"{wanted}-{n}" in taken:
        n += 1
    return f"{wanted}-{n}"


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------- pinned views (meta/views.json) ----------

def read_text(root):
    """The file's text, or None when the kb has no pinned views yet."""
    try:
        with open(os.path.join(root, VIEWS_REL), encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None


def parse(text):
    """The list of views in `text` (None or blank = none). A file that is not a list of valid views is a 409: the
    owner fixes or removes it, nothing here guesses."""
    if text is None or not text.strip():
        return []
    try:
        data = json.loads(text)
    except ValueError:
        raise ViewsError(409, f"{VIEWS_REL} is not valid JSON; fix or remove it") from None
    if not isinstance(data, list):
        raise ViewsError(409, f"{VIEWS_REL} must be a JSON list of views")
    out, seen = [], set()
    for i, v in enumerate(data):
        if not isinstance(v, dict):
            raise ViewsError(409, f"{VIEWS_REL}: entry {i} is not an object")
        try:
            view = {"id": clean_id(v.get("id")), "name": clean_name(v.get("name")),
                    "created": str(v.get("created") or ""), "spec": clean_spec(v.get("spec"))}
        except ViewsError as e:
            raise ViewsError(409, f"{VIEWS_REL}: entry {i}: {e}") from None
        if view["id"] in seen:
            raise ViewsError(409, f"{VIEWS_REL}: duplicate id {view['id']!r}")
        seen.add(view["id"])
        out.append(view)
    return out


def load(root):
    return parse(read_text(root))


def render(views):
    """Deterministic file text: two-space indent, trailing newline, field order id, name, created, spec."""
    return json.dumps([{"id": v["id"], "name": v["name"], "created": v["created"], "spec": v["spec"]}
                       for v in views], indent=2, ensure_ascii=False) + "\n"


def write_text(root, text):
    """Write `text` to meta/views.json (None removes the file). The caller commits."""
    full = os.path.join(root, VIEWS_REL)
    if text is None:
        with contextlib.suppress(FileNotFoundError):
            os.remove(full)
        return
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(text)


def find(views, view_id):
    for v in views:
        if v["id"] == view_id:
            return v
    raise ViewsError(404, f"no pinned view {view_id!r}")


# ---------- recent steps (.local/recent.json, never committed) ----------

def _clean_recent(data):
    out = []
    for e in data if isinstance(data, list) else []:
        if isinstance(e, dict) and isinstance(e.get("text"), str):
            out.append({"at": str(e.get("at") or ""), "text": e["text"],
                        "spec": e["spec"] if isinstance(e.get("spec"), dict) else {}})
    return out[-MAX_RECENT:]


def load_recent(root):
    """Recent steps, oldest first. A missing or damaged file is an empty list: this is a convenience, not data."""
    try:
        with open(os.path.join(root, RECENT_REL), encoding="utf-8") as f:
            return _clean_recent(json.load(f))
    except (OSError, ValueError):
        return []


def _write_recent(root, entries):
    full = os.path.join(root, RECENT_REL)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    ensure_local_ignored(root)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(full), prefix=".recent-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, full)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise


def append_recent(root, text, spec=None, at=None):
    """Append one step and keep the newest MAX_RECENT. Returns the new list."""
    if not isinstance(text, str) or not text.strip():
        raise ViewsError(400, "a recent step needs text")
    entry = {"at": at or now_iso(), "text": " ".join(text.split())[:MAX_TEXT], "spec": clean_spec(spec)}
    entries = (load_recent(root) + [entry])[-MAX_RECENT:]
    _write_recent(root, entries)
    return entries


def clear_recent(root):
    with contextlib.suppress(FileNotFoundError):
        os.remove(os.path.join(root, RECENT_REL))


def _exclude_file(root):
    """The repository's local exclude file for a kb checkout (None when the kb is not a repo or it cannot be found)."""
    dot = os.path.join(root, ".git")
    if os.path.isfile(dot):                                  # a linked worktree: ".git" is a pointer file
        try:
            with open(dot, encoding="utf-8") as f:
                line = f.read().strip()
        except OSError:
            return None
        if not line.startswith("gitdir:"):
            return None
        dot = os.path.normpath(os.path.join(root, line[len("gitdir:"):].strip()))
        common = os.path.join(dot, "commondir")              # the shared info/ lives in the common dir
        if os.path.isfile(common):
            with contextlib.suppress(OSError), open(common, encoding="utf-8") as f:
                dot = os.path.normpath(os.path.join(dot, f.read().strip()))
    if not os.path.isdir(dot):
        return None
    return os.path.join(dot, "info", "exclude")


def ensure_local_ignored(root):
    """Make sure `.local/` is ignored in this checkout even when its tracked ignore file predates the rule: add it to the
    repository's local exclude file (untracked, per clone). Best effort; the ops commit path never stages it anyway."""
    exclude = _exclude_file(root)
    if not exclude:
        return
    rule = f"{LOCAL_DIR}/"
    try:
        try:
            with open(exclude, encoding="utf-8") as f:
                text = f.read()
        except FileNotFoundError:
            text = ""
        if rule in (line.strip() for line in text.splitlines()):
            return
        os.makedirs(os.path.dirname(exclude), exist_ok=True)
        with open(exclude, "a", encoding="utf-8") as f:
            f.write(("" if not text or text.endswith("\n") else "\n") + rule + "\n")
    except OSError:
        pass
