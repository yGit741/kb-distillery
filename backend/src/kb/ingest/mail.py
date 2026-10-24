"""Parse a Gmail-style .mbox/.eml export into a thread bundle for raw/inbox/. Zero LLM.

Attachment bytes never pass through an LLM context. Two sources feed the same
pipeline: a locally exported .mbox/.eml file (e.g. Google Takeout), or a direct
IMAP fetch (Gmail's X-GM-THRID extension) that streams straight to disk —
neither path ever routes attachment bytes through an agent's conversation.
"""
import email
import email.policy
import email.utils
import html
import imaplib
import io
import mailbox
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

from .paths import ROOT
from . import resolve as resolve_mod

INBOX = os.path.join(ROOT, "raw", "inbox")
IMAP_HOST = "imap.gmail.com"
KEYCHAIN_SERVICE = "thesis-kb-gmail-imap"


def _ascii_slug(text):
    text = re.sub(r"[^\w\s-]", "", text or "", flags=re.ASCII)
    text = re.sub(r"[\s_]+", "-", text).strip("-").lower()
    return text


def _sanitize_filename(name):
    name = re.sub(r"[^\w.\-]+", "-", name or "attachment").strip("-")
    return name or "attachment"


_IMG_CID_RE = re.compile(r'<img\b[^>]*\bsrc=["\']cid:([^"\']+)["\'][^>]*>', re.I)
_ATTACHMENT_TOKEN_RE = re.compile(r"\{\{ATTACHMENT:(\d+)\}\}")

# Boundaries marking the start of quoted reply history — the point past which
# a message is just re-including everything sent before it, in whatever form
# the client wrote it inline (Gmail's "On ... wrote:" intro line, or Outlook's
# "From: ... Sent: ... To: ... Subject:" header block). Only the *first* match
# matters: everything after it, at any nesting depth, is quoted.
_QUOTE_BOUNDARY_RES = [
    re.compile(r"\bOn\s.{0,200}?wrote:", re.S),
    re.compile(r"\bFrom:.{0,300}?Sent:.{0,300}?To:.{0,300}?Subject:", re.S),
]


def _strip_quoted_history(text):
    cut = len(text)
    for pat in _QUOTE_BOUNDARY_RES:
        m = pat.search(text)
        if m:
            cut = min(cut, m.start())
    return text[:cut]


def _decode_body(msg, content_id_to_index=None):
    """Return (body_text, referenced_indices) — this message's own new content only.

    Prefers the HTML part over plain text: Gmail's plain-text alternative
    represents every inline image as a dead "[image: name.png]" string with no
    link back to the real attachment, so there is no way to recover correct
    placement from plain text alone. The HTML part's own <img src="cid:...">
    tags give an unambiguous, position-correct reference — each is resolved to
    the matching attachment via Content-ID and replaced with an
    "{{ATTACHMENT:i}}" token in place, in true reading order. Callers fill the
    token in after attachment disk names are assigned (see render_thread).

    Both Gmail and Outlook re-include the *entire* prior conversation inline in
    every reply (top-posting), which would otherwise repeat every paragraph and
    image once per message down the thread. _strip_quoted_history() cuts the
    body at the first quote-boundary marker, so only genuinely new content (and
    only the images that appear within it) survives — an attachment that's
    referenced solely inside quoted history is not double-counted as "shown".

    Falls back to plain text (placeholders un-resolved, quote-boundary cut
    still applied) only when a message genuinely has no HTML part.
    """
    content_id_to_index = content_id_to_index or {}
    body = msg.get_body(preferencelist=("html", "plain"))
    if body is None:
        return "", set()
    content = body.get_content()
    if body.get_content_type() == "text/html":
        content = _IMG_CID_RE.sub(
            lambda m: f"\n{{{{ATTACHMENT:{content_id_to_index[m.group(1)]}}}}}\n"
            if m.group(1) in content_id_to_index else "",
            content)
        content = re.sub(r"<(style|script)\b[^>]*>.*?</\1>", " ", content,
                          flags=re.I | re.S)
        content = re.sub(r"<br\s*/?>", "\n", content, flags=re.I)
        content = re.sub(r"</(p|div|tr|li|h[1-6])\s*>", "\n\n", content, flags=re.I)
        content = re.sub(r"<[^>]+>", " ", content)
        content = html.unescape(content)
        content = re.sub(r"[ \t\xa0]+", " ", content)
        content = re.sub(r"^[ \t\xa0]+$", "", content, flags=re.M)
        content = re.sub(r"\n[ \t]+", "\n", content)
        content = re.sub(r"\n{3,}", "\n\n", content)
    content = _strip_quoted_history(content)
    referenced = {int(i) for i in _ATTACHMENT_TOKEN_RE.findall(content)}
    return content.strip(), referenced


