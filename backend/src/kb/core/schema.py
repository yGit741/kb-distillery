"""Single source of truth for the vault schema. Imported by guard.py and lint.py."""

# The source model (schema 1.0): every page has a `layer` and a `type` inside that layer.
#   source      the digest of one raw item, faithful to it; `depth` says how far it is read
#   collection  a table grouping sources (a book's page partition, a course/series contents table)
#   concept     knowledge across sources: ideas, topics, questions, people
LAYERS = ("concept", "collection", "source")

# Reading depth of a source, deepened in place — separate from its reading lifecycle `status`.
DEPTH = ("listed", "easy", "full", "deep")          # ordered: listed = cataloged, not read yet

_READ = {"to-read", "reading", "digested"}
_GROW = {"seed", "growing", "solid"}

SOURCE_TYPES = frozenset({
    "paper",          # academic work
    "part",           # a page range of a book or notebook
    "lecture",        # one class session: slides + own notes
    "article",        # non-academic writeup: web clip, tutorial
    "video",          # a talk or video, with own notes
    "conversation",   # a substantive email thread
    "ai-chat",        # a substantive LLM chat (rendered from meta/chats/ trees)
    "blog-post",      # one post of a blog series
})
# Collections whose table is a page partition of their own raw PDF.
PARTITION_COLLECTIONS = frozenset({"book", "notebook"})
# Collections whose table lists member raw files (corpus.tsv `collection` must agree).
CONTENTS_COLLECTIONS = frozenset({"course", "series"})
COLLECTION_TYPES = PARTITION_COLLECTIONS | CONTENTS_COLLECTIONS
CONCEPT_TYPES = frozenset({"idea", "topic", "question", "person"})
# Tool-owned auxiliary types: a scope is a personal working set of raw files (collection layer),
# a distilled-think page a transient proposal from think/ (concept layer). Neither is a hub.
AUX_LAYER = {"scope": "collection", "distilled-think": "concept"}

LAYER_OF = {**{t: "source" for t in SOURCE_TYPES}, **{t: "collection" for t in COLLECTION_TYPES},
            **{t: "concept" for t in CONCEPT_TYPES}, **AUX_LAYER}

TYPE_STATUS = {
    **{t: _READ for t in SOURCE_TYPES},
    **{t: _READ for t in COLLECTION_TYPES},
    "topic":        _GROW,   # exactly one per TOPIC_SLUGS entry
    "idea":         _GROW,
    "person":       set(),   # no status: progress is `verified:` (backend/src/kb/core/persons.py, schema 0.12)
    "question":     {"open", "partial", "resolved"},
    "distilled-think": {"review", "applied", "archived"},
    "scope":        {"active", "parked"},   # a personal working set of raw files (backend/src/kb/core/scopes.py, schema 0.13)
}
assert set(TYPE_STATUS) == set(LAYER_OF)

# Types whose pages must carry a `raw:` provenance field (a path, a list of paths, or `none`).
NEEDS_RAW = SOURCE_TYPES | PARTITION_COLLECTIONS
# Types whose printed-docs/ filename year must agree with `year:`.
YEARED = {"paper", "book", "part"}

# Filename prefix per type. wiki/ is flat, so the prefix is the type at a glance: the type
# requires the prefix and the prefix requires the type. idea and person stay bare: they are
# the most-linked nodes and read better in prose. Topics keep their historical `theme-` prefix.
SLUG_PREFIX = {
    "paper": "paper-", "part": "part-", "lecture": "lecture-", "article": "article-",
    "video": "video-", "conversation": "conversation-", "ai-chat": "chat-", "blog-post": "blog-",
    "book": "book-", "notebook": "notebook-", "course": "course-", "series": "series-",
    "topic": "theme-", "question": "q-", "distilled-think": "distilled-think-",
    "scope": "scope-",
}
BARE_TYPES = {"idea", "person"}

# Display metadata for the dashboard (served by /api/schema; the JS keeps no type lists).
TYPE_LABEL = {
    "paper": "Paper", "part": "Book part", "lecture": "Lecture", "article": "Article",
    "video": "Video", "conversation": "Conversation", "ai-chat": "AI chat", "blog-post": "Blog post",
    "book": "Book", "notebook": "Notebook", "course": "Course", "series": "Series",
    "topic": "Topic", "idea": "Idea", "question": "Question", "person": "Person",
    "distilled-think": "Distilled", "scope": "Scope",
}
TYPE_ORDER = ("topic", "idea", "question", "person", "course", "series", "book", "notebook",
              "paper", "part", "lecture", "article", "blog-post", "video", "ai-chat", "conversation",
              "distilled-think", "scope")
