"""Digest instructions: the knowledge base's `digest/` (focus.md, types.md and any prompt override) with the
explorer's `meta-defaults/digest/` behind it. Ingest is identical for every knowledge base; digest is one
engine plus these per-kb instructions.

    python -m kb_distillery.core.digest            print the resolved instructions (the digest skills read this first)
    python -m kb_distillery.core.digest --where    which file each part comes from
"""
import os
import sys

from kb_distillery.paths import DIGEST_INSTRUCTIONS_PATH, META_DEFAULTS_PATH, ROOT

PARTS = ("focus.md", "types.md")


def instruction_files(root=None):
    """part → (path, origin) with origin "kb" or "explorer"."""
    out = {}
    own_dir = os.path.join(root or ROOT, "digest") if root else DIGEST_INSTRUCTIONS_PATH
    for part in PARTS:
        own = os.path.join(own_dir, part)
        if os.path.isfile(own) and not own.startswith(META_DEFAULTS_PATH):
            out[part] = (own, "kb")
            continue
        default = os.path.join(META_DEFAULTS_PATH, "digest", part)
        if os.path.isfile(default):
            out[part] = (default, "explorer")
    return out


def digest_instructions(root=None):
    """The text a digest prompt is prefixed with: focus first, then the concept kinds."""
    chunks = []
    for part, (path, _origin) in instruction_files(root).items():
        with open(path, encoding="utf-8") as f:
            chunks.append(f.read().strip())
    return "\n\n".join(chunks)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--where" in argv:
        for part, (path, origin) in instruction_files().items():
            print(f"{part:<10} {origin:<8} {path}")
        return 0
    print(digest_instructions())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
