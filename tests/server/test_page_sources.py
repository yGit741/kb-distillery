"""GET /api/pages/{slug}/sources on the fixture kb plus a few pages and corpus rows added for the test."""
import os

import pytest
from fastapi.testclient import TestClient

from kb_distillery.config import paths
from kb_distillery.server.app import create_app
from kb_distillery.server.models.page_sources import PageSources

PAPER = """---
type: paper
layer: source
raw: raw/printed-docs/2026-paper-x.pdf
created: 2026-10-01
---

# Paper X

Body.
"""
IDEA = """---
type: idea
layer: concept
sources: [{resource: ps-paper-x.md}, {resource: https://example.org/blog/post}]
---

# Soft claims

## Evidence

Shown in [Paper X](ps-paper-x.md) and at https://example.org/blog/post.

## Open questions

Nothing cited here.
"""
BARE = "---\ntype: idea\nlayer: concept\nsources: []\n---\n\n# Bare idea\n"
ROW = "raw/printed-docs/2026-paper-x.pdf\tabc123\tprinted-docs\tsource\tps-paper-x\t\t\n"


@pytest.fixture
def client():
    root = paths.ROOT
    made = {f"wiki/{n}.md": t for n, t in (("ps-paper-x", PAPER), ("ps-soft-claims", IDEA), ("ps-bare", BARE))}
    corpus = os.path.join(root, "meta", "corpus.tsv")
    old = open(corpus, encoding="utf-8").read() if os.path.exists(corpus) else None
    os.makedirs(os.path.dirname(corpus), exist_ok=True)
    for rel, text in made.items():
        with open(os.path.join(root, rel), "w", encoding="utf-8") as f:
            f.write(text)
    with open(corpus, "w", encoding="utf-8") as f:
        f.write((old or "path\tsha1\tkind\tdisposition\tslug\tcollection\tscopes\n") + ROW)
    try:
        with TestClient(create_app()) as c:
            yield c
    finally:
        for rel in made:
            os.remove(os.path.join(root, rel))
        if old is None:
            os.remove(corpus)
        else:
            with open(corpus, "w", encoding="utf-8") as f:
                f.write(old)


def test_concept_page_lists_source_page_raw_file_and_url(client):
    r = client.get("/api/pages/ps-soft-claims/sources")
    assert r.status_code == 200
    body = PageSources.model_validate(r.json())
    assert body.slug == "ps-soft-claims" and body.counts.total == 2
    by = {s.id: s for s in body.sources}
    raw = by["raw/printed-docs/2026-paper-x.pdf"]
    assert (raw.title, raw.kind, raw.format, raw.disposition) == ("Paper X", "pdf", "printed-docs", "source")
    assert raw.slug == "ps-paper-x" and raw.added == "2026-10-01" and raw.via == ["sources"]
    assert raw.route == "/pipeline?q=raw/printed-docs/2026-paper-x.pdf"
    assert raw.cited_in_sections == ["Evidence"]
    web = by["https://example.org/blog/post"]
    assert web.disposition == "external" and web.kind == "web" and web.cited_in_sections == ["Evidence"]
    assert body.counts.raw == 1 and body.counts.external == 1 and body.counts.by_disposition == {"source": 1, "external": 1}


def test_source_page_lists_its_own_raw_file(client):
    body = client.get("/api/pages/ps-paper-x/sources").json()
    assert [s["path_rel"] for s in body["sources"]] == ["raw/printed-docs/2026-paper-x.pdf"]
    assert body["sources"][0]["via"] == ["raw"]


def test_page_without_sources_is_empty_not_404(client):
    r = client.get("/api/pages/ps-bare/sources")
    assert r.status_code == 200
    assert r.json()["sources"] == [] and r.json()["counts"]["total"] == 0


def test_unknown_slug_and_unknown_kb_are_404(client):
    assert client.get("/api/pages/no-such-page-xyz/sources").status_code == 404
    assert client.get("/api/pages/ps-bare/sources", params={"kb": "nope"}).status_code == 404