LAYER_LABEL = {"source": "Sources", "collection": "Collections", "concept": "Concepts"}
assert set(TYPE_ORDER) == set(LAYER_OF) == set(TYPE_LABEL)


# Retired names (schema 0.x). There is no read compatibility: lint names the replacement in its
# error, the 0008 migration rewrote the vault, and nothing else may read these.
RETIRED_TYPES = {"theme": "topic", "concept": "idea"}
RETIRED_KEYS = {"digestion-status": "depth"}
RETIRED_DEPTH = {"catalog": "listed"}
RETIRED_DISPOSITIONS = {"digested": "source"}


def layer_of(page_type):
    """`idea` → `concept`; None for an unknown type."""
    return LAYER_OF.get(page_type)


def is_source(page_type):
    return page_type in SOURCE_TYPES


RESERVED_PREFIXES = tuple(sorted(set(SLUG_PREFIX.values()), key=len, reverse=True))


def make_slug(page_type, stem):
    """`paper` + `2023-toolformer` → `paper-2023-toolformer`; idempotent."""
    prefix = SLUG_PREFIX.get(page_type, "")
    return stem if stem.startswith(prefix) else prefix + stem


def strip_prefix(slug):
    """`book-2014-analysis…` → `2014-analysis…`."""
    for p in RESERVED_PREFIXES:
        if slug.startswith(p):
            return slug[len(p):]
    return slug

WIKI_DIR = "wiki"
META_DIR = "meta"
RAW_DIR = "raw"
THINK_DIR = "think"  # human sandbox at vault root — not linted
QUARANTINE_DIR = "_quarantine"

# Markdown allowed at the vault root.
ROOT_MD = {"index.md", "AGENTS.md", "CLAUDE.md", "README.md", "GEMINI.md"}

# Top-level vault shape — only these dirs/files may sit at the root (dot-* tooling exempt).
FRONTEND_DIR = "frontend"            # React app (tooling lane); node_modules is gitignored
# Code and tooling folders beside the vault content (tooling lane; see TOOLING_PATHS).
CODE_TOP_DIRS = frozenset({"backend", "frontend", "share", "skills", "tools"})
ROOT_DIRS = frozenset({WIKI_DIR, RAW_DIR, THINK_DIR, META_DIR, QUARANTINE_DIR, FRONTEND_DIR}) | CODE_TOP_DIRS
ROOT_FILES = frozenset(ROOT_MD) | frozenset({"pixi.toml", "pixi.lock", ".gitignore"})
# Obsidian/plugin state at root — gitignored, not KB content; lint skips, guard still blocks agents.
ROOT_LINT_IGNORE = frozenset({"copilot"})

# Generated by lint.py — never hand-edited.
GENERATED = {"index.md", "meta/corpus.tsv"}

# Fixed TOP-LEVEL shape of raw/: one folder per FORMAT (how the bytes were produced), never
# per course or person — membership lives in corpus.tsv `collection`, so a raw file never
# moves after catalog. Split rule: typed → printed-docs (even if annotated), by hand →
# handwritten, slides → presentations whatever the extension.
RAW_INBOX = "inbox"                  # the single unclassified queue; arbitrary shape, must drain
RAW_PRINTED = "printed-docs"         # papers, books, course books, typed notes, blog posts
RAW_HANDWRITTEN = "handwritten"      # reMarkable notebooks, handwritten summaries
RAW_PRESENTATIONS = "presentations"  # decks: pdf, pptx, key
RAW_CHATS = "llm-chats"              # LLM conversation exports (md)
RAW_EMAILS = "emails"                # emails/<YYYY-MM-DD-thread>/ thread.md + attachments
RAW_WEB = "web-clips"                # Web Clipper pages (md, html)
RAW_IMAGES = "images"                # screenshots, figures
RAW_SUBDIRS = [RAW_INBOX, RAW_PRINTED, RAW_HANDWRITTEN, RAW_PRESENTATIONS, RAW_CHATS,
               RAW_EMAILS, RAW_WEB, RAW_IMAGES]
# Only emails/ nests (one thread folder); every other format folder is flat.
RAW_NESTED = {RAW_EMAILS}
# Flat format folders: lowercase ascii kebab names, unique across the vault.
RAW_NAME = r"^[a-z0-9]+([._-][a-z0-9]+)*\.[a-z0-9]+$"