def _message_factory(f):
    return email.message_from_binary_file(f, policy=email.policy.default)


def _iter_source(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".mbox":
        box = mailbox.mbox(path, factory=_message_factory)
        try:
            for msg in box:
                yield msg
        finally:
            box.close()
    else:
        with open(path, "rb") as f:
            yield _message_factory(f)


def _sort_key(msg):
    dt = msg["date"]
    if dt is None:
        return 0.0
    try:
        return dt.timestamp()
    except (OSError, OverflowError, ValueError):
        return 0.0


def parse_source(path):
    """Return normalized message dicts, sorted chronologically."""
    if not os.path.isfile(path):
        raise ValueError(f"not found: {path}")

    messages = []
    for msg in _iter_source(path):
        date_hdr = msg.get("Date")
        try:
            dt = email.utils.parsedate_to_datetime(date_hdr) if date_hdr else None
        except (TypeError, ValueError):
            dt = None
        sender = email.utils.parseaddr(str(msg.get("From", "")))[1] or str(msg.get("From", ""))
        to = [a for _, a in email.utils.getaddresses([str(msg.get("To", ""))]) if a]
        subject = str(msg.get("Subject", "")).strip()

        attachments = []
        content_id_to_index = {}
        for part in msg.iter_attachments():
            filename = part.get_filename() or "attachment"
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            cid = part.get("Content-ID")
            if cid:
                content_id_to_index[cid.strip("<>")] = len(attachments)
            attachments.append((filename, payload))

        body, referenced = _decode_body(msg, content_id_to_index)

        messages.append({
            "date": dt,
            "sender": sender,
            "to": to,
            "subject": subject,
            "body": body,
            "referenced_attachments": referenced,
            "attachments": attachments,
        })

    if not messages:
        raise ValueError(f"no messages parsed from {path}")
    messages.sort(key=_sort_key)
    return messages


def _dhash(payload, hash_size=8):
    """Perceptual hash of image bytes; None if payload isn't a decodable image.

    Robust to resize/recompression (unlike a byte/SHA1 hash) — this is what
    catches Outlook re-embedding a downscaled thumbnail of an image already
    sent earlier in the same thread's quoted history.
    """
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        img = (Image.open(io.BytesIO(payload))
               .convert("L").resize((hash_size + 1, hash_size), Image.LANCZOS))
    except Exception:
        return None
    pixels = list(img.getdata())
    bits = []
    for row in range(hash_size):
        for col in range(hash_size):
            left = pixels[row * (hash_size + 1) + col]
            right = pixels[row * (hash_size + 1) + col + 1]
            bits.append(left > right)
    val = 0
    for b in bits:
        val = (val << 1) | int(b)
    return val


def _hamming(a, b):
    return bin(a ^ b).count("1")


def _dedupe_clusters(messages, threshold=10):
    """Cluster visually-duplicate attachments across the whole thread.

    Scoped to one thread only — the duplication pattern this targets (Outlook
    re-embedding a downscaled copy of an image already sent earlier in the same
    thread's quoted history) is thread-local, not cross-thread.

    Returns a dict mapping (msg_index, attachment_index) -> keeper (msg_index,
    attachment_index, filename, payload) for every attachment, including
    entries that map to themselves (singleton clusters).
    """
    items = []  # (msg_idx, att_idx, filename, payload, hash, pixels)
    for mi, m in enumerate(messages):
        for ai, (filename, payload) in enumerate(m["attachments"]):
            h = _dhash(payload)
            pixels = 0
            if h is not None:
                try:
                    from PIL import Image
                    with Image.open(io.BytesIO(payload)) as img:
                        pixels = img.size[0] * img.size[1]
                except Exception:
                    pixels = len(payload)
            items.append([mi, ai, filename, payload, h, pixels])

    clusters = []  # list of lists of item-indices
    for idx, item in enumerate(items):
        if item[4] is None:  # not a decodable image — always its own cluster
            clusters.append([idx])
            continue
        placed = False
        for c in clusters:
            rep = items[c[0]]
            if rep[4] is not None and _hamming(item[4], rep[4]) <= threshold:
                c.append(idx)
                placed = True
                break
        if not placed:
            clusters.append([idx])

    keeper_of = {}
    for c in clusters:
        keeper_idx = max(c, key=lambda i: items[i][5])
        keeper = items[keeper_idx]
        for idx in c:
            mi, ai = items[idx][0], items[idx][1]
            keeper_of[(mi, ai)] = (keeper[0], keeper[1], keeper[2], keeper[3])
    return keeper_of


def assign_attachment_names(messages, prefix=""):
    """Mutate messages in place: add 'files' = [(disk_name, payload)].

    Names are globally unique across the whole vault, not just within this
    thread: Gmail's own attachment filenames are almost always generic
    ("image.png", "image001.png", ...), so two different threads routinely
    produce identically-named files. Since raw material gets referenced by
    bare filename in Obsidian wikilinks (`![[image.png]]`), a same-thread-only
    uniqueness guarantee is not enough — Obsidian resolves `![[name]]` against
    the whole vault and will silently pick whichever file matches first,
    embedding the wrong image with no error. Prefixing with the thread's own
    dir name (already vault-unique, since scrap_mail refuses to overwrite an
    existing thread folder) fixes this at the source.

    Visually-duplicate attachments (see _dedupe_clusters) collapse onto one
    disk name — every cluster member gets the keeper's name and payload, so
    write_attachments() only ever writes the highest-resolution copy, and each
    message's own "Attachments:" listing still shows the (shared) filename.
    """
    keeper_of = _dedupe_clusters(messages)
    used = set()
    keeper_names = {}  # (keeper_mi, keeper_ai) -> assigned disk name
    tag = _ascii_slug(prefix)[:60] if prefix else ""

    for i, m in enumerate(messages, start=1):
        files = []
        for ai, (filename, payload) in enumerate(m["attachments"]):
            keeper_mi, keeper_ai, keeper_filename, keeper_payload = keeper_of[(i - 1, ai)]
            key = (keeper_mi, keeper_ai)
            if key in keeper_names:
                files.append((keeper_names[key], keeper_payload))
                continue
            safe = _sanitize_filename(keeper_filename)
            base = f"{tag}-{keeper_mi + 1:02d}-{safe}" if tag else f"{keeper_mi + 1:02d}-{safe}"
            name = base
            n = 1
            while name in used:
                stem, ext = os.path.splitext(base)
                name = f"{stem}-{n}{ext}"
                n += 1
            used.add(name)
            keeper_names[key] = name
            files.append((name, keeper_payload))
        m["files"] = files
    return messages


def thread_slug(messages, slug=None, fallback_id=None):
    """Derive a folder/wiki slug. Falls back to a caller-supplied unique id
    (e.g. the Gmail thread id) rather than the bare literal "thread" when the
    subject has no ASCII content (all-Hebrew subjects, which are extremely
    common here) — otherwise every such thread collides on the same slug.
    """
    if slug:
        return _ascii_slug(slug) or "thread"
    subject = next((m["subject"] for m in messages if m["subject"]), "")
    ascii_slug = _ascii_slug(subject)
    if ascii_slug:
        return ascii_slug
    return f"thread-{fallback_id}" if fallback_id else "thread"


def thread_dir_name(messages, slug=None, fallback_id=None):
    dates = [m["date"] for m in messages if m["date"]]
    day = min(dates).strftime("%Y-%m-%d") if dates else datetime.now().strftime("%Y-%m-%d")
    return f"{day}-{thread_slug(messages, slug, fallback_id=fallback_id)}"


def render_thread(messages, thread_id=""):
    participants = sorted({m["sender"] for m in messages if m["sender"]})
    dates = [m["date"] for m in messages if m["date"]]
    date_range = ""
    if dates:
        lo, hi = min(dates), max(dates)
        date_range = (lo.strftime("%Y-%m-%d") if lo.date() == hi.date()
                      else f"{lo.strftime('%Y-%m-%d')}..{hi.strftime('%Y-%m-%d')}")
    subject = next((m["subject"] for m in messages if m["subject"]), "")

    lines = [
        "---",
        f"thread-id: {thread_id}",
        f"subject: {subject}",
        f"participants: [{', '.join(participants)}]",
        f"date-range: {date_range}",
        f"message-count: {len(messages)}",
        "---",
        "",
        f"# {subject or 'Untitled thread'}",
        "",
    ]

    token_re = re.compile(r"\{\{ATTACHMENT:(\d+)\}\}")
    already_shown = set()  # filenames shown anywhere earlier in the thread —
    # Outlook/Gmail re-attach the same (already-deduped) file on every reply
    # in the quoted chain, so without this every message would re-list images
    # that already appeared, undoing the point of trimming quoted history.

    for i, m in enumerate(messages, start=1):
        date_str = m["date"].strftime("%Y-%m-%d %H:%M") if m["date"] else "unknown date"
        lines.append(f"## {i}. {m['sender'] or 'unknown'} — {date_str}")
        lines.append("")

        files = m.get("files", [])
        referenced = m.get("referenced_attachments", set())

        def _embed(match, files=files):
            idx = int(match.group(1))
            if idx < len(files):
                name = files[idx][0]
                already_shown.add(name)
                return f"![[{name}]]"
            return ""

        body = token_re.sub(_embed, m["body"]) if m["body"] else ""
        lines.append(body or "*(no body)*")

        # attachments the HTML body never referenced inline (real file
        # attachments, or an <img> whose cid: we couldn't resolve) — but only
        # if genuinely new to the thread, not a repeat from quoted history
        leftover = [name for idx, (name, _payload) in enumerate(files)
                    if idx not in referenced and name not in already_shown]
        already_shown.update(leftover)
        if leftover:
            lines.append("")
            lines.append("Attachments:")
            for name in leftover:
                lines.append(f"- `{name}`")
        lines.append("")
    return "\n".join(lines)


def write_attachments(messages, dest_dir):
    written = []
    seen = set()
    for m in messages:
        for name, payload in m.get("files", []):
            if name in seen:  # deduped attachment, already written for an earlier message
                continue
            seen.add(name)
            with open(os.path.join(dest_dir, name), "wb") as f:
                f.write(payload)
            written.append(name)
    return written


def scrap_mail(source, slug=None, force=False, fallback_id=None):
    """Parse a .mbox/.eml export into raw/inbox/mail-<dir>/ (thread.md + attachments)."""
    if not os.path.isfile(source):
        raise ValueError(f"not found: {source}")

    if not force:
        with open(source, "rb") as f:
            data = f.read()
        h = resolve_mod.sha1_bytes(data)
        dupes = resolve_mod.find_by_sha1(h)
        if dupes:
            print(f"DUPLICATE bytes (sha1 {h}) — already at {dupes[0]}")
            print("scrap-mail blocked — pass --force to re-import", file=sys.stderr)
            raise resolve_mod.DuplicateBlocked(
                [{"raw": dupes[0], "sha1": h, "reason": "byte-identity"}])

    messages = parse_source(source)
    dir_name = thread_dir_name(messages, slug=slug, fallback_id=fallback_id)
    assign_attachment_names(messages, prefix=dir_name)

    dest_rel = f"raw/inbox/mail-{dir_name}"
    dest = os.path.join(ROOT, dest_rel)
    if os.path.isdir(dest) and not force:
        raise ValueError(f"already exists: {dest_rel} (pass --force to overwrite)")
    os.makedirs(dest, exist_ok=True)

    body = render_thread(messages, thread_id=dir_name)
    with open(os.path.join(dest, "thread.md"), "w", encoding="utf-8") as f:
        f.write(body)

    attached = write_attachments(messages, dest)
    print(f"scrap (mail) → {dest_rel}/  "
          f"({len(messages)} messages, {len(attached)} attachments)")
    return dest_rel


def _keychain_password(account, service=KEYCHAIN_SERVICE):
    result = subprocess.run(
        ["security", "find-generic-password", "-a", account, "-s", service, "-w"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise ValueError(
            f"no Keychain entry for account={account!r} service={service!r} — "
            f"store an app password first (see skills/scrap-data/mail/SKILL.md)")
    return result.stdout.strip()


def _all_mail_folder(conn):
    """Find Gmail's All Mail folder by \\All special-use flag — name varies by UI locale."""
    typ, folders = conn.list()
    if typ == "OK":
        for raw in folders:
            line = raw.decode() if isinstance(raw, bytes) else raw
            if "\\All" in line:
                m = re.search(r'"([^"]+)"\s*$', line)
                return m.group(1) if m else line.split()[-1]
    return "[Gmail]/All Mail"


def fetch_imap_thread(thread_id_hex, account, service=KEYCHAIN_SERVICE):
    """Fetch every message in a Gmail thread via IMAP (X-GM-THRID). Returns list of raw RFC822 bytes.

    Read-only select — never marks messages as read or otherwise mutates the mailbox.
    """
    password = _keychain_password(account, service=service)
    thrid_dec = str(int(thread_id_hex, 16))

    conn = imaplib.IMAP4_SSL(IMAP_HOST)
    try:
        conn.login(account, password)
        folder = _all_mail_folder(conn)
        typ, _ = conn.select(f'"{folder}"', readonly=True)
        if typ != "OK":
            raise ValueError(f"could not select {folder!r}")

        typ, data = conn.search(None, "X-GM-THRID", thrid_dec)
        if typ != "OK":
            raise ValueError(f"IMAP search failed for thread {thread_id_hex}: {data}")
        ids = data[0].split()
        if not ids:
            raise ValueError(f"no messages found for thread {thread_id_hex}")

        raw_messages = []
        for num in ids:
            typ, msg_data = conn.fetch(num, "(RFC822)")
            if typ != "OK" or not msg_data or msg_data[0] is None:
                raise ValueError(f"IMAP fetch failed for message {num!r}: {msg_data}")
            raw_messages.append(msg_data[0][1])
        return raw_messages
    finally:
        try:
            conn.logout()
        except imaplib.IMAP4.error:
            pass


def scrap_imap_thread(thread_id_hex, account, slug=None, force=False, service=KEYCHAIN_SERVICE):
    """Fetch a Gmail thread via IMAP and run it through the normal scrap_mail pipeline."""
    raw_messages = fetch_imap_thread(thread_id_hex, account, service=service)

    tmp_dir = tempfile.mkdtemp(prefix="imap-thread-")
    try:
        tmp_mbox = os.path.join(tmp_dir, "thread.mbox")
        box = mailbox.mbox(tmp_mbox)
        box.lock()
        try:
            for raw in raw_messages:
                box.add(email.message_from_bytes(raw, policy=email.policy.default))
            box.flush()
        finally:
            box.close()
        return scrap_mail(tmp_mbox, slug=slug, force=force, fallback_id=thread_id_hex[-8:])
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
