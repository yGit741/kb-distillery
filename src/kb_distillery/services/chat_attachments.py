"""Chat attachments: files a user adds to one chat session, kept under `.cache/chat/<session>/attachments/`.

Never `raw/` or `wiki/`. The agent may `Read` only its own session's directory (`chat_agent._policy_attachments`).
Layout: `<id>__<safe name>` per file; a PDF's extracted text sits in `extracted/<id>.txt`, written once at upload.
HTTP-free: the router adapts it.
"""
import os
import re
import secrets

from kb_distillery import llm
from kb_distillery.config import paths

MAX_BYTES = 20 * 1024 * 1024
MAX_FILES = 10
TEXT_EXTS = {".md", ".txt", ".csv", ".json", ".html"}
IMAGE_EXTS = set(llm.IMAGE_TYPES)
ALLOWED = TEXT_EXTS | IMAGE_EXTS | {".pdf"}
SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
ID_RE = re.compile(r"^[0-9a-f]{12}$")
SEP = "__"
EXTRACTED = "extracted"


class AttachmentError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


def chat_root():
    return os.path.join(os.path.realpath(paths.CACHE_PATH), "chat")


def session_dir(session):
    if not isinstance(session, str) or not SESSION_RE.match(session):
        raise AttachmentError(400, "invalid session id")
    return os.path.join(chat_root(), session, "attachments")


def safe_name(name):
    base = os.path.basename((name or "").replace("\\", "/"))
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip(".-")
    stem, ext = os.path.splitext(base)
    return (stem[:80] or "file") + ext.lower()


def kind_of(ext):
    return "pdf" if ext == ".pdf" else "image" if ext in IMAGE_EXTS else "text"


def _entry(d, fname):
    id_, _, name = fname.partition(SEP)
    if not ID_RE.match(id_) or not name:
        return None
    path = os.path.join(d, fname)
    if os.path.islink(path) or not os.path.isfile(path):
        return None
    return {"id": id_, "name": name, "kind": kind_of(os.path.splitext(name)[1]), "bytes": os.path.getsize(path),
            "path": path}


def listing(session):
    d = session_dir(session)
    if not os.path.isdir(d):
        return []
    return [e for e in (_entry(d, f) for f in sorted(os.listdir(d))) if e]


def public(entry):
    return {k: entry[k] for k in ("id", "name", "kind", "bytes")}


def extract_pdf_text(path):
    """The text layer of a PDF via PDFium (the same engine as the parse layer), pages separated by a form feed."""
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(path)
    try:
        return "\n\f\n".join(pdf[i].get_textpage().get_text_range() for i in range(len(pdf)))
    finally:
        pdf.close()


def add(session, filename, stream):
    """Store one upload (a file-like with .read(n)); returns the public entry."""
    d = session_dir(session)
    name = safe_name(filename)
    ext = os.path.splitext(name)[1]
    if ext not in ALLOWED:
        raise AttachmentError(415, f"file type {ext or '(none)'} is not allowed; use {', '.join(sorted(ALLOWED))}")
    if len(listing(session)) >= MAX_FILES:
        raise AttachmentError(409, f"at most {MAX_FILES} files per chat")
    os.makedirs(d, exist_ok=True)
    id_ = secrets.token_hex(6)
    path = os.path.join(d, f"{id_}{SEP}{name}")
    size = 0
    try:
        with open(path, "wb") as out:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_BYTES:
                    raise AttachmentError(413, f"file is over {MAX_BYTES // (1024 * 1024)} MB")
                out.write(chunk)
        if size == 0:
            raise AttachmentError(400, "empty file")
        if ext == ".pdf":
            with open(path, "rb") as f:
                if f.read(5) != b"%PDF-":
                    raise AttachmentError(400, "not a PDF")
            try:
                text = extract_pdf_text(path)
            except Exception as exc:
                raise AttachmentError(400, f"cannot read the PDF: {exc}")
            os.makedirs(os.path.join(d, EXTRACTED), exist_ok=True)
            with open(os.path.join(d, EXTRACTED, f"{id_}.txt"), "w", encoding="utf-8") as f:
                f.write(text)
    except BaseException:
        for p in (path, os.path.join(d, EXTRACTED, f"{id_}.txt")):
            if os.path.exists(p):
                os.remove(p)
        raise
    return public(_entry(d, os.path.basename(path)))


def remove(session, id_):
    if not ID_RE.match(id_ or ""):
        raise AttachmentError(400, "invalid attachment id")
    hit = next((e for e in listing(session) if e["id"] == id_), None)
    if not hit:
        raise AttachmentError(404, "no such attachment")
    os.remove(hit["path"])
    txt = os.path.join(session_dir(session), EXTRACTED, f"{id_}.txt")
    if os.path.isfile(txt):
        os.remove(txt)


def resolve(session, ids):
    """Ids -> entries (with `path`, and `text_path` for a PDF). Unknown ids are skipped."""
    if not session or not ids:
        return []
    by_id = {e["id"]: e for e in listing(session)}
    out = []
    for id_ in ids:
        e = by_id.get(id_)
        if not e:
            continue
        if e["kind"] == "pdf":
            e = {**e, "text_path": os.path.join(session_dir(session), EXTRACTED, f"{id_}.txt")}
        out.append(e)
    return out


def prompt_note(entries):
    """A short block for the question: where each non-image file can be Read (images ride as image blocks)."""
    lines = []
    for e in entries:
        if e["kind"] == "image":
            lines.append(f"- {e['name']} (image, attached above)")
        else:
            lines.append(f"- {e['name']}: {e.get('text_path') or e['path']}")
    return ("\n\nAttached files (read them with the Read tool):\n" + "\n".join(lines)) if lines else ""


def image_paths(entries):
    return tuple(e["path"] for e in entries if e["kind"] == "image")