def unit_type_for_raw(raw_rel):
    """The source type a raw file becomes when digested on its own (format → type)."""
    parts = (raw_rel or "").replace("\\", "/").split("/")
    fmt = parts[1] if len(parts) > 2 else ""
    ext = parts[-1].rsplit(".", 1)[-1].lower() if "." in parts[-1] else ""
    if fmt in (RAW_PRESENTATIONS, RAW_HANDWRITTEN):
        return "lecture"
    if fmt == RAW_CHATS:
        return "ai-chat"
    if fmt == RAW_EMAILS:
        return "conversation"
    if fmt == RAW_PRINTED and ext == "md" and parts[-1].startswith("blog-"):
        return "blog-post"
    if fmt == RAW_WEB or (fmt == RAW_PRINTED and ext != "pdf"):
        return "article"
    return "paper"


def unit_slug_for_raw(raw_rel, page_type=None):
    """`raw/printed-docs/2023-toolformer.pdf` → `paper-2023-toolformer`. Email threads take the
    thread folder name; a stem already naming its type (`rl-lecture-01`) isn't repeated."""
    import re
    page_type = page_type or unit_type_for_raw(raw_rel)
    parts = (raw_rel or "").replace("\\", "/").rstrip("/").split("/")
    name = parts[2] if len(parts) > 3 and parts[1] == RAW_EMAILS else parts[-1]
    stem = re.sub(r"[^a-z0-9]+", "-", name.rsplit(".", 1)[0].lower()).strip("-")
    word = SLUG_PREFIX.get(page_type, "").rstrip("-")
    if word and stem.startswith(f"{word}-"):
        stem = stem[len(word) + 1:]
    stem = re.sub(rf"-{word}-", "-", stem) if word in ("lecture", "conversation") else stem
    return make_slug(page_type, stem)


# raw/emails/<thread-dir> naming: <YYYY-MM-DD>-<kebab-slug>
MAIL_DIR_NAME = r"^\d{4}-\d{2}-\d{2}-[a-z0-9]+(-[a-z0-9]+)*$"

# Agent-generated, agent-writable transcription sidecar living inside an
# already-cataloged raw entity folder: raw/<kind>/<entity>/parsed.md. Only
# legal for kinds whose folders are genuinely one-per-entity. Widen this set only
# when a new kind gets its own dedicated per-entity folder.
PARSED_FILENAME = "parsed.md"
SIDECAR_ELIGIBLE_KINDS = {RAW_EMAILS}

# --- conversation trees (Gemini/LLM chat clips) ---------------------------
CHATS_DIR = "meta/chats"
CHAT_TREE_SCHEMA = "conversation-tree/1"

# raw/ files git never holds (gitignored, tracked by the manifest only). A checkout missing
# several of them is a *partial checkout* — a clone, a CI run, a fresh worktree before its links —
# and lint keeps their manifest rows instead of "forgetting" them.
RAW_BINARY_EXTS = {".pdf", ".epub", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic",
                   ".pptx", ".ppt", ".key", ".docx", ".zip"}
PARTIAL_CHECKOUT_MIN = 5          # fewer missing binaries = someone deleted files on purpose

# --- corpus manifest ------------------------------------------------------
MANIFEST = "meta/corpus.tsv"
# `collection`: comma-separated hub/person slugs the file belongs to (hand-editable, like
# `disposition`). A course/series hub's Contents table must list exactly its members.
# `scopes` (schema 0.13): comma-separated `scope-*` slugs whose working set holds the file (hand-editable).
MANIFEST_COLS = ["path", "sha1", "kind", "disposition", "slug", "collection", "scopes"]

# `source`: a wiki page cites the file via `raw:` (it is the raw item of a Source page).
DISPOSITIONS = {"queued", "source", "partial", "skip", "sidecar"}
DUPE_PREFIX = "dupe:"
INK_PREFIX = "ink:"
# `asset:<clip path>` — a figure downloaded with a web clip (raw/images/<clip stem>-NN.<ext>),
# part of that clip the way an ink overlay is part of its PDF: never a backlog item of its own.
ASSET_PREFIX = "asset:"
ASSET_NAME = r"^(?P<clip>.+)-\d{2,3}\.(png|jpe?g|gif|webp)$"

