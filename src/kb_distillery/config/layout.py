"""The folder layout inside a knowledge base: repo-relative names, nothing else (no imports).

`kb_distillery.config.paths` builds absolute paths from these and `kb_distillery.vault.schema` re-exports them beside the
rest of the schema, so renaming a vault folder is still one edit, here.
"""
WIKI_DIR = "wiki"
META_DIR = "meta"
RAW_DIR = "raw"
THINK_DIR = "think"  # human sandbox at vault root — not linted
QUARANTINE_DIR = "_quarantine"

# OKF v0.2 reserved files of the bundle root (wiki/): the generated catalog and the append-only timeline.
INDEX_REL = f"{WIKI_DIR}/index.md"
LOG_REL = f"{WIKI_DIR}/log.md"

MANIFEST = "meta/corpus.tsv"        # the corpus manifest

# session state of the ops / ingest / distill workflows (meta/.<x>)
OPS_DIR = "meta/.ops"
INGEST_DIR = "meta/.ingest"
DISTILL_DIR = "meta/.distill"
JOBS_DIR = "meta/.jobs"           # app digest jobs (kb_distillery.services.digest_jobs)
