"""Mail and AI chat (schema 1.2): the source type `conversation` is split by what it really held.

Every `type: conversation` page becomes one of
  * `ai-chat` (`chat-<stem>`, `legacy: true`) when its `raw:` is under raw/llm-chats/ — hand-digested
    Gemini chats from before meta/chats/ trees; lint lets a legacy ai-chat go without `conversation:`;
  * `mail` (`mail-<stem>`) otherwise — an email thread under raw/emails/.
The file is renamed, the old slug is kept in `aliases:`, and every `[[old]]` / `[[old|…]]` / `[[old#…]]`
link (bodies and `related:`) in wiki/ is rewritten. think/ is user-owned and never rewritten — links
there are reported. Only the `type:` line, `legacy:`, `aliases:` and link targets change. Idempotent.

    python src/kb_distillery/migrations/0010_mail_type.py [--root R] [--dry-run]
"""
import argparse
import os
import re

PRODUCES = (1, 2)
OLD_PREFIX = "conversation-"
CHATS = "raw/llm-chats/"


def _fm_get(text, key):
    m = re.search(rf"^{key}:\s*(.*)$", text.split("\n---", 1)[0], re.M)
    return m.group(1).strip() if m else ""


def plan(root):
    """{old_slug: (new_slug, new_type)} for every wiki/conversation-*.md typed conversation."""
    wiki = os.path.join(root, "wiki")
    out = {}
    for fn in sorted(os.listdir(wiki)) if os.path.isdir(wiki) else []:
        if not (fn.endswith(".md") and fn.startswith(OLD_PREFIX)):
            continue
        with open(os.path.join(wiki, fn), encoding="utf-8") as f:
            text = f.read()
        if _fm_get(text, "type") != "conversation":
            continue
        raw = _fm_get(text, "raw")
        new_type = "ai-chat" if CHATS in raw else "mail"
        stem = fn[len(OLD_PREFIX):-3]
        new = ("chat-" if new_type == "ai-chat" else "mail-") + stem
        if os.path.exists(os.path.join(wiki, new + ".md")):
            raise RuntimeError(f"refusing to migrate: wiki/{new}.md already exists")
        out[fn[:-3]] = (new, new_type)
    return out


def _retype(text, old, new_type):
    head, sep, body = text.partition("\n---\n")
    head = re.sub(r"^type: conversation$", f"type: {new_type}", head, count=1, flags=re.M)
    if new_type == "ai-chat" and not re.search(r"^legacy:", head, re.M):
        head = re.sub(r"^(type: ai-chat)$", r"\1\nlegacy: true", head, count=1, flags=re.M)
    m = re.search(r"^aliases: \[(.*)\]$", head, re.M)
    block = re.search(r"^aliases:\s*\n((?:\s*- .*\n?)*)", head, re.M)
    if m:
        items = [a.strip() for a in m.group(1).split(",") if a.strip()]
        if old not in items:
            head = head[:m.start()] + f"aliases: [{', '.join(items + [old])}]" + head[m.end():]
    elif block and block.group(1).strip():
        if not re.search(rf"^\s*- {re.escape(old)}\s*$", block.group(1), re.M):
            head = head[:block.end(1)].rstrip("\n") + f"\n  - {old}" + ("\n" + head[block.end(1):] if head[block.end(1):] else "")
    elif not re.search(r"^aliases:", head, re.M):
        head += f"\naliases: [{old}]"
    else:
        head = re.sub(r"^aliases:.*$", f"aliases: [{old}]", head, count=1, flags=re.M)
    return head + sep + body


def _relink(text, mapping):
    """`[[old]]`, `[[old|x]]`, `[[old#h]]` → the new slug."""
    def link(m):
        return "[[" + mapping.get(m.group(1), m.group(1)) + m.group(2)
    return re.sub(r"\[\[([^\]|#]+)((?:[|#][^\]]*)?\]\])", link, text)


def _relink_fm(head, mapping):
    """Bare slugs in `related:` only (`related: [a, conversation-x]`); `aliases:`, `raw:` etc. are left."""
    out = []
    for line in head.split("\n"):
        if line.startswith("related:"):
            for old, new in mapping.items():
                line = re.sub(rf"(?<![\w-]){re.escape(old)}(?![\w-])", new, line)
        out.append(line)
    return _relink("\n".join(out), mapping)


def apply(root, dry_run=False):
    root = os.path.abspath(root)
    wiki = os.path.join(root, "wiki")
    renames = plan(root)
    mapping = {o: n for o, (n, _t) in renames.items()}
    if not renames:
        print("mail type: nothing to change")
        return {"renamed": 0}
    if dry_run:
        for o, (n, t) in renames.items():
            print(f"{o} → {n} ({t})")
        return {"renamed": len(renames), "dry_run": True}
    for old, (new, new_type) in renames.items():
        src = os.path.join(wiki, old + ".md")
        with open(src, encoding="utf-8", newline="") as f:
            text = f.read()
        with open(os.path.join(wiki, new + ".md"), "w", encoding="utf-8", newline="") as f:
            f.write(_retype(text, old, new_type))
        os.remove(src)
    touched = 0
    for fn in sorted(os.listdir(wiki)):
        if not fn.endswith(".md"):
            continue
        p = os.path.join(wiki, fn)
        with open(p, encoding="utf-8", newline="") as f:
            text = f.read()
        head, sep, body = text.partition("\n---\n")
        new = _relink_fm(head, mapping) + sep + _relink(body, mapping) if sep else _relink(text, mapping)
        if new != text:
            with open(p, "w", encoding="utf-8", newline="") as f:
                f.write(new)
            touched += 1
    think = os.path.join(root, "think")
    left = []
    for d, _s, files in os.walk(think) if os.path.isdir(think) else []:
        for fn in files:
            if fn.endswith(".md"):
                with open(os.path.join(d, fn), encoding="utf-8", errors="replace") as f:
                    if any(f"[[{o}" in f.read() for o in mapping):
                        left.append(os.path.relpath(os.path.join(d, fn), root))
    print(f"mail type: {len(renames)} pages renamed, {touched} pages relinked"
          + (f"; think/ still links old slugs (aliases resolve them): {left}" if left else ""))
    return {"renamed": len(renames), "relinked": touched, "think": left}


if __name__ == "__main__":
    from kb_distillery.config.paths import vault_root
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=vault_root())
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    apply(a.root, dry_run=a.dry_run)