# --- health thresholds ----------------------------------------------------
# The inbox is a queue: a few files are normal; only an old or overflowing one is a problem.
INBOX_ERROR = 50
INBOX_STALE_DAYS = 30

# A PDF this long is a book: digest it one section at a time, never whole.
BOOK_MIN_PAGES = 60

# --- naming --------------------------------------------------------------
PAPER_NAME = r"^(1[89]|20)\d{2}-[a-z0-9]+(-[a-z0-9]+)*\.pdf$"
PAPER_YEAR_MIN, PAPER_YEAR_MAX = 1800, 2100

INK_SUFFIX = " (annotations)"
BLANK_PDF_BYTES = 700

INGEST_DIR = "meta/.ingest"
INGEST_STALE_HOURS = 24

DISTILL_DIR = "meta/.distill"

# Research topics: the `area:` whitelist; each has exactly one `theme-<slug>` topic page.
TOPIC_SLUGS = frozenset({
    "statistics",
    "boolean-analysis",
    "fourier-analysis",
    "optimization-theory",
    "learning-theory",
    "info-theory",
    "implicit-regularization",
    "tensor-factorization",
    "complex-nn",
    "quantum",
})

DEPRECATED_AREA_SLUGS = frozenset({
    "why-things-work",
    "adv-ml", "adv-nlp", "adv-stats", "nlp", "rl", "prob-models", "ak-summaries",
    "thesis-directions",
})

DISTILLED_THINK_PREFIX = SLUG_PREFIX["distilled-think"]
TOPIC_PREFIX = SLUG_PREFIX["topic"]
# Placeholder titles a chat clip arrives with — never acceptable on an ai-chat page.
PLACEHOLDER_TITLE = r"^New (chat|notebook)\b"

# Git lanes. Knowledge = KB content, one kb(...) commit per operation on main (backend/src/kb/ops).
# Tooling = code, skills, config, docs, shipped on demand via infra/* PRs (ship.py).
# Anything in neither list is "other": reported, never committed by either.
# Knowledge wins on overlap (meta/log.md is knowledge, meta/ is tooling).
# Directories end in "/".
KNOWLEDGE_PATHS = [
    "wiki/",
    "think/",
    "raw/",
    "index.md",
    "meta/corpus.tsv",
    "meta/log.md",
    "meta/coherence-warnings.tsv",
    "meta/aliases.tsv",
    "meta/chats/",
]


TOOLING_PATHS = [
    # Obsidian config: only app.json, core-plugins.json, community-plugins.json are tracked
    # (what another vault user needs); the rest is gitignored. Ships with any infra PR.
    ".obsidian/",
    "meta/",
    "backend/",
    "share/",
    "skills/",
    "tools/",
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    ".integrator.toml",  # integrator skill config (~/.claude/skills/integrator)
    "pixi.toml",
    "pixi.lock",
    ".gitignore",
    "frontend/",
    ".cursor/",
    ".claude/",
    ".vscode/",
    ".github/",
]


def _matches(path, prefixes):
    return any(path == p.rstrip("/") or (p.endswith("/") and path.startswith(p)) for p in prefixes)


def lane_of(path):
    """Return "knowledge", "tooling" or "other" for a repo-relative path."""
    path = path.replace("\\", "/").removeprefix("./")
    if _matches(path, KNOWLEDGE_PATHS):
        return "knowledge"
    if _matches(path, TOOLING_PATHS):
        return "tooling"
    return "other"


# Knowledge versioning: kb-x.y.z — x = paradigm, y = schema, z = knowledge step.
# (x, y) changes only inside a schema/paradigm PR (with its migration); z is derived
# from git (last first-parent KB-Version + 1). Tooling is not versioned — infra work
# is identified by its PR number (#N). See backend/src/kb/git/commit_policy.py.
SCHEMA_VERSION = (1, 0)     # 1.0: the source model (layer + type, depth, disposition source)

# What undo/restore may rewrite. Never raw/ (immutable, PDFs untracked), think/
# (human-owned), meta/log.md (append-only) or generated files (lint regenerates them).
RESTORABLE_PATHS = ["wiki/", "meta/aliases.tsv", "meta/chats/"]

# tools/githooks policy: "warn" prints violations, "enforce" rejects (env KB_POLICY overrides).
GIT_POLICY_MODE = "enforce"

# guard.py: wiki writes need an open ops/ingest/distill session (False = warn only).
OPS_STRICT = False
OPS_DIR = "meta/.ops"
